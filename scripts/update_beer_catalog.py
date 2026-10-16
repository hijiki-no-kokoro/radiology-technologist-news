#!/usr/bin/env python3
"""Collect public single-can facts. Preserve previous entries; never infer JAN/ABV.

Only this program's --apply mode changes the catalog, its page version and cache.
No user records, credentials, third-party images or paid APIs are involved.
"""
import argparse
import concurrent.futures
import copy
import datetime as dt
import hashlib
from html.parser import HTMLParser
import http.cookiejar
import json
import math
import os
from pathlib import Path
import re
import subprocess
import time
import unicodedata
import urllib.parse
import urllib.request

HOSTS = {'www.asahibeer.co.jp', 'outer1.kirin.co.jp', 'www.takarashuzo.co.jp',
         'www.sapporobeer.jp', 'www.tokyu-store.co.jp', 'products.suntory.co.jp'}
NAMES = {'asahi': 'アサヒビール', 'kirin': 'キリンビール', 'takara': '宝酒造',
         'sapporo': 'サッポロビール', 'suntory': 'サントリー'}
PREFIX = '/* Public product facts; automatic collection never writes user records. */\n'
WRAP = "(function(root,factory){if(typeof module==='object'&&module.exports)module.exports=factory();else root.BeerCatalog=factory();})(typeof window!=='undefined'?window:this,function(){return Object.freeze("


def norm(s):
    return unicodedata.normalize('NFKC', s)


def clean(s):
    return re.sub(r'\s+', ' ', norm(s)).strip()


class Node:
    def __init__(self, tag='', attrs=(), parent=None):
        self.tag, self.attrs, self.parent, self.children = tag, dict(attrs), parent, []

    def text(self):
        return ''.join(c if isinstance(c, str) else c.text() for c in self.children)

    def walk(self):
        for c in self.children:
            if isinstance(c, Node):
                yield c
                yield from c.walk()

    def find(self, tag, **attrs):
        return [n for n in self.walk() if n.tag == tag and all(
            v in n.attrs.get(k, '').split() if k == 'class' else n.attrs.get(k) == v
            for k, v in attrs.items())]


class Parser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = self.cur = Node('root')

    def handle_starttag(self, t, a):
        n = Node(t, a, self.cur)
        self.cur.children.append(n)
        if t not in {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}:
            self.cur = n
        elif t == 'br':
            self.cur.children.append('\n')

    def handle_startendtag(self, t, a):
        self.handle_starttag(t, a)
        self.handle_endtag(t)

    def handle_endtag(self, t):
        p = self.cur
        while p.parent:
            if p.tag == t:
                self.cur = p.parent
                return
            p = p.parent

    def handle_data(self, d):
        self.cur.children.append(d)


def dom(s):
    p = Parser()
    p.feed(s)
    for n in p.root.find('script') + p.root.find('style'):
        n.children = []
    return p.root


def links(s, url):
    return sorted({urllib.parse.urljoin(url, n.attrs['href']).split('#')[0]
                   for n in dom(s).find('a') if n.attrs.get('href')})


def allowed(url):
    p = urllib.parse.urlsplit(url)
    if p.scheme != 'https' or p.hostname not in HOSTS or p.username or p.password or p.port:
        raise ValueError('Unapproved source URL')
    return url


class Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        allowed(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class Fetcher:
    """Fresh per-run cache, bounded requests, three detail requests at a time."""
    def __init__(self):
        self.cache = {}
        self.errors = []
        self.opener = urllib.request.build_opener(Redirect(), urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.deadline = time.monotonic() + 900

    def get(self, url, encoding='utf-8', data=None):
        allowed(url)
        key = (url, data)
        if data is None and key in self.cache:
            return self.cache[key].decode(encoding, 'replace')
        if time.monotonic() > self.deadline or len(self.cache) >= 1400:
            raise RuntimeError('Collection limit reached')
        req = urllib.request.Request(url, data=data, headers={
            'User-Agent': 'BeerSaveCatalog/1.0 (weekly public product facts)',
            'Content-Type': 'application/x-www-form-urlencoded'})
        with self.opener.open(req, timeout=20) as r:
            allowed(r.geturl())
            b = r.read(4_000_001)
            if len(b) > 4_000_000:
                raise ValueError('Source too large')
        if data is None:
            self.cache[key] = b
        return b.decode(encoding, 'replace')

    def batch(self, urls, encoding='utf-8'):
        urls = sorted(set(urls))
        if len(urls) > 500:
            raise ValueError('Unexpected detail-page count')

        def one(u):
            try:
                return u, self.get(u, encoding)
            except Exception as e:
                self.errors.append({'url': u, 'error': str(e)[:200]})
                return u, None

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
            return list(ex.map(one, urls))


def jan_ok(s):
    if not isinstance(s, str) or not re.fullmatch(r'(?:\d{8}|\d{13})', s) or set(s) == {'0'}:
        return False
    ds = list(map(int, s))
    return (10 - sum(n * (3 if i % 2 == 0 else 1) for i, n in enumerate(reversed(ds[:-1]))) % 10) % 10 == ds[-1]


def future_release(text, today):
    # Only explicit product release fields, never unrelated copyright/news dates.
    m = re.search(r'(?:発売日|発売予定日|発売期日)\s*[:：]?\s*(\d{4})[年/.-]\s*(\d{1,2})[月/.-]\s*(\d{1,2})', norm(text))
    if not m:
        return False
    return dt.date(*map(int, m.groups())) > today


def fact(maker, name, vol, abv, jan, category, url, energy=None, jan_source=None):
    p = {'manufacturer': maker, 'productName': clean(name), 'volumeMl': float(vol),
         'alcoholPercent': float(abv), 'janCode': jan, 'category': category, 'source': url,
         'caloriesKcal': round(float(energy) * float(vol) / 100, 4) if energy is not None else None}
    if jan_source:
        p['janSource'] = jan_source
    return p


def parse_asahi(s, url, today):
    d = dom(s)
    t = clean(d.text())
    h = d.find('h2', **{'class': 'product-info-head'})
    a = re.search(r'アルコール分\s*(\d+(?:\.\d+)?)\s*%', t)
    c = re.search(r'エネルギー\s*(\d+(?:\.\d+)?)\s*kcal', t)
    if not h or not a or future_release(t, today):
        return []
    cat = 'chuhai' if '/sour/' in url else 'happoshu' if re.search(r'発泡酒|新ジャンル', t[t.find('商品情報TOP'):t.find('容器:')]) else 'beer'
    energy = c[1] if c and '表示単位:100ml当たり' in t else None
    return [fact(NAMES['asahi'], h[0].text(), v, a[1], j, cat, url, energy)
            for v, j in re.findall(r'容器:\s*缶\s*内容量:\s*(\d+)ml\s*JANコード\s*単品:\s*(\d{13}|\d{8})(?!\d)', t)]


def asahi(f, today):
    urls, indexes = set(), set()
    for seed in ['https://www.asahibeer.co.jp/products/beer/', 'https://www.asahibeer.co.jp/products/sour/']:
        for u in links(f.get(seed, 'cp932'), seed):
            if re.search(r'/products/(beer|sour)/[^/]+/index.html$', u):
                indexes.add(u)
            elif re.search(r'/products/(beer|sour)/[^/]+/[A-Za-z0-9_-]+\.html$', u):
                urls.add(u)
    for u, s in f.batch(indexes, 'cp932'):
        if s:
            urls.update(x for x in links(s, u) if re.search(r'/products/(beer|sour)/[^/]+/[A-Za-z0-9_-]+\.html$', x) and not x.endswith('/index.html'))
    return [p for u, s in f.batch(urls, 'cp932') if s for p in parse_asahi(s, u, today)]


def hidden_fields(d):
    return {n.attrs['name']: n.attrs.get('value', '') for n in d.find('input')
            if n.attrs.get('name') and n.attrs.get('type') == 'hidden'}


def parse_kirin(s, url, name, group, today):
    t = clean(dom(s).text())
    v = re.search(r'バラ容量\s*(\d+)ml', t)
    a = re.search(r'アルコール分\s*(\d+(?:\.\d+)?)%', t)
    j = re.search(r'JANコード\s*(\d{13}|\d{8})(?!\d)', t)
    c = re.search(r'エネルギー\s*(\d+(?:\.\d+)?)kcal', t)
    if not (v and a and j and '包装形態 バラ' in t and '容器 缶' in t) or future_release(t, today):
        return []
    cat = 'chuhai' if group == 'チューハイ・カクテル' else 'happoshu' if ('発泡酒' in group or '新ジャンル' in group) else 'beer'
    return [fact(NAMES['kirin'], name, v[1], a[1], j[1], cat, url, c[1] if c and '表示単位 100ml当たり' in t else None)]


def kirin(f, today):
    u = 'https://outer1.kirin.co.jp/kirin/brandList'
    d = dom(f.get(u))
    base, brands, group, details = hidden_fields(d), [], '', {}
    for n in d.walk():
        if n.tag == 'a' and n.attrs.get('name'):
            group = norm(n.attrs['name'])
        m = re.search(r"toSearch\('([^']+)'", n.attrs.get('href', ''))
        if m and group in {'ビール', '海外ブランドビール', '発泡酒', '新ジャンル(発泡酒2)', 'チューハイ・カクテル'}:
            brands.append((group, m[1]))
    if not 1 <= len(brands) <= 100:
        raise ValueError('Kirin brand list format changed')
    for group, bid in brands:
        fields = {**base, 'bland.blandNm': bid, 'searchResult.kbn': 'bland_search'}
        for page in range(15):
            s = f.get('https://outer1.kirin.co.jp/kirin/search', data=urllib.parse.urlencode(fields).encode())
            d = dom(s)
            for n in d.find('a'):
                m = re.search(r"dspDatail\('([^']+)'\s*,\s*'([^']+)'\s*,\s*'([^']+)'", n.attrs.get('href', ''))
                name = clean(n.text())
                if m and name and '缶' in name and not re.search(r'パック|セット|ギフト|ケース', name):
                    details['https://outer1.kirin.co.jp/kirin/detail/' + m[1] + '_' + m[3]] = (name, group)
            next_link = any(re.search(r"toBackNext\(\s*'next'\s*\)", n.attrs.get('href', '') + n.attrs.get('onclick', '')) for n in d.walk())
            if not next_link:
                break
            fields = hidden_fields(d)
            inputs = {n.attrs.get('id'): n.attrs for n in d.find('input')}
            index = fields.get('index') or inputs.get('index', {}).get('value')
            if not index:
                raise ValueError('Kirin pagination changed')
            for k, v in [('cnt', index), ('backNext', 'next'), ('kbn', 'backNext')]:
                fields[inputs.get(k, {}).get('name', k)] = v
        else:
            raise ValueError('Kirin pagination limit reached')
    return [p for u, s in f.batch(details) if s for p in parse_kirin(s, u, *details[u], today)]


def parse_takara(s, url, today):
    d = dom(s)
    t = clean(d.text())
    h = [n for n in d.find('h1') if clean(n.text())]
    v = re.search(r'容量\s*(\d+)ml', t)
    a = re.search(r'アルコール度数\s*(\d+(?:\.\d+)?)%', t)
    j = re.search(r'JANコード\s*(\d{13}|\d{8})(?!\d)', t)
    if not (h and v and a and j and re.search(r'容器\s*缶', t)) or future_release(t, today):
        return []
    return [fact(NAMES['takara'], h[0].text(), v[1], a[1], j[1], 'chuhai', url)]


def takara(f, today):
    seed = 'https://www.takarashuzo.co.jp/tkr-shohin/cmn_b_list.php?p_CategID=4'
    ids = set(re.findall(r'javascript:search\((\d+)\)', f.get(seed)))
    urls = set()
    if not 1 <= len(ids) <= 100:
        raise ValueError('Takara brand list format changed')
    for bid in sorted(ids):
        u = 'https://www.takarashuzo.co.jp/tkr-shohin/cmn_p_list.php?p_BrandID=' + bid
        urls.update(x for x in links(f.get(u), u) if 'cmn_p_detail.php?p_prodid=' in x)
    return [p for u, s in f.batch(urls) if s for p in parse_takara(s, u, today)]


def sap_key(s):
    return re.sub(r'[\s・〈〉<>「」®TM]', '', norm(s)).replace('サッポロ', '')


def sapporo(f, today):
    urls, facts = set(), []
    for seed in ['https://www.sapporobeer.jp/product/lineup/beer/?brand=77', 'https://www.sapporobeer.jp/product/lineup/sour/?brand=3593']:
        urls.update(x for x in links(f.get(seed), seed) if re.search(r'/product/(beer|sour)/[^/]+/$', x))
    for u, s in f.batch(urls):
        if not s:
            continue
        d = dom(s)
        t = clean(d.text())
        h = [x for x in d.find('h1') if clean(x.text())]
        a = re.search(r'アルコール分\s*(\d+(?:\.\d+)?)%', t)
        c = re.search(r'エネルギー\s*(\d+(?:\.\d+)?)kcal', t)
        vols = set(map(int, re.findall(r'(\d+)ml缶', t)))
        if h and a and vols and not future_release(t, today):
            name = clean(h[0].text())
            cat = 'chuhai' if '/sour/' in u else 'happoshu' if any(x in name for x in ['GOLD STAR', '麦とホップ', 'ホワイトベルグ']) else 'beer'
            # Only use calories when their 100ml basis appears explicitly.
            energy = c[1] if c and re.search(r'100ml(?:当たり|あたり)', t) else None
            facts.append((name, vols, a[1], energy, cat, u))
    jan_url = 'https://www.tokyu-store.co.jp/netsuper/campaign.html'
    raw = norm(dom(f.get(jan_url)).text())
    products = []
    for j, name in re.findall(r'(?m)^\s*(\d{13})\s+\d+\s+([^\n]+)', raw):
        if '缶' not in name or re.search(r'×|ケース|パック|セット', name):
            continue
        v = re.search(r'(\d+)ml缶', name)
        if not v:
            continue
        base = re.sub(r'\d+ml缶.*$', '', name).strip()
        matched = [x for x in facts if sap_key(x[0]) == sap_key(base) and int(v[1]) in x[1]]
        if len(matched) == 1:
            n, _, a, e, cat, u = matched[0]
            products.append(fact(NAMES['sapporo'], n, v[1], a, j, cat, u, e, jan_url))
    return products


def parse_suntory(s, url, today):
    d = dom(s)
    t = clean(d.text())
    h = [x for x in d.find('h1') if clean(x.text())]
    v = re.search(r'容量\s*(\d+)\s*ml', t, re.I)
    a = re.search(r'アルコール(?:度数|分)\s*(\d+(?:\.\d+)?)\s*%', t)
    j = re.search(r'JANコード\s*(\d{13}|\d{8})(?!\d)', t)
    c = re.search(r'エネルギー\s*(\d+(?:\.\d+)?)\s*kcal', t)
    if not (h and v and a and j and '缶' in h[0].text()) or future_release(t, today):
        return []
    cat = 'happoshu' if '発泡酒' in t else 'beer' if 'ビール類' in t else 'highball' if 'ウイスキー' in t else 'wine' if 'ワイン' in t else 'shochu' if '焼酎' in t else 'chuhai'
    return [fact(NAMES['suntory'], h[0].text(), v[1], a[1], j[1], cat, url, c[1] if c and re.search(r'100ml(?:あたり|当たり)', t) else None)]


def suntory(f, today):
    seed = 'https://products.suntory.co.jp/'
    first = links(f.get(seed), seed)
    urls = {x for x in first if re.fullmatch(r'https://products\.suntory\.co\.jp/d/\d{13}/?', x)}
    brands = [x for x in first if re.match(r'https://products\.suntory\.co\.jp/b/', x)]
    for u, s in f.batch(brands):
        if s:
            urls.update(x for x in links(s, u) if re.fullmatch(r'https://products\.suntory\.co\.jp/d/\d{13}/?', x))
    pages = f.batch(urls)
    products = [p for u, s in pages if s for p in parse_suntory(s, u, today)]
    return products


def validate(p):
    if not jan_ok(p.get('janCode')) or not p.get('productName') or len(p['productName']) > 200:
        return False
    for k, low, high in [('volumeMl', 1, 10000), ('alcoholPercent', .01, 100)]:
        n = p.get(k)
        if isinstance(n, bool) or not isinstance(n, (float, int)) or not math.isfinite(n) or not low <= n <= high:
            return False
    n = p.get('caloriesKcal')
    if n is not None and (not isinstance(n, (float, int)) or not math.isfinite(n) or not 0 <= n <= 1000000):
        return False
    allowed(p['source'])
    if p.get('janSource'):
        allowed(p['janSource'])
    return True


def signature(p):
    return p['manufacturer'], p['volumeMl'], p['alcoholPercent']


def merge(old, facts, today):
    result = copy.deepcopy(old)
    byjan = {p['janCode']: p for p in result}
    if len(byjan) != len(result):
        raise ValueError('Duplicate JAN in existing dictionary')
    groups, rejected, held, added = {}, [], [], []
    for p in facts:
        if not validate(p):
            rejected.append({'janCode': p.get('janCode'), 'reason': 'Required single-can facts invalid'})
            continue
        groups.setdefault(p['janCode'], []).append(p)
    for j, ps in sorted(groups.items()):
        p = ps[0]
        conflict = len({signature(x) for x in ps}) > 1
        prior = byjan.get(j)
        if conflict or (prior and signature(prior) != signature(p)):
            held.append({'janCode': j, 'reason': 'Same JAN has conflicting manufacturer/volume/ABV', 'observed': ps})
            if prior:
                prior['requiresConfirmation'] = True
            continue
        if prior:
            continue  # Preserve names, revisions, calories and OCR aliases byte-for-byte.
        n = re.sub(r'\s*\d+(?:\.\d+)?\s*ml\s*缶\s*$', '', p['productName'], flags=re.I).strip()
        source = p['source'] + (' JAN:' + p['janSource'] if p.get('janSource') else '')
        if len(source) > 200:
            held.append({'janCode': j, 'reason': 'Source exceeds record field length'})
            continue
        x = {'id': 'catalog-' + j, 'manufacturer': p['manufacturer'], 'brand': n, 'productName': n,
             'flavor': '', 'category': p['category'], 'containerType': 'can', 'volumeMl': p['volumeMl'],
             'alcoholPercent': p['alcoholPercent'], 'caloriesKcal': p['caloriesKcal'], 'sugarGrams': None,
             'janCode': j, 'revision': '公式情報確認 ' + today.isoformat(), 'source': source,
             'aliases': [n], 'excludeTokens': [], 'catalog': True}
        result.append(x)
        added.append({'janCode': j, 'productName': n, 'source': source})
    if len(added) > 100:
        raise ValueError('More than 100 additions in one run: review parser/source changes first')
    return sorted(result, key=lambda p: p['janCode']), added, held, rejected


def read_catalog(path):
    s = path.read_text()
    # JSON.parse only: never execute a remote script to inspect the dictionary.
    m = re.search(r'return Object\.freeze\((\{.*\})\);\}\);', s, re.S)
    if not m:
        raise ValueError('Dictionary wrapper changed')
    return json.loads(m[1])


def render_catalog(payload):
    # Escape HTML-sensitive characters even though the data is in an external JS file.
    j = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).replace('<', '\\u003c').replace('\u2028', '\\u2028').replace('\u2029', '\\u2029')
    return PREFIX + WRAP + j + ');});\n'


def write_outputs(root, payload):
    app = root / 'beer-save'
    version = payload['version']
    catalog = render_catalog(payload)
    log = (app / 'log.html').read_text()
    log, count = re.subn(r'(\.js\?v=)[A-Za-z0-9_-]+', lambda m: m[1] + version, log)
    if count < 5 or 'id="beerCatalogInfo"' not in log:
        raise ValueError('Page version/status hook changed')
    sw, count = re.subn(r"const CACHE='beer-save-[^']+';", "const CACHE='beer-save-" + version + "';", (app / 'sw.js').read_text(), count=1)
    if count != 1:
        raise ValueError('Service worker cache hook changed')
    # Validate everything before touching any target; rollback staging files on errors.
    staged = []
    try:
        for name, body in [('beer-catalog.js', catalog), ('log.html', log), ('sw.js', sw)]:
            target = app / name
            tmp = target.with_suffix(target.suffix + '.catalog-tmp')
            tmp.write_text(body)
            staged.append((tmp, target))
        for tmp, target in staged:
            os.replace(tmp, target)
    finally:
        for tmp, _ in staged:
            tmp.unlink(missing_ok=True)


def run(args):
    root = args.root.resolve()
    today = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date()
    old = read_catalog(root / 'beer-save/beer-catalog.js')
    facts, statuses = [], {}
    for name in args.sources.split(','):
        if name not in NAMES:
            raise ValueError('Unknown collector ' + name)
        f = Fetcher()
        try:
            rows = globals()[name](f, today)
            valid = [p for p in rows if validate(p)]
            if not valid:
                raise ValueError('No verifiable single-can records; source format/access requires review')
            facts.extend(valid)
            statuses[name] = {'manufacturer': NAMES[name], 'status': 'partial' if f.errors else 'ok',
                              'verifiedRecords': len(valid), 'pageErrors': f.errors}
        except Exception as e:
            statuses[name] = {'manufacturer': NAMES[name], 'status': 'unavailable', 'error': str(e)[:300]}
        print(name + ': ' + statuses[name]['status'], flush=True)
    statuses['sangaria'] = {'manufacturer': 'サンガリア', 'status': 'manual',
                            'reason': 'JAN is in image-based PDF; automatic addition disabled'}
    products, added, held, rejected = merge(old['products'], facts, today)
    partial = any(x['status'] != 'ok' for k, x in statuses.items() if k != 'sangaria')
    report = {'checkedOn': today.isoformat(), 'previousCount': len(old['products']), 'count': len(products),
              'added': added, 'held': held, 'rejected': rejected, 'sources': statuses,
              'partial': partial, 'applied': False}
    success = any(x['status'] in {'ok', 'partial'} for x in statuses.values())
    if success and args.apply:
        bodyhash = hashlib.sha256(json.dumps(products, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:12]
        payload = {**old, 'verifiedOn': today.isoformat(), 'version': 'catalog-auto-' + today.strftime('%Y%m%d') + '-' + bodyhash,
                   'products': products, 'autoUpdate': {'checkedOn': today.isoformat(), 'frequency': 'weekly',
                                                       'partial': partial, 'sources': statuses}}
        write_outputs(root, payload)
        report['applied'] = True
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({k: report[k] for k in ['checkedOn', 'count', 'partial', 'applied']}, ensure_ascii=False))
    if not success:
        raise RuntimeError('All configured manufacturer sources unavailable; dictionary left unchanged')
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    p.add_argument('--sources', default='asahi,kirin,takara,sapporo,suntory')
    p.add_argument('--report', type=Path, default=Path('work/beer-catalog-report.json'))
    p.add_argument('--apply', action='store_true')
    run(p.parse_args())
