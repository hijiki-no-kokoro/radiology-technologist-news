import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / 'index.html'
NEWS_JSON = ROOT / 'news.json'

FEEDS = [
    ('JART', 'https://www.jart.jp/'),
    ('厚生労働省', 'https://www.mhlw.go.jp/stf/seisakunitsuite/bunya/0000188411.html'),
    ('原子力規制委員会', 'https://www.nra.go.jp/'),
    ('PMDA', 'https://www.pmda.go.jp/'),
]


def fetch(url):
    req = Request(url, headers={'User-Agent': 'Mozilla/5.0 radiology-technologist-news'})
    with urlopen(req, timeout=20) as r:
        return r.read().decode('utf-8', errors='ignore')


def extract_links(html, base):
    links = []
    for href, text in re.findall(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', html, re.I | re.S):
        text = re.sub(r'<[^>]+>', '', text)
        text = re.sub(r'\s+', ' ', text).strip()
        if len(text) < 8:
            continue
        if href.startswith('/'):
            p = urlparse(base)
            href = f'{p.scheme}://{p.netloc}{href}'
        elif href.startswith('#') or href.startswith('javascript:'):
            continue
        elif not href.startswith('http'):
            href = base.rstrip('/') + '/' + href.lstrip('/')
        links.append((text, href))
    return links[:40]


def load_news():
    if not NEWS_JSON.exists():
        return []
    try:
        return json.loads(NEWS_JSON.read_text(encoding='utf-8'))
    except Exception:
        return []


def main():
    now = datetime.now(timezone.utc).astimezone()
    news = load_news()
    seen = {item.get('url') for item in news}

    # This first version intentionally gathers official-source headlines.
    # AI summarization is added when OPENAI_API_KEY is configured.
    for source, url in FEEDS:
        try:
            html = fetch(url)
            for title, link in extract_links(html, url):
                if link in seen:
                    continue
                if not any(k in title for k in ('放射', '診療', '医療', '線量', 'AI', 'MRI', 'CT', '被ばく', '技師', '画像')):
                    continue
                news.append({
                    'date': now.strftime('%Y-%m-%d'),
                    'category': source,
                    'importance': '中',
                    'headline': title,
                    'summary': '公式サイトで公開された最新情報です。',
                    'why': '放射線部門の制度・安全管理・診療運用に関係する可能性があるため、内容確認を推奨します。',
                    'source': source,
                    'url': link,
                })
                seen.add(link)
                if len(news) >= 100:
                    break
        except Exception as e:
            print(f'feed error: {source}: {e}')

    news.sort(key=lambda x: (x.get('date', ''), x.get('importance', '')), reverse=True)
    news = news[:100]
    NEWS_JSON.write_text(json.dumps(news, ensure_ascii=False, indent=2), encoding='utf-8')

    # Keep the existing HTML design and inject a current DB payload.
    html = INDEX.read_text(encoding='utf-8')
    marker_start = '<!-- NEWS_DB_START -->'
    marker_end = '<!-- NEWS_DB_END -->'
    if marker_start in html and marker_end in html:
        payload = json.dumps(news, ensure_ascii=False).replace('</', '<\\/')
        html = re.sub(marker_start + r'.*?' + marker_end,
                      marker_start + '\n<script>window.NEWS_DB=' + payload + ';</script>\n' + marker_end,
                      html, flags=re.S)
        INDEX.write_text(html, encoding='utf-8')

    print(f'Updated {len(news)} news items at {now.isoformat()}')


if __name__ == '__main__':
    main()
