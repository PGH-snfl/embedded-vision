"""Exercise the embedded editor's message boundary and saved revision contract."""
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ESBUILD = ROOT / 'third_party/velxio/frontend/node_modules/.bin/esbuild'


def bundle(tmp_path, name):
    target = tmp_path / (name + '.cjs')
    subprocess.run([str(ESBUILD), str(ROOT / 'frontend' / (name + '.js')),
                    '--bundle', '--platform=node', '--format=cjs', '--target=node12',
                    '--outfile=' + str(target)], check=True, capture_output=True)
    return target


def run_node(script, module):
    subprocess.run(['node', '-e', script, str(module)], check=True,
                   capture_output=True, text=True)


def test_motion_request_checks_origin_source_channel_and_prevents_duplicates(tmp_path):
    module = bundle(tmp_path, 'robot-workbench')
    script = r'''
const assert = require('assert');
const { TextEncoder } = require('util');
global.TextEncoder = TextEncoder;
global.crypto = {getRandomValues(a) { return require('crypto').randomFillSync(a); }};
global.btoa = s => Buffer.from(s, 'binary').toString('base64');
global.location = {pathname:'/', origin:'http://127.0.0.1:8766', hostname:'127.0.0.1'};
const listeners = new Map();
global.window = {
  addEventListener(name, cb) { listeners.set(name, cb); },
  removeEventListener(name, cb) { if(listeners.get(name) === cb) listeners.delete(name); },
};
const frameWindow = {messages: [], postMessage(message, origin) { this.messages.push({message, origin}); }};
const frame = {contentWindow: frameWindow, inert:false};
const status = {textContent:''};
const host = {innerHTML:'', isConnected:true,
  querySelector(s) {return s === 'iframe' ? frame : status;}};
const {mountRobotWorkbench} = require(process.argv[1]);
let release, calls = 0;
const blocking = new Promise(resolve => {release = resolve;});
const cleanup = mountRobotWorkbench(host, {project:{embeddedVision:{}}, onMotion:async (payload, saved) => {
  calls++;
  assert.deepStrictEqual(payload, {wires:[]});
  saved(-1); saved('3'); saved(3);
  await blocking;
}});
const url = new URL(frame.src);
assert.equal(url.origin, 'http://127.0.0.1:8768');
const channel = url.searchParams.get('channel');
assert.match(channel, /^[a-f0-9]{48}$/);
const valid = {source:frameWindow, origin:url.origin, data:{type:'ev:motion-request',channel,payload:{wires:[]}}};
const dispatch = event => listeners.get('message')(event);
dispatch({...valid,origin:'https://evil.example'});
dispatch({...valid,source:{}});
dispatch({...valid,data:{...valid.data,channel:'wrong'}});
dispatch({...valid,data:{...valid.data,type:'other'}});
assert.equal(calls,0);
const report={...valid,data:{type:'ev:editor-status',channel,phase:'loading',message:'배치 계산 중'}};
dispatch({...report,origin:'https://evil.example'});assert.notEqual(status.textContent,'배치 계산 중');
dispatch(report);assert.equal(status.textContent,'배치 계산 중');
dispatch({...report,data:{...report.data,phase:'other',message:'invalid'}});assert.equal(status.textContent,'배치 계산 중');
dispatch({...report,data:{...report.data,phase:'ready',message:'회로 준비됨'}});frame.onload();assert.equal(status.textContent,'회로 준비됨');
dispatch(valid);
assert.equal(calls,1);
assert.equal(frame.inert,true);
dispatch(valid);
assert.equal(calls,1);
assert.deepStrictEqual(frameWindow.messages,[{origin:url.origin,message:{type:'ev:revision-saved',channel,revision:3}}]);
release();
setImmediate(() => {
  assert.equal(frame.inert,false);
  assert.match(status.textContent,/저장했습니다/);
  host.isConnected=false;
  dispatch(valid);
  assert.equal(calls,1);
  cleanup();
  assert.equal(listeners.has('message'),false);
});
'''
    run_node(script, module)


def test_translation_request_checks_sender_and_returns_result_to_frame(tmp_path):
    module = bundle(tmp_path, 'robot-workbench')
    script = r'''
const assert=require('assert'); global.TextEncoder=require('util').TextEncoder;
global.crypto={getRandomValues:a=>require('crypto').randomFillSync(a)};
global.btoa=s=>Buffer.from(s,'binary').toString('base64');
global.location={pathname:'/',origin:'http://127.0.0.1:8766',hostname:'127.0.0.1'};
const listeners=new Map();global.window={addEventListener:(n,f)=>listeners.set(n,f),removeEventListener:(n,f)=>listeners.delete(n)};
const frameWindow={messages:[],postMessage(message,origin){this.messages.push({message,origin})}};
const frame={contentWindow:frameWindow},status={};
const host={isConnected:true,querySelector:s=>s==='iframe'?frame:status};
const {mountRobotWorkbench}=require(process.argv[1]);let calls=0,release;
const wait=new Promise(r=>release=r);
const snapshot={format:'velxio-project',wires:[]};
const close=mountRobotWorkbench(host,{project:{embeddedVision:{}},onTranslate:async (source,target,project)=>{calls++;assert.equal(source,'source');assert.equal(target,'arduino_cpp');assert.deepStrictEqual(project,snapshot);await wait;return {code:'result',filename:'test.ino'};}});
const url=new URL(frame.src),channel=url.searchParams.get('channel'),requestId='a'.repeat(32);
const event={source:frameWindow,origin:url.origin,data:{type:'ev:translate-request',channel,requestId,source:'source',target:'arduino_cpp',project:snapshot}};
const dispatch=e=>listeners.get('message')(e);
dispatch({...event,origin:'https://bad.example'});dispatch({...event,source:{}});
dispatch({...event,data:{...event.data,channel:'incorrect'}});
dispatch({...event,data:{...event.data,requestId:'bad'}});
dispatch({...event,data:{...event.data,source:'x'.repeat(50001)}});
dispatch({...event,data:{...event.data,target:'bad'}});assert.equal(calls,0);
dispatch(event);dispatch({...event,data:{...event.data,requestId:'b'.repeat(32)}});assert.equal(calls,1);release();
setImmediate(()=>{assert.equal(frameWindow.messages[0].message.requestId,'b'.repeat(32));assert.match(frameWindow.messages[0].message.error,/처리 중/);assert.deepStrictEqual(frameWindow.messages[1],{origin:url.origin,message:{type:'ev:translate-result',channel,requestId,result:{code:'result',filename:'test.ino'}}});close();});
'''
    run_node(script, module)


def test_editor_tab_motion_reply_only_for_valid_request(tmp_path):
    module = bundle(tmp_path, 'robot-workbench')
    script = r'''
const assert=require('assert');global.TextEncoder=require('util').TextEncoder;
global.crypto={getRandomValues:a=>require('crypto').randomFillSync(a)};
global.btoa=s=>Buffer.from(s,'binary').toString('base64');
global.location={pathname:'/',origin:'http://127.0.0.1:8766',hostname:'127.0.0.1'};
const listeners=new Map();global.window={addEventListener:(n,f)=>listeners.set(n,f),removeEventListener:(n,f)=>listeners.delete(n)};
const frameWindow={messages:[],postMessage(message,origin){this.messages.push({message,origin})}};
const frame={contentWindow:frameWindow},status={};const host={isConnected:true,querySelector:s=>s==='iframe'?frame:status};
const {mountRobotWorkbench}=require(process.argv[1]);let calls=0;
mountRobotWorkbench(host,{project:{embeddedVision:{}},motionTab:true,onMotion:async (payload,saved)=>{calls++;saved(4);return 'http://127.0.0.1:8766/rover-motion.html?revision=4';}});
const url=new URL(frame.src),channel=url.searchParams.get('channel'),requestId='a'.repeat(32);
assert.equal(url.searchParams.get('motion_tab'),'1');
const event={source:frameWindow,origin:url.origin,data:{type:'ev:motion-request',channel,popup:true,requestId,payload:{}}};
const dispatch=e=>listeners.get('message')(e);
dispatch({...event,origin:'https://bad.example'});dispatch({...event,data:{...event.data,popup:false}});dispatch({...event,data:{...event.data,requestId:'bad'}});assert.equal(calls,0);
dispatch(event);setImmediate(()=>{assert.equal(calls,1);assert.deepStrictEqual(frameWindow.messages.map(x=>x.message.type),['ev:revision-saved','ev:motion-result']);assert.equal(frameWindow.messages[1].message.requestId,requestId);assert.match(frameWindow.messages[1].message.url,/rover-motion.html/);});
'''
    run_node(script, module)


def test_editor_commit_tracks_server_revision_and_rejects_stale_writer(tmp_path):
    module = bundle(tmp_path, 'rover-circuit-storage')
    script = r'''
const assert = require('assert');
const {createRoverCircuitStorage} = require(process.argv[1]);
(async () => {
 let revision=4, graph={version:1,components:[],connections:[]};
 const calls=[];
 const api=async (url, options) => {
   if (!options) return {revision,circuit:graph};
   const body=JSON.parse(options.body); calls.push({url,body});
   if (body.expected_revision !== revision) throw Error('다른 화면에서 회로가 변경되었습니다.');
   if (url.endsWith('/commit')) {
     graph={version:1,components:[],connections:[{id:body.project.id}]};
     return {revision:++revision,circuit:graph,validation:{allowed:true}};
   }
   if (url.endsWith('/validate')) return {revision,allowed:true};
   throw Error('unexpected request');
 };
 const store=createRoverCircuitStorage(api,'/project','goal-v1');
 await assert.rejects(store.commitEditor({id:'initial'}),/불러오지/);
 await store.load();
 const result=await store.commitEditor({id:'wire-a'});
 assert.deepStrictEqual(result,{revision:5,validation:{allowed:true}});
 assert.equal(store.revision(),5);
 assert.equal(store.snapshot().connections[0].id,'wire-a');
 assert.equal(calls[0].body.expected_revision,4);
 assert.equal(calls[0].body.function_version,'goal-v1');
 await store.validate();
 assert.equal(calls[1].body.expected_revision,5);
 revision++;
 await assert.rejects(store.commitEditor({id:'stale'}),/다른 화면/);
 assert.equal(store.revision(),5);
 assert.equal(store.snapshot().connections[0].id,'wire-a');
})().catch(e=>{console.error(e);process.exit(1)});
'''
    run_node(script, module)
