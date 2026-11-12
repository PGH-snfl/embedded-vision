"""Real DOM clicks; no browser networking or paid analysis."""
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
NODE='/home/snowflower/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node'


def test_model_button_selection_persistence_and_existing_photo_reanalysis(tmp_path):
    output=tmp_path/'ui.cjs';entry=tmp_path/'entry.js'
    entry.write_text(f"export * from '{ROOT}/frontend/analysis-model.js?v=analysis-model-1';\nexport * from '{ROOT}/frontend/planner.js';\n")
    # Keep the planner and selector real; inventory drawing is outside this test.
    build=tmp_path/'build.cjs'
    # An ESM build plugin isolates only the unrelated inventory renderer.
    build.write_text("const esbuild=require("+repr(str(ROOT/'third_party/velxio/frontend/node_modules/esbuild'))+");esbuild.build({entryPoints:[process.argv[2]],outfile:process.argv[3],bundle:true,platform:'node',format:'cjs',plugins:[{name:'inventory-test-double',setup(b){b.onResolve({filter:/\\/inventory\\.js/},a=>({path:a.path,namespace:'stub'}));b.onLoad({filter:/.*/,namespace:'stub'},()=>({contents:'export function initInventory(){return {load:async()=>({}),render(){},clearAuto(){}}}',loader:'js'}));}}]}).catch(e=>{console.error(e);process.exit(1)});")
    subprocess.run([NODE,str(build),str(entry),str(output)],check=True,capture_output=True)
    script=r'''
const assert=require('node:assert/strict'),fs=require('node:fs');
const {JSDOM}=require(process.argv[2]);
const dom=new JSDOM(fs.readFileSync(process.argv[3],'utf8'),{url:'http://localhost/w/'+'a'.repeat(32)+'/'});
global.window=dom.window;global.document=dom.window.document;global.location=dom.window.location;
global.localStorage=dom.window.localStorage;global.CustomEvent=dom.window.CustomEvent;
const {initAnalysisModel,selectedAnalysisModel,initPlanner}=require(process.argv[1]);
const SOL='gpt-6.1-sol',ASTRA='gpt-6-astra',key='ev-analysis-model:test';
let requests=[];global.fetch=()=>{throw Error('No automatic networking on model selection')};
initAnalysisModel({storageKey:key});
const button=document.querySelector('#agent-model-button'),menu=document.querySelector('#agent-model-menu');
assert.match(button.textContent,/Sol/);menu.open=true;
document.querySelector(`[data-analysis-model="${ASTRA}"]`).click();
assert.equal(selectedAnalysisModel(),ASTRA);assert.match(button.textContent,/Astra/);
assert.equal(document.querySelector(`[data-analysis-model="${ASTRA}"]`).getAttribute('aria-pressed'),'true');
assert.equal(menu.open,false);assert.equal(document.activeElement,button);assert.equal(localStorage.getItem(key),ASTRA);
initAnalysisModel({storageKey:key});assert.equal(selectedAnalysisModel(),ASTRA);
initAnalysisModel({storageKey:'other-workspace'});assert.equal(selectedAnalysisModel(),SOL);
const report={status:'reviewed_candidates',skill:{name:'embedded-system-inspection',http_calls:4},initial_ids:['P1'],added_ids:[],reviewed_ids:['P1'],grouped_ids:[],reviews:[{part_id:'P1',name:'Small IC',markings:['TEST'],disposition:'visible'}],crops:[{crop_id:'CROP1',part_ids:['P1'],purpose:'component_review'}],uninspected_regions:[]};
const pid='b'.repeat(32),plan={id:'c'.repeat(32),inventory:{},analysis_model:SOL,component_inspection:report};
let job={id:'old',status:'done',analysis_model:SOL,plan_id:plan.id,stale:false};
const state={data:{graph:{project_id:pid,revision:1,mode:'photo'}},assetId:'image'};
const esc=s=>String(s??'').replaceAll('<','&lt;');
const api=async url=>{requests.push(['GET',url]);if(url.endsWith('/auto-analysis'))return {configured:true,job};if(url.endsWith('/new-design'))return {};if(url==='/api/planner/status')return {configured:true};return {plan};};
const post=async(url,body)=>{requests.push(['POST',url,body]);job={...job,id:'new',analysis_model:body.model,plan_id:null};return {job};};
const planner=initPlanner({state,api,post,run:f=>f(),message(){},esc,renderVisuals(){}});
const pause=()=>new Promise(resolve=>setImmediate(resolve));
(async()=>{
 planner.render();await pause();await pause();
 assert.equal(document.querySelector('#auto-start'),null);
 assert.match(document.querySelector('.component-inspection summary').textContent,/1\/1/);
 assert.match(document.querySelector('.inspection-crops img').src,/inspection\/CROP1$/);
 assert.match(document.querySelector('.inspection-crops figcaption').textContent,/Small IC/);
 const before=requests.length;
 document.querySelector(`[data-analysis-model="${ASTRA}"]`).click();
 assert.equal(requests.length,before);assert.match(document.querySelector('#auto-start').textContent,/Astra로 다시 분석/);
 assert.match(document.querySelector('#auto-analysis-panel .tag').textContent,/Sol/);
 document.querySelector('#auto-start').click();await pause();await pause();
 const calls=requests.filter(r=>r[0]==='POST');assert.equal(calls.length,1);
 assert.equal(calls[0][1],'/auto-analysis?retry=true');assert.equal(calls[0][2].model,ASTRA);
 assert.match(document.querySelector('#auto-analysis-panel .tag').textContent,/Astra/);
 assert.equal(document.querySelector('.component-inspection'),null,'old plan crops are not shown as a new job review');
 job={...job,status:'error',failed_stage:'components',message:'OpenAI API HTTP 400. 요청 설정 오류.',error:{task:'component_inventory',http_calls:1,param:'tools[0].environment',request_id:'req_unit'}};
 await planner.refresh();await pause();await pause();
 const alert=document.querySelector('.analysis-failure[role=alert]');assert.ok(alert);
 assert.match(alert.querySelector('.errors').textContent,/HTTP 400/);
 assert.equal(alert.querySelector('.errors').closest('details'),null,'failure must be visible without opening details');
 assert.match(alert.textContent,/구성품 목록/);assert.match(alert.textContent,/tools\[0\].environment/);
 assert.equal(requests.filter(r=>r[0]==='POST').length,1,'a failed job is not automatically retried');
 menu.open=true;menu.dispatchEvent(new dom.window.KeyboardEvent('keydown',{key:'Escape',bubbles:true}));assert.equal(menu.open,false);
 initAnalysisModel({storageKey:'blocked',storage:{getItem(){throw Error('blocked')},setItem(){throw Error('blocked')}}});
 document.querySelector(`[data-analysis-model="${ASTRA}"]`).click();assert.equal(selectedAnalysisModel(),ASTRA);
 console.log('Model selector DOM: choice, actual job label, persistence, workspace isolation, explicit reanalysis, Escape, blocked storage passed');
})().catch(e=>{console.error(e);process.exit(1)});
'''
    result=subprocess.run([NODE,'-e',script,str(output),str(ROOT/'third_party/velxio/frontend/node_modules/jsdom'),str(ROOT/'frontend/index.html')],capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stderr
