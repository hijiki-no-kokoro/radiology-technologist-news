import json, os, re, smtplib, xml.etree.ElementTree as ET
from email.mime.text import MIMEText
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path
from urllib.parse import quote, urljoin
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
NEWS_JSON = ROOT / 'news.json'
ARCHIVE_DIR = ROOT / 'archive'      # 200件からあふれた記事を月ごとに保存
MAX_RECENT = 200
META_JSON = ROOT / 'news_meta.json'
SEMINARS_JSON = ROOT / 'seminars.json'  # 技師会の研修・講習会の日程  # 最終更新時刻と新着件数(画面の右上に表示)
HTML_DIR = ROOT / 'daily_html'


def feed_date(item):
    """Date used for the daily edition; keep the original publication date intact."""
    return item.get('featured_date') or item.get('date')


def build_daily_html(items, date_str):
    special = [x for x in items if feed_date(x) == date_str and x.get('track') != 'general']
    general = [x for x in items if feed_date(x) == date_str and x.get('track') == 'general']

    def esc(s):
        return (str(s or '').replace('&','&amp;').replace('<','&lt;').replace('>','&gt;').replace(chr(34),'&quot;'))

    def card(x):
        return ('<article class="card"><div class="meta"><span class="tag">' + esc(x.get('category')) + '</span><span class="imp">重要度 ' + esc(x.get('importance')) + '</span><span class="date">' + esc(x.get('date')) + '</span></div><h2>' + esc(x.get('headline')) + '</h2>' + ('<p>' + esc(x.get('summary')) + '</p>' if x.get('summary') else '') + ('<div class="why"><b>ポイント：</b>' + esc(x.get('why')) + '</div>' if x.get('why') else '') + '<a href="' + esc(x.get('url')) + '" target="_blank" rel="noopener">' + esc(x.get('source') or '情報源') + ' ↗</a></article>')

    def section(title, badge, data, empty):
        body = ''.join(card(x) for x in data) or '<div class="empty">' + empty + '</div>'
        return '<section><div class="section-title"><h2>' + title + '</h2><span class="badge">' + badge + '</span></div>' + body + '</section>'

    return ('<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>放射線技師ニュース ' + date_str + '</title><style>body{margin:0;background:#f3f6f9;color:#17212b;font-family:-apple-system,BlinkMacSystemFont,"Noto Sans JP","Yu Gothic",sans-serif}main{max-width:900px;margin:auto;padding:16px}header,.card{background:#fff;border:1px solid #dfe5eb;border-radius:16px;padding:18px;margin:12px 0}h1{font-size:25px;margin:0 0 8px}h2{font-size:18px;line-height:1.5;margin:10px 0}.meta{display:flex;gap:7px;flex-wrap:wrap;font-size:12px;color:#687585}.tag,.imp,.badge{border:1px solid #d3dbe4;border-radius:999px;padding:4px 9px}p{font-size:14px;line-height:1.8}.why{background:#f7f9fb;border-radius:10px;padding:11px;font-size:13px;line-height:1.7}.section-title{display:flex;justify-content:space-between;align-items:center;margin-top:26px}.empty{background:#fff;border-radius:12px;padding:16px;color:#687585}</style></head><body><main>'
            '<header><h1>🔥 今日の放射線部門ニュース</h1><div>' + date_str + '</div></header>'
            + section('専門ニュース','放射線・医療実務',special,'本日の専門ニュースはありません。')
            + section('一般ニュース','一般メディア・周辺動向',general,'本日の一般ニュースはありません。')
            + '</main></body></html>')
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
    '胃がん検診 X線 OR 胃透視 OR バリウム',
    '胃部X線検査 OR 胃X線検診 診療放射線技師',
    'がん検診 マンモグラフィ OR 胸部X線 精度管理',
    '人間ドック OR 健診 放射線技師 OR 画像',
    '血管撮影 OR IVR OR アンギオ 放射線技師 OR 被ばく',
    '超音波検査 OR エコー検査 診療放射線技師 OR 検査技師',
    'site:jart.jp "診療放射線技師"',
    'site:jsrt.or.jp "診療放射線技師" OR "放射線技術"',
    'site:radiology.jp "診療放射線技師" OR "放射線"',
    'site:jsnm.org 核医学 "放射線技師"',
    'site:jastro.or.jp 放射線治療 "放射線技師"',
    'site:jsmp.org 医学物理 放射線治療 OR 線量管理',
    'site:mhlw.go.jp "診療放射線技師" 放射線',
    'site:pmda.go.jp 放射線 CT MRI 医療機器',
    'site:nra.go.jp 医療 放射線 安全',
]

OFFICIAL = (
    'jart.jp',
    'jsrt.or.jp',
    'jrs.or.jp',
    'radiology.jp',
    'jsnm.org',
    'jastro.or.jp',
    'jsmp.org',
    'mhlw.go.jp',
    'nra.go.jp',
    'pmda.go.jp',
    'mext.go.jp',
    'med-safe.jp',
    'jcqhc.or.jp',
    'jsgcs.or.jp',
    'qabcs.or.jp',
    'jastro.or.jp', 'jsmp.org', 'jsmrm.jp', 'jsir.or.jp', 'jsum.or.jp', 'jsnmt.org', 'jsct-tech.org',
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
    '検診',
    'マンモグラフィ',
    '血管撮影',
    '超音波',
    'その他'
)

# ChatGPTの日次編集版で確認した「部門で直ちに周知・検討したい」公式情報。
# RSSの短いタイトルを、ホームページでも実務に使える要約と重要度で表示する。
# featured_date は掲載日ではなく、日次ニュースとして選定した日を表す。
CURATED_SPECIALIST = (
    (
        '第66回放射線治療セミナー',
        {
            'category': '放射線治療',
            'importance': '高',
            'summary': 'IGRTを支える教育体制、運用の基礎、臨床上の注意点や工夫を扱うWebセミナー。申込は10月1日正午～11月26日正午。',
            'why': 'IGRTの運用の基礎から臨床上の注意点まで学べます。治療に関わるなら申込期間を確認しておきましょう。',
            'source': '日本放射線技術学会（JSRT）',
            'featured_date': '2026-09-22',
        },
    ),
    (
        '実地で学ぶMRI安全管理セミナー',
        {
            'category': 'MRI',
            'importance': '高',
            'summary': 'MRI安全管理を実地で学ぶセミナーの案内。',
            'why': 'MRI室の安全管理を実地で学べる内容です。MRIに関わるなら確認しておきましょう。',
            'source': '日本放射線技術学会（JSRT）',
            'featured_date': '2026-09-22',
        },
    ),
    (
        '診断X線領域の線量測定基礎Webセミナー（血管撮影領域CBCT編）',
        {
            'category': '安全管理',
            'importance': '高',
            'summary': '血管撮影領域CBCTの線量測定を学ぶWebセミナー。',
            'why': '血管撮影・IVRの患者線量の評価と最適化を基礎から学べます。',
            'source': '日本放射線技術学会（JSRT）',
            'featured_date': '2026-09-22',
        },
    ),
    (
        '医療放射線安全管理講習会（WEB）',
        {
            'category': '安全管理',
            'importance': '高',
            'summary': '立入検査、タスク・シフト、グリーンラジオロジー、IVR、核医学治療などを扱う講習会。',
            'why': '立入検査への対応、医療放射線の安全管理、タスク・シフトの要点をまとめて学べます。',
            'source': '日本診療放射線技師会（JART）',
            'featured_date': '2026-09-22',
        },
    ),
)

DIRECT_TERMS = (
    '診療放射線技師',
    '放射線技師',
    '放射線部',
    '放射線科',
    '診療用放射線',
)

STRONG_MODALITY_TERMS = (
    '胃透視', '胃X線', '胃部X線', 'バリウム', '上部消化管造影', '胃がん検診', '乳がん検診', '肺がん検診',
    '血管撮影', 'IVR', 'アンギオ', '超音波検査', 'エコー検査',
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
    '市場調査',
    '市場規模',
    '市場動向',
    '市場レポート',
    '画像ギャラリー',
    'フォトギャラリー',
)

NON_RADIOLOGY_TERMS = (
    'ポケモン', 'ポケカ', '資産形成', '投資', '株式投資', '副業',
    '競馬', '競輪', '競艇', 'ギャンブル', '仮想通貨', '暗号資産'
)

MARKET_REPORT_DOMAINS = (
    'newscast.jp', 'atpress.ne.jp'
)

SOURCE_STATUS = {}  # 取得元ごとの結果(news_meta.json に記録して、取れなくなったら気付けるように)


def fetch(url):
    return urlopen(
        Request(
            url,
            headers={
                'User-Agent': 'Mozilla/5.0 (compatible; radiology-technologist-news; +https://hijiki-no-kokoro.github.io/radiology-technologist-news/)',
                'Accept': 'text/html,application/xhtml+xml,application/xml,application/rss+xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'ja,en;q=0.5',
            }
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
    # 医療安全情報は取得時に放射線関連だけを選んでいるので、そのまま残す
    if dom(x.get('url', '')) in SAFETY_INFO_DOMAINS:
        return True
    # 放射線系学会のサイトから直接取った記事は、学会の性質上すべて対象にする
    if any(dom(x.get('url', '')) == d or dom(x.get('url', '')).endswith('.' + d) for d in SOCIETY_DOMAINS):
        return True

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
        '放射線被ばく相談員',
    ):
        return False

    # 技師会サイトのメニュー(「〇〇の情報をご紹介しています。 詳細を見る」)
    if title.endswith('詳細を見る'):
        return False

    if any(
        k in title
        for k in NOISE_TITLE_TERMS
    ):
        return False

    # 見出しが取れなかったページ(「Untitled - 日本診療放射線技師会」など)
    if re.match(r'^\s*(untitled|no title|無題)\s*(-|$)', title, flags=re.I):
        return False

    if is_market_report(x):
        return False

    if is_foreign_local_news(x):
        return False

    if is_light_read(x):
        return False

    return True


# 業務に役立たない読み物(漫画風の体験談・釣り見出し・闘病記・事件報道)
LIGHT_READ_SOURCES = ('trill', '選挙ドットコム')
LIGHT_READ_PATTERN = re.compile(
    r'→.*…|….*→'                     # 「…患者のネイルに→感心するも…」型の漫画記事
    r'|顔面蒼白|まさかの|即答した正体|あるあるを描く|著者インタビュー'
    r'|【闘病】|闘病記'
    r'|殺意|殺害|刺殺|遺体'
)


def is_light_read(x):
    source = str(x.get('source') or '').lower()
    if any(s in source for s in LIGHT_READ_SOURCES):
        return True
    title = str(x.get('title') or x.get('headline') or '')
    return bool(LIGHT_READ_PATTERN.search(title))


# 海外の地方病院ニュースを機械翻訳した配信元(装置の故障・導入など現地の話題が大半)
FOREIGN_LOCAL_SOURCES = ('vietnam.vn', 'laodong.vn', 'vnexpress', 'baomoi', 'tuoitre', 'thanhnien')


def is_foreign_local_news(x):
    source = str(x.get('source') or '').lower()
    url = str(x.get('url') or '').lower()
    return any(s in source or s in url for s in FOREIGN_LOCAL_SOURCES)


# 同じ団体の配信元名の表記ゆれをそろえる(表示とフィルタの一貫性のため)
SOURCE_ALIASES = (
    (r'^(公益社団法人\s*)?日本放射線技術学会(（JSRT）|\(JSRT\))?$|^jsrt(\.or\.jp)?$', '日本放射線技術学会'),
    (r'^(公益社団法人\s*)?日本診療放射線技師会(（JART）|\(JART\))?$|^jart(\.jp)?$', '日本診療放射線技師会'),
    (r'^(公益社団法人\s*)?日本医学放射線学会(（JRS）|\(JRS\))?$|^radiology\.jp$', '日本医学放射線学会'),
    (r'readyfor', 'READYFOR'),
)


def normalize_sources(item):
    item['source'] = normalize_source(item.get('source'))
    for a in item.get('also') or []:
        a['source'] = normalize_source(a.get('source'))
    return item


def normalize_source(source):
    s = str(source or '').strip()
    for pattern, name in SOURCE_ALIASES:
        if re.search(pattern, s, flags=re.I):
            return name
    return s


# 市場調査会社の宣伝記事(「〇〇市場、2035年に89億米ドルへ」など)は実務に役立たないので除外する
MARKET_REPORT_SOURCES = (
    'pando.life', 'spherical insights', 'indexbox', 'sns insider',
    'global information', 'gii', 'researchandmarkets', 'report ocean',
    'kenresearch', 'market research',
)


def is_market_report(x):
    title = str(x.get('title') or x.get('headline') or '')
    source = str(x.get('source') or '').lower()
    if any(s in source for s in MARKET_REPORT_SOURCES):
        return True
    if re.search(r'マーケットリサーチ|マーケット調査|市場調査レポート|CAGR|年平均成長率', title, flags=re.I):
        return True
    if '市場' not in title:
        return False
    return bool(re.search(
        r'CAGR|年平均成長率|億\s*米?ドル|万\s*米?ドル|市場規模|市場予測|世界市場|市場分析|市場の(最新)?動向|成長見通し'
        r'|\d{4}年\s*(から|～|〜|-)\s*\d{4}年|トップ\s*\d+\s*企業|メーカーランキング',
        title, flags=re.I,
    ))


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


# --------------------------------------------------
# 医療安全情報(日本医療機能評価機構・PMDA)を直接取得する
# --------------------------------------------------
SAFETY_INFO_DOMAINS = ('med-safe.jp', 'pmda.go.jp')
MED_SAFE_LIST = 'https://www.med-safe.jp/contents/info/'
PMDA_SAFETY_LIST = 'https://www.pmda.go.jp/safety/info-services/medical-safety-info/0001.html'
# 放射線部門に関係しそうな号だけを取り込む
SAFETY_RADIOLOGY_TERMS = (
    'MRI', 'CT', '造影', '放射線', '画像', 'X線', 'エックス線', 'レントゲン', '撮影', '透視', '血管撮影',
    '核医学', 'RI', '被ばく', '植込', '植え込', 'ペースメーカ', '検査', '読影', '金属',
)


def _is_radiology_safety(title):
    return any(_term_in(k, title.lower()) for k in SAFETY_RADIOLOGY_TERMS)


def parse_med_safe(html, limit=3):
    """医療機能評価機構の一覧から、新しい号(番号の大きい順)の放射線関連を返す。"""
    found = {}
    for m in re.finditer(r'<a[^>]+href=["\'](?P<href>[^"\']*med-safe_(?P<no>\d+)\.pdf)["\'][^>]*>(?P<text>.*?)</a>', html, re.I | re.S):
        text = clean_html(m.group('text'))
        no = int(m.group('no'))
        # 「医療機器等・検査 No.239：患者に植込まれた医療機器の確認不足（第2報）」→ 題名部分
        title = re.sub(r'^.*?No\.?\s*\d+\s*[:：]\s*', '', text).strip() or text
        if not title or no in found or 'まとめ' in text:
            continue
        found[no] = {'no': no, 'title': title, 'text': text, 'url': urljoin(MED_SAFE_LIST, m.group('href'))}
    items = [found[k] for k in sorted(found, reverse=True)]
    # 分類名(「医療機器等・検査」など)も含めて判定する
    return [x for x in items if _is_radiology_safety(x['text'])][:limit] if items else []


def parse_pmda_safety(html, limit=3):
    """PMDA医療安全情報の表から、発行年月つきで放射線関連を返す(新しい順)。"""
    out = []
    for row in re.split(r'<tr[\s>]', html, flags=re.I)[1:]:
        no = re.search(r'No\.?\s*(\d+)|>\s*(\d{1,3})\s*<', row)
        ym = re.search(r'(20\d{2})年\s*(\d{1,2})月', row)
        link = re.search(r'<a[^>]+href=["\'](?P<href>[^"\']+\.pdf)["\'][^>]*>(?P<text>.*?)</a>', row, re.I | re.S)
        if not (ym and link):
            continue
        title = clean_html(link.group('text'))
        if not title or title.startswith('[') or '掲示用' in title:
            continue
        out.append({
            'no': int(next(g for g in no.groups() if g)) if no else 0,
            'title': title,
            'url': urljoin(PMDA_SAFETY_LIST, link.group('href')),
            'published': f'{int(ym.group(1)):04d}-{int(ym.group(2)):02d}-01',
        })
    out.sort(key=lambda x: (x['published'], x['no']), reverse=True)
    return [x for x in out if _is_radiology_safety(x['title'])][:limit]


def direct_safety_info():
    """放射線に関係する医療安全情報を、記事の形(title/url/source/published)で返す。"""
    out = []
    now = datetime.now(JST)
    try:
        for x in parse_med_safe(fetch(MED_SAFE_LIST)):
            out.append({
                'title': f'医療安全情報 No.{x["no"]}：{x["title"]}',
                'url': x['url'], 'description': '', 'source': '日本医療機能評価機構',
                # 一覧に発行日がないため、初めて見つけた日を日付にする
                'published': now.isoformat(),
            })
        SOURCE_STATUS['医療機能評価機構'] = {'picked': sum(1 for x in out if x['source'] == '日本医療機能評価機構')}
    except Exception as e:
        print('med-safe direct error:', e)
        SOURCE_STATUS['医療機能評価機構'] = {'error': f'{type(e).__name__}: {e}'[:160]}
    try:
        for x in parse_pmda_safety(fetch(PMDA_SAFETY_LIST)):
            if (now.date() - datetime.fromisoformat(x['published']).date()).days > 120:
                continue
            out.append({
                'title': f'PMDA医療安全情報 No.{x["no"]}：{x["title"]}',
                'url': x['url'], 'description': '', 'source': 'PMDA',
                'published': datetime.fromisoformat(x['published']).replace(tzinfo=JST).isoformat(),
            })
        SOURCE_STATUS['PMDA'] = {'picked': sum(1 for x in out if x['source'] == 'PMDA')}
    except Exception as e:
        print('PMDA direct error:', e)
        SOURCE_STATUS['PMDA'] = {'error': f'{type(e).__name__}: {e}'[:160]}
    print(f'Safety info candidates: {len(out)}')
    return out


# --------------------------------------------------
# 技師会(JART)の研修・講習会一覧から日程を読む
# 例: 「告示研修 受付前 告示研修（実技研修）東京都2026/11/23 受付期間：2026/9/18〜2026/11/8
#      開催日：2026/11/23〜2026/11/23 開催地域：東京都 …」
# --------------------------------------------------
JART_SEMINAR_PAGES = ('https://www.jart.jp/', 'https://www.jart.jp/seminar/')
_JDATE = r'(20\d{2})\s*[/年]\s*(\d{1,2})\s*[/月]\s*(\d{1,2})日?(?:\s*[（(][^）)]*[）)])?'
_JRANGE = _JDATE + r'\s*[〜～\-－~]\s*' + _JDATE


def _jd(g):
    d = _to_date(g[0], g[1], g[2])
    return d.isoformat() if d else ''


def parse_jart_seminars(html, base='https://www.jart.jp/'):
    out = {}
    for m in re.finditer(r'<a[^>]+href=["\'](?P<href>[^"\']*/seminar/[^"\']+)["\'][^>]*>(?P<text>.*?)</a>', html, re.I | re.S):
        text = re.sub(r'\s+', ' ', clean_html(m.group('text'))).strip()
        ev = re.search(r'開催日\s*[:：]\s*' + _JRANGE, text)
        if not ev:
            continue
        ap = re.search(r'受付期間\s*[:：]\s*' + _JRANGE, text)
        head = text.split('受付期間')[0] if '受付期間' in text else text.split('開催日')[0]
        st = re.search(r'(申込み可|受付前|申込み不可|受付終了|満員|定員に達しました)', head)
        status = st.group(1) if st else ''
        kind, title = '', head
        if st:
            kind = head[:st.start()].strip()
            title = head[st.end():].strip()
        place = ''
        pm = re.search(r'開催地域\s*[:：]\s*(\S+)', text)
        if pm:
            place = pm.group(1)
        url = urljoin(base, m.group('href'))
        g = ev.groups()
        out[url] = {
            'title': title, 'url': url, 'kind': kind, 'status': status,
            'event_start': _jd(g[:3]), 'event_end': _jd(g[3:6]),
            'apply_start': _jd(ap.groups()[:3]) if ap else '', 'apply_end': _jd(ap.groups()[3:6]) if ap else '',
            'place': place,
        }
    return list(out.values())


ROMAJI_PREF = {
    'hokkaido': '北海道', 'sapporo': '北海道', 'aomori': '青森', 'iwate': '岩手', 'miyagi': '宮城', 'sendai': '宮城',
    'akita': '秋田', 'yamagata': '山形', 'fukushima': '福島', 'ibaraki': '茨城', 'tochigi': '栃木', 'gunma': '群馬',
    'saitama': '埼玉', 'chiba': '千葉', 'tokyo': '東京', 'kanagawa': '神奈川', 'yokohama': '神奈川', 'niigata': '新潟',
    'toyama': '富山', 'ishikawa': '石川', 'kanazawa': '石川', 'fukui': '福井', 'yamanashi': '山梨', 'nagano': '長野',
    'gifu': '岐阜', 'shizuoka': '静岡', 'aichi': '愛知', 'nagoya': '愛知', 'mie': '三重', 'shiga': '滋賀', 'kyoto': '京都',
    'osaka': '大阪', 'hyogo': '兵庫', 'kobe': '兵庫', 'nara': '奈良', 'wakayama': '和歌山', 'tottori': '鳥取',
    'shimane': '島根', 'okayama': '岡山', 'hiroshima': '広島', 'yamaguchi': '山口', 'tokushima': '徳島',
    'kagawa': '香川', 'takamatsu': '香川', 'ehime': '愛媛', 'matsuyama': '愛媛', 'kochi': '高知', 'fukuoka': '福岡',
    'saga': '佐賀', 'nagasaki': '長崎', 'kumamoto': '熊本', 'oita': '大分', 'miyazaki': '宮崎', 'kagoshima': '鹿児島',
    'okinawa': '沖縄', 'web': 'オンライン', 'online': 'オンライン',
}


def parse_qabcs_seminars(xml):
    """精中機構の講習会RSS(日付=開催日)から、技師向け(撮影・超音波技術)の講習会だけを返す。"""
    out = []
    for x in parse_rss(xml):
        url, title = x['url'], x['title']
        path = re.sub(r'^https?://[^/]+', '', url).lower()
        # URLの _g は技師向け、_d は医師向け
        is_tech = bool(re.search(r'_g/', path)) or ('技術' in title and '医師' not in title)
        if not is_tech:
            continue
        place = next((p for p in PREFECTURES if p in title), '')
        if not place:
            m = re.search(r'_([a-z]+)\.html', path)
            place = ROMAJI_PREF.get(m.group(1), '') if m else ''
        day = x['published'][:10]
        out.append({
            'title': title, 'url': url, 'kind': '精中機構', 'status': '',
            'event_start': day, 'event_end': day, 'apply_start': '', 'apply_end': '', 'place': place,
            'category': '超音波' if '/us/' in path or '超音波' in title else 'マンモグラフィ',
        })
    return out


def update_seminars():
    """技師会の研修日程を seminars.json に保存する。取れなかった日は前回分を残す。"""
    today = datetime.now(JST).date().isoformat()
    found = {}
    for page in JART_SEMINAR_PAGES:
        try:
            for x in parse_jart_seminars(fetch(page), page):
                found[x['url']] = x
        except Exception as e:
            print('JART seminar error:', page, e)
            SOURCE_STATUS.setdefault('技師会の研修一覧', {})['error'] = f'{type(e).__name__}: {e}'[:160]
    try:
        ev = parse_jmrts(fetch(JMRTS_TOP))[1]
        for x in ev:
            found[x['url'] + '#' + x['event_start']] = x
        SOURCE_STATUS['MR認定研究会・セミナー'] = {'listed': len(ev)}
    except Exception as e:
        print('JMRTS seminar error:', e)
        SOURCE_STATUS['MR認定研究会・セミナー'] = {'error': f'{type(e).__name__}: {e}'[:160]}
    try:
        q = parse_qabcs_seminars(fetch(QABCS_FEED))
        for x in q:
            found[x['url']] = x
        SOURCE_STATUS['精中機構の講習会'] = {'listed': len(q)}
    except Exception as e:
        print('QABCS seminar error:', e)
        SOURCE_STATUS['精中機構の講習会'] = {'error': f'{type(e).__name__}: {e}'[:160]}
    try:
        old = json.loads(SEMINARS_JSON.read_text(encoding='utf-8')).get('items', [])
    except Exception:
        old = []
    if not found:
        items = old
    else:
        items = list(found.values())
    # 終わった研修は外す。何年も続く常設のオンライン講座は「随時」として残す
    items = [x for x in items if (x.get('event_end') or x.get('event_start') or '') >= today]
    items.sort(key=lambda x: (x.get('event_start') or '9999', x.get('title') or ''))
    SEMINARS_JSON.write_text(json.dumps({'checked_at': datetime.now(JST).isoformat(timespec='minutes'),
                                         'items': items}, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f'JART seminars: {len(found)} found, {len(items)} upcoming')
    SOURCE_STATUS.setdefault('技師会の研修一覧', {}).update({'listed': len(found), 'upcoming': len(items)})


# --------------------------------------------------
# 学会・厚労省の新着を直接取得する
# --------------------------------------------------
SOCIETY_DOMAINS = ('jsrt.or.jp', 'radiology.jp', 'jsnm.org', 'jsgcs.or.jp', 'jastro.or.jp', 'jsmp.org', 'jsmrm.jp',
                   'jsir.or.jp', 'jsum.or.jp', 'jsnmt.org', 'jsct-tech.org')
JSRT_NEWS = 'https://www.jsrt.or.jp/data/'
JRS_TOP = 'https://www.radiology.jp/'
JSNM_FEED = 'https://jsnm.org/feed/'
MHLW_FEED = 'https://www.mhlw.go.jp/stf/news.rdf'
JSGCS_TOP = 'https://www.jsgcs.or.jp/'
JMRTS_TOP = 'https://plaza.umin.ac.jp/~JMRTS/'

# 分野ごとの専門学会。(表示名, URL, 読み方, 既定の分類, リンク条件, 読み始める目印)
# 読み方: rss = RSS、list = 日付とリンクが並ぶお知らせ一覧(parse_dated_links)
SPECIALTY_SOURCES = (
    ('日本放射線腫瘍学会', 'https://www.jastro.or.jp/', 'list', '放射線治療', '.', 'news_list'),
    ('日本医学物理学会', 'https://www.jsmp.org/feed/', 'rss', '放射線治療', None, None),
    ('日本磁気共鳴医学会', 'https://www.jsmrm.jp/', 'list', 'MRI', '/modules/news/', 'box_news'),
    ('日本IVR学会', 'https://www.jsir.or.jp/feed/', 'rss', '血管撮影', None, None),
    ('日本超音波医学会', 'https://www.jsum.or.jp/feed/', 'rss', '超音波', None, None),
    ('日本核医学技術学会', 'https://jsnmt.org/news/feed/', 'rss', '核医学', None, None),
    ('日本CT技術学会', 'https://www.jsct-tech.org/', 'list', 'CT', '.', None),
)
# 専門学会の記事で、分類が一般的なもの(その他・学術・教育・制度)になった場合は学会の分野を使う
SPECIALTY_DEFAULT_CATEGORY = {name: cat for name, _, _, cat, *_ in SPECIALTY_SOURCES}
SPECIALTY_DEFAULT_CATEGORY['日本磁気共鳴専門技術者認定機構'] = 'MRI'

QABCS_FEED = 'https://www.qabcs.or.jp/rss2.xml'
DIRECT_MAX_PER_SOURCE = 5   # 初回に古い記事がまとめて入らないよう、1回あたりの上限
DIRECT_DAYS = 21            # これより古い記事は取り込まない(学会は更新がまばらなため3週間)


def parse_rss(xml):
    """RSS 2.0(item/pubDate)と RSS 1.0(rdf:item/dc:date)の両方に対応。"""
    out = []
    for it in re.findall(r'<item\b[^>]*>(.*?)</item>', xml, re.S | re.I):
        title = re.search(r'<title>(.*?)</title>', it, re.S)
        link = re.search(r'<link>(.*?)</link>', it, re.S)
        pub = re.search(r'<pubDate>(.*?)</pubDate>', it, re.S) or re.search(r'<dc:date>(.*?)</dc:date>', it, re.S)
        if not (title and link):
            continue
        t = unescape(re.sub(r'<!\[CDATA\[|\]\]>', '', title.group(1))).strip()
        try:
            raw = pub.group(1).strip() if pub else ''
            dt = parsedate_to_datetime(raw) if re.match(r'[A-Za-z]{3},', raw) else datetime.fromisoformat(raw.replace('Z', '+00:00'))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=JST)
            published = dt.astimezone(JST).isoformat()
        except Exception:
            continue
        out.append({'title': t, 'url': unescape(link.group(1).strip()), 'published': published})
    return out


def parse_jsrt(html):
    """<tr><th>2026/10/27</th>…<a href=".../data/news/70512/">［案内板］…</a></tr>"""
    out = []
    for row in re.split(r'<tr[\s>]', html, flags=re.I)[1:]:
        d = re.search(r'(20\d{2})/(\d{1,2})/(\d{1,2})', row)
        a = re.search(r'<a[^>]+href=["\'](?P<h>[^"\']*/data/news/\d+/?)["\'][^>]*>(?P<t>.*?)</a>', row, re.I | re.S)
        if d and a:
            dt = _to_date(*d.groups())
            if dt:
                out.append({'title': clean_html(a.group('t')), 'url': urljoin(JSRT_NEWS, a.group('h')),
                            'published': datetime(dt.year, dt.month, dt.day, tzinfo=JST).isoformat()})
    return out


def parse_jrs(html):
    """<dt><time datetime="2026-10-23">…</time></dt><dd><a href="member_info/…">題名</a></dd>"""
    out = []
    for m in re.finditer(r'<time[^>]+datetime=["\'](20\d{2}-\d{2}-\d{2})["\'][^>]*>.*?</time>\s*(?:</dt>)?\s*<dd>\s*<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', html, re.I | re.S):
        out.append({'title': clean_html(m.group(3)), 'url': urljoin(JRS_TOP, m.group(2)),
                    'published': datetime.fromisoformat(m.group(1)).replace(tzinfo=JST).isoformat()})
    return out


def parse_jsgcs(html):
    """<article><span class="date">2026.10.13</span>…<a href=".../archives/51">題名</a></article>"""
    out = {}
    for art in re.findall(r'<article\b[^>]*>(.*?)</article>', html, re.S | re.I):
        d = re.search(r'(20\d{2})[./](\d{1,2})[./](\d{1,2})', art)
        a = re.search(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', art, re.S | re.I)
        if d and a:
            dt = _to_date(*d.groups())
            url = urljoin(JSGCS_TOP, a.group(1))
            if dt and url not in out:
                out[url] = {'title': clean_html(a.group(2)), 'url': url,
                            'published': datetime(dt.year, dt.month, dt.day, tzinfo=JST).isoformat()}
    return list(out.values())


_DATE_ANY = re.compile(r'(20\d{2})\s*[./年-]\s*(\d{1,2})\s*[./月-]\s*(\d{1,2})日?')


def parse_dated_links(html, base, href_re=r'.', start=None):
    """「日付 + リンク」が並ぶお知らせ一覧を読む汎用の処理。

    各リンクについて、直前のリンクとの間(直前の文字)にある日付を優先し、なければ
    次のリンクまでの間(直後の文字)にある日付を使う。リンク文字の中の日付は使わない
    (イベント紹介のバナーなどを拾わないため)。
    """
    if start and start in html:
        html = html[html.index(start):]
    anchors = list(re.finditer(r'<a\b[^>]*href=["\']([^"\'#][^"\']*)["\'][^>]*>(.*?)</a>', html, re.S | re.I))
    out = {}
    for i, m in enumerate(anchors):
        href, title = m.group(1), clean_html(m.group(2))
        if len(title) < 6 or not re.search(href_re, href):
            continue
        prev_end = anchors[i - 1].end() if i else max(0, m.start() - 400)
        next_start = anchors[i + 1].start() if i + 1 < len(anchors) else m.end() + 300
        before = clean_html(html[max(prev_end, m.start() - 400):m.start()])
        after = clean_html(html[m.end():min(next_start, m.end() + 300)])
        d = (list(_DATE_ANY.finditer(before)) or [None])[-1] or _DATE_ANY.search(after)
        if not d:
            continue
        dt = _to_date(*d.groups()[:3])
        url = urljoin(base, href)
        if dt and url not in out:
            out[url] = {'title': title, 'url': url, 'published': datetime(dt.year, dt.month, dt.day, tzinfo=JST).isoformat()}
    return list(out.values())


CITY_PREF = {'神戸': '兵庫', '函館': '北海道', '札幌': '北海道', '仙台': '宮城', '横浜': '神奈川', '名古屋': '愛知',
             '金沢': '石川', '博多': '福岡', '高松': '香川', '松山': '愛媛'}


def parse_jmrts(html, today=None):
    """日本磁気共鳴専門技術者認定機構のトップ一覧。

    <li><span class="label">お知らせ</span><span class="date">【現地開催：11/7(土)】<a href="…">第10回高知MRI技術研究会開催のお知らせ＜2026.10></a></span></li>
    戻り値: (記事のリスト, 研究会・セミナーの日程のリスト)
    """
    today = today or datetime.now(JST).date()
    news, events = [], []
    for li in re.findall(r'<li[^>]*>(.*?)</li>', html, re.S | re.I):
        lab = re.search(r'class=["\'][^"\']*label[^"\']*["\'][^>]*>(.*?)</span>', li, re.S | re.I)
        a = re.search(r'<a[^>]+href=["\']([^"\'#][^"\']*)["\'][^>]*>(.*?)</a>', li, re.S | re.I)
        if not (lab and a):
            continue
        label = clean_html(lab.group(1))
        text = clean_html(a.group(2))
        ym = re.search(r'[＜<]\s*(20\d{2})\.(\d{1,2})\s*[＞>]', unescape(text))
        title = re.sub(r'\s*[＜<]\s*20\d{2}\.\d{1,2}\s*[＞>]\s*$', '', unescape(text)).strip()
        url = urljoin(JMRTS_TOP, a.group(1))
        ev = re.search(r'【([^】]*?)開催[:：]\s*(\d{1,2})/(\d{1,2})', clean_html(li))
        if ev:
            mode, mm, dd = ev.group(1), int(ev.group(2)), int(ev.group(3))
            dt = _to_date(today.year, mm, dd)
            if dt and (today - dt).days > 60:
                dt = _to_date(today.year + 1, mm, dd)
            if not dt:
                continue
            place = 'オンライン' if re.search(r'web|ウェブ|オンライン', mode, re.I) else ''
            if not place:
                place = next((p for p in PREFECTURES if p in title), '') or next((v for k, v in CITY_PREF.items() if k in title), '')
            events.append({'title': title, 'url': url, 'kind': 'JMRTS', 'status': '', 'event_start': dt.isoformat(),
                           'event_end': dt.isoformat(), 'apply_start': '', 'apply_end': '', 'place': place,
                           'category': 'MRI', 'source': '日本磁気共鳴専門技術者認定機構'})
            continue
        if not ym:
            continue
        y, m = int(ym.group(1)), int(ym.group(2))
        # 一覧には年月しかないので、今月の掲載分は「見つけた日」を日付にする
        if (y, m) == (today.year, today.month):
            published = datetime.combine(today, datetime.min.time()).replace(tzinfo=JST)
        else:
            published = datetime(y, m, 1, tzinfo=JST)
        news.append({'title': f'{title}' if label in title else title, 'url': url, 'published': published.isoformat(), 'label': label})
    return news, events


def direct_official_news():
    """学会(技術学会・医学放射線学会・核医学会)と厚労省の新着を、記事の形で返す。"""
    sources = (
        ('日本放射線技術学会', JSRT_NEWS, parse_jsrt),
        ('日本医学放射線学会', JRS_TOP, parse_jrs),
        ('日本核医学会', JSNM_FEED, parse_rss),
        ('厚生労働省', MHLW_FEED, parse_rss),
        ('日本消化器がん検診学会', JSGCS_TOP, parse_jsgcs),
        ('日本磁気共鳴専門技術者認定機構', JMRTS_TOP, lambda html: parse_jmrts(html)[0]),
    ) + tuple(
        (name, url, parse_rss if kind == 'rss' else (lambda html, _u=url, _f=flt, _s=start: parse_dated_links(html, _u, _f, _s)))
        for name, url, kind, _cat, flt, start in SPECIALTY_SOURCES
    )
    now = datetime.now(JST)
    out = []
    for name, url, parser in sources:
        try:
            items = parser(fetch(url))
        except Exception as e:
            print(f'{name} direct error:', e)
            SOURCE_STATUS[name] = {'error': f'{type(e).__name__}: {e}'[:160]}
            continue
        picked = []
        for x in sorted(items, key=lambda x: x['published'], reverse=True):
            try:
                age = (now - datetime.fromisoformat(x['published'])).days
            except Exception:
                continue
            if age > DIRECT_DAYS or not x['title']:
                continue
            item = {'title': x['title'], 'url': x['url'], 'description': '', 'source': name, 'published': x['published']}
            # 厚労省は省全体の新着なので、放射線に関係するもの(毎日の整理で残る基準と同じ)だけ
            if name == '厚生労働省' and not relevant(item):
                continue
            if not is_news_item(item):
                continue
            picked.append(item)
            if len(picked) >= DIRECT_MAX_PER_SOURCE:
                break
        print(f'{name}: {len(items)} listed, {len(picked)} picked')
        SOURCE_STATUS[name] = {'listed': len(items), 'picked': len(picked)}
        out.extend(picked)
    return out


# 上から順に最初に当てはまったカテゴリを使う。
# 英字の語は単語単位で判定する(「AI」「CT」「RI」が他の単語の一部に当たらないように)。
CATEGORY_RULES = (
    ('診療報酬・補助金', ('診療報酬', '報酬改定', '補助金', '助成金', '加算', '施設基準')),
    ('職能', ('STAT', 'タスクシフト', 'タスク・シフト', 'タスクシェア', 'タスク・シェア', '業務範囲',
              '職能', '告示研修', '静脈路', '筋注')),
    ('安全管理', ('安全管理', '医療安全', '放射線安全', '放射線防護', '被ばく', '線量管理', '線量測定',
                  '診断参考レベル', 'DRL', '品質管理', '個人情報', '脆弱性', 'サイバー',
                  '限定出荷', '出荷停止', '供給停止', '供給不足', 'リコール', '自主回収')),
    ('放射線治療', ('放射線治療', '放射線療法', '照射', '寡分割', '定位放射線', 'リニアック', '陽子線',
                    '粒子線', '重粒子', 'BNCT', 'IGRT', 'IMRT', 'SBRT', 'ZAP-X', 'サイバーナイフ', 'トモセラピー')),
    ('核医学', ('核医学', '放射性医薬品', 'RI内用', 'セラノスティクス', 'リガンド療法', '核種', 'サイクロトロン',
                'SPECT', 'PET', 'MIBG', 'Ac225', 'Lu-177', 'ルテチウム', '99mTc', 'テクネチウム', 'PSMA')),
    ('血管撮影', ('血管撮影', 'アンギオ', 'IVR', 'インターベンショナル', 'DSA', '心カテ', '心臓カテーテル',
                  'カテーテル治療', '血管内治療', '脳血管内')),
    # マンモグラフィ: 乳がん検診の記事もこちら(超音波・検診より先に判定)
    ('マンモグラフィ', ('マンモ', '乳房撮影', '乳房X線', 'トモシンセシス', '乳がん検診', '乳癌検診', '精度管理中央機構')),
    # 超音波: 「妊婦健診のエコー」などは検診より超音波として扱う
    ('超音波', ('超音波', 'エコー検査', 'エコー', 'ultrasound', 'ultrasonography')),
    # 検診: 胃透視など検診で行う撮影も含める(CT・一般撮影より先に判定)
    ('検診', ('検診', '健診', '人間ドック', 'ドック', '胃透視', '胃X線', '胃部X線', 'バリウム', '上部消化管造影',
              '対策型', '任意型', '消化器がん検診', '読影認定')),
    ('CT', ('CT', 'コンピュータ断層', 'computed tomography', 'フォトンカウンティング')),
    ('MRI', ('MRI', 'MR研究会', '磁気共鳴', 'magnetic resonance', 'テスラ')),
    ('一般撮影', ('一般撮影', '単純X線', 'X線撮影', 'レントゲン', 'FPD', '骨密度', '透視', '生殖腺')),
    ('AI', ('AI', '人工知能', '画像診断支援', '読影支援', '深層学習', 'ディープラーニング', '言語モデル')),
    ('制度', ('制度', '厚生労働省', '医政', '法改正', '省令', '立入検査', '施設認定', '認証申請')),
    ('教育', ('教育', '国家試験', '研修', '認定', 'セミナー', '講習', '講演会', 'eラーニング', 'e-ラーニング', '留学')),
    ('学術', ('学術', '研究', '学会', 'ガイドライン', 'パブリックコメント', '論文', 'ESMO', 'ASTRO', 'RSNA')),
)


def _term_in(term, text):
    if re.fullmatch(r'[A-Za-z0-9\-]+', term):
        return re.search(r'(?<![a-z0-9])' + re.escape(term.lower()) + r'(?![a-z0-9])', text) is not None
    return term.lower() in text


def category(x):
    # 配信元名(「日本放射線技術学会」の「学会」など)では判定しない
    t = ' '.join(
        str(x.get(k) or '') for k in ('title', 'headline', 'description', 'summary')
    ).lower()

    for cat, terms in CATEGORY_RULES:
        if any(_term_in(k, t) for k in terms):
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

    # 公式機関の更新は、職能・制度・安全・教育に直接関係する場合に
    # 専門ニュースとして採用する。一般メディアのCT/MRI言及だけでは
    # 専門枠に入れず、一般ニュース側で扱う。
    if is_official(x.get('url', '')):
        return any(k.lower() in text for k in specialist_terms)

    return False


# Google News 経由だと URL が news.google.com になるため、配信元名でも公式情報を判定する。
OFFICIAL_SOURCE_NAMES = (
    '日本診療放射線技師会', 'jart',
    '日本放射線技術学会', 'jsrt',
    '日本医学放射線学会',
    '日本核医学会', '日本核医学技術学会',
    '日本放射線腫瘍学会',
    '日本医学物理学会',
    '日本磁気共鳴医学会',
    '厚生労働省', '原子力規制委員会',
    '医薬品医療機器総合機構', 'pmda',
    '日本医療機能評価機構',
    '日本消化器がん検診学会', '精中機構',
    '日本放射線腫瘍学会', '日本医学物理学会', '日本磁気共鳴医学会', '日本磁気共鳴専門技術者認定機構',
    '日本ivr学会', '日本超音波医学会', '日本核医学技術学会', '日本ct技術学会',
)

# 高: 自分の部署で確認・対応が必要になりうる情報
IMPORTANCE_HIGH_TERMS = (
    # 制度・報酬・法令
    '診療報酬', '報酬改定', '補助金', '法改正', '省令', '施行規則', '医療法',
    'タスクシフト', 'タスクシェア', '業務範囲', '指定規則',
    # 放射線安全
    '医療被ばく', '被ばく線量', '線量管理', '診断参考レベル', 'drl',
    # 薬剤・装置の供給と安全性
    '限定出荷', '出荷停止', '供給停止', '供給不足', '出荷調整',
    'リコール', '自主回収', '安全性情報', '添付文書改訂',
    # 医療事故の再発防止情報(医療機能評価機構・PMDAの医療安全情報など)
    '医療安全情報', '注意喚起', '再発防止', '医療事故',
    # 点数の変更
    '管理加算', '加算', '保険診療',
    # 会員・患者情報
    '個人情報漏えい', '個人情報漏洩', '不審アクセス', 'サイバー攻撃',
    # 指針
    'ガイドライン改訂', 'ガイドライン公表', 'ガイドラインを改訂', '指針改訂',
)

# 研修・講習会などの開催案内は「高」の語を含んでも「中」までにする
EVENT_TERMS = (
    '研修', '講習', 'セミナー', '講演会', '学術大会', '勉強会', 'ウェビナー',
    '開催', '開講', '募集', '参加者',
)

# 中: 国内の装置・AIの承認や導入
IMPORTANCE_MID_TERMS = (
    '薬事承認', '承認取得', '国内初', '日本初', '国内で初', '保険適用',
)

# 低: 業務への影響が小さい話題
IMPORTANCE_LOW_TERMS = (
    '逮捕', '停職', '懲戒', '書類送検', '不起訴',
    'ペット', '動物病院', '犬', '猫',
    '市場規模', '市場予測', '億米ドル', 'cagr',
    'ベトナム', 'vietnam', '韓国',
    '漫画', 'マンガ', 'インタビュー', '体験', 'フェア',
)


def is_official_source(x):
    src = str(x.get('source') or '').lower()
    return any(name.lower() in src for name in OFFICIAL_SOURCE_NAMES)


def importance(x, official):
    # 判定は見出しと要約だけで行う(配信元名に含まれる語で誤判定しないため)
    t = ' '.join(
        str(x.get(k) or '') for k in ('title', 'headline', 'description', 'summary')
    ).lower()
    official = official or is_official_source(x)

    def has(terms):
        return any(k.lower() in t for k in terms)

    if has(IMPORTANCE_LOW_TERMS) and not official:
        return '低'

    # 「画像診断ガイドライン2026年度版の全記事の公開」のように語が離れている場合も拾う
    guideline_release = re.search(r'(ガイドライン|指針).{0,30}(公開|公表|改訂|発刊|刊行)', t) \
        or (official and re.search(r'ガイドライン|指針|提言|勧告', t) and not re.search(r'研修|セミナー|講習|講演|募集|パブリックコメント|対応研修', t))
    # 学会・団体の声明は撮影手技の見直しなど実務に直結する
    official_statement = official and '声明' in t

    if has(IMPORTANCE_HIGH_TERMS) or guideline_release or official_statement:
        if has(EVENT_TERMS):
            return '中'
        return '高'

    if official:
        return '中'

    if has(IMPORTANCE_MID_TERMS):
        return '中'

    return '低'


# 記事ごとの一言(ポイント)。上から順に最初に当てはまったものを使う。
# どれにも当てはまらない記事は空欄にする(全記事に同じ定型文を付けない)。
TECHNOLOGIST_NOTES = (
    (('限定出荷', '出荷停止', '供給停止', '供給不足', '出荷調整'),
     '自施設で使っている薬剤か確認し、代替品や検査予定への影響を把握しておきましょう。'),
    (('リコール', '自主回収', '安全性情報', '添付文書改訂'),
     '自施設に該当する機器・薬剤がないか確認しておきましょう。'),
    (('個人情報漏えい', '個人情報漏洩', '不審アクセス'),
     '登録しているメールアドレスに不審なメールが届いていないか注意しましょう。'),
    (('サイバー攻撃', 'ランサムウェア'),
     'PACS・RISが止まったときに検査をどう続けるか、ダウンタイム時の手順を確認しておきましょう。'),
    (('医療安全情報', '注意喚起', '再発防止', '医療機能評価機構'),
     '自分の検査で同じ確認漏れが起きないか、問診やチェックの手順を見直すきっかけにしましょう。'),
    (('声明',),
     '撮影手技の見直しにつながる内容です。推奨が変わった点と根拠を確認しておきましょう。'),
    (('__guideline_release__',),
     '推奨内容の変更点を確認し、普段の撮影条件やプロトコルと照らし合わせておきましょう。'),
    (('診療報酬', '報酬改定', '施設基準', '加算', '保険診療'),
     '算定要件や点数の変更点を押さえておきましょう。担当する検査の算定に関わることがあります。'),
    (('告示研修',),
     '業務範囲の拡大に伴う告示研修です。未受講なら日程と申込方法を確認しておきましょう。'),
    (('パブリックコメント', 'パブコメ'),
     '意見募集の締切と、改訂される点を確認しておきましょう。'),
    (('原稿募集', '留学生', '候補者', '公募'),
     '応募条件と締切を確認しておきましょう。'),
    (('__event__',),
     '興味のある内容なら、開催日と申込期限を確認しておきましょう。'),
    (('法改正', '省令', '施行規則', '医療法', '指定規則', '業務範囲', 'タスクシフト', 'タスクシェア'),
     '自分の業務範囲や手順に関わる変更がないか確認しておきましょう。'),
    (('医療被ばく', '被ばく線量', '線量管理', '診断参考レベル', 'drl'),
     '線量管理やDRLとの比較の考え方を見直すきっかけになります。'),
    (('薬事承認', '承認取得', '国内初', '日本初', '国内で初', '保険適用'),
     '新しい装置・技術の動向として押さえておきましょう。'),
)


def technologist_note(x):
    """重要度「低」以外の記事に、判定理由に応じた一言を返す。"""
    if x.get('importance') == '低':
        return ''
    t = ' '.join(
        str(x.get(k) or '') for k in ('title', 'headline', 'description', 'summary')
    ).lower()
    flags = {
        '__guideline_release__': bool(re.search(r'(ガイドライン|指針).{0,30}(公開|公表|改訂|発刊|刊行)', t)
                                      or ((is_official(x.get('url', '')) or is_official_source(x))
                                          and re.search(r'ガイドライン|指針|提言|勧告', t)
                                          and not re.search(r'研修|セミナー|講習|講演|募集|パブリックコメント', t))),
        # 「開催報告」「開催遅延」「中止」は申込を促す案内ではない
        '__event__': any(k.lower() in t for k in EVENT_TERMS)
        and not any(k in t for k in ('報告', '遅延', '中止', '延期')),
    }
    for terms, note in TECHNOLOGIST_NOTES:
        if any(flags.get(k) if k in flags else k.lower() in t for k in terms):
            return note
    return ''


PREFECTURES = (
    '北海道', '青森', '岩手', '宮城', '秋田', '山形', '福島', '茨城', '栃木', '群馬', '埼玉', '千葉', '東京', '神奈川',
    '新潟', '富山', '石川', '福井', '山梨', '長野', '岐阜', '静岡', '愛知', '三重', '滋賀', '京都', '大阪', '兵庫',
    '奈良', '和歌山', '鳥取', '島根', '岡山', '広島', '山口', '徳島', '香川', '愛媛', '高知', '福岡', '佐賀', '長崎',
    '熊本', '大分', '宮崎', '鹿児島', '沖縄',
)
_DATE_YMD = re.compile(r'(?<!\d)(20\d{2})/(\d{1,2})/(\d{1,2})(?!\d)')
_DATE_MD = re.compile(r'(?<!\d)(\d{1,2})月(\d{1,2})日')
_NOT_EVENT_AFTER = re.compile(r'^\s*(\d{1,2}[:：]\d{2}\s*)?(更新|追記|掲載|発売|付)')


def _to_date(y, m, d):
    try:
        return datetime(int(y), int(m), int(d)).date()
    except ValueError:
        return None


def extract_schedule(x):
    """研修・講習会の案内から開催日(または申込締切)と開催地を取り出す。

    戻り値: {'event_date': 'YYYY-MM-DD', 'event_kind': '開催'|'申込締切', 'event_place': str} または {}
    """
    head = str(x.get('headline') or x.get('title') or '')
    text = head + ' ' + str(x.get('summary') or '')
    low = text.lower()
    if not (any(k.lower() in low for k in EVENT_TERMS) or '告示研修' in text):
        return {}
    if any(k in text for k in ('報告', '中止', '延期', '遅延')):
        return {}
    try:
        base = datetime.fromisoformat(str(x.get('date'))[:10]).date()
    except ValueError:
        base = datetime.now(JST).date()

    def md_date(m, d):
        dt = _to_date(base.year, m, d)
        if dt and (base - dt).days > 60:      # 「1月9日」が年明けを指す場合
            dt = _to_date(base.year + 1, m, d)
        return dt

    found = None
    # 申込締切: 「申込は10月1日正午～11月26日正午」のように範囲の終わりを使う
    m = re.search(r'(申込|申し込み|受付|締切|〆切)[^。]{0,30}?[～〜\-－]\s*(\d{1,2})月(\d{1,2})日', text) \
        or re.search(r'(申込|申し込み|受付)(締切|期限)[はが：:\s]*(\d{1,2})月(\d{1,2})日', text)
    if m:
        mm, dd = m.groups()[-2:]
        dt = md_date(mm, dd)
        if dt:
            found = (dt, '申込締切')
    if not found:
        head_wo_prefix = re.sub(r'^\s*\d{4}/\d{1,2}/\d{1,2}\s+(お知らせ|会告/告示|会告|告示)', '', head)
        for pat, conv in ((_DATE_YMD, lambda g: _to_date(*g)), (_DATE_MD, lambda g: md_date(*g))):
            for mt in pat.finditer(head_wo_prefix):
                if _NOT_EVENT_AFTER.match(head_wo_prefix[mt.end():]):
                    continue
                dt = conv(mt.groups())
                if dt:
                    found = (dt, '開催')
                    break
            if found:
                break
    if not found:
        return {}
    place = ''
    for pref in PREFECTURES:
        if pref in head:
            place = pref
            break
    if not place and re.search(r'web|ウェブ|オンライン|eラーニング|e-ラーニング|ウェビナー', low):
        place = 'オンライン'
    return {'event_date': found[0].isoformat(), 'event_kind': found[1], 'event_place': place}


def clean_summary(x):
    """見出しをそのまま繰り返しているだけの要約は空にする。"""
    summary = str(x.get('summary') or '').strip()
    source = str(x.get('source') or '').strip()
    if source and summary.endswith(source):
        summary_wo_source = summary[:-len(source)].strip()
    else:
        summary_wo_source = summary
    head = canonical_title(x.get('headline') or x.get('title'))
    if canonical_title(summary_wo_source) == head:
        return ''
    body = canonical_title(re.sub(r'\s+\S+$', '', summary))  # 末尾の媒体名を除く
    if not summary or same_story(head, canonical_title(summary)) or same_story(head, body):
        return ''
    return summary


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


def archive_items(items):
    """news.json から外れる記事を archive/YYYY-MM.json に追記し、月の一覧を更新する。"""
    if not items:
        return
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    by_month = {}
    for x in items:
        month = str(feed_date(x) or x.get('date') or '')[:7]
        if re.fullmatch(r'20\d{2}-\d{2}', month):
            by_month.setdefault(month, []).append(x)
    for month, new in by_month.items():
        path = ARCHIVE_DIR / f'{month}.json'
        try:
            old = json.loads(path.read_text(encoding='utf-8'))
        except Exception:
            old = []
        urls = {x.get('url') for x in old}
        merged = old + [x for x in new if x.get('url') not in urls]
        merged.sort(key=lambda x: str(feed_date(x) or ''), reverse=True)
        path.write_text(json.dumps(merged, ensure_ascii=False, indent=1), encoding='utf-8')
    write_archive_index()


def write_archive_index():
    months = []
    for path in sorted(ARCHIVE_DIR.glob('20??-??.json'), reverse=True):
        try:
            months.append({'month': path.stem, 'count': len(json.loads(path.read_text(encoding='utf-8')))})
        except Exception:
            continue
    (ARCHIVE_DIR / 'index.json').write_text(json.dumps({'months': months}, ensure_ascii=False, indent=1), encoding='utf-8')


SITE_URL = 'https://hijiki-no-kokoro.github.io/radiology-technologist-news/'


def build_notice(items):
    """要確認の新着をメール本文にする。"""
    lines = [f'今日の要確認が{len(items)}件あります。', '']
    for x in items:
        lines.append('■ ' + str(x.get('headline') or ''))
        if x.get('why'):
            lines.append('  ポイント: ' + x['why'])
        lines.append('  ' + str(x.get('source') or '') + '  ' + str(x.get('url') or ''))
        lines.append('')
    lines.append('一覧: ' + SITE_URL)
    subject = f'【技師ニュース】要確認 {len(items)}件: ' + str(items[0].get('headline') or '')[:40]
    return subject, '\n'.join(lines)


def notify_high(items):
    """新しく入った要確認を Gmail で自分宛てに知らせる。

    GitHub の Secrets に GMAIL_USER と GMAIL_APP_PASSWORD を登録したときだけ動く
    (NOTIFY_TO を登録すると宛先を変えられる。未登録なら GMAIL_USER 宛て)。
    """
    user, password = os.environ.get('GMAIL_USER'), os.environ.get('GMAIL_APP_PASSWORD')
    if not items:
        return 'no-items'
    if not (user and password):
        print('Mail notice skipped: GMAIL_USER / GMAIL_APP_PASSWORD not set')
        return 'not-configured'
    to = os.environ.get('NOTIFY_TO') or user
    subject, body = build_notice(items)
    msg = MIMEText(body, 'plain', 'utf-8')
    msg['Subject'], msg['From'], msg['To'] = subject, user, to
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465, timeout=30) as smtp:
            smtp.login(user, password.replace(' ', ''))
            smtp.send_message(msg)
        print(f'Mail notice sent: {len(items)} items')
        return 'sent'
    except Exception as e:
        print('Mail notice error:', e)
        return 'error'


def load():
    try:
        return json.loads(
            NEWS_JSON.read_text(
                encoding='utf-8'
            )
        )
    except Exception:
        return []


def apply_curated_specialist(item):
    """Apply editor-reviewed detail without replacing the original source URL."""
    title = str(item.get('headline') or item.get('title') or '')
    for needle, metadata in CURATED_SPECIALIST:
        if needle in title:
            item.update(metadata)
            item['track'] = 'official'
            break
    return item


def canonical_title(title):
    """Collapse duplicate titles that differ only by outlet name or decoration.

    Google News titles end with " - 媒体名", syndicated copies add "【画像】" or
    "(東海テレビ)", and JART's own list prefixes "2026/10/19 お知らせ".
    """
    t = str(title or '').strip()
    t = re.sub(r'\s+-\s+[^-]{1,40}$', '', t)                      # " - ライブドアニュース"
    # "(東海テレビ)" "（PR TIMES）" のような媒体名だけを外す。
    # "（2026/10/14更新）" "（第3部）" のように記事を区別する括弧は残す。
    m = re.search(r'\s*[\(（]([^()（）]{1,20})[\)）]\s*$', t)
    if m and not re.search(r'[0-9０-９第部章編回版号更新]', m.group(1)):
        t = t[:m.start()]
    t = re.sub(r'\s*\d+枚目/全\d+枚.*$', '', t)                    # "3枚目/全44枚 1448871"
    t = re.sub(r'^\s*(?:【[^】]{1,30}】|［[^］]{1,10}］|\[[^\]]{1,10}\])\s*', '', t)   # 【画像】【JIRA…】［案内板］［お知らせ］
    t = re.sub(r'^\s*\d{4}/\d{1,2}/\d{1,2}\s+(?:お知らせ|会告/告示|会告|告示)?\s*', '', t)
    return norm(t)


MIN_PREFIX_MATCH = 24


def same_story(a, b):
    """True when two canonical titles are the same story (one may be truncated)."""
    if not a or not b:
        return False
    if a == b:
        return True
    short, long_ = sorted((a, b), key=len)
    return len(short) >= MIN_PREFIX_MATCH and long_.startswith(short)


def find_story(key, kept):
    """Return the already-kept item whose title is the same story as key."""
    for k, item in kept:
        if same_story(key, k):
            return item
    return None


def merge_duplicate(keep, dup):
    """Record a duplicate's outlet on the kept item instead of discarding it."""
    also = keep.setdefault('also', [])
    urls = {keep.get('url')} | {a.get('url') for a in also}
    for entry in [{'source': dup.get('source'), 'url': dup.get('url')}] + list(dup.get('also') or []):
        if entry.get('url') and entry['url'] not in urls:
            also.append({'source': entry.get('source') or dom(entry['url']), 'url': entry['url']})
            urls.add(entry['url'])
    if not also:
        keep.pop('also', None)


def clean_db(db):
    today = datetime.now(JST).date()
    out = []
    kept = []  # (canonical title, item)
    seen_urls = set()

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

        x = apply_curated_specialist(x)
        k = canonical_title(x.get('headline'))

        if not k and not x.get('url'):
            continue

        if x.get('url') in seen_urls:
            continue

        # 同じ記事の別媒体版は捨てずに、残す1件の「他の配信元」に記録する。
        original = find_story(k, kept) if k else None
        if original is not None:
            merge_duplicate(original, x)
            seen_urls.add(x.get('url'))
            continue

        seen_urls.add(x.get('url'))
        seen_urls.update(a.get('url') for a in x.get('also') or [])
        kept.append((k, x))

        # 分類ルールの改善を過去分にも反映する(手動指定のカテゴリは後で上書きされる)
        x['category'] = category(x)
        # 専門学会の記事は、一般的な分類なら学会の分野にそろえる
        if x['category'] in ('その他', '学術', '教育', '制度') and normalize_source(x.get('source')) in SPECIALTY_DEFAULT_CATEGORY:
            x['category'] = SPECIALTY_DEFAULT_CATEGORY[normalize_source(x.get('source'))]
        x['importance'] = importance(
            x,
            is_official(x.get('url', '')) or x.get('source') == 'JART'
        )
        x['summary'] = clean_summary(x)
        x['why'] = technologist_note(x)
        for k in ('event_date', 'event_kind', 'event_place'):
            x.pop(k, None)
        x.update(extract_schedule(x))

        # 過去データも現行の選定基準で再分類し、表示のズレを残さない。
        # 重要度「高」は業務に直結するので、一般メディア発でも専門ニュース側に出す
        x['track'] = (
            'official'
            if is_specialist(x) or x.get('importance') == '高'
            else 'general'
        )

        out.append(normalize_sources(apply_curated_specialist(x)))

    return out


def make_item(x):
    official = (
        is_official(x.get('url', ''))
        or x.get('source') == 'JART'
    )

    item = {
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
        'why': '',
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
    item['summary'] = clean_summary(item)
    item['why'] = technologist_note(item)
    item.update(extract_schedule(item))
    return normalize_sources(apply_curated_specialist(item))


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

    known_titles = [canonical_title(x.get('headline')) for x in db]
    known_urls = {x.get('url') for x in db}
    for x in db:
        known_urls.update(a.get('url') for a in x.get('also') or [])

    def is_known(item):
        if item['url'] in known_urls:
            return True
        k = canonical_title(item['title'])
        return any(same_story(k, t) for t in known_titles)

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

        if not is_known(x):
            candidates[x['url']] = x

    # 医療安全情報(新しい号だけ。既にある号は is_known で除く)
    safety_new = [x for x in direct_safety_info() if not is_known(x)]
    # 学会・厚労省の新着(Googleニュースの件数枠とは別に入れる)
    official_new = [x for x in direct_official_news() if not is_known(x)]

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

                if not is_known(x):
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

    # 医療安全情報・学会・厚労省の新着は件数枠とは別に必ず載せる
    for x in safety_new + official_new:
        item = make_item(x)
        item['track'] = 'official'
        added.append(item)
        specialist_titles.add(canonical_title(x['title']))

    for x in specialist:
        if len(specialist_titles) >= 5:
            break
        k = canonical_title(x['title'])

        if not k or any(same_story(k, t) for t in specialist_titles):
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

    for x in general:
        if len(general_titles) >= 5:
            break
        k = canonical_title(x['title'])

        if not k or any(same_story(k, t) for t in specialist_titles | general_titles):
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

    # 上限を超えた古い記事は消さずに月別アーカイブへ移す
    archive_items(final[MAX_RECENT:])
    final = final[:MAX_RECENT]
    NEWS_JSON.write_text(
        json.dumps(final, ensure_ascii=False, indent=2),
        encoding='utf-8'
    )

    update_seminars()

    # 今回新しく入った記事のうち、毎日の整理を通って「高」になったものだけ知らせる
    added_urls = {x['url'] for x in added}
    new_high = [x for x in final if x.get('url') in added_urls and x.get('importance') == '高']
    SOURCE_STATUS['メール通知'] = {'result': notify_high(new_high), 'items': len(new_high)}

    META_JSON.write_text(
        json.dumps({
            'checked_at': datetime.now(JST).isoformat(timespec='minutes'),
            'added': len(added),
            'total': len(final),
            'sources': SOURCE_STATUS,
        }, ensure_ascii=False, indent=2),
        encoding='utf-8'
    )

    HTML_DIR.mkdir(parents=True, exist_ok=True)
    today_str = datetime.now(JST).date().isoformat()
    (HTML_DIR / f'放射線技師ニュース_{today_str}.html').write_text(
        build_daily_html(final, today_str),
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
