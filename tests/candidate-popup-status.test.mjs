import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
const require=createRequire(import.meta.url);
const {JSDOM}=require('jsdom');

test('manual candidate selection updates inline simulator without opening a new tab',async()=>{
  const dom=new JSDOM('<main id="parent"><div id="function-intent"></div></main>',{url:'http://127.0.0.1:8766/'});
  globalThis.window=dom.window;globalThis.document=dom.window.document;globalThis.location=dom.window.location;
  let popups=0;window.open=()=>{popups++;return null;};
  const {renderFunctionIntent}=await import('../frontend/function-intent.js');
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const candidate={id:'blink',kind:'led_blink',title:'LED 점멸',plausibility:'medium',rationale:'LED',input_behavior:'전원',output_behavior:'점멸',evidence:[],assumptions:[],distinguishing_check:'확인'};
  const intent={status:'UNKNOWN',kind:'unknown',summary:'확인 필요',evidence:[],unknowns:[],acceptance_criteria:[],display_text:null};
  const original={function:intent,function_options:[],function_hypotheses:[candidate],recommended_hypothesis_id:'blink',hypothesis_previews:[{candidate_id:'blink',proposal:{simulator_supported:true}}],proposals:[]};
  const next={...original,function:{...intent,status:'USER_DEFINED',kind:'led_blink'},recommended:'arduino_led_blink',function_version:'v1',proposals:[{recipe:'arduino_led_blink',simulator_supported:true}]};
  let complete;
  const changed=new Promise(resolve=>{complete=resolve;});
  const api=async url=>url.includes('/function-candidate')?next:{};
  const config={data:original,api,endpoint:'/api/test',revision:1,esc,onChange:()=>{
    document.querySelector('#parent').innerHTML='<div id="function-intent"></div>';
    renderFunctionIntent(document.querySelector('#function-intent'),{...config,data:next});
    complete();
  }};
  const old=document.querySelector('#function-intent');
  renderFunctionIntent(old,config);
  old.querySelector('[data-candidate]').click();
  await changed;
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(old.isConnected,false);
  assert.equal(popups,0);
  assert.match(document.querySelector('#function-intent [data-candidate-status]').textContent,/회로와 시뮬레이터를 위에서 준비/);
  dom.window.close();
});

test('each candidate shows only its own simulation behavior before its button',async()=>{
  const dom=new JSDOM('<div id="function-intent"></div>',{url:'http://127.0.0.1:8766/'});
  globalThis.window=dom.window;globalThis.document=dom.window.document;globalThis.location=dom.window.location;
  const {renderFunctionIntent}=await import('../frontend/function-intent.js');
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const candidate=(id,kind)=>({id,kind,title:id,plausibility:'medium',rationale:'추정',input_behavior:'입력',output_behavior:'방향 미상',evidence:[],assumptions:[],distinguishing_check:'확인'});
  const data={function:{status:'UNKNOWN',kind:'unknown',summary:'',evidence:[],unknowns:[],acceptance_criteria:[],display_text:null},function_options:[],function_hypotheses:[candidate('light','light_led'),candidate('blink','led_blink')],recommended_hypothesis_id:'light',hypothesis_previews:[{candidate_id:'blink',proposal:{simulator_supported:true,simulation_behavior:'0.5초마다 점멸'}},{candidate_id:'light',proposal:{simulator_supported:true,simulation_behavior:'어두우면 켜고 밝으면 끕니다'}}],proposals:[]};
  const host=document.querySelector('#function-intent');
  renderFunctionIntent(host,{data,api:async()=>{},endpoint:'',revision:1,esc,onChange:()=>{}});
  const light=host.querySelector('[data-candidate="light"]').closest('article');
  const blink=host.querySelector('[data-candidate="blink"]').closest('article');
  assert.match(light.textContent,/방향 미상/);
  assert.match(light.querySelector('.simulation-assumptions').textContent,/어두우면 켜고 밝으면 끕니다/);
  assert.match(blink.querySelector('.simulation-assumptions').textContent,/0\.5초마다 점멸/);
  assert.doesNotMatch(blink.textContent,/어두우면 켜고/);
  dom.window.close();
});
