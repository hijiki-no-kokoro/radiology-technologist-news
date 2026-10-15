(function(){
  'use strict';
  const R=BeerRecognition,E=BeerPhotoEngine;
  const capture=$('beerPhotoInput'),library=$('beerLibraryInput'),status=$('beerPhotoStatus'),panel=$('beerPhotoResult'),candidates=$('beerPhotoCandidates'),names=$('beerPhotoNames');
  const buttons=[$('beerPhotoButton'),$('beerBarcodeButton'),$('beerNutritionButton')];
  let context=null,dirty=false,mode='front',generation=0,busy=false,pendingReview=null,readMethod='camera';
  function say(text,error=false){status.textContent=text;status.classList.toggle('error',error);}
  function setBusy(value){busy=value;buttons.forEach(button=>button.disabled=value||!repo);library.disabled=value||!repo;$('beerJanLookupButton').disabled=value||!repo;$('beerCancel').hidden=!value;}
  function clearResult(){panel.hidden=true;$('beerPhotoText').textContent='';$('beerPhotoSummary').textContent='';candidates.replaceChildren();names.replaceChildren();}
  function review(text){
    return new Promise(resolve=>{pendingReview?.(false);pendingReview=resolve;$('beerPhotoConfirmText').textContent=text;const d=$('beerPhotoConfirm');if(d.showModal)d.showModal();else d.setAttribute('open','');});
  }
  function resolveReview(value){const d=$('beerPhotoConfirm');if(d.close)d.close();else d.removeAttribute('open');const done=pendingReview;pendingReview=null;done?.(value);}
  $('beerPhotoConfirmNo').onclick=()=>resolveReview(false);$('beerPhotoConfirmYes').onclick=()=>resolveReview(true);$('beerPhotoConfirm').addEventListener('cancel',()=>resolveReview(false));
  function afterSave(){context=null;dirty=false;clearResult();capture.value='';library.value='';}
  function begin(nextMode){if(busy)return;mode=nextMode;say('カメラで撮影し、写真を使用してください。戻って反応がない場合は「写真を選択」から読み込めます。');capture.click();}
  function inputTime(iso){return new Date(Date.parse(iso)+9*3600000).toISOString().slice(0,16);}
  function formLink(){ $('drinkForm').scrollIntoView?.({behavior:'smooth',block:'start'}); }
  $('beerPhotoFormLink').onclick=formLink;
  async function fill(plan,product=null,at){
    if(dirty&&!await review('入力中の商品情報を読み取り結果で置き換えますか？'))return false;
    const p=product||{productName:plan.info.nameLines[0]||'',manufacturer:'',brand:'',flavor:'',revision:'',category:'other',source:'缶の表示（端末内OCR・要確認）',volumeMl:plan.info.volumeMl,alcoholPercent:plan.info.alcoholPercent,caloriesKcal:R.calories(plan.info,plan.info.volumeMl),janCode:plan.janCode};
    for(const id of ['productName','manufacturer','brand','flavor','revision','category','source','volumeMl','alcoholPercent','caloriesKcal','janCode'])$(id).value=(id==='janCode'?(plan.janCode||p.janCode):p[id])??'';
    $('purchasePriceYen').value='';$('included').checked=false;$('sessionAssignment').value='current';$('savedProduct').value=product?.catalog?'':product?.id||'';$('startedAt').value=inputTime(at);
    context={startedAt:at,recordMethod:readMethod,janCode:plan.janCode};dirty=false;return true;
  }
  function button(label,action){const b=document.createElement('button');b.type='button';b.textContent=label;b.onclick=action;return b;}
  function productLabel(p){return p.productName+' / '+p.volumeMl+'ml / '+p.alcoholPercent+'%'+(p.revision?' / '+p.revision:'');}
  function applied(p){return '入力欄に反映：'+p.productName+'・'+p.volumeMl+'ml・'+p.alcoholPercent+'%。缶の表示を確認し「この1缶を保存」を押してください。';}
  async function show(plan,at,barcodeError=''){
    clearResult();panel.hidden=false;$('beerPhotoText').textContent=plan.info.text||'文字は読み取れませんでした。';
    const values=[plan.janCode?'読み取ったJAN：'+plan.janCode:'',plan.info.volumeMl!==null?plan.info.volumeMl+'ml':'',plan.info.alcoholPercent!==null?plan.info.alcoholPercent+'%':'',...plan.info.warnings].filter(Boolean);
    $('beerPhotoSummary').textContent=values.join(' / ')||'商品情報を読み取れませんでした。缶の商品名・容量・度数を大きく撮るか、バーコード撮影をお試しください。';
    for(const p of plan.candidates)candidates.append(button(productLabel(p)+' を入力',async()=>{if(await fill(plan,p,at)){say(applied(p));$('beerPhotoSummary').textContent=applied(p);formLink();}}));
    if(plan.candidates.length===1&&!plan.conflict){
      const p=plan.candidates[0];if(await fill(plan,p,at)){say(applied(p));$('beerPhotoSummary').textContent=applied(p);}else say('入力中の内容を保持しました。読み取り候補は上に表示しています。');
    }else if(plan.candidates.length){
      say(plan.conflict?'読み取り値と商品情報が一致しません。上の候補と缶の表示を確認してください。':'商品候補が見つかりました。容量・度数・新旧仕様を確認して、上の候補を1つ選んでください。',plan.conflict);
      $('beerPhotoSummary').textContent+=(plan.conflict?' ／ 不一致のため反映していません。':' ／ 仕様が複数あるため選択してください。');
    }else if(plan.reason==='unknown-barcode'){
      if(await fill(plan,null,at))say('JAN '+plan.janCode+' を読み取りましたが、対応商品情報がありません。JAN欄には反映済みです。商品名・容量・度数を入力して一度保存すると、次回から照合できます。');
      else say('このJANの商品情報がなく、入力中の内容を保持しました。');
    }else if(plan.info.nameLines.length||plan.info.volumeMl!==null||plan.info.alcoholPercent!==null){
      if(await fill(plan,null,at))say('読み取れた内容を入力欄へ反映しました。商品名は候補です。空欄と缶の表示を確認して保存してください。');
      else say('入力中の内容を保持しました。読み取れた内容は上に表示しています。');
    }else say(barcodeError||'商品情報を読み取れませんでした。バーコード撮影または写真の選び直しをお試しください。',true);
    for(const name of plan.info.nameLines)names.append(button('商品名に使う：'+name,()=>{$('productName').value=name;dirty=true;say('商品名を入力しました。容量・度数を確認して保存してください。');}));
  }
  function autoSave(plan,at){
    const p=plan.candidates[0],input={...p,startedAt:at,purchasePriceYen:null,allocation:'additional',recordMethod:'camera',verificationStatus:'dictionary-confirmed'};
    try{const next=B.add(state,input);lastAdded=next.drinks.at(-1).id;commit(next);afterSave();say(productLabel(p)+' を1缶記録しました。JANが商品情報と一致しました。写真は保存していません。');note('写真から '+p.productName+' を1缶記録しました。タイムラインから取り消せます。');return true;}
    catch(error){say(error.message+' 自動保存せず、内容の確認に進みます。',true);return false;}
  }
  async function applyResult(result,at,hadDraft,selectedMode){
    const plan=R.plan(result.text,result.barcode,state.products,window.BeerCatalog?.products||[]);
    if(selectedMode==='nutrition'){
      const value=R.calories(plan.info,Number($('volumeMl').value));showNutrition(plan);
      if(value===null){say('カロリーの基準量または容量を確認できません。読み取った文字を見て入力してください。',true);return;}
      if($('caloriesKcal').value!==''&&!await review('入力中のカロリーを '+value+'kcal に変更しますか？'))return;
      $('caloriesKcal').value=value;context=context||{startedAt:$('startedAt').value+':00+09:00',recordMethod:'camera'};dirty=true;say('1缶のカロリー '+value+'kcal を入力しました。換算結果を確認して保存してください。');return;
    }
    if(selectedMode==='barcode'&&!plan.janCode){clearResult();panel.hidden=false;$('beerPhotoSummary').textContent='バーコードは読み取れませんでした。下の欄に缶の数字を入力して照合できます。';say(result.barcodeError||'バーコードを読み取れませんでした。数字と縦線全体を大きく撮影するか、JANの数字を入力してください。',true);return;}
    if(plan.autoSave&&state.cameraPreferences.autoSaveKnownBarcode&&!hadDraft&&!dirty){if(autoSave(plan,at))return;}
    await show(plan,at,result.barcodeError);
  }
  async function read(input,selectedMode){
    let file=input.files?.[0];if(!file)return;
    const token=++generation,at=context?.startedAt||new Date().toISOString(),hadDraft=dirty||!!context;
    input.value='';readMethod='camera';setBusy(true);clearResult();panel.hidden=false;$('beerPhotoSummary').textContent='写真を受け取りました。読み取り結果をここに表示します。';say('写真を受け取りました。'+(selectedMode==='barcode'?'バーコード':'商品名・容量・度数')+'を読み取っています。');
    try{const result=await E.scan(file,{mode:selectedMode,progress:text=>{if(token===generation)say(text);}});if(token===generation)await applyResult(result,at,hadDraft,selectedMode);}
    catch(error){if(token===generation){$('beerPhotoSummary').textContent='読み取り結果は入力欄に反映していません。写真の選び直し・バーコード撮影・JAN入力を利用できます。';say(error.name==='AbortError'?'読み取りを中止しました。時間切れの場合は、通信を確認して写真を選び直してください。':'読み取れませんでした。'+error.message,true);}}
    finally{file=null;if(token===generation)setBusy(false);}
  }
  capture.onchange=()=>read(capture,mode);library.onchange=()=>read(library,'front');
  $('beerJanLookupButton').onclick=async()=>{
    const code=R.jan($('beerJanLookup').value);if(!code){say('缶のバーコードにある8桁または13桁の数字を確認してください。',true);return;}
    readMethod='manual';setBusy(true);try{await applyResult({text:'',barcode:code},context?.startedAt||new Date().toISOString(),true,'barcode');}finally{setBusy(false);}
  };
  function showNutrition(plan){clearResult();panel.hidden=false;$('beerPhotoText').textContent=plan.info.text;$('beerPhotoSummary').textContent=plan.info.calorieValue!==null?'読み取り値 '+plan.info.calorieValue+'kcal / '+(plan.info.calorieBasis==='100ml'?'100ml当たり':plan.info.calorieBasis==='can'?'1缶当たり':'基準量未確認'):'カロリーは確認できませんでした。';}
  $('beerPhotoButton').onclick=()=>begin('front');$('beerBarcodeButton').onclick=()=>begin('barcode');$('beerNutritionButton').onclick=()=>begin('nutrition');
  $('beerCancel').onclick=()=>{generation++;E.cancel();resolveReview(false);setBusy(false);say('読み取りを中止しました。写真は保存していません。');};
  $('drinkForm').addEventListener('input',()=>{dirty=true;});$('drinkForm').addEventListener('change',()=>{dirty=true;});
  $('autoBarcode').checked=state?.cameraPreferences.autoSaveKnownBarcode??true;
  $('autoBarcode').onchange=()=>guarded(()=>{const next=structuredClone(state);next.cameraPreferences.autoSaveKnownBarcode=$('autoBarcode').checked;commit(next);say('JAN一致時の自動保存設定を変更しました。');});
  window.BeerPhotoForm={metadata:()=>context?{recordMethod:context.recordMethod}:{recordMethod:'manual'},janFor:p=>context?.janCode||p.janCode||'',afterSave};
  window.addEventListener('pagehide',()=>{generation++;E.cancel();resolveReview(false);context=null;clearResult();});setBusy(false);
})();
