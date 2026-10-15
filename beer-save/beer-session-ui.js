(function(){
 'use strict';
 if(!repo||!state)return;
 const stamp=iso=>new Intl.DateTimeFormat('ja-JP',{timeZone:'Asia/Tokyo',month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'}).format(new Date(iso));
 const duration=minutes=>Math.floor(minutes/60)+'時間'+(minutes%60?minutes%60+'分':'');
 let finishDirty=false;
 const review=$('sessionConfirm');let pending=null;
 function closeReview(){pending=null;if(typeof review.close==='function')review.close();else review.removeAttribute('open');}
 function askReview(message,action){if(pending)throw Error('確認中の変更があります');pending=action;$('sessionConfirmText').textContent=message;if(typeof review.showModal==='function')review.showModal();else review.setAttribute('open','');}
 $('sessionConfirmNo').onclick=closeReview;
 $('sessionConfirmYes').onclick=()=>{const action=pending;closeReview();if(action)guarded(action);};
 review.addEventListener('cancel',()=>{pending=null;});

 function summaryHTML(x){
  return '<p class="hint">開始 '+esc(stamp(x.session.startedAt))+(x.session.finishedAt?' ／ 終了 '+esc(stamp(x.session.finishedAt)):' ／ 終了未記録')+'</p><div class="value">'+x.count+'缶 <small>'+decimal(x.grams)+'g・'+decimal(x.volumeMl)+'ml</small></div><p class="hint">350ml・5%ビール換算 '+decimal(x.beerEquivalent)+'本</p><details style="margin:12px 0"><summary>分解時間の参考表示：約'+duration(x.decompositionMinutes)+'</summary><p class="hint">この回に詳細登録した分について、飲み終えてからの単純な目安です。本数だけの旧記録やセッション未設定の記録は含みません。飲酒中の代謝は差し引いていません。</p><p class="hint">個人差が大きく、この時間が経過してもアルコールの消失や運転可否を判断できません。残存アルコール量を示すものではありません。</p><p class="hint">計算の参考：純アルコール10gにつき約2.5時間。<a href="https://izonsho.mhlw.go.jp/alcoholwacth/" target="_blank" rel="noopener noreferrer">厚生労働省 アルコールウォッチ</a>（2026年10月15日確認）</p></details>';
 }
 function render(){
  const active=B.activeSession(state),latest=active||[...state.sessions].sort((a,b)=>b.startedAt.localeCompare(a.startedAt))[0];
  $('sessionTitle').textContent=active?'今回の飲酒':latest?'直近の飲酒（終了）':'今回の飲酒';
  $('finishBtn').hidden=!active;$('finishBtn').disabled=!active;$('sessionFinishControls').hidden=!active;
  if(latest){const x=B.sessionSummary(state,latest.id);$('sessionSummary').innerHTML=summaryHTML(x);$('sessionTimeline').innerHTML=timeline(x.drinks);
   if(active&&Date.now()-Date.parse(active.startedAt)>86400000)$('sessionSummary').insertAdjacentHTML('afterbegin','<p class="notice">開始から24時間以上経過しています。終了を忘れた場合は、飲み終えた日時を指定して終了してください。日付だけでは自動終了しません。</p>');
  }else{$('sessionSummary').innerHTML='<p class="muted">1缶を登録すると今回の飲酒が始まります。深夜0時をまたいでも、終了するまで同じ回として表示します。</p>';$('sessionTimeline').innerHTML='';}
  if(!finishDirty)$('sessionFinishedAt').value=nowInput();
  $('dayStartHour').value=String(state.settings.dayStartHour);$('dayBoundaryHint').textContent='集計日：'+today()+' ／ 区切り：日本時間 '+state.settings.dayStartHour+'時。過去の記録日は保持します。';
  $('countDay').max=today();if($('countDay').value>today())$('countDay').value=today();
  $('sessionHistory').innerHTML=state.sessions.length?[...state.sessions].sort((a,b)=>b.startedAt.localeCompare(a.startedAt)).map(s=>{const x=B.sessionSummary(state,s.id);return '<details style="margin:12px 0"><summary>'+esc(stamp(s.startedAt))+'から ／ '+x.count+'缶 ／ '+(s.finishedAt?'終了':'終了未記録')+'</summary>'+summaryHTML(x)+'<div class="timeline">'+timeline(x.drinks)+'</div></details>';}).join(''):'<p class="muted">これからの記録を飲酒セッションごとに表示します。以前の記録は下の日別履歴に残っています。</p>';
 }
 $('sessionFinishedAt').oninput=()=>{finishDirty=true;};
 $('finishBtn').onclick=()=>guarded(()=>{
  const s=B.activeSession(state);if(!s)throw Error('終了する飲酒セッションがありません');
  const when=finishDirty?$('sessionFinishedAt').value+':00+09:00':new Date().toISOString();
  if(Date.parse(when)>Date.now()+60000)throw Error('未来の終了時刻は保存できません');
  const next=B.finish(state,when,s.id),n=B.sessionSummary(state,s.id).count;
  askReview('今回の飲酒 '+n+'缶を '+stamp(when)+' に終了します。以前の未設定記録は変更しません。保存時に変更前のJSONもダウンロードします。',()=>{exportJson();finishDirty=false;commit(next,true);note('今回の飲酒の終了時刻を保存しました。変更前のJSONもダウンロードしました。');});
 });
 $('dayBoundaryForm').onsubmit=event=>{event.preventDefault();guarded(()=>{
  const next=structuredClone(state);next.settings.dayStartHour=Number($('dayStartHour').value);B.canonical(next);
  if(next.settings.dayStartHour===state.settings.dayStartHour){note('区切り時刻は現在と同じです。');return;}
  askReview('1日の区切りを日本時間 '+next.settings.dayStartHour+'時に変更します。これからの詳細記録と今日の表示に適用し、過去の記録日は変えません。保存時に変更前のJSONもダウンロードします。',()=>{exportJson();commit(next,true);note('区切り時刻を変更しました。過去の記録日・本数はそのままです。');});
 });};
 window.BeerSessionUI={render};render();
})();
