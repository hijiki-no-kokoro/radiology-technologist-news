import json, re, xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path
from urllib.parse import quote, urljoin
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
NEWS_JSON = ROOT / 'news.json'
JST = timezone(timedelta(hours=9))

QUERIES = [
    '診療放射線技師 OR 放射線技師 OR 放射線部',
    '放射線診療 CT MRI FPD',
    '放射線 被ばく 線量管理 安全管理',
    '核医学 SPECT PET 放射線技師',
    '放射線 AI 画像診断 読影支援',
    '診療報酬 放射線 画像診断 補助金',
    'site:jart.jp 診療放射線技師',
    'site:jsrt.or.jp 放射線技師 OR 放射線技術',
    'site:radiology.jp 放射線診療 OR 放射線技師',
    'site:jsnm.org 核医学 放射線技師',
    'site:jastro.or.jp 放射線治療 放射線技師',
    'site:mhlw.go.jp 診療放射線技師',
    'site:pmda.go.jp 放射線 CT MRI 医療機器',
]

OFFICIAL = ('jart.jp','jsrt.or.jp','jrs.or.jp','radiology.jp','jsnm.org','jastro.or.jp','mhlw.go.jp','nra.go.jp','pmda.go.jp','mext.go.jp')
CATEGORIES = ('制度','職能','学術','AI','CT','MRI','一般撮影','安全管理','核医学','放射線治療','教育','診療報酬・補助金','その他')

# 「国家試験」「研修」「AI」など単独では他職種ニュースを拾うため、放射線診療に直接結び付く語だけを対象にする。
TARGET_TERMS = (
    '診療放射線技師','放射線技師','放射線部','放射線科','放射線診療',
    'CT','MRI','FPD','一般撮影','マンモグラフィ','核医学','SPECT','PET',
    '放射線治療','被ばく','線量管理','画像診断','読影','STAT','X線撮影',
    'タスクシフト','タスクシェア','放射線安全'
)
BAD_TERMS = ('漫画','マンガ','芸能','俳優','女優','アイドル','タレント','グラビア','写真集')


def fetch(url):
    req = Request(url, headers={'User-Agent':'Mozilla/5.0 radiology-technologist-news'})
    return urlopen(req, timeout=30).read().decode('utf-8','ignore')


def clean_html(s):
    return ' '.join(unescape(re.sub(r'<[^>]+>', ' ', s or '')).split())


def rss(q):
    url = 'https://news.google.com/rss/search?q=' + quote(q + ' when:1d') + '&hl=ja&gl=JP&ceid=JP:ja'
    root = ET.fromstring(fetch(url))
    out = []
    for it in root.findall('./channel/item'):
        title = unescape(it.findtext('title',''))
        link = it.findtext('link','')
        desc = clean_html(it.findtext('description',''))[:700]
        pub = it.findtext('pubDate','')
        src = (it.find('source').text if it.find('source') is not None else '')
        try: dt = parsedate_to_datetime(pub).astimezone(JST)
        except Exception: continue
        if title and link: out.append({'title':title,'url':link,'description':desc,'source':src,'published':dt.isoformat()})
    return out


def norm(s):
    return re.sub(r'[^0-9a-zぁ-んァ-ヶ一-龠]','',str(s or '').lower())


def dom(url):
    m = re.search(r'https?://([^/]+)', url or '')
    return m.group(1).lower().replace('www.','') if m else ''


def is_official(url):
    d = dom(url)
    return any(d == z or d.endswith('.' + z) for z in OFFICIAL)


def relevant(x):
    text = (x.get('title','') + ' ' + x.get('description','') + ' ' + x.get('source','')).lower()
    if any(k.lower() in text for k in BAD_TERMS): return False
    # AI、医療機器、国家試験、研修などだけでは採用しない。
    return any(k.lower() in text for k in TARGET_TERMS)


def parse_nearby_date(html, pos):
    block = clean_html(html[max(0,pos-1800):pos])
    dates = re.findall(r'(20\d{2})[/.年](\d{1,2})[/.月](\d{1,2})', block)
    if dates:
        y,m,d = dates[-1]
        return f'{y}-{int(m):02d}-{int(d):02d}T00:00:00+09:00'
    return None


def direct_official():
    out = []
    now = datetime.now(JST).isoformat()

    # JARTトップ：本会からのお知らせを直接取得
    try:
        html = fetch('https://www.jart.jp/')
        for m in re.finditer(r'<a[^>]+href=["\'](?P<href>[^"\']+)["\'][^>]*>\s*(?P<title>.*?)\s*</a>', html, re.I|re.S):
            title = clean_html(m.group('title'))
            if not title or not relevant({'title':title,'source':'JART'}): continue
            href = urljoin('https://www.jart.jp/', m.group('href'))
            date = parse_nearby_date(html, m.start()) or now
            out.append({'title':title,'url':href,'description':title,'source':'JART','published':date})
    except Exception as e:
        print('JART direct error:', e)

    # JARTのイベントページ：更新された放射線技師向けセミナーを補完
    for url in ('https://www.jart.jp/activity/lifelong-study','https://www.jart.jp/seminar'):
        try:
            html = fetch(url)
            for m in re.finditer(r'<a[^>]+href=["\'](?P<href>[^"\']+)["\'][^>]*>\s*(?P<title>.*?)\s*</a>', html, re.I|re.S):
                title = clean_html(m.group('title'))
                if not title or not relevant({'title':title,'source':'JART'}): continue
                if not any(k in title for k in ('STAT','告示研修','放射線','ディスプレイ','画像')): continue
                href = urljoin(url, m.group('href'))
                out.append({'title':title,'url':href,'description':title,'source':'JART','published':now})
        except Exception as e:
            print('JART seminar error:', e)

    # 厚労省：診療放射線技師関連だけ。日付もリンク周辺から取得する。
    try:
        html = fetch('https://www.mhlw.go.jp/stf/new-info/')
        for m in re.finditer(r'<a[^>]+href=["\'](?P<href>[^"\']+)["\'][^>]*>\s*(?P<title>.*?)\s*</a>', html, re.I|re.S):
            title = clean_html(m.group('title'))
            if not title or not relevant({'title':title,'source':'厚生労働省'}): continue
            href = urljoin('https://www.mhlw.go.jp/stf/new-info/', m.group('href'))
            date = parse_nearby_date(html, m.start()) or now
            out.append({'title':title,'url':href,'description':title,'source':'厚生労働省','published':date})
    except Exception as e:
        print('MHLW direct error:', e)
    return out


def category(x):
    t = (x.get('title','') + ' ' + x.get('description','')).lower()
    rules = [
        ('診療報酬・補助金',('診療報酬','補助金','助成金','加算')),
        ('安全管理',('安全管理','安全','被ばく','線量管理','線量','放射線安全')),
        ('一般撮影',('一般撮影','FPD','マンモグラフィ','X線撮影')),
        ('CT',('CT','computed tomography')),
        ('MRI',('MRI','magnetic resonance')),
        ('核医学',('核医学','SPECT','PET','MIBG','DAT','RI')),
        ('放射線治療',('放射線治療','リニアック','陽子線','粒子線','IGRT')),
        ('AI',('AI','人工知能','画像診断支援','読影支援')),
        ('教育',('国家試験','研修','認定','セミナー','講習')),
        ('学術',('学術','研究','学会','ガイドライン','パブリックコメント')),
        ('職能',('STAT','タスクシフト','タスクシェア','業務範囲','職能')),
        ('制度',('制度','養成','確保','厚生労働省','医政')),
    ]
    for cat, terms in rules:
        if any(k.lower() in t for k in terms): return cat
    return 'その他'


def importance(x, official):
    t = (x.get('title','') + ' ' + x.get('description','')).lower()
    if any(k.lower() in t for k in ('診療報酬','補助金','安全管理','被ばく','線量管理','装置更新','タスクシフト','タスクシェア','業務範囲','STAT','告示研修')): return '高'
    if official or any(k.lower() in t for k in ('CT','MRI','AI','研修','セミナー')): return '中'
    return '低'


def load():
    try: return json.loads(NEWS_JSON.read_text(encoding='utf-8'))
    except Exception: return []


def main():
    now = datetime.now(JST)
    cutoff = now - timedelta(hours=26)
    db = load()

    # 既存DBも厳格フィルタ。過去に混入した他職種の国家試験等を残さない。
    db = [x for x in db if relevant(x)]
    seen = {norm(x.get('headline')) or x.get('url') for x in db}
    candidates = {}

    for x in direct_official():
        try: dt = datetime.fromisoformat(x['published'])
        except Exception: continue
        if dt < cutoff or not relevant(x): continue
        k = norm(x['title']) or x['url']
        if k not in seen: candidates[x['url']] = x

    for q in QUERIES:
        try:
            for x in rss(q):
                if datetime.fromisoformat(x['published']) < cutoff or not relevant(x): continue
                k = norm(x['title']) or x['url']
                if k in seen: continue
                candidates[x['url']] = x
        except Exception as e:
            print('RSS error:', e)

    fresh = sorted(candidates.values(), key=lambda x:(is_official(x['url']) or x.get('source') in ('JART','厚生労働省'), x['published']), reverse=True)
    added = []
    titles = set()
    for x in fresh[:25]:
        k = norm(x['title'])
        if not k or k in titles: continue
        titles.add(k)
        official = is_official(x['url']) or x.get('source') in ('JART','厚生労働省')
        added.append({
            'date': x['published'][:10],
            'category': category(x),
            'importance': importance(x, official),
            'headline': x['title'],
            'summary': re.sub(r'\s+',' ',x.get('description','')).strip()[:220],
            'why': '公式情報のため、放射線部門の運用・教育・制度への影響を確認する価値があります。' if official else '放射線部門の実務への影響を確認する価値があります。',
            'source': x.get('source') or dom(x['url']),
            'url': x['url'],
            'track': 'official' if official else 'general'
        })

    db = added + db
    final=[]; seen=set()
    for x in sorted(db, key=lambda z:(z.get('date',''), {'高':3,'中':2,'低':1}.get(z.get('importance'),0)), reverse=True):
        k = norm(x.get('headline')) or x.get('url')
        if not k or k in seen: continue
        seen.add(k); final.append(x)

    NEWS_JSON.write_text(json.dumps(final[:200], ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Added {len(added)} new items; database now has {len(final[:200])} items.')
    for x in added[:15]: print(x['date'], x['track'], x['category'], x['headline'])

if __name__ == '__main__': main()
