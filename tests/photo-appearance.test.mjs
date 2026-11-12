import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
const require=createRequire(new URL('../third_party/velxio/frontend/package.json',import.meta.url));
const {JSDOM}=require('jsdom'),dom=new JSDOM('<div id="host"></div>',{url:'http://127.0.0.1:8897/'});
globalThis.location=dom.window.location;globalThis.window=dom.window;globalThis.document=dom.window.document;
const {renderPhotoAppearance}=await import('../frontend/photo-appearance.js');
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const scene={summary:'<script>photo</script>',objects:[{label:'<img src=x>',geometry:{shape:'box'}},{label:'hidden',geometry:null}]};
test('opens the existing photo workbench with no new inference or export',async()=>{
 const host=document.querySelector('#host'),opened={opener:{},location:'',close(){}};window.open=()=>opened;
 const calls=[];renderPhotoAppearance(host,{scene,esc,endpoint:'/api/example',api:async url=>{calls.push(url);return {format:'velxio-project',components:[],embeddedVision:{focus_photo_on_open:true}};}});
 assert.match(host.textContent,/사진 기반 구조 · 1개/);assert.equal(host.querySelectorAll('script,img').length,0);
 await host.querySelector('button').onclick();assert.deepEqual(calls,['/api/example/photo-workbench']);
 assert.equal(new URL(opened.location).pathname,'/editor');assert.equal(opened.opener,null);
 renderPhotoAppearance(host,{scene,esc,stale:true});assert.equal(host.innerHTML,'');
});
test('closes the reserved tab and enables retry when geometry cannot be loaded',async()=>{
 const host=document.querySelector('#host');let closed=false;window.open=()=>({opener:{},close:()=>{closed=true;}});
 renderPhotoAppearance(host,{scene,esc,endpoint:'/api/example',api:async()=>{throw Error('입력이 변경되었습니다.');}});
 await host.querySelector('button').onclick();assert.equal(closed,true);assert.equal(host.querySelector('button').disabled,false);
 assert.match(host.querySelector('[role=status]').textContent,/입력이 변경/);
});
