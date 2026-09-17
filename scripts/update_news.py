import json, os, re, xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen
ROOT=Path(__file__).resolve().parents[1]; NEWS_JSON=ROOT/'news.json'
QUERIES=['診療放射線技師 OR 放射線技師 OR 放射線部','放射線診療 CT MRI FPD','放射線 被ばく 線量管理 安全管理','核医学 SPECT PET 放射線技師','放射線 AI 画像診断 読影支援','診療報酬 放射線 画像診断 補助金','site:jart.jp 診療放射線技師','site:jart.jp 放射線技師','site:jsrt.or.jp 放射線技師','site:jrs.or.jp 放射線診療','site:jsnm.org 核医学','site:jastro.or.jp 放射線治療','site:mhlw.go.jp 診療放射線技師','site:nra.go.jp 放射線 医療']
OFFICIAL=('jart.jp','jsrt.or.jp','jrs.or.jp','jsnm.org','jastro.or.jp','mhlw.go.jp','nra.go.jp','pmda.go.jp','mext.go.jp','fda.gov','iaea.org','who.int','canon-medical.co.jp','fujifilm.com','gehealthcare.co.jp','siemens-healthineers.com','philips.co.jp')
CATEGORIES=('制度','職能','学術','AI','CT','MRI','一般撮影','安全管理','核医学','放射線治療','教育','診療報酬・補助金','その他')
def fetch(url):
 r=Request(url,headers={'User-Agent':'Mozilla/5.0 radiology-technologist-news'}); return urlopen(r,timeout=30).read().decode('utf-8','ignore')
def rss(q):
 root=ET.fromstring(fetch('https://news.google.com/rss/search?q='+quote(q+' when:2d')+'&hl=ja&gl=JP&ceid=JP:ja')); out=[]
 for it in root.findall('./channel/item'):
  title=unescape(it.findtext('title','')); link=it.findtext('link',''); desc=unescape(re.sub('<[^>]+>',' ',it.findtext('description',''))); pub=it.findtext('pubDate',''); se=it.find('source'); src=se.text if se is not None else ''
  try: dt=parsedate_to_datetime(pub).astimezone(timezone.utc)
  except: dt=datetime.now(timezone.utc)
  if title and link: out.append({'title':title,'url':link,'description':desc[:700],'source':src,'published':dt.isoformat()})
 return out
def norm(s): return re.sub(r'[^0-9a-zぁ-んァ-ヶ一-龠]','',str(s or '').lower())
def dom(url):
 m=re.search(r'https?://([^/]+)',url or ''); return m.group(1).lower().replace('www.','') if m else ''
def is_official(url):
 d=dom(url); return any(d==z or d.endswith('.'+z) for z in OFFICIAL)
def relevant(x):
 text=(x.get('title','')+' '+x.get('description','')+' '+x.get('source','')).lower()
 bad=('漫画','マンガ','芸能','俳優','女優','アイドル','タレント','画像集','写真集','昭和あるある','グラビア')
 good=('診療放射線技師','放射線技師','放射線部','放射線科','CT','MRI','FPD','一般撮影','マンモグラフィ','核医学','SPECT','PET','放射線治療','線量','被ばく','AI','画像診断','読影','STAT','診療報酬','補助金','国家試験','研修','認定','医療機器','装置更新')
 return not any(k.lower() in text for k in bad) and any(k.lower() in text for k in good)
def load():
 try: return json.loads(NEWS_JSON.read_text(encoding='utf-8'))
 except: return []
def enrich(items):
 key=os.environ.get('OPENAI_API_KEY')
 if not key: return items
 payload=[{'id':i,'title':x['title'],'source':x['source'],'description':x['description']} for i,x in enumerate(items[:30])]
 prompt='''病院の放射線部門を管理する技師長向けにニュースを分類してください。各項目へ category, importance, summary, why を付けてください。categoryは必ず次の13個から1個だけ選択し、複数カテゴリを連結しないでください：制度、職能、学術、AI、CT、MRI、一般撮影、安全管理、核医学、放射線治療、教育、診療報酬・補助金、その他。FPDは独立カテゴリにせず、FPDに関するニュースは内容に最も近い「一般撮影」または「安全管理」などへ分類してください。importanceは高・中・低の1個。重要度は技師長の実務への影響で判定し、制度変更、人員、安全、線量、装置更新、診療報酬、補助金、AI導入などを高く評価してください。'''+json.dumps(payload,ensure_ascii=False)
 body=json.dumps({'model':'gpt-4o-mini','messages':[{'role':'system','content':'Return valid JSON only.'},{'role':'user','content':prompt}],'temperature':0.1,'response_format':{'type':'json_object'}}).encode()
 try:
  req=Request('https://api.openai.com/v1/chat/completions',data=body,headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'}); data=json.loads(urlopen(req,timeout=60).read().decode()); data=json.loads(data['choices'][0]['message']['content']); vals=data.get('items',[]); by={int(v['id']):v for v in vals if 'id' in v}
  for i,x in enumerate(items[:30]):
   if i in by: x.update({k:by[i][k] for k in ('category','importance','summary','why') if k in by[i]})
 except Exception as e: print('AI skipped:',e)
 return items
def category(x):
 c=x.get('category','その他')
 if c in CATEGORIES: return c
 t=(str(c)+' '+x.get('headline','')+' '+x.get('summary','')).lower()
 rules=[('診療報酬・補助金',('診療報酬','補助金','助成金','加算')),('安全管理',('安全','被ばく','線量')),('一般撮影',('一般撮影','FPD','マンモグラフィ')),('CT',('CT',)),('MRI',('MRI',)),('核医学',('核医学','SPECT','PET','MIBG','DAT')),('放射線治療',('放射線治療','リニアック','陽子線','粒子線')),('教育',('教育','国家試験','研修','認定')),('AI',('AI','人工知能','AI導入')),('学術',('学術','研究','学会')),('制度',('制度','養成','確保')),('職能',('職能','タスクシフト','タスクシェア'))]
 for cat,terms in rules:
  if any(k.lower() in t for k in terms): return cat
 return 'その他'
def importance(x,official):
 t=(x.get('headline','')+' '+x.get('summary','')+' '+x.get('why','')).lower(); high=('法令','制度変更','診療報酬','補助金','安全','被ばく','線量管理','装置更新','保守','人員','養成','確保','AI導入','タスクシフト','医療機器')
 if any(k.lower() in t for k in high): return '高'
 return x.get('importance') if x.get('importance') in ('高','中','低') else ('中' if official else '低')
def main():
 now=datetime.now(timezone.utc); cutoff=now-timedelta(hours=30); db=load(); clean=[]; seen=set()
 for x in db:
  k=norm(x.get('headline')) or x.get('url')
  if k and k not in seen: seen.add(k); clean.append(x)
 db=clean; urls={x.get('url') for x in db}; titles={norm(x.get('headline')) for x in db}; candidates={}
 for q in QUERIES:
  try:
   for x in rss(q):
    if x['published']>=cutoff.isoformat() and x['url'] not in urls and norm(x['title']) not in titles and relevant(x): candidates[x['url']]=x
  except Exception as e: print('RSS error:',e)
 fresh=enrich(sorted(candidates.values(),key=lambda x:x['published'],reverse=True)[:30]); added=[]; newtitles=set()
 for x in fresh:
  k=norm(x['title'])
  if not k or k in newtitles or not relevant(x): continue
  newtitles.add(k); official=is_official(x['url']); d=dom(x['url'])
  added.append({'date':x['published'][:10],'category':category(x),'importance':importance(x,official),'headline':x['title'],'summary':x.get('summary') or x.get('description','')[:180],'why':x.get('why') or '放射線部門の実務への影響を確認する価値があります。','source':x.get('source') or d,'url':x['url'],'track':'official' if official else 'general'})
 db+=added; final=[]; seen=set()
 for x in sorted(db,key=lambda z:(z.get('date',''),{'高':3,'中':2,'低':1}.get(z.get('importance'),0)),reverse=True):
  k=norm(x.get('headline')) or x.get('url')
  if k in seen: continue
  seen.add(k); x['category']=category(x)
  if 'track' not in x: x['track']='official' if is_official(x.get('url','')) else 'general'
  final.append(x)
 NEWS_JSON.write_text(json.dumps(final[:200],ensure_ascii=False,indent=2),encoding='utf-8'); print(f'Added {len(added)} new items; database now has {len(final[:200])} items.')
if __name__=='__main__': main()
