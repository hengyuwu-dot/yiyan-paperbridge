const test = require('node:test');
const assert = require('node:assert/strict');
const {SynchronizedReader, fraction, documentTerms} = require('../paperbridge/static/reader.js');

test('new papers inherit saved terminology while existing papers retain their own choices', () => {
  const saved = 'flux ratio = 自定通量比';
  assert.equal(documentTerms({glossary:''}, saved, true), saved);
  assert.equal(documentTerms({glossary:'prior = 本篇先验'}, saved, false), 'prior = 本篇先验');
  assert.equal(documentTerms({glossary:''}, saved, false), '');
  assert.equal(documentTerms({}, saved, false), saved);
});

function pane(height, width) {
  return {scrollTop:0, scrollLeft:0, scrollHeight:height, clientHeight:400,
    scrollWidth:width, clientWidth:300, addEventListener(){}};
}
test('same normalized reading position in differently sized pages, from either pane', () => {
  const left = pane(1200,600), right = pane(1400,700);
  const reader = Object.create(SynchronizedReader.prototype);
  Object.assign(reader,{panes:[left,right],expected:new WeakMap(),enabled:true});
  left.scrollTop = 400; left.scrollLeft = 150;
  reader.scrolled(left);
  assert.equal(right.scrollTop,500); assert.equal(right.scrollLeft,200);
  reader.scrolled(right); // Ignore the generated event, preventing a feedback loop.
  assert.equal(reader.active,left);
  right.scrollTop = 800; right.scrollLeft = 320;
  reader.scrolled(right);
  assert.equal(left.scrollTop,640); assert.equal(left.scrollLeft,240);
  reader.enabled = false; left.scrollTop = 100; reader.scrolled(left);
  assert.equal(right.scrollTop,800);
  reader.reset(); assert.equal(left.scrollTop,0); assert.equal(right.scrollTop,0);
});
test('short pages and boundary scroll values do not create invalid coordinates', () => {
  assert.equal(fraction(10,0),0); assert.equal(fraction(-3,20),0);
  assert.equal(fraction(100,20),1);
});

test('independent zoom keeps each reading position; linked zoom applies to both', () => {
  const left = pane(1200,600), right = pane(1400,700);
  const papers = [left,right].map(p => ({style:{set width(v){
    this.value = v; p.scrollWidth = Number.parseFloat(v); p.scrollHeight = p.scrollWidth * 3;
  }}}));
  const reader = Object.create(SynchronizedReader.prototype);
  Object.assign(reader,{panes:[left,right],papers,scales:[100,100],sideZooms:[{},{ }],zoomControl:{},expected:new WeakMap(),enabled:false,active:left});
  left.scrollTop = 400; right.scrollTop = 800;
  reader.setZoom(0,200,false);
  assert.equal(papers[0].style.value,'552px'); assert.equal(papers[1].style.value,'276px');
  assert.equal(reader.sideZooms[0].value,'200'); assert.equal(reader.sideZooms[1].value,'100');
  assert.equal(fraction(left.scrollTop,left.scrollHeight-400),0.5);
  assert.equal(fraction(right.scrollTop,right.scrollHeight-400),0.8);
  reader.enabled = true; reader.setZoom(1,300,true);
  assert.equal(papers[0].style.value,'828px'); assert.equal(papers[1].style.value,'828px');
  assert.equal(reader.zoomControl.value,'300');
  assert.equal(fraction(right.scrollTop,right.scrollHeight-400),0.5);
});
