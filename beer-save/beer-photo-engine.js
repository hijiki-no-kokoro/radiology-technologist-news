(function(root){
  'use strict';
  const LIBRARIES={barcode:'./vendor/zxing-browser-0.2.1.min.js',ocr:'./vendor/tesseract-7.0.0.min.js'};
  const CORE='https://cdn.jsdelivr.net/npm/tesseract.js-core@7.0.0';
  const MODEL_ROOT='https://cdn.jsdelivr.net/npm/@tesseract.js-data/';
  const loads=new Map();let active=null,sequence=0;
  const abortError=()=>new DOMException('読み取りを中止しました','AbortError');
  function race(promise,signal){
    if(signal.aborted)return Promise.reject(abortError());
    return new Promise((resolve,reject)=>{const stop=()=>reject(abortError());signal.addEventListener('abort',stop,{once:true});Promise.resolve(promise).then(resolve,reject).finally(()=>signal.removeEventListener('abort',stop));});
  }
  function load(kind){
    if(kind==='barcode'&&root.ZXingBrowser)return Promise.resolve();
    if(kind==='ocr'&&root.Tesseract)return Promise.resolve();
    if(loads.has(kind))return loads.get(kind);
    const task=new Promise((resolve,reject)=>{const script=document.createElement('script');let timer;
      const finish=error=>{clearTimeout(timer);script.onload=null;script.onerror=null;if(error){script.remove();loads.delete(kind);reject(error);}else resolve();};
      script.src=new URL(LIBRARIES[kind],document.baseURI).href;script.onload=()=>finish();script.onerror=()=>finish(Error('認識機能を読み込めません。通信を確認するか、手動で登録してください。'));
      timer=setTimeout(()=>finish(Error('認識機能の読み込みが時間切れになりました。手動登録も利用できます。')),20000);document.head.append(script);
    });loads.set(kind,task);return task;
  }
  function release(job){
    if(job.url){URL.revokeObjectURL(job.url);job.url=null;}
    if(job.image){job.image.src='';job.image=null;}
    for(const canvas of job.canvases){canvas.width=1;canvas.height=1;}job.canvases=[];
    if(job.worker){job.worker.terminate().catch(()=>{});job.worker=null;}
    if(active===job)active=null;
  }
  function cancel(){if(active){active.controller.abort();release(active);}}
  async function canvasFor(file,job){
    if(file.size>25*1024*1024)throw Error('25MB以下の画像を選んでください。撮影サイズを小さくすると読み取りやすくなります。');
    if(file.type&&!file.type.startsWith('image/'))throw Error('写真のファイルを選んでください。');
    const image=new Image();job.image=image;job.url=URL.createObjectURL(file);
    await race(new Promise((resolve,reject)=>{image.onload=resolve;image.onerror=()=>reject(Error('この画像形式を読み込めません。JPEGまたはPNGの写真を選んでください。'));image.src=job.url;}),job.controller.signal);
    if(!image.naturalWidth||!image.naturalHeight)throw Error('画像の大きさを確認できません');
    const scale=Math.min(1,1800/Math.max(image.naturalWidth,image.naturalHeight));
    const canvas=document.createElement('canvas');canvas.width=Math.max(1,Math.round(image.naturalWidth*scale));canvas.height=Math.max(1,Math.round(image.naturalHeight*scale));job.canvases.push(canvas);
    const ctx=canvas.getContext('2d',{willReadFrequently:true});if(!ctx)throw Error('画像処理を利用できません');
    ctx.fillStyle='white';ctx.fillRect(0,0,canvas.width,canvas.height);ctx.drawImage(image,0,0,canvas.width,canvas.height);return canvas;
  }
  async function barcode(canvas,job){
    await race(load('barcode'),job.controller.signal);
    const reader=new root.ZXingBrowser.BrowserMultiFormatReader();
    reader.possibleFormats=[root.ZXingBrowser.BarcodeFormat.EAN_13,root.ZXingBrowser.BarcodeFormat.EAN_8,root.ZXingBrowser.BarcodeFormat.UPC_A];
    for(let rotation=0;rotation<2;rotation++){
      if(job.controller.signal.aborted)throw abortError();let target=canvas;
      if(rotation){target=document.createElement('canvas');target.width=canvas.height;target.height=canvas.width;job.canvases.push(target);const ctx=target.getContext('2d');ctx.translate(target.width/2,target.height/2);ctx.rotate(Math.PI/2);ctx.drawImage(canvas,-canvas.width/2,-canvas.height/2);}
      try{const result=reader.decodeFromCanvas(target),code=root.BeerRecognition.jan(result.getText());if(code)return code;}catch(error){if(error.name==='AbortError')throw error;}
      await race(new Promise(resolve=>setTimeout(resolve,0)),job.controller.signal);
    }
    return '';
  }
  async function ocr(canvas,job,progress){
    await race(load('ocr'),job.controller.signal);progress('文字認識データを準備しています（初回は通信が必要です）');
    const pending=root.Tesseract.createWorker('jpn',1,{langPath:MODEL_ROOT+'jpn@1.0.0/4.0.0_best_int',workerPath:new URL('./vendor/tesseract-worker-7.0.0.min.js',document.baseURI).href,corePath:CORE,workerBlobURL:false,cacheMethod:'none',errorHandler:error=>{job.error=Error('文字認識を初期化できませんでした。通信を確認してください。');job.controller.abort();},logger:event=>{if(!job.controller.signal.aborted&&event.status==='recognizing text')progress('文字を読み取っています '+Math.round(event.progress*100)+'%');}});
    pending.then(worker=>{if(job.controller.signal.aborted)worker.terminate().catch(()=>{});}).catch(()=>{});
    job.worker=await race(pending,job.controller.signal);
    await race(job.worker.setParameters({tessedit_pageseg_mode:root.Tesseract.PSM.SPARSE_TEXT,user_defined_dpi:'300'}),job.controller.signal);
    const result=await race(job.worker.recognize(canvas,{}, {text:true}),job.controller.signal);
    return {text:result.data.text||'',confidence:result.data.confidence||0};
  }
  async function scan(file,{mode='front',progress=()=>{}}={}){
    cancel();const job={id:++sequence,controller:new AbortController(),canvases:[],worker:null,image:null,url:null};active=job;
    const timer=setTimeout(()=>job.controller.abort(),90000);
    try{
      progress('写真を端末内で準備しています');const canvas=await canvasFor(file,job);let code='',read={text:'',confidence:0},barcodeError=null;
      if(mode!=='nutrition'){progress('バーコードを読み取っています');try{code=await barcode(canvas,job);}catch(error){if(error.name==='AbortError')throw error;barcodeError=error.message;}}
      if(mode!=='barcode'){try{read=await ocr(canvas,job,progress);}catch(error){if(error.name==='AbortError')throw error;if(!code)throw error;read={text:'',confidence:0,ocrError:error.message};}}
      if(job.controller.signal.aborted)throw abortError();return {barcode:code,text:read.text,confidence:read.confidence,barcodeError};
    }catch(error){throw job.error||error;}finally{clearTimeout(timer);release(job);file=null;}
  }
  root.BeerPhotoEngine={scan,cancel};window.addEventListener('pagehide',cancel);
})(window);
