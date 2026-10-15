/* 酒ログ Phase 2: no network, no images, and no writes to the v1 key. */
(function(root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.BeerLog = factory();
})(typeof window !== 'undefined' ? window : this, function() {
  'use strict';
  const DEFAULTS = {baseline:4,target:2,price:180,abv:5,volume:350};
  const clone = o => JSON.parse(JSON.stringify(o));
  const fail = message => { throw new Error(message); };
  const object = o => o && typeof o === 'object' && !Array.isArray(o);
  function number(n, label, min=0, max=1e9, optional=false) {
    if (optional && (n === null || n === undefined || n === '')) return null;
    if (typeof n !== 'number' || !Number.isFinite(n) || n < min || n > max) fail(label+'の値が不正です');
    return n;
  }
  function text(s, label, optional=false) {
    if (optional && (s === undefined || s === null)) return '';
    if (typeof s !== 'string' || s.length > 300 || (!optional && !s.trim())) fail(label+'を確認してください');
    return s.trim();
  }
  function dayKey(timestamp) {
    const time = Date.parse(timestamp);
    if (!Number.isFinite(time)) fail('日時が不正です');
    return new Date(time+9*3600000).toISOString().slice(0,10);
  }
  function validDay(key) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(key) || !Number.isFinite(Date.parse(key+'T00:00:00+09:00')) || dayKey(key+'T00:00:00+09:00')!==key) fail('日付が不正です');
    return key;
  }
  function time(s) {
    if (typeof s !== 'string' || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d{1,3})?)?(Z|[+-]\d{2}:\d{2})$/.test(s) || !Number.isFinite(Date.parse(s))) fail('タイムゾーン付き日時が必要です');
    validDay(s.slice(0,10));
    return new Date(s).toISOString();
  }
  function settings(s={}) {
    if (!object(s)) fail('設定が不正です');
    const p = {...DEFAULTS,...s};
    const r = {baseline:number(p.baseline,'基準本数',1,12),target:number(p.target,'目標本数',0,12),price:number(p.price,'基準価格',0),abv:number(p.abv,'旧設定の度数',0,100),volume:number(p.volume,'旧設定の容量',0,10000)};
    if (!Number.isInteger(r.baseline) || !Number.isInteger(r.target) || r.target>r.baseline) fail('本数設定を確認してください');
    return r;
  }
  function counts(records) {
    if (!object(records)) fail('日別本数が不正です');
    const r = {};
    for (const [key,value] of Object.entries(records)) {
      validDay(key); number(value,'本数',0,10000);
      if (!Number.isInteger(value)) fail('本数は整数で指定してください');
      r[key] = value;
    }
    return r;
  }
  function empty() { return {version:3,settings:clone(DEFAULTS),countOnlyRecords:{},products:[],drinks:[],legacyRaw:null,originLegacyRaw:null,cameraPreferences:{autoSaveKnownBarcode:true}}; }
  function migrate(raw) {
    if (typeof raw !== 'string') fail('旧データがありません');
    const old = JSON.parse(raw);
    if (!object(old) || !object(old.records) || !object(old.settings) || old.version !== undefined) fail('旧形式のデータではありません');
    return {...empty(),settings:settings(old.settings),countOnlyRecords:counts(old.records),legacyRaw:raw,originLegacyRaw:raw};
  }
  function normalizeJan(value){
    if(value===undefined||value===null||value==='')return '';
    if(typeof value!=='string')fail('JANコードは数字の文字列で入力してください');
    let code=value.normalize('NFKC').replace(/[\s-]/g,'');if(/^\d{12}$/.test(code))code='0'+code;
    if(!/^(\d{8}|\d{13})$/.test(code)||/^0+$/.test(code))fail('JANコードは有効な8桁または13桁で入力してください');
    const digits=[...code].map(Number),check=digits.pop();let sum=0;for(let i=digits.length-1,w=3;i>=0;i--,w=w===3?1:3)sum+=digits[i]*w;
    if((10-sum%10)%10!==check)fail('JANコードのチェック数字が一致しません');return code;
  }
  function method(value,allowed,fallback){const result=value??fallback;if(!allowed.includes(result))fail('記録方法が不正です');return result;}
  function fingerprint(p) {
    return JSON.stringify([p.manufacturer,p.brand,p.productName,p.flavor,p.volumeMl,p.alcoholPercent,p.revision].map(x=>typeof x==='string'?x.normalize('NFKC').toLowerCase().trim():x));
  }
  function product(p) {
    if (!object(p)) fail('商品情報が不正です');
    return {manufacturer:text(p.manufacturer,'メーカー',true),brand:text(p.brand,'ブランド',true),productName:text(p.productName,'商品名'),flavor:text(p.flavor,'フレーバー',true),category:text(p.category||'other','カテゴリ'),containerType:'can',volumeMl:number(p.volumeMl,'容量',1,10000),alcoholPercent:number(p.alcoholPercent,'度数',0.01,100),caloriesKcal:number(p.caloriesKcal,'カロリー',0,1e6,true),sugarGrams:number(p.sugarGrams,'糖質',0,1e6,true),revision:text(p.revision,'商品版・変更メモ',true),janCode:normalizeJan(p.janCode),source:text(p.source,'情報の根拠',true)};
  }
  function pure(p) {return p.volumeMl*p.alcoholPercent/100*0.8;}
  function id() {return (typeof crypto!=='undefined' && crypto.randomUUID) ? crypto.randomUUID() : Date.now().toString(36)+'-'+Math.random().toString(36).slice(2)+'-'+Math.random().toString(36).slice(2);}
  function canonical(value) {
    if (!object(value) || ![2,3].includes(value.version) || !object(value.settings) || !Array.isArray(value.drinks) || !Array.isArray(value.products)) fail('対応していないバックアップ形式です');
    const r={version:3,settings:settings(value.settings),countOnlyRecords:counts(value.countOnlyRecords),products:[],drinks:[],legacyRaw:null,originLegacyRaw:null,cameraPreferences:{autoSaveKnownBarcode:true}};
    if(value.cameraPreferences!==undefined){if(!object(value.cameraPreferences)||typeof value.cameraPreferences.autoSaveKnownBarcode!=='boolean')fail('撮影設定が不正です');r.cameraPreferences={autoSaveKnownBarcode:value.cameraPreferences.autoSaveKnownBarcode};}
    if (value.legacyRaw!==null && value.legacyRaw!==undefined) {migrate(value.legacyRaw);r.legacyRaw=value.legacyRaw;}
    if(value.originLegacyRaw!==null && value.originLegacyRaw!==undefined){migrate(value.originLegacyRaw);r.originLegacyRaw=value.originLegacyRaw;}
    const productIds=new Set();
    for(const p of value.products) {
      const pid=text(p.id,'商品ID'); if(productIds.has(pid)) fail('商品IDが重複しています');productIds.add(pid);
      r.products.push({id:pid,...product(p)});
    }
    const drinkIds=new Set(), included={};
    for(const d of value.drinks) {
      const did=text(d.id,'記録ID'); if(drinkIds.has(did)) fail('記録IDが重複しています');drinkIds.add(did);
      const pid=text(d.productId,'商品ID');if(!productIds.has(pid))fail('商品の参照先がありません');
      const snapshot=product(d.snapshot),startedAt=time(d.startedAt),finishedAt=d.finishedAt===null?null:time(d.finishedAt);
      if (finishedAt && Date.parse(finishedAt)<Date.parse(startedAt)) fail('終了時刻は開始時刻以降にしてください');
      if (!['additional','included'].includes(d.allocation)) fail('本数の集計方式が不正です');
      const key=dayKey(startedAt);
      if(d.allocation==='included') included[key]=(included[key]||0)+1;
      r.drinks.push({id:did,productId:pid,snapshot,pureAlcoholGrams:pure(snapshot),purchasePriceYen:number(d.purchasePriceYen,'購入価格',0,1e9,true),startedAt,finishedAt,allocation:d.allocation,recordMethod:method(d.recordMethod,['manual','camera'],'manual'),verificationStatus:method(d.verificationStatus,['user-confirmed','dictionary-confirmed'],'user-confirmed'),createdAt:time(d.createdAt),updatedAt:time(d.updatedAt)});
    }
    for(const [key,n] of Object.entries(included)) if(n>(r.countOnlyRecords[key]||0)) fail(key+'の旧本数より詳細記録が多くなっています');
    return r;
  }
  function add(state,input,options={}) {
    const next=canonical(state),p=product(input),startedAt=time(input.startedAt),pid=fingerprint(p);
    const old=next.products.find(x=>fingerprint(x)===pid);
    const productId=old?old.id:id();
    if(!old)next.products.push({id:productId,...p});else Object.assign(old,p);
    const duplicate=next.drinks.some(d=>d.productId===productId && Math.abs(Date.parse(d.startedAt)-Date.parse(startedAt))<120000);
    if(duplicate && !options.allowDuplicate)fail('同じ商品が2分以内に登録されています。別の1缶か確認してください');
    const now=new Date().toISOString();
    next.drinks.push({id:options.id||id(),productId,snapshot:p,pureAlcoholGrams:pure(p),purchasePriceYen:input.purchasePriceYen??null,startedAt,finishedAt:null,allocation:input.allocation||'additional',recordMethod:input.recordMethod||'manual',verificationStatus:input.verificationStatus||'user-confirmed',createdAt:now,updatedAt:now});
    return canonical(next);
  }
  function keys(state) {return [...new Set([...Object.keys(state.countOnlyRecords),...state.drinks.map(d=>dayKey(d.startedAt))])].sort();}
  function aggregate(state,predicate=()=>true) {
    const details=state.drinks.filter(d=>predicate(dayKey(d.startedAt)));
    const unknown=Object.entries(state.countOnlyRecords).filter(([k])=>predicate(k)).reduce((s,[key,n])=>s+n-details.filter(d=>d.allocation==='included'&&dayKey(d.startedAt)===key).length,0);
    const sum=field=>({value:details.reduce((s,d)=>s+(field(d)??0),0),unknown:unknown+details.filter(d=>field(d)===null).length});
    const alcohol=sum(d=>d.pureAlcoholGrams),calories=sum(d=>d.snapshot.caloriesKcal),spending=sum(d=>d.purchasePriceYen);
    const allKeys=keys(state).filter(predicate),count=details.length+unknown;
    const dayCount=key=>(state.countOnlyRecords[key]||0)+state.drinks.filter(d=>dayKey(d.startedAt)===key&&d.allocation==='additional').length;
    const savings=allKeys.reduce((s,key)=>s+Math.max(0,state.settings.baseline-dayCount(key))*state.settings.price,0);
    return {count,unknownDetails:unknown,alcohol,calories,spending,beerEquivalent:alcohol.value/14,savings,recordedDays:allKeys.length};
  }
  function setDailyTotal(state,key,total) {
    validDay(key);number(total,'日別本数',0,10000);if(!Number.isInteger(total))fail('本数は整数で指定してください');
    const next=canonical(state),details=next.drinks.filter(d=>dayKey(d.startedAt)===key),additional=details.filter(d=>d.allocation==='additional').length,included=details.length-additional;
    if(total<details.length)fail('詳細記録が'+details.length+'缶あります。それより少ない本数には変更できません');
    next.countOnlyRecords[key]=total-additional;
    if(next.countOnlyRecords[key]<included)fail('本数を確認してください');
    return canonical(next);
  }
  function remove(state,did) {
    const next=canonical(state);const d=next.drinks.find(x=>x.id===did);if(!d)fail('記録が見つかりません');
    next.drinks=next.drinks.filter(x=>x.id!==did);
    // Included records annotate the original count: undo removes details, not that old count.
    return canonical(next);
  }
  function finish(state,when) {
    const next=canonical(state),end=time(when);
    for(const d of next.drinks.filter(x=>!x.finishedAt)) {
      if(Date.parse(d.startedAt)>Date.parse(end))fail('開始前の終了時刻です');
      d.finishedAt=end;d.updatedAt=new Date().toISOString();
    }
    return canonical(next);
  }
  function decode(raw) {
    if(typeof raw!=='string' || raw.length>10*1024*1024)fail('バックアップは10MB以下にしてください');
    const value=JSON.parse(raw);
    return [2,3].includes(value.version) ? canonical(value) : migrate(raw);
  }
  function merge(state,incoming) {
    const a=canonical(state),b=canonical(incoming);
    if(JSON.stringify(a.settings)!==JSON.stringify(b.settings))fail('設定が異なります。統合せず、バックアップ後に復元を選んでください');
    for(const [key,n] of Object.entries(b.countOnlyRecords)){
      if(Object.hasOwn(a.countOnlyRecords,key)&&a.countOnlyRecords[key]!==n)fail(key+'の本数が異なります。自動で上書きしません');
      a.countOnlyRecords[key]=n;
    }
    for(const field of ['products','drinks'])for(const item of b[field]){
      const found=a[field].find(x=>x.id===item.id);
      if(found && JSON.stringify(found)!==JSON.stringify(item))fail('同じIDの内容が異なります。自動で上書きしません');
      if(!found)a[field].push(item);
    }
    if(a.legacyRaw && b.legacyRaw && a.legacyRaw!==b.legacyRaw)fail('旧データのバックアップが異なります');
    a.legacyRaw=a.legacyRaw||b.legacyRaw;
    return canonical(a);
  }
  function serialize(state){return JSON.stringify(canonical(state),null,2);}
  function csv(state){
    const cell=x=>{let value=String(x??'');if(typeof x==='string' && /^[=+@\-\t\r\n]/.test(value))value="'"+value;return '"'+value.replaceAll('"','""')+'"';};
    const rows=[['種別','日付(JST)','商品名','容量ml','度数%','純アルコールg','カロリーkcal','購入価格円','開始時刻','終了時刻','本数集計','詳細未登録本数']];
    for(const d of state.drinks)rows.push(['詳細',dayKey(d.startedAt),d.snapshot.productName,d.snapshot.volumeMl,d.snapshot.alcoholPercent,d.pureAlcoholGrams,d.snapshot.caloriesKcal,d.purchasePriceYen,d.startedAt,d.finishedAt,d.allocation==='included'?'旧本数に含む':'追加',0]);
    for(const [key,n] of Object.entries(state.countOnlyRecords)){
      const remaining=n-state.drinks.filter(d=>d.allocation==='included'&&dayKey(d.startedAt)===key).length;
      if(remaining||n===0)rows.push(['本数のみ',key,'','','','','','','','', '旧記録・本数入力',remaining]);
    }
    return '\ufeff'+rows.map(r=>r.map(cell).join(',')).join('\r\n');
  }
  function repository(storage,key='beer_save_pwa_v2_preview') {
    let expected=storage.getItem(key),state=expected===null?empty():decode(expected);
    return {
      get:()=>clone(state),
      commit(next,backup=false){
        if(storage.getItem(key)!==expected)fail('別の画面で記録が更新されています。再読み込みしてから操作してください');
        const raw=serialize(next);
        if(backup&&expected!==null)storage.setItem(key+'_recovery',expected);
        storage.setItem(key,raw); // localStorage setItem is atomic; update memory only on success.
        expected=raw;state=JSON.parse(raw);return clone(state);
      }
    };
  }
  return {DEFAULTS,normalizeJan,empty,migrate,canonical,product,fingerprint,pure,dayKey,validDay,add,aggregate,setDailyTotal,remove,finish,decode,merge,serialize,csv,repository};
});
