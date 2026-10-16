const {test}=require('node:test');
const assert=require('node:assert/strict');
const B=require('../beer-save/beer-core.js');
const R=require('../beer-save/beer-recognition.js');
const C=require('../beer-save/beer-catalog.js');
test('every generated single-can record has valid facts and a unique JAN',()=>{
  const seen=new Set();assert.ok(C.products.length>=478);
  for(const p of C.products){assert.equal(R.jan(p.janCode),p.janCode);assert.ok(!seen.has(p.janCode));seen.add(p.janCode);assert.doesNotThrow(()=>B.product(p));}
});
test('every unambiguous generated record is usable by barcode',()=>{
  for(const p of C.products){const plan=R.plan('',p.janCode,[],C.products);assert.equal(plan.candidates.length,1);assert.equal(plan.autoSave,!p.requiresConfirmation);}
});
test('changed same-JAN formulation cannot auto-save even with a saved copy',()=>{
  const original=C.products.find(p=>p.janCode==='4901004006714');
  const held={...original,requiresConfirmation:true};
  for(const saved of [[],[{id:'saved',...B.product(original)}]] ){
    const plan=R.plan('',original.janCode,saved,[held]);assert.equal(plan.autoSave,false);assert.equal(plan.conflict,true);assert.match(plan.reviewReason,/変更/);assert.equal(plan.candidates.length,1);
  }
});
test('unchanged saved copies do not become duplicate candidates',()=>{
  for(const p of C.products){const saved={id:'saved',...B.product(p)};const before=JSON.stringify(saved);const plan=R.plan('',p.janCode,[saved],C.products);assert.equal(plan.candidates.length,1);assert.equal(plan.autoSave,!p.requiresConfirmation);assert.equal(JSON.stringify(saved),before);}
});
test('OCR-only recognition never automatically records a new limited product',()=>{
  assert.equal(R.plan('季節限定ビール 350ml ALC.5%','',[],C.products).autoSave,false);
});
