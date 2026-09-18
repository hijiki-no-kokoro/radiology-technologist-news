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
    '"診療放射線技師" OR "放射線技師"',
    '"放射線部" CT MRI FPD',
    '"放射線" 被ばく 線量管理 安全管理',
    '核医学 SPECT PET "放射線技師"',
    '放射線 AI 画像診断 読影支援',
    '診療報酬 放射線 画像診断 補助金',
    'CT MRI 医療 画像診断 放射線',
    '医用画像 AI CT MRI 病院',
    '放射線 医療機器 CT MRI 最新',
    '放射線治療 医療機器 最新',
    'マンモグラフィ 医療機器 放射線',
    'FPD X線撮影 医療 最新',
    'site:jart.jp "診療放射線技師"',
    'site:jsrt.or.jp "診療放射線技師" OR "放射線技術"',
    'site:radiology.jp "診療放射線技師" OR "放射線"',
    'site:jsnm.org 核医学 "放射線技師"',
    'site:jastro.or.jp 放射線治療 "放射線技師"',
    'site:mhlw.go.jp "診療放射線技師" 放射線',
    'site:pmda.go.jp 放射線 CT MRI 医療機器',
]

OFFICIAL = (
    'jart.jp',
    'jsrt.or.jp',
    'jrs.or.jp',
    'radiology.jp',
    'jsnm.org',
    'jastro.or.jp',
    'mhlw.go.jp',
    'nra.go.jp',
    'pmda.go.jp',
    'mext.go.jp',
)

CATEGORIES = (
    '制度',
    '職能',
    '学術',
    'AI',
    'CT',
    'MRI',
    '一般撮影',
    '安全管理',
    '核医学',
    '放射線治療',
    '教育',
    '診療報酬・補助金',
    'その他'
)

DIRECT_TERMS = (
    '診療放射線技師',
    '放射線技師',
    '放射線部',
    '放射線科',
    '診療用放射線',
)

STRONG_MODALITY_TERMS = (
    'CT',
    'MRI',
    'FPD',
    '一般撮影',
    'マンモグラフィ',
    '核医学',
    'SPECT',
    'PET',
    '放射線治療',
    '被ばく',
    '線量管理',
    '画像診断AI',
    '画像診断支援',
    '読影支援',
    'STAT',
    'X線撮影',
    'タスクシフト',
    'タスクシェア',
    '放射線安全',
    '医療被ばく',
    '線量最適化',
    '画像診断',
)

BROAD_MODALITY_TERMS = (
    '画像診断',
    '読影',
    '医用画像',
    '放射線',
    '医療画像',
)

BAD_TERMS = (
    '漫画',
    'マンガ',
    '芸能',
    '俳優',
    '女優',
    'アイドル',
    'タレント',
    'グラビア',
    '写真集',
    '求人',
    '転職',
    '保険',
)

NOISE_TITLE_TERMS = (
    '受付期間：',
    '開催日：',
    '会誌・投稿',
    '活動紹介',
    '技師会概要',
)

NON_RADIOLOGY_TERMS = (
    'ポケモン', 'ポケカ', '資産形成', '投資', '株式投資', '副業',
    '競馬', '競輪', '競艇', 'ギャンブル', '仮想通貨', '暗号資産'
)

MARKET_REPORT_DOMAINS = (
    'newscast.jp', 'atpress.ne.jp'
)

def fetch(url):
    return urlopen(
        Request(
            url,
            headers={'User-Agent': 'Mozilla/5.0 radiology-technologist-news'}
        ),
        timeout=30
    ).read().decode('utf-8', 'ignore')


def clean_html(s):
    return ' '.join(
        unescape(re.sub(r'<[^>]+>', ' ', s or '')).split()
    )


def rss(q):
    root = ET.fromstring(
        fetch(
            'https://news.google.com/rss/search?q='
            + quote(q + ' when:2d')
            + '&hl=ja&gl=JP&ceid=JP:ja'
        )
    )

    out = []

    for it in root.findall('./channel/item'):
        try:
            dt = parsedate_to_datetime(
                it.findtext('pubDate', '')
            ).astimezone(JST)
        except Exception:
            continue

        title = unescape(it.findtext('title', ''))
        link = it.findtext('link', '')
        desc = clean_html(
            it.findtext('description', '')
        )[:700]

        se = it.find('source')
        src = se.text if se is not None else ''

        if title and link:
            out.append({
                'title': title,
                'url': link,
                'description': desc,
                'source': src,
                'published': dt.isoformat(),
            })

    return out


def norm(s):
    return re.sub(
        r'[^0-9a-zぁ-んァ-ヶ一-龠]',
        '',
        str(s or '').lower()
    )


def dom(url):
    m = re.search(r'https?://([^/]+)', url or '')
    return (
        m.group(1).lower().replace('www.', '')
        if m else ''
    )


def is_official(url):
    d = dom(url)
    return any(
        d == z or d.endswith('.' + z)
        for z in OFFICIAL
    )


def article_text(x):
    return ' '.join(
        str(x.get(k, '') or '')
        for k in (
            'title',
            'headline',
            'description',
            'summary',
            'source'
        )
    ).lower()


def relevant(x):
    text = article_text(x)

    if any(k.lower() in text for k in BAD_TERMS):
        return False

    if any(k.lower() in text for k in NON_RADIOLOGY_TERMS):
        return False

    direct = any(
        k.lower() in text
        for k in DIRECT_TERMS
    )

    strong = any(
        k.lower() in text
        for k in STRONG_MODALITY_TERMS
    )

    broad = any(
        k.lower() in text
        for k in BROAD_MODALITY_TERMS
    )

    if is_official(x.get('url', '')):
        return direct or strong or broad

    return (
        direct
        or strong
        or (
            broad
            and any(
                k in text
                for k in (
                    '医療',
                    '病院',
                    '患者',
                    '診断',
                    '画像',
                    '放射線'
                )
            )
        )
    )


def is_news_item(x):
    url = x.get('url', '')
    title = (
        x.get('title')
        or x.get('headline')
        or ''
    ).strip()

    if '/activity/lifelong-study' in url:
        return False

    if re.search(r'^画像\s*\d+\s*/\s*\d+', title):
        return False

    if title in (
        '日本診療放射線技師会誌JART',
        'みんなに知ってもらいたい診療放射線技師のこと',
        '日本診療放射線技師会について',
        '都道府県診療放射線技師会・放射線技師会',
        '活動紹介',
        '会誌・投稿',
        '一般向け情報',
        '技師会概要',
        '医療被ばく個別相談センター',
    ):
        return False

    if any(
        k in title
        for k in NOISE_TITLE_TERMS
    ):
        return False

    return True


def parse_nearby_date(html, pos):
    dates = re.findall(
        r'(20\d{2})[/.年](\d{1,2})[/.月](\d{1,2})',
        clean_html(html[max(0, pos - 1800):pos])
    )

    if dates:
        y, m, d = dates[-1]
        return (
            f'{y}-{int(m):02d}-{int(d):02d}'
            'T00:00:00+09:00'
        )

    return None


def direct_jart():
    out = []

    try:
        html = fetch('https://www.jart.jp/')

        for m in re.finditer(
            r'<a[^>]+href=["\'](?P<href>[^"\']+)["\'][^>]*>'
            r'\s*(?P<title>.*?)\s*</a>',
            html,
            re.I | re.S
        ):
            title = clean_html(m.group('title'))
            href = urljoin(
                'https://www.jart.jp/',
                m.group('href')
            )
            date = parse_nearby_date(
                html,
                m.start()
            )

            test_item = {
                'title': title,
                'source': 'JART',
                'url': href,
            }

            if (
                title
                and date
                and '/news/info/' in href.lower()
                and relevant(test_item)
                and is_news_item(test_item)
            ):
                out.append({
                    'title': title,
                    'url': href,
                    'description': title,
                    'source': 'JART',
                    'published': date,
                })

    except Exception as e:
        print('JART direct error:', e)

    return out


def category(x):
    t = article_text(x)

    rules = [
        (
            '診療報酬・補助金',
            ('診療報酬', '補助金', '助成金', '加算')
        ),
        (
            '安全管理',
            (
                '安全管理',
                '安全',
                '被ばく',
                '線量管理',
                '医療被ばく',
                '線量',
                '放射線安全',
                '線量最適化'
            )
        ),
        (
            '一般撮影',
            (
                '一般撮影',
                'FPD',
                'マンモグラフィ',
                'X線撮影'
            )
        ),
        (
            'CT',
            ('CT', 'computed tomography')
        ),
        (
            'MRI',
            ('MRI', 'magnetic resonance')
        ),
        (
            '核医学',
            (
                '核医学',
                'SPECT',
                'PET',
                'MIBG',
                'DAT',
                'RI'
            )
        ),
        (
            '放射線治療',
            (
                '放射線治療',
                'リニアック',
                '陽子線',
                '粒子線',
                'IGRT'
            )
        ),
        (
            'AI',
            (
                'AI',
                '人工知能',
                '画像診断支援',
                '読影支援'
            )
        ),
        (
            '教育',
            (
                '教育',
                '国家試験',
                '研修',
                '認定',
                'セミナー',
                '講習'
            )
        ),
        (
            '学術',
            (
                '学術',
                '研究',
                '学会',
                'ガイドライン',
                'パブリックコメント'
            )
        ),
        (
            '職能',
            (
                'STAT',
                'タスクシフト',
                'タスクシェア',
                '業務範囲',
                '職能'
            )
        ),
        (
            '制度',
            (
                '制度',
                '養成',
                '確保',
                '厚生労働省',
                '医政'
            )
        ),
    ]

    for cat, terms in rules:
        if any(
            k.lower() in t
            for k in terms
        ):
            return cat

    return 'その他'


def is_specialist(x):
    """
    放射線部門の実務に直接関係するニュースか判定する。
    「診療放射線技師」という語がなくても、
    CT/MRI/核医学/放射線治療/線量管理/画像診断AI等なら専門扱い。
    """

    text = article_text(x)
    title = (x.get('title') or x.get('headline') or '').lower()
    domain = dom(x.get('url', ''))

    if any(k.lower() in text for k in NON_RADIOLOGY_TERMS):
        return False

    if re.search(r'^画像\s*\d+\s*/\s*\d+', title):
        return False

    if domain in MARKET_REPORT_DOMAINS and any(
        k in title for k in ('市場', '市場規模', '市場動向', 'シェア', '成長分析', '業界予測', '市場レポート')
    ):
        return False

    direct_context = (
        '業務', '業務範囲', 'タスクシフト', 'タスクシェア', '教育', '研修',
        '国家試験', '資格', '認定', '職能', 'STAT', '学会', '病院',
        '放射線部', '放射線科', '検査', '撮影', '被ばく', '線量', '画像',
        'CT', 'MRI', '核医学', 'SPECT', 'PET', '放射線治療', '診療', '制度',
        '講習', '実習', '告示研修', '養成', '確保', 'アンケート', 'ガイドライン'
    )

    if any(k.lower() in text for k in DIRECT_TERMS):
        # 「放射線技師」という語だけの一般記事は専門扱いしない
        if any(k.lower() in text for k in direct_context):
            return True

    specialist_terms = (
        'CT',
        'MRI',
        'FPD',
        '一般撮影',
        'マンモグラフィ',
        '核医学',
        'SPECT',
        'PET',
        '放射線治療',
        '被ばく',
        '線量管理',
        '医療被ばく',
        '線量最適化',
        '放射線安全',
        '画像診断AI',
        '画像診断支援',
        '読影支援',
        '医用画像',
        'X線撮影',
        'タスクシフト',
        'タスクシェア',
        '診療用放射線',
        '診療報酬',
        '放射線医療機器',
    )

    return any(
        k.lower() in text
        for k in specialist_terms
    )


def importance(x, official):
    t = article_text(x)

    if any(
        k.lower() in t
        for k in (
            '診療報酬',
            '補助金',
            '安全管理',
            '被ばく',
            '線量管理',
            '装置更新',
            'タスクシフト',
            'タスクシェア',
            '業務範囲',
            'STAT',
            'ガイドライン',
        )
    ):
        return '高'

    if official:
        return '中'

    return '低'


def score(x):
    t = article_text(x)
    s = 0

    if any(
        k.lower() in t
        for k in DIRECT_TERMS
    ):
        s += 12

    if is_official(x.get('url', '')) \
            or x.get('source') == 'JART':
        s += 4

    if any(
        k.lower() in t
        for k in (
            '制度',
            '診療報酬',
            '補助金',
            '安全管理',
            '被ばく',
            '線量管理',
            '装置更新',
            'タスクシフト',
            'タスクシェア',
            'ガイドライン',
        )
    ):
        s += 4

    if any(
        k.lower() in t
        for k in STRONG_MODALITY_TERMS
    ):
        s += 3

    if any(
        k.lower() in t
        for k in (
            'CT',
            'MRI',
            'SPECT',
            'PET',
            'FPD',
            'マンモグラフィ',
            '放射線治療',
        )
    ):
        s += 2

    if any(
        k.lower() in t
        for k in (
            '漫画',
            'マンガ',
            '芸能',
            '俳優',
            '女優',
            'アイドル',
            'タレント',
        )
    ):
        s -= 20

    return s


def load():
    try:
        return json.loads(
            NEWS_JSON.read_text(
                encoding='utf-8'
            )
        )
    except Exception:
        return []


def clean_db(db):
    today = datetime.now(JST).date()
    out = []
    seen = set()

    for x in db:
        try:
            item_date = datetime.fromisoformat(
                str(x.get('date', '')).replace(
                    'Z',
                    '+00:00'
                )
            ).date()

            if item_date > today:
                continue

        except Exception:
            continue

        if not relevant(x):
            continue

        if not is_news_item(x):
            continue

        k = (
            norm(x.get('headline'))
            or x.get('url')
        )

        if not k or k in seen:
            continue

        seen.add(k)

        x['category'] = (
            x.get('category')
            if x.get('category') in CATEGORIES
            else category(x)
        )

        if not x.get('track'):
            x['track'] = (
                'official'
                if is_official(x.get('url', ''))
                else 'general'
            )

        out.append(x)

    return out


def make_item(x):
    official = (
        is_official(x.get('url', ''))
        or x.get('source') == 'JART'
    )

    return {
        'date': x['published'][:10],
        'category': category(x),
        'importance': importance(
            x,
            official
        ),
        'headline': x['title'],
        'summary': re.sub(
            r'\s+',
            ' ',
            x.get('description', '')
        ).strip()[:220],
        'why': (
            '公式情報のため、放射線部門の運用・教育・制度への影響を確認する価値があります。'
            if official
            else
            '放射線部門の実務への影響を確認する価値があります。'
        ),
        'source': (
            x.get('source')
            or dom(x['url'])
        ),
        'url': x['url'],
        'track': (
            'official'
            if official
            else 'general'
        ),
    }


def main():
    cutoff = (
        datetime.now(JST)
        - timedelta(hours=72)
    )
    ongoing_cutoff = (
        datetime.now(JST)
        - timedelta(days=30)
    )

    db = clean_db(load())

    seen = {
        norm(x.get('headline'))
        or x.get('url')
        for x in db
    }

    candidates = {}

    # JART直接取得
    for x in direct_jart():
        try:
            if datetime.fromisoformat(
                x['published']
            ) < cutoff:
                continue
        except Exception:
            continue

        k = (
            norm(x['title'])
            or x['url']
        )

        if k not in seen:
            candidates[x['url']] = x

    # Google News RSS
    for q in QUERIES:
        try:
            for x in rss(q):

                try:
                    published = datetime.fromisoformat(
                        x['published']
                    )
                except Exception:
                    continue

                if published < cutoff:
                    if not (is_official(x.get('url','')) and any(k.lower() in article_text(x) for k in ('継続','アンケート','募集','受付','ガイドライン','研修','講習')) and published >= ongoing_cutoff):
                        continue

                if not relevant(x):
                    continue

                if not is_news_item(x):
                    continue

                k = (
                    norm(x['title'])
                    or x['url']
                )

                if k not in seen:
                    candidates[x['url']] = x

        except Exception as e:
            print('RSS error:', e)

    # --------------------------------------------------
    # 専門ニュースと一般ニュースを分離して選ぶ
    # --------------------------------------------------

    fresh = list(candidates.values())

    specialist = [
        x for x in fresh
        if is_specialist(x)
    ]

    general = [
        x for x in fresh
        if not is_specialist(x)
    ]

    specialist.sort(
        key=lambda x: (
            score(x),
            x.get('published', '')
        ),
        reverse=True
    )

    general.sort(
        key=lambda x: (
            score(x),
            x.get('published', '')
        ),
        reverse=True
    )

    # --------------------------------------------------
    # 専門ニュース
    # 最大5件
    # 「技師」という語がなくても実務関連なら採用
    # --------------------------------------------------

    added = []
    specialist_titles = set()

    for x in specialist[:5]:
        k = norm(x['title'])

        if not k or k in specialist_titles:
            continue

        specialist_titles.add(k)

        item = make_item(x)

        # 専門ニュースとして明示
        item['track'] = 'official'

        added.append(item)

    # --------------------------------------------------
    # 一般ニュース
    # 最大5件
    # 専門ニュースとは別枠
    # --------------------------------------------------

    general_titles = set()

    for x in general[:5]:
        k = norm(x['title'])

        if not k or k in specialist_titles:
            continue

        if k in general_titles:
            continue

        general_titles.add(k)

        item = make_item(x)
        item['track'] = 'general'

        added.append(item)

    # --------------------------------------------------
    # DBへ保存
    # --------------------------------------------------

    final = clean_db(
        added + db
    )

    # 万一、新規データが全部clean_dbで落ちても
    # 既存データを壊さない
    if added and not final:
        final = added + db

    NEWS_JSON.write_text(
        json.dumps(
            final[:200],
            ensure_ascii=False,
            indent=2
        ),
        encoding='utf-8'
    )

    print(
        f'Added {len(added)} new items; '
        f'database now has {len(final[:200])} items.'
    )

    print(
        f'Specialist candidates: '
        f'{len(specialist)}'
    )

    print(
        f'General candidates: '
        f'{len(general)}'
    )

    for x in added:
        print(
            x['date'],
            x['track'],
            x['category'],
            x['headline']
        )


if __name__ == '__main__':
    main()
