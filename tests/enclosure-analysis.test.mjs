import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
const require=createRequire(new URL('../third_party/velxio/frontend/package.json',import.meta.url));
const {JSDOM}=require('jsdom');
const dom=new JSDOM('<div id="host"></div>',{url:'http://127.0.0.1:8897/'});
globalThis.location=dom.window.location;globalThis.window=dom.window;globalThis.document=dom.window.document;
const {renderEnclosureAnalysis}=await import('../frontend/enclosure-analysis.js');
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const node=(id,parent_id)=>({id,parent_id,name:'<script>bad</script>',role:'power',purpose:'<img src=x onerror=bad()>',candidate_parts:['후보'],rationale:'근거',alternatives:[],confidence:'medium'});
const analysis={summary:'<b>추정</b>',enclosures:[{name:'외장',rationale:'추론',modules:[node('supply',null),node('cap','supply')],assumptions:['가정'],unknowns:['미확인']}]};
test('shows a nested hypothesis tree, escapes input and clears stale results',()=>{
 const host=document.querySelector('#host');
 renderEnclosureAnalysis(host,{analysis,esc,endpoint:'/api/example'});
 assert.equal(host.querySelectorAll('.enclosure-module-tree li').length,2);
 assert.equal(host.querySelectorAll('script,img,b').length,0);
 assert.match(host.textContent,/내부 추정·3D 분해도/);assert.match(host.textContent,/실제 존재 여부 미확인/);
 assert.ok(host.querySelector('.compact-details:not([open])'));
 renderEnclosureAnalysis(host,{analysis,esc,stale:true});assert.equal(host.innerHTML,'');
});
test('does not leave a blank tab open if saved analysis is missing',async()=>{
 const host=document.querySelector('#host');let closed=false,requested='';
 window.open=()=>({opener:{},close:()=>{closed=true;}});
 renderEnclosureAnalysis(host,{analysis,esc,endpoint:'/api/example',api:async url=>{requested=url;return {available:false};}});
 await host.querySelector('[data-enclosure-open]').onclick();
 assert.equal(requested,'/api/example/enclosure-study');assert.equal(closed,true);
 assert.match(host.querySelector('[role=status]').textContent,/사진 분석을 다시 실행/);
});
test('shows selected parts and opens the wired implementation with runnable code',async()=>{
 const host=document.querySelector('#host');let requested='';const tab={opener:{},location:'',close(){}};window.open=()=>tab;
 const implementation={status:'DESIGN_SELECTED',title:'입력 제어',behavior:'다이얼로 밝기 제어',parts:[{id:'R1',name:'220Ω 저항',quantity:1,purpose:'전류 제한',selection_reason:'GPIO LED 구동',parameters:{value:'220'}}],connections:[{source:'U1.5',target:'R1.1'}],structures:[]};
 const project={format:'velxio-project',boards:[],components:[],wires:[],fileGroups:{},embeddedVision:{source_graph_sha256:'a'.repeat(64)}};
 renderEnclosureAnalysis(host,{analysis:null,implementation,esc,endpoint:'/api/example',functionVersion:'b'.repeat(64),api:async url=>{requested=url;return project;}});
 assert.match(host.textContent,/선정 완료/);assert.match(host.textContent,/220Ω 저항/);assert.doesNotMatch(host.textContent,/미확인|내부 후보/);
 await host.querySelector('[data-enclosure-open]').onclick();
 assert.match(requested,/functional-workbench\?function_version=/);assert.equal(new URL(tab.location).searchParams.get('autorun'),'1');
});
