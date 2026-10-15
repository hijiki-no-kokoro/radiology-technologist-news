(function(){
  'use strict';
  const R=BeerRecognition,E=BeerPhotoEngine;
  const capture=$('beerPhotoInput'),status=$('beerPhotoStatus'),panel=$('beerPhotoResult'),candidates=$('beerPhotoCandidates'),names=$('beerPhotoNames');
  const buttons=[$('beerPhotoButton'),$('beerBarcodeButton'),$('beerNutritionButton')];
  let context=null,dirty=false,mode='front',generation=0,busy=false;
  function say(text,error=false){status.textContent=text;status.classList.toggle('error',error);}
  function setBusy(value){busy=value;buttons.forEach(button=>button.disabled=value||!repo);$('beerCancel').hidden=!value;}
  function clearResult(){panel.hidden=true;$('beerPhotoText').textContent='';$('beerPhotoSummary').textContent='';candidates.replaceChildren();names.replaceChildren();}
  function afterSave(){context=null;dirty=false;clearResult();capture.value='';}
  function begin(nextMode){
    if(busy)return;
    mode=nextMode;capture.click();
  }
  function inputTime(iso){return new Date(Date.parse(iso)+9*3600000).toISOString().slice(0,16);}
  function fill(plan,product=null,at){
    if((dirty||context)&&!confirm('入力中の商品情報を読み取り結果で置き換えますか？'))return false;
    const p=product||{productName:'',manufacturer:'',brand:'',flavor:'',revision:'',category:'other',source:'缶の表示（端末内OCR・要確認）',volumeMl:plan.info.volumeMl,alcoholPercent:plan.info.alcoholPercent,caloriesKcal:R.calories(plan.info,plan.info.volumeMl),janCode:plan.janCode};
    for(const id of ['productName','manufacturer','brand','flavor','revision','category','source','volumeMl','alcoholPercent','caloriesKcal','janCode'])$(id).value=(id==='janCode'?(plan.janCode||p.janCode):p[id])??'';
    $('purchasePriceYen').value='';$('included').checked=false;$('sessionAssignment').value='current';$('savedProduct').value=product?.id||'';$('startedAt').value=inputTime(at);
    context={startedAt:at,recordMethod:'camera',janCode:plan.janCode};dirty=false;return true;
  }
  function button(label,action){const b=document.createElement('button');b.type='button';b.textContent=label;b.onclick=action;return b;}
  function show(plan,at){
    clearResult();panel.hidden=false;$('beerPhotoText').textContent=plan.info.text||'文字は読み取れませんでした。';
    const values=[plan.janCode?'JAN '+plan.janCode:'',plan.info.volumeMl!==null?plan.info.volumeMl+'ml':'',plan.info.alcoholPercent!==null?plan.info.alcoholPercent+'%':'',...plan.info.warnings].filter(Boolean);
    $('beerPhotoSummary').textContent=values.join(' / ')||'容量・度数を確定できませんでした。手動登録は引き続き使えます。';
    for(const p of plan.candidates)candidates.append(button(p.productName+' / '+p.volumeMl+'ml / '+p.alcoholPercent+'% を確認して入力',()=>{if(fill(plan,p,at))say('商品情報を入力しました。缶の表示と内容を確認し、下の「この1缶を保存」を押してください。');}));
    if(!plan.candidates.length){
      if(fill(plan,null,at))say(plan.reason==='unknown-barcode'?'このバーコードは未登録です。商品名と数値を確認して1回保存すると、次回から辞書で照合できます。':'読み取れた数値を入力しました。商品名と内容を確認して保存してください。');
      for(const name of plan.info.nameLines)names.append(button('商品名に使う：'+name,()=>{$('productName').value=name;dirty=true;say('商品名を入力しました。容量・度数を確認して保存してください。');}));
    }else say(plan.conflict?'辞書と写真の容量・度数が一致しません。自動保存を止めました。缶の表示を確認してください。':'候補を確認して選んでください。文字認識だけでは自動保存しません。',plan.conflict);
  }
  function autoSave(plan,at){
    const p=plan.candidates[0],input={...p,startedAt:at,purchasePriceYen:null,allocation:'additional',recordMethod:'camera',verificationStatus:'dictionary-confirmed'};
    try{const next=B.add(state,input);lastAdded=next.drinks.at(-1).id;commit(next);afterSave();say(p.productName+'を1缶記録しました。JANが商品辞書と一致しました。写真はアプリ内に保存していません。');note('写真から '+p.productName+' を1缶記録しました。タイムラインから取り消せます。');return true;}
    catch(error){say(error.message+' 自動保存せず、内容の確認に進みます。',true);return false;}
  }
  capture.onchange=async()=>{
    let file=capture.files?.[0];capture.value='';if(!file)return;
    const token=++generation,at=context?.startedAt||new Date().toISOString(),hadDraft=dirty||!!context;
    setBusy(true);say('写真を読み取っています。処理後に画像を破棄します。');
    try{
      const result=await E.scan(file,{mode,progress:text=>{if(token===generation)say(text);}});if(token!==generation)return;
      const plan=R.plan(result.text,result.barcode,state.products);
      if(mode==='nutrition'){
        const value=R.calories(plan.info,Number($('volumeMl').value));
        if(value===null){showNutrition(plan);say('カロリーの基準量または容量を確認できません。読み取った文字を見て手動で入力してください。',true);return;}
        if($('caloriesKcal').value!==''&&!confirm('入力中のカロリーを、読み取り結果の '+value+'kcal に変更しますか？'))return;
        $('caloriesKcal').value=value;context=context||{startedAt:$('startedAt').value+':00+09:00',recordMethod:'camera'};dirty=true;showNutrition(plan);say('1缶のカロリー '+value+'kcal を入力しました。缶の表示と換算結果を確認して保存してください。');return;
      }
      if(mode==='barcode'&&!plan.janCode){say(result.barcodeError||'バーコードを読み取れませんでした。明るい場所で、数字と縦線全体を撮影するか手動で入力してください。',true);return;}
      if(plan.autoSave&&state.cameraPreferences.autoSaveKnownBarcode&&!hadDraft&&!dirty){if(autoSave(plan,at))return;}
      show(plan,at);
    }catch(error){if(token===generation)say(error.name==='AbortError'?'読み取りを中止しました。時間切れの場合も、手動登録を利用できます。':'読み取れませんでした。'+error.message+' 手動登録はそのまま利用できます。',true);}
    finally{file=null;if(token===generation)setBusy(false);}
  };
  function showNutrition(plan){clearResult();panel.hidden=false;$('beerPhotoText').textContent=plan.info.text;$('beerPhotoSummary').textContent=plan.info.calorieValue!==null?'読み取り値 '+plan.info.calorieValue+'kcal / '+(plan.info.calorieBasis==='100ml'?'100ml当たり':plan.info.calorieBasis==='can'?'1缶当たり':'基準量未確認'):'カロリーは確認できませんでした。';}
  $('beerPhotoButton').onclick=()=>begin('front');$('beerBarcodeButton').onclick=()=>begin('barcode');$('beerNutritionButton').onclick=()=>begin('nutrition');
  $('beerCancel').onclick=()=>{generation++;E.cancel();setBusy(false);say('読み取りを中止しました。写真はアプリ内に保存していません。');};
  $('drinkForm').addEventListener('input',()=>{dirty=true;});$('drinkForm').addEventListener('change',()=>{dirty=true;});
  $('autoBarcode').checked=state?.cameraPreferences.autoSaveKnownBarcode??true;
  $('autoBarcode').onchange=()=>guarded(()=>{const next=structuredClone(state);next.cameraPreferences.autoSaveKnownBarcode=$('autoBarcode').checked;commit(next);say('バーコード一致時の自動保存設定を変更しました。');});
  window.BeerPhotoForm={metadata:()=>context?{recordMethod:'camera'}:{recordMethod:'manual'},janFor:p=>context?.janCode||p.janCode||'',afterSave};
  window.addEventListener('pagehide',()=>{generation++;E.cancel();context=null;clearResult();});setBusy(false);
})();
