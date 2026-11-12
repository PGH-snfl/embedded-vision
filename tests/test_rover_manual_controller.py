"""Test held controls, asynchronous verification and stopping behavior."""
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]


def test_manual_controls_reject_stale_validation_and_stop_on_focus_loss(tmp_path):
    bundle=tmp_path/'manual.cjs'
    subprocess.run([str(ROOT/'third_party/velxio/frontend/node_modules/.bin/esbuild'),str(ROOT/'frontend/rover-src/manual-control.js'),
                    '--bundle','--platform=node','--format=cjs','--target=node12',f'--outfile={bundle}'],check=True,capture_output=True)
    code=r'''
const assert=require('assert');const {createManualController,manualDirection}=require(process.argv[1]);
const tick=()=>new Promise(r=>setImmediate(r));const wait=ms=>new Promise(r=>setTimeout(r,ms));
class Emitter {constructor(){this.l={}} addEventListener(k,f){if(!this.l[k])this.l[k]=[];this.l[k].push(f)} removeEventListener(k,f){this.l[k]=(this.l[k]||[]).filter(x=>x!==f)} emit(k,e={}){for(const f of this.l[k]||[])f(e)}}
const doc=new Emitter();doc.hidden=false;doc.body={};doc.documentElement={};const win=new Emitter();
const btn=new Emitter();btn.dataset={roverHold:'forward'};btn.setPointerCapture=()=>{};
const host={querySelectorAll:()=>[btn],closest:()=>null,contains:t=>t===btn};
const key=(code,target=doc.body,repeat=false)=>({code,target,repeat,preventDefault(){}});
async function main(){
 assert.equal(manualDirection(['forward','left']),'forward-left');assert.equal(manualDirection(['forward','backward']),null);
 let pending=[],runs=[],stops=0,notes=[],enabled=true;
 const c=createManualController({host,doc,win,enabled:()=>enabled,validateMotion:()=>new Promise(resolve=>pending.push(resolve)),stop:()=>stops++,run:n=>runs.push(n),onStatus:m=>notes.push(m),recheckMs:20,timeoutMs:70});
 enabled=false;doc.emit('keydown',key('KeyW'));await tick();assert.equal(pending.length,0);enabled=true;
 doc.emit('keydown',key('KeyW'));await tick();assert.equal(pending.length,1);
 doc.emit('keyup',key('KeyW'));pending.shift()({allowed:true});await tick();assert.deepEqual(runs,[]);
 doc.emit('keydown',key('KeyW'));await tick();let old=pending.shift();
 doc.emit('keydown',key('KeyA'));await tick();let latest=pending.shift();old({allowed:true});await tick();assert.deepEqual(runs,[]);
 latest({allowed:true});await tick();assert.deepEqual(runs,['forward-left']);
 await wait(30);assert.equal(pending.length,1);pending.shift()({allowed:false,message:'회로 변경'});await tick();assert.equal(notes[notes.length-1],'회로 변경');assert(stops>=4);
 doc.emit('keydown',key('KeyW',doc.body,true));await tick();assert.equal(pending.length,0);
 const input={closest:()=>({})};doc.emit('keydown',key('KeyW',input));await tick();assert.equal(pending.length,0);
 // An idle manual controller must not stop an automatic drive when the user
 // focuses the obstacle-distance slider or another input.
 const idleStops=stops;doc.emit('focusin',{target:input});assert.equal(stops,idleStops);
 // A held manual key, on the other hand, is released when an input is focused.
 doc.emit('keydown',key('KeyW'));await tick();assert.equal(pending.length,1);
 const heldValidation=pending.shift(),heldStops=stops;doc.emit('focusin',{target:input});assert.equal(stops,heldStops+1);
 heldValidation({allowed:true});await tick();assert.deepEqual(runs,['forward-left']);
 const ev={button:0,pointerId:7,currentTarget:btn,preventDefault(){}};btn.emit('pointerdown',ev);await tick();assert.equal(btn.dataset.active,'true');pending.shift()({allowed:true});await tick();assert.equal(runs[runs.length-1],'forward');
 win.emit('blur');assert.equal(btn.dataset.active,'false');const before=runs.length;await wait(30);assert.equal(runs.length,before);
 doc.emit('keydown',key('KeyS'));await tick();assert.equal(pending.length,1);await wait(90);assert.match(notes[notes.length-1],/초과/);pending.shift()({allowed:true});await tick();assert.equal(runs.length,before);
 c.dispose();assert.equal((doc.l.keydown||[]).length,0);
}main().catch(e=>{console.error(e);process.exit(1)});
'''
    result=subprocess.run(['node','-e',code,str(bundle)],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
