"""A stale or failed circuit check never starts an assumed movement."""
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]


def test_motion_guard_enforces_validation_and_immediate_stop(tmp_path):
    bundle=tmp_path/'rover.cjs'
    esbuild=ROOT/'third_party/velxio/frontend/node_modules/.bin/esbuild'
    subprocess.run([str(esbuild),str(ROOT/'frontend/rover-src/simulator.js'),
                    '--bundle','--platform=node','--format=cjs','--target=node12',f'--outfile={bundle}'],
                   check=True,capture_output=True,text=True)
    code=r'''
const assert=require('assert');
const {createMotionGuard}=require(process.argv[1]);
(async()=>{
 let commands=[],events=[],resolve;
 const guard=createMotionGuard({validateMotion:()=>new Promise(r=>resolve=r),onCommand:c=>commands.push(c),onState:(b,m)=>events.push([b,m])});
 let pending=guard.request('forward');
 assert.deepStrictEqual(commands,['stop']);assert.equal(events[0][0],true);
 await guard.request('stop');assert.equal(commands[commands.length-1],'stop');
 resolve({allowed:true});await pending;assert.deepStrictEqual(commands,['stop','stop']);assert.equal(events[events.length-1][0],false);
 pending=guard.request('left');resolve({allowed:false,message:'연결 오류'});await pending;
 assert.equal(commands[commands.length-1],'stop');assert.equal(events[events.length-1][1],'연결 오류');
 pending=guard.request('right');resolve({allowed:true});await pending;assert.equal(commands[commands.length-1],'right');
 let denied=[];const failing=createMotionGuard({validateMotion:async()=>{throw Error('서버 오류');},onCommand:c=>denied.push(c),onState:(b,m)=>events.push([b,m])});
 await failing.request('forward');assert.deepStrictEqual(denied,['stop','stop']);assert(events[events.length-1][1].includes('서버 오류'));
 let direct=[];const legacy=createMotionGuard({onCommand:c=>direct.push(c),onState:()=>{}});
 await legacy.request('forward');assert.deepStrictEqual(direct,['forward']);
 let deferred,disposed=[];const cancelled=createMotionGuard({validateMotion:()=>new Promise(r=>deferred=r),onCommand:c=>disposed.push(c),onState:()=>{}});
 pending=cancelled.request('forward');cancelled.dispose();deferred(true);await pending;assert.deepStrictEqual(disposed,['stop']);
})().catch(e=>{console.error(e);process.exit(1);});
'''
    subprocess.run(['node','-e',code,str(bundle)],check=True,capture_output=True,text=True)
