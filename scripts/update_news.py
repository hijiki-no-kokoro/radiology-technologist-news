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
QUERIES=['"診療放射線技師" OR "放射線技師"','"放射線部" CT MRI FPD','"放射線" 被ばく 線量管理 安全管理','核医学 SPECT PET "放射線技師"','放射線 AI 画像診断 読影支援','診療報酬 放射線 画像診断 補助金','CT MRI 医療 画像診断 放射線','医用画像 AI CT MRI 病院','放射線 医療機器 CT MRI 最新','site:jart.jp "診療放射線技師"','site:jsrt.or.jp "診療放射線技師" OR "放射線技術"','site:radiology.jp "診療放射線技師" OR "放射線"','site:jsnm.org 核医学 "放射線技師"','site:jastro.or.jp 放射線治療 "放射線技師"','site:mhlw.go.jp "診療放射線技師" 放射線','site:pmda.go.jp 放射線 CT MRI 医療機器']
OFFICIAL=('jart.jp','jsrt.or.jp','jrs.or.jp','radiology.jp','jsnm.org','jastro.or.jp','mhlw.go.jp','nra.go.jp','pmda.go.jp','mext.go.jp')
CATEGORIES=('制度','職能','学術','AI','CT','MRI','一般撮影','安全管理','核医学','放射線治療','教育','診療報酬・補助金','その他')
DIRECT_TERMS=('診療放射線技師','放射線技師','放射線部','放射線科','診療用放射線')
STRONG_MODALITY_TERMS=('CT','MRI','FPD','一般撮影','マンモグラフィ','核医学','SPECT','PET','放射線治療','被ばく','線量管理','画像診断AI','画像診断支援','読影支援','STAT','X線撮影','タスクシフト','タスクシェア','放射線安全')
BROAD_MODALITY_TERMS=('画像診断','読影','医用画像','放射線','医療画像')
BAD_TERMS=('漫画','マンガ','芸能','俳優','女優','アイドル','タレント','グラビア','写真集','求人','転職','保険')
NOISE_TITLE_TERMS=('受付期間：','開催日：','会誌・投稿','活動紹介','技師会概要')

def fetch(url): return urlopen(Request(url,headers={'User-Agent':'Mozilla/5.0 radiology-technologist-news'}),timeout=30).read().decode('utf-8','ignore')
def clean_html(s): return ' '.join(unescape(re.sub(r'<[^>]+>',' ',s or '')).split())
def rss(q):
    root=ET.fromstring(fetch('https://news.google.com/rss/search?q='+quote(q+' when:2d')+'&hl=ja&gl=JP&ceid=JP:ja')); out=[]
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
    text=' '.join(str(x.get(k,'') or '') for k in ('title','headline','description','summary','source')).lower()
    if any(k.lower() in text for k in BAD_TERMS): return False
    direct=any(k.lower() in text for k in DIRECT_TERMS)
    strong=any(k.lower() in text for k in STRONG_MODALITY_TERMS)
    broad=any(k.lower() in text for k in BROAD_MODALITY_TERMS)
    if is_official(x.get('url','')):
        return direct or strong or broad
    return direct or strong or (broad and any(k in text for k in ('医療','病院','患者','診断','画像','放射線')))
def is_news_item(x):
    url=x.get('url',''); title=(x.get('title') or x.get('headline') or '').strip()
    if '/activity/lifelong-study' in url or '/seminar/' in url: return False
    if title in ('日本診療放射線技師会誌JART','みんなに知ってもらいたい診療放射線技師のこと','日本診療放射線技師会について','都道府県診療放射線技師会・放射線技師会','活動紹介','会誌・投稿','一般向け情報','技師会概要','医療被ばく個別相談センター'): return False
    if any(k in title for k in NOISE_TITLE_TERMS): return False
    return True
def parse_nearby_date(html,pos):
    dates=re.findall(r'(20\d{2})[/.年](\d{1,2})[/.月](\d{1,2})',clean_html(html[max(0,pos-1800):pos]))
    if dates:
        y,m,d=dates[-1]; return f'{y}-{int(m):02d}-{int(d):02d}T00:00:00+09:00'
    return None
def direct_jart():
    out=[]
    try:
        html=fetch('https://www.jart.jp/')
        for m in re.finditer(r'<a[^>]+href=["\'](?P<href>[^"\']+)["\'][^>]*>\s*(?P<title>.*?)\s*</a>',html,re.I|re.S):
            title=clean_html(m.group('title')); href=urljoin('https://www.jart.jp/',m.group('href')); date=parse_nearby_date(html,m.start())
            if title and date and '/news/info/' in href.lower() and relevant({'title':title,'source':'JART','url':href}) and is_news_item({'title':title,'url':href}): out.append({'title':title,'url':href,'description':title,'source':'JART','published':date})
    except Exception as e: print('JART direct error:',e)
    return out
def category(x):
    t=' '.join(str(x.get(k,'') or '') for k in ('title','headline','description','summary')).lower(); rules=[('診療報酬・補助金',('診療報酬','補助金','助成金','加算')),('安全管理',('安全管理','安全','被ばく','線量管理','医療被ばく','線量','放射線安全')),('一般撮影',('一般撮影','FPD','マンモグラフィ','X線撮影')),('CT',('CT','computed tomography')),('MRI',('MRI','magnetic resonance')),('核医学',('核医学','SPECT','PET','MIBG','DAT','RI')),('放射線治療',('放射線治療','リニアック','陽子線','粒子線','IGRT')),('AI',('AI','人工知能','画像診断支援','読影支援')),('教育',('教育','国家試験','研修','認定','セミナー','講習')),('学術',('学術','研究','学会','ガイドライン','パブリックコメント')),('職能',('STAT','タスクシフト','タスクシェア','業務範囲','職能')),('制度',('制度','養成','確保','厚生労働省','医政'))]
    for cat,terms in rules:
        if any(k.lower() in t for k in terms): return cat
    return 'その他'
def importance(x,official):
    t=' '.join(str(x.get(k,'') or '') for k in ('title','headline','description','summary')).lower()
    if any(k.lower() in t for k in ('診療報酬','補助金','安全管理','被ばく','線量管理','装置更新','タスクシフト','タスクシェア','業務範囲','STAT','ガイドライン')): return '高'
    if official: return '中'
    return '低'
def load():
    try: return json.loads(NEWS_JSON.read_text(encoding='utf-8'))
    except Exception: return []
def clean_db(db):
    today=datetime.now(JST).date(); out=[]; seen=set()
    for x in db:
        try:
            if datetime.fromisoformat(str(x.get('date','')).replace('Z','+00:00')).date()>today: continue
        except Exception: continue
        if not relevant(x) or not is_news_item(x): continue
        k=norm(x.get('headline')) or x.get('url')
        if not k or k in seen: continue
        seen.add(k); x['category']=x.get('category') if x.get('category') in CATEGORIES else category(x); x['track']=x.get('track') or ('official' if is_official(x.get('url','')) else 'general'); out.append(x)
    return out
def main():
    cutoff=datetime.now(JST)-timedelta(hours=48); db=clean_db(load()); seen={norm(x.get('headline')) or x.get('url') for x in db}; candidates={}
    for x in direct_jart():
        if datetime.fromisoformat(x['published'])>=cutoff:
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
        if any(k.lower() in t for k in DIRECT_TERMS): s+=10
        if is_official(x.get('url','')) or x.get('source')=='JART': s+=4
        if any(k.lower() in t for k in ('制度','診療報酬','補助金','安全管理','被ばく','線量管理','装置更新','タスクシフト','タスクシェア','ガイドライン')): s+=4
        if any(k.lower() in t for k in STRONG_MODALITY_TERMS): s+=2
        if any(k.lower() in t for k in ('漫画','マンガ','芸能','俳優','女優','アイドル','タレント')): s-=10
        return s
    fresh=sorted(candidates.values(),key=lambda x:(score(x),x.get('published','')),reverse=True); added=[]; titles=set()
    for x in fresh[:5]:
        k=norm(x['title'])
        if not k or k in titles: continue
        titles.add(k); official=is_official(x['url']) or x.get('source')=='JART'
        added.append({'date':x['published'][:10],'category':category(x),'importance':importance(x,official),'headline':x['title'],'summary':re.sub(r'\s+',' ',x.get('description','')).strip()[:220],'why':'公式情報のため、放射線部門の運用・教育・制度への影響を確認する価値があります。' if official else '放射線部門の実務への影響を確認する価値があります。','source':x.get('source') or dom(x['url']),'url':x['url'],'track':'official' if official else 'general'})
    final=clean_db(added+db)
    if added and not final: final=added+db
    NEWS_JSON.write_text(json.dumps(final[:200],ensure_ascii=False,indent=2),encoding='utf-8'); print(f'Added {len(added)} new items; database now has {len(final[:200])} items.')
    for x in added: print(x['date'],x['track'],x['category'],x['headline'])
if __name__=='__main__': main()
