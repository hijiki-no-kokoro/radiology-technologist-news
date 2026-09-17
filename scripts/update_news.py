import json, os, re, xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path
from urllib.parse import quote, urljoin
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parents[1]
NEWS_JSON=ROOT/'news.json'

QUERIES=[
 '診療放射線技師 OR 放射線技師 OR 放射線部',
 '放射線診療 CT MRI FPD',
 '放射線 被ばく 線量管理 安全管理',
 '核医学 SPECT PET 放射線技師',
 '放射線 AI 画像診断 読影支援',
 '診療報酬 放射線 画像診断 補助金',
 'site:jart.jp 診療放射線技師',
 'site:jsrt.or.jp 放射線技師 OR 放射線技術',
 'site:radiology.jp 診療放射線技師 OR 放射線',
 'site:jsnm.org 核医学 放射線技師',
 'site:jastro.or.jp 放射線治療 放射線技師',
 'site:mhlw.go.jp 診療放射線技師 放射線',
 'site:pmda.go.jp 放射線 CT MRI 医療機器',
]

OFFICIAL=('jart.jp','jsrt.or.jp','jrs.or.jp','radiology.jp','jsnm.org','jastro.or.jp','mhlw.go.jp','nra.go.jp','pmda.go.jp','mext.go.jp','fda.gov','iaea.org','who.int','canon-medical.co.jp','fujifilm.com','gehealthcare.co.jp','siemens-healthineers.com','philips.co.jp')
CATEGORIES=('制度','職能','学術','AI','CT','MRI','一般撮影','安全管理','核医学','放射線治療','教育','診療報酬・補助金','その他')


def fetch(url):
    r=Request(url,headers={'User-Agent':'Mozilla/5.0 radiology-technologist-news'})
    return urlopen(r,timeout=30).read().decode('utf-8','ignore')


def rss(q):
    root=ET.fromstring(fetch('https://news.google.com/rss/search?q='+quote(q+' when:2d')+'&hl=ja&gl=JP&ceid=JP:ja'))
    out=[]
    for it in root.findall('./channel/item'):
        title=unescape(it.findtext('title',''))
        link=it.findtext('link','')
        desc=unescape(re.sub('<[^>]+>',' ',it.findtext('description','')))
        pub=it.findtext('pubDate','')
        se=it.find('source')
        src=se.text if se is not None else ''
        try: dt=parsedate_to_datetime(pub).astimezone(timezone.utc)
        except Exception: dt=datetime.now(timezone.utc)
        if title and link:
            out.append({'title':title,'url':link,'description':desc[:700],'source':src,'published':dt.isoformat()})
    return out


def direct_official():
    """公式サイトを直接読む。Google Newsの索引遅延に依存しない。"""
    out=[]
    now=datetime.now(timezone.utc).isoformat()

    # JARTトップには「本会からのお知らせ」が掲載されるため、日付＋リンク周辺を直接抽出。
    try:
        html=fetch('https://www.jart.jp/')
        for m in re.finditer(r'<a[^>]+href=["\'](?P<href>[^"\']+)["\'][^>]*>\s*(?P<title>.*?)\s*</a>',html,re.I|re.S):
            title=' '.join(re.sub(r'<[^>]+>',' ',m.group('title')).split())
            if not title or not any(k in title for k in ('STAT','告示研修','アンケート','研修','セミナー','学術大会','お知らせ')):
                continue
            href=urljoin('https://www.jart.jp/',m.group('href'))
            before=html[max(0,m.start()-800):m.start()]
            dm=re.search(r'(20\d{2})[/.年](\d{1,2})[/.月](\d{1,2})',re.sub(r'<[^>]+>',' ',before))
            date=f'{dm.group(1)}-{int(dm.group(2)):02d}-{int(dm.group(3)):02d}' if dm else now[:10]
            out.append({'title':title,'url':href,'description':title,'source':'JART','published':date+'T00:00:00+09:00'})
    except Exception as e:
        print('JART direct error:',e)

    # JART生涯教育・告示研修ページも直接取得。更新日がGoogle Newsに載らない場合を補完。
    for url in ('https://www.jart.jp/activity/lifelong-study','https://www.jart.jp/activity/lifelong-study/notification-training'):
        try:
            html=fetch(url)
            for m in re.finditer(r'<a[^>]+href=["\'](?P<href>[^"\']+)["\'][^>]*>\s*(?P<title>.*?)\s*</a>',html,re.I|re.S):
                title=' '.join(re.sub(r'<[^>]+>',' ',m.group('title')).split())
                if not title or not any(k in title for k in ('STAT','告示研修','研修','セミナー')):
                    continue
                href=urljoin(url,m.group('href'))
                out.append({'title':title,'url':href,'description':title,'source':'JART','published':now})
        except Exception as e:
            print('JART page error:',e)

    # 厚労省「過去の新着情報」は日付ごとにまとまっているので、放射線関連だけを直接抽出。
    try:
        html=fetch('https://www.mhlw.go.jp/stf/new-info/')
        clean=re.sub(r'<script.*?</script>|<style.*?</style>',' ',html,flags=re.I|re.S)
        clean=re.sub(r'<[^>]+>',' ',clean)
        clean=' '.join(unescape(clean).split())
        relevant_terms=('診療放射線技師','放射線技師','放射線','医療機器','診療報酬','医療安全','線量','国家試験')
        if any(k in clean for k in relevant_terms):
            # 個別リンクはHTML側から取得
            for m in re.finditer(r'<a[^>]+href=["\'](?P<href>[^"\']+)["\'][^>]*>\s*(?P<title>.*?)\s*</a>',html,re.I|re.S):
                title=' '.join(re.sub(r'<[^>]+>',' ',m.group('title')).split())
                if not title or not any(k in title for k in relevant_terms):
                    continue
                href=urljoin('https://www.mhlw.go.jp/stf/new-info/',m.group('href'))
                out.append({'title':title,'url':href,'description':title,'source':'厚生労働省','published':now})
    except Exception as e:
        print('MHLW direct error:',e)

    return out


def norm(s):
    return re.sub(r'[^0-9a-zぁ-んァ-ヶ一-龠]','',str(s or '').lower())


def dom(url):
    m=re.search(r'https?://([^/]+)',url or '')
    return m.group(1).lower().replace('www.','') if m else ''


def is_official(url):
    d=dom(url)
    return any(d==z or d.endswith('.'+z) for z in OFFICIAL)


def relevant(x):
    text=(x.get('title','')+' '+x.get('description','')+' '+x.get('source','')).lower()
    bad=('漫画','マンガ','芸能','俳優','女優','アイドル','タレント','画像集','写真集','昭和あるある','グラビア')
    good=('診療放射線技師','放射線技師','放射線部','放射線科','CT','MRI','FPD','一般撮影','マンモグラフィ','核医学','SPECT','PET','放射線治療','線量','被ばく','AI','画像診断','読影','STAT','診療報酬','補助金','国家試験','研修','認定','医療機器','装置更新','タスクシフト','タスクシェア')
    return not any(k.lower() in text for k in bad) and any(k.lower() in text for k in good)


def category(x):
    t=(x.get('title','')+' '+x.get('description','')+' '+x.get('source','')).lower()
    rules=[
      ('診療報酬・補助金',('診療報酬','補助金','助成金','加算')),
      ('安全管理',('安全管理','安全','被ばく','線量管理','線量')),
      ('一般撮影',('一般撮影','FPD','マンモグラフィ','X線撮影')),
      ('CT',('CT','computed tomography')),
      ('MRI',('MRI','magnetic resonance')),
      ('核医学',('核医学','SPECT','PET','MIBG','DAT','RI')),
      ('放射線治療',('放射線治療','リニアック','陽子線','粒子線','IGRT')),
      ('教育',('教育','国家試験','研修','認定','セミナー','講習')),
      ('AI',('AI','人工知能','画像診断支援','読影支援')),
      ('学術',('学術','研究','学会','ガイドライン','パブリックコメント')),
      ('制度',('制度','養成','確保','厚生労働省','医政')),
      ('職能',('職能','タスクシフト','タスクシェア','業務範囲')),
    ]
    for cat,terms in rules:
        if any(k.lower() in t for k in terms): return cat
    return 'その他'


def importance(x, official):
    t=(x.get('title','')+' '+x.get('description','')).lower()
    high=('制度変更','診療報酬','補助金','安全管理','被ばく','線量管理','装置更新','人員','養成','確保','AI導入','タスクシフト','タスクシェア','ガイドライン','業務範囲','STAT','告示研修')
    if any(k.lower() in t for k in high): return '高'
    if official: return '中'
    return '低'


def load():
    try: return json.loads(NEWS_JSON.read_text(encoding='utf-8'))
    except Exception: return []


def main():
    now=datetime.now(timezone.utc)
    cutoff=now-timedelta(hours=30)
    db=load()
    seen={norm(x.get('headline')) or x.get('url') for x in db}
    candidates={}

    # まず公式サイトを直接取得。Google News側の索引遅延を回避する。
    for x in direct_official():
        try:
            dt=datetime.fromisoformat(x['published'].replace('Z','+00:00'))
            if dt < cutoff: continue
        except Exception: pass
        if not relevant(x): continue
        k=norm(x['title']) or x['url']
        if k not in seen: candidates[x['url']]=x

    # 一般ニュース＋公式サイトのGoogle News索引も補完として使用。
    for q in QUERIES:
        try:
            for x in rss(q):
                if x['published'] < cutoff.isoformat() or not relevant(x): continue
                k=norm(x['title']) or x['url']
                if k in seen: continue
                candidates[x['url']]=x
        except Exception as e:
            print('RSS error:',e)

    fresh=sorted(candidates.values(),key=lambda x:(is_official(x['url']),x['published']),reverse=True)
    added=[]; added_titles=set()
    for x in fresh[:50]:
        k=norm(x['title'])
        if not k or k in added_titles: continue
        added_titles.add(k)
        official=is_official(x['url']) or x.get('source') in ('JART','厚生労働省')
        cat=category(x)
        added.append({
          'date':x['published'][:10],
          'category':cat,
          'importance':importance(x,official),
          'headline':x['title'],
          'summary':re.sub(r'\s+',' ',x.get('description','')).strip()[:220],
          'why':'公式情報のため、放射線部門の運用・教育・制度への影響を確認する価値があります。' if official else '放射線部門の実務への影響を確認する価値があります。',
          'source':x.get('source') or dom(x['url']),
          'url':x['url'],
          'track':'official' if official else 'general'
        })

    db += added
    final=[]; seen=set()
    for x in sorted(db,key=lambda z:(z.get('date',''),{'高':3,'中':2,'低':1}.get(z.get('importance'),0)),reverse=True):
        k=norm(x.get('headline')) or x.get('url')
        if not k or k in seen: continue
        seen.add(k)
        x['category']=x.get('category') if x.get('category') in CATEGORIES else category(x)
        if 'track' not in x: x['track']='official' if is_official(x.get('url','')) else 'general'
        final.append(x)

    NEWS_JSON.write_text(json.dumps(final[:200],ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'Added {len(added)} new items; database now has {len(final[:200])} items.')
    for x in added[:15]: print(x['date'],x['track'],x['category'],x['headline'])

if __name__=='__main__': main()
