import json, re, xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path
from urllib.parse import quote, urljoin
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parents[1]
NEWS_JSON=ROOT/'news.json'
JST=timezone(timedelta(hours=9))
QUERIES=['"診療放射線技師" OR "放射線技師"','"放射線部" CT MRI FPD','"放射線" 被ばく 線量管理 安全管理','核医学 SPECT PET "放射線技師"','放射線 AI 画像診断 読影支援','診療報酬 放射線 画像診断 補助金','site:jart.jp "診療放射線技師"','site:jsrt.or.jp "診療放射線技師" OR "放射線技術"','site:radiology.jp "診療放射線技師" OR "放射線"','site:jsnm.org 核医学 "放射線技師"','site:jastro.or.jp 放射線治療 "放射線技師"','site:mhlw.go.jp "診療放射線技師" 放射線','site:pmda.go.jp 放射線 CT MRI 医療機器']
OFFICIAL=('jart.jp','jsrt.or.jp','jrs.or.jp','radiology.jp','jsnm.org','jastro.or.jp','mhlw.go.jp','nra.go.jp','pmda.go.jp','mext.go.jp')
CATEGORIES=('制度','職能','学術','AI','CT','MRI','一般撮影','安全管理','核医学','放射線治療','教育','診療報酬・補助金','その他')
TARGET_TERMS=('診療放射線技師','放射線技師','放射線部','放射線科','放射線診療','CT','MRI','FPD','一般撮影','マンモグラフィ','核医学','SPECT','PET','放射線治療','被ばく','線量管理','画像診断','読影','STAT','X線撮影','タスクシフト','タスクシェア','放射線安全')
OTHER_JOBS=('作業療法士','理学療法士','言語聴覚士','視能訓練士','臨床工学技士','臨床検査技師','歯科衛生士','歯科技工士','薬剤師','看護師','保健師','助産師','介護福祉士','社会福祉士','精神保健福祉士','柔道整復師','あん摩マッサージ指圧師','はり師','きゅう師','義肢装具士')
BAD_TERMS=('漫画','マンガ','芸能','俳優','女優','アイドル','タレント','グラビア','写真集','求人','転職','保険')

def fetch(url):
    return urlopen(Request(url,headers={'User-Agent':'Mozilla/5.0 radiology-technologist-news'}),timeout=30).read().decode('utf-8','ignore')

def clean_html(s): return ' '.join(unescape(re.sub(r'<[^>]+>',' ',s or '')).split())

def rss(q):
    root=ET.fromstring(fetch('https://news.google.com/rss/search?q='+quote(q+' when:1d')+'&hl=ja&gl=JP&ceid=JP:ja'))
    out=[]
    for it in root.findall('./channel/item'):
        try: dt=parsedate_to_datetime(it.findtext('pubDate','')).astimezone(JST)
        except Exception: continue
        title=unescape(it.findtext('title','')); link=it.findtext('link',''); desc=clean_html(it.findtext('description',''))[:700]; se=it.find('source'); src=se.text if se is not None else ''
        if title and link: out.append({'title':title,'url':link,'description':desc,'source':src,'published':dt.isoformat()})
    return out

def norm(s): return re.sub(r'[^0-9a-zぁ-んァ-ヶ一-龠]','',str(s or '').lower())
def dom(url):
    m=re.search(r'https?://([^/]+)',url or ''); return m.group(1).lower().replace('www.','') if m else ''
def is_official(url):
    d=dom(url); return any(d==z or d.endswith('.'+z) for z in OFFICIAL)

def relevant(x):
    text=(x.get('title','')+' '+x.get('description','')+' '+x.get('source','')).lower()
    if any(k.lower() in text for k in OTHER_JOBS) or any(k.lower() in text for k in BAD_TERMS): return False
    # 「国家試験」「研修」「AI」「医療機器」など一般語だけでは採用しない。
    return any(k.lower() in text for k in TARGET_TERMS)

def is_news_item(x):
    url=x.get('url',''); title=x.get('title','').strip()
    # JARTの固定案内・研修一覧・ナビゲーションを除外。
    if '/activity/lifelong-study' in url: return False
    if '/seminar/' in url: return False
    if title in ('日本診療放射線技師会誌JART','みんなに知ってもらいたい診療放射線技師のこと','日本診療放射線技師会について','都道府県診療放射線技師会・放射線技師会','活動紹介','会誌・投稿','一般向け情報','技師会概要','医療被ばく個別相談センター'): return False
    if '受付期間：' in title or '開催日：' in title: return False
    return True

def parse_nearby_date(html,pos):
    block=clean_html(html[max(0,pos-1800):pos]); dates=re.findall(r'(20\d{2})[/.年](\d{1,2})[/.月](\d{1,2})',block)
    if dates:
        y,m,d=dates[-1]; return f'{y}-{int(m):02d}-{int(d):02d}T00:00:00+09:00'
    return None

def direct_jart():
    out=[]; now=datetime.now(JST).isoformat()
    try:
        html=fetch('https://www.jart.jp/')
        for m in re.finditer(r'<a[^>]+href=["\'](?P<href>[^"\']+)["\'][^>]*>\s*(?P<title>.*?)\s*</a>',html,re.I|re.S):
            title=clean_html(m.group('title')); href=urljoin('https://www.jart.jp/',m.group('href'))
            if not title or '/news/info/' not in href.lower(): continue
            date=parse_nearby_date(html,m.start())
            if not date: continue
            item={'title':title,'url':href,'description':title,'source':'JART','published':date}
            if relevant(item) and is_news_item(item): out.append(item)
    except Exception as e: print('JART direct error:',e)
    return out

def category(x):
    t=(x.get('title','')+' '+x.get('description','')).lower()
    rules=[('診療報酬・補助金',('診療報酬','補助金','助成金','加算')),('安全管理',('安全管理','安全','被ばく','線量管理','医療被ばく','線量','放射線安全')),('一般撮影',('一般撮影','FPD','マンモグラフィ','X線撮影')),('CT',('CT','computed tomography')),('MRI',('MRI','magnetic resonance')),('核医学',('核医学','SPECT','PET','MIBG','DAT','RI')),('放射線治療',('放射線治療','リニアック','陽子線','粒子線','IGRT')),('AI',('AI','人工知能','画像診断支援','読影支援')),('教育',('教育','国家試験','研修','認定','セミナー','講習')),('学術',('学術','研究','学会','ガイドライン','パブリックコメント')),('職能',('STAT','タスクシフト','タスクシェア','業務範囲','職能')),('制度',('制度','養成','確保','厚生労働省','医政'))]
    for cat,terms in rules:
        if any(k.lower() in t for k in terms): return cat
    return 'その他'

def importance(x,official):
    t=(x.get('title','')+' '+x.get('description','')).lower()
    if any(k.lower() in t for k in ('診療報酬','補助金','安全管理','被ばく','線量管理','装置更新','タスクシフト','タスクシェア','業務範囲','STAT')): return '高'
    if official: return '中'
    return '低'

def load():
    try: return json.loads(NEWS_JSON.read_text(encoding='utf-8'))
    except Exception: return []

def clean_db(db):
    today=datetime.now(JST).date(); out=[]; seen=set()
    for x in db:
        try:
            d=datetime.fromisoformat(str(x.get('date','')).replace('Z','+00:00')).date()
            if d>today: continue
        except Exception: continue
        if not relevant(x) or not is_news_item(x): continue
        k=norm(x.get('headline')) or x.get('url')
        if not k or k in seen: continue
        seen.add(k); x['category']=x.get('category') if x.get('category') in CATEGORIES else category(x); x['track']=x.get('track') or ('official' if is_official(x.get('url','')) else 'general'); out.append(x)
    return out

def main():
    now=datetime.now(JST); cutoff=now-timedelta(hours=26); db=clean_db(load()); seen={norm(x.get('headline')) or x.get('url') for x in db}; candidates={}
    for x in direct_jart():
        try: dt=datetime.fromisoformat(x['published'])
        except Exception: continue
        if dt>=cutoff and relevant(x) and is_news_item(x):
            k=norm(x['title']) or x['url']
            if k not in seen: candidates[x['url']]=x
    for q in QUERIES:
        try:
            for x in rss(q):
                if datetime.fromisoformat(x['published'])<cutoff or not relevant(x) or not is_news_item(x): continue
                k=norm(x['title']) or x['url']
                if k not in seen: candidates[x['url']]=x
        except Exception as e: print('RSS error:',e)
    def score(x):
        t=(x.get('title','')+' '+x.get('description','')).lower(); s=0
        if any(k.lower() in t for k in ('診療放射線技師','放射線技師','放射線部','診療用放射線')): s+=10
        if is_official(x.get('url','')) or x.get('source')=='JART': s+=4
        if any(k.lower() in t for k in ('制度','診療報酬','補助金','安全管理','被ばく','線量管理','装置更新','タスクシフト','タスクシェア')): s+=4
        if any(k.lower() in t for k in ('CT','MRI','FPD','SPECT','PET','マンモグラフィ','放射線治療','画像診断','AI')): s+=2
        return s
    fresh=sorted(candidates.values(),key=lambda x:(score(x),x.get('published','')),reverse=True); added=[]; titles=set()
    for x in fresh[:8]:
        k=norm(x['title'])
        if not k or k in titles: continue
        titles.add(k); official=is_official(x['url']) or x.get('source')=='JART'
        added.append({'date':x['published'][:10],'category':category(x),'importance':importance(x,official),'headline':x['title'],'summary':re.sub(r'\s+',' ',x.get('description','')).strip()[:220],'why':'公式情報のため、放射線部門の運用・教育・制度への影響を確認する価値があります。' if official else '放射線部門の実務への影響を確認する価値があります。','source':x.get('source') or dom(x['url']),'url':x['url'],'track':'official' if official else 'general'})
    final=clean_db(added+db); NEWS_JSON.write_text(json.dumps(final[:200],ensure_ascii=False,indent=2),encoding='utf-8'); print(f'Added {len(added)} new items; database now has {len(final[:200])} items.'); [print(x['date'],x['track'],x['category'],x['headline']) for x in added]

if __name__=='__main__': main()
