import json
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
NEWS_JSON = ROOT / 'news.json'

QUERIES = [
    '診療放射線技師 OR 放射線技師 OR 放射線部',
    '放射線診療 CT MRI FPD',
    '放射線 被ばく 線量管理 安全管理',
    '核医学 SPECT PET 放射線技師',
    '放射線 AI 画像診断 読影支援',
    '診療報酬 放射線 画像診断 補助金',
]

OFFICIAL_DOMAINS = (
    'jart.jp', 'jsrt.or.jp', 'jrs.or.jp', 'jsnm.org', 'jastro.or.jp',
    'mhlw.go.jp', 'nra.go.jp', 'pmda.go.jp', 'mext.go.jp',
    'fda.gov', 'iaea.org', 'who.int', 'canon-medical.co.jp',
    'fujifilm.com', 'gehealthcare.co.jp', 'siemens-healthineers.com',
    'philips.co.jp',
)


def fetch(url):
    req = Request(url, headers={'User-Agent': 'Mozilla/5.0 radiology-technologist-news'})
    with urlopen(req, timeout=30) as r:
        return r.read().decode('utf-8', errors='ignore')


def rss_items(query):
    url = 'https://news.google.com/rss/search?q=' + quote(query + ' when:2d') + '&hl=ja&gl=JP&ceid=JP:ja'
    root = ET.fromstring(fetch(url))
    out = []
    for item in root.findall('./channel/item'):
        title = unescape(item.findtext('title', ''))
        link = item.findtext('link', '')
        desc = unescape(re.sub('<[^>]+>', ' ', item.findtext('description', '')))
        pub = item.findtext('pubDate', '')
        source_el = item.find('source')
        source = source_el.text if source_el is not None else ''
        try:
            dt = parsedate_to_datetime(pub).astimezone(timezone.utc)
        except Exception:
            dt = datetime.now(timezone.utc)
        out.append({'title': title, 'url': link, 'description': desc[:700], 'source': source, 'published': dt.isoformat()})
    return out


def domain(url):
    m = re.search(r'https?://([^/]+)', url or '')
    return m.group(1).lower().replace('www.', '') if m else ''


def load_news():
    if not NEWS_JSON.exists():
        return []
    try:
        return json.loads(NEWS_JSON.read_text(encoding='utf-8'))
    except Exception:
        return []


def ai_enrich(items):
    key = os.environ.get('OPENAI_API_KEY')
    if not key or not items:
        return items
    payload = []
    for i, x in enumerate(items[:15]):
        payload.append({'id': i, 'title': x['title'], 'source': x['source'], 'description': x['description']})
    prompt = '''あなたは日本の診療放射線技師長向けニュース編集者です。以下のニュース候補を評価してください。
各項目についてJSON配列で、id、category、importance、summary、whyを返してください。
categoryは「制度・職能」「学術・AI」「CT・MRI」「一般撮影・FPD」「安全管理」「核医学」「放射線治療」「教育」「診療報酬・補助金」「その他」のいずれか。
importanceは「高」「中」「低」。診療放射線技師の業務、放射線部門管理、装置更新、線量管理、安全、AI、制度変更、補助金に直結するものを高くしてください。
summaryは日本語で2文以内、whyは技師長目線で1文。推測で内容を足さず、入力情報だけで判断してください。
候補:
''' + json.dumps(payload, ensure_ascii=False)
    body = json.dumps({
        'model': 'gpt-4o-mini',
        'messages': [
            {'role': 'system', 'content': 'Return valid JSON only.'},
            {'role': 'user', 'content': prompt},
        ],
        'temperature': 0.2,
        'response_format': {'type': 'json_object'},
    }).encode()
    try:
        req = Request('https://api.openai.com/v1/chat/completions', data=body, headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'})
        raw = json.loads(urlopen(req, timeout=60).read().decode())
        text = raw['choices'][0]['message']['content']
        data = json.loads(text)
        enriched = data.get('items', data if isinstance(data, list) else [])
        by_id = {int(x['id']): x for x in enriched if 'id' in x}
        for i, item in enumerate(items[:15]):
            e = by_id.get(i)
            if e:
                item.update({k: e[k] for k in ('category', 'importance', 'summary', 'why') if k in e})
    except Exception as e:
        print('OpenAI enrichment skipped:', e)
    return items


def main():
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=30)
    db = load_news()
    seen = {x.get('url') for x in db}
    candidates = {}
    for query in QUERIES:
        try:
            for item in rss_items(query):
                if item['published'] < cutoff.isoformat():
                    continue
                if item['url'] in seen:
                    continue
                candidates[item['url']] = item
        except Exception as e:
            print('RSS error:', e)

    fresh = sorted(candidates.values(), key=lambda x: x['published'], reverse=True)[:30]
    fresh = ai_enrich(fresh)
    for x in fresh:
        d = domain(x['url'])
        official = any(d == z or d.endswith('.' + z) for z in OFFICIAL_DOMAINS)
        x.update({
            'date': x['published'][:10],
            'category': x.get('category', 'その他'),
            'importance': x.get('importance', '高' if official else '中'),
            'headline': x.pop('title'),
            'summary': x.get('summary', x.pop('description', '')[:180] or '最新情報が公開されています。'),
            'why': x.get('why', '放射線部門の運用・安全管理に関係する可能性があるため、原文確認を推奨します。'),
            'source': x.get('source') or d,
        })
        x.pop('published', None)

    db.extend(fresh)
    db.sort(key=lambda x: (x.get('date', ''), {'高': 3, '中': 2, '低': 1}.get(x.get('importance'), 0)), reverse=True)
    db = db[:200]
    NEWS_JSON.write_text(json.dumps(db, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Added {len(fresh)} new items; database now has {len(db)} items.')


if __name__ == '__main__':
    main()
