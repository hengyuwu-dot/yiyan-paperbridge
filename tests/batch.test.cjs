const test = require('node:test');
const assert = require('node:assert/strict');
const {BatchQueue, processing} = require('../paperbridge/static/batch.js');
function storage(){ const map = new Map(); return {getItem:k=>map.get(k),setItem:(k,v)=>map.set(k,v)}; }
test('batch continues after validation failures and snapshots settings across asynchronous requests', async () => {
  const saved = storage(), queue = new BatchQueue(saved);
  const ids = ['a','b','c','d'].map(c=>c.repeat(32));
  ids.forEach((id,i)=>queue.add({id,name:`${i}.pdf`,status:i===3?'complete':'ready'}));
  const settings = {pages:'2-3',glossary:'flux = 通量'};
  const submitted = [];
  await queue.start(settings,async(id,chosen)=>{
    submitted.push({id,settings:{...chosen}}); settings.glossary = 'changed';
    if(id===ids[1]) throw new Error('页码超出范围');
    return {id,name:'paper.pdf',status:'queued',progress:0};
  },()=>{});
  assert.deepEqual(submitted.map(s=>s.id),ids.slice(0,3));
  assert.ok(submitted.every(s=>s.settings.glossary==='flux = 通量'));
  assert.equal(queue.items[1].error,'页码超出范围');
  const restored = new BatchQueue(saved);
  assert.equal(restored.items[2].status,'queued'); assert.ok(processing(restored.items[0].status));
  restored.clear(); assert.equal(new BatchQueue(saved).items.length,0);
});

test('submission failures survive status refresh and disappear on a successful retry', async () => {
  const queue = new BatchQueue(storage()), id = 'e'.repeat(32);
  queue.add({id,name:'one-page.pdf',status:'ready',progress:0});
  await queue.start({pages:'2-3'},async()=>{throw new Error('页码超出范围')},()=>{});
  queue.update({id,name:'one-page.pdf',status:'ready',progress:0});
  assert.equal(queue.items[0].error,'页码超出范围');
  await queue.start({pages:'1'},async()=>({id,name:'one-page.pdf',status:'queued',progress:0,settings:{pages:'1'}}),()=>{});
  assert.equal(queue.items[0].error,undefined); assert.equal(queue.items[0].pages,'1');
});

test('late status replies cannot revive a cleared list or update a newly added paper', async () => {
  const queue = new BatchQueue(storage()), first='f'.repeat(32), second='a'.repeat(32);
  queue.add({id:first,name:'old.pdf',status:'ready'});
  let resolve;
  const pending=queue.refresh(()=>new Promise(done=>{resolve=done}));
  queue.clear(); queue.add({id:second,name:'new.pdf',status:'ready'});
  resolve({id:first,name:'old.pdf',status:'complete',progress:100});
  await pending;
  assert.deepEqual(queue.items.map(item=>[item.id,item.status]),[[second,'ready']]);
  await queue.refresh(async()=>{throw new Error('服务暂时断开')});
  assert.equal(queue.items[0].fetchError,'服务暂时断开');
  await queue.refresh(async()=>({id:second,name:'new.pdf',status:'ready'}));
  assert.equal(queue.items[0].fetchError,undefined);
});

test('removing an idle paper preserves others, rejects active tasks, and ignores its late refresh',async()=>{
  const queue=new BatchQueue(storage()), idle='1'.repeat(32),active='2'.repeat(32);
  queue.add({id:idle,name:'idle.pdf',status:'ready'});queue.add({id:active,name:'active.pdf',status:'running'});
  let finish;
  const pending=queue.refresh(id=>id===idle ? new Promise(resolve=>{finish=resolve}) : Promise.resolve({id:active,name:'active.pdf',status:'running'}));
  assert.equal(queue.remove(active),false);assert.equal(queue.remove(idle),true);
  finish({id:idle,name:'idle.pdf',status:'complete'});await pending;
  assert.deepEqual(queue.items.map(item=>item.id),[active]);assert.equal(queue.remove(idle),false);
});
