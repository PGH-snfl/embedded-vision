"""The rover model is an idealized estimate, not hardware or MCU validation."""
import subprocess
from pathlib import Path


ROOT=Path(__file__).resolve().parents[1]


def test_ideal_rover_trajectory_and_command_contract(tmp_path):
    output=tmp_path/'kinematics.cjs'
    esbuild=ROOT/'third_party/velxio/frontend/node_modules/.bin/esbuild'
    subprocess.run([str(esbuild),str(ROOT/'frontend/rover-src/kinematics.js'),
                    '--bundle','--platform=node','--format=cjs','--target=node12',f'--outfile={output}'],
                   check=True,capture_output=True,text=True)
    script=r'''
const assert=require('assert');
const {stepRover,ROVER_COMMANDS,ROVER_ASSUMPTIONS}=require(process.argv[1]);
const near=(a,b)=>assert(Math.abs(a-b)<1e-9,`${a} != ${b}`);
assert.deepEqual(ROVER_COMMANDS.forward,[0.5,0.5]);
assert.deepEqual(ROVER_COMMANDS.backward,[-0.5,-0.5]);
assert.deepEqual(ROVER_COMMANDS.left,[0,0.5]);
assert.deepEqual(ROVER_COMMANDS.right,[0.5,0]);
assert.deepEqual(ROVER_COMMANDS.stop,[0,0]);
assert.equal(ROVER_ASSUMPTIONS.durationSeconds,1);
const start={x:0,y:0,heading:0};
const f=stepRover(start,...ROVER_COMMANDS.forward,2);near(f.x,.2);near(f.y,0);near(f.heading,0);
const b=stepRover(start,...ROVER_COMMANDS.backward,2);near(b.x,-.2);near(b.y,0);
const l=stepRover(start,...ROVER_COMMANDS.left,2),r=stepRover(start,...ROVER_COMMANDS.right,2);
near(l.x,r.x);near(l.y,-r.y);near(l.heading,-r.heading);assert(l.y>0&&r.y<0);
const stop=stepRover(l,...ROVER_COMMANDS.stop,2);assert.deepEqual(stop,l);
const midpoint=stepRover(start,...ROVER_COMMANDS.left,1);
const twice=stepRover(midpoint,...ROVER_COMMANDS.left,1);near(twice.x,l.x);near(twice.y,l.y);near(twice.heading,l.heading);
for(const bad of [[2,0,1],[0,0,-1],[0,0,2.1],[NaN,0,1]])assert.throws(()=>stepRover(start,...bad));
'''
    subprocess.run(['node','-e',script,str(output)],check=True,capture_output=True,text=True)


def test_rover_world_directions_and_wheel_sides(tmp_path):
    """The body front is +X and its left side is -Z at heading zero."""
    esbuild=ROOT/'third_party/velxio/frontend/node_modules/.bin/esbuild'
    kinematics=tmp_path/'kinematics.cjs'
    manual=tmp_path/'manual.cjs'
    for source, output in [('kinematics.js',kinematics),('manual-control.js',manual)]:
        subprocess.run([str(esbuild),str(ROOT/'frontend/rover-src'/source),
                        '--bundle','--platform=node','--format=cjs','--target=node12',f'--outfile={output}'],
                       check=True,capture_output=True,text=True)
    script=r'''
const assert=require('assert');
const {stepRover,ROVER_COMMANDS,roverPoseToWorld,ROVER_WHEEL_LAYOUT}=require(process.argv[1]);
const {MANUAL_COMMANDS,manualDirection}=require(process.argv[2]);
const near=(a,b)=>assert(Math.abs(a-b)<1e-9,`${a} != ${b}`);
const start={x:0,y:0,heading:0};
const world=pair=>roverPoseToWorld(stepRover(start,...pair,1));
assert.deepStrictEqual(ROVER_WHEEL_LAYOUT,[{side:'left',z:-.07},{side:'right',z:.07}]);
let forward=world(ROVER_COMMANDS.forward),backward=world(ROVER_COMMANDS.backward);
assert(forward.x>0);near(forward.z,0);near(forward.rotationY,0);
assert(backward.x<0);near(backward.z,0);near(backward.rotationY,0);
const left=world(ROVER_COMMANDS.left),right=world(ROVER_COMMANDS.right);
assert(left.x>0&&left.z<0&&left.rotationY>0);  // nose turns toward body-left (-Z)
assert(right.x>0&&right.z>0&&right.rotationY<0);
for(const [name,signX,signZ,signHeading] of [
 ['forward-left',1,-1,1],['forward-right',1,1,-1],
 ['backward-left',-1,1,1],['backward-right',-1,-1,-1]]){
 const result=world(MANUAL_COMMANDS[name]);
 assert.equal(Math.sign(result.x),signX,name+' x');
 assert.equal(Math.sign(result.z),signZ,name+' z');
 assert.equal(Math.sign(result.rotationY),signHeading,name+' nose rotation');
}
assert.equal(manualDirection(['forward','left']),'forward-left');
assert.equal(manualDirection(['forward','right']),'forward-right');
assert.equal(manualDirection(['backward','left']),'backward-left');
assert.equal(manualDirection(['backward','right']),'backward-right');
const rotated=roverPoseToWorld(stepRover({x:0,y:0,heading:Math.PI/2},...ROVER_COMMANDS.forward,1));
near(rotated.x,0);assert(rotated.z<0);near(rotated.rotationY,Math.PI/2);
'''
    subprocess.run(['node','-e',script,str(kinematics),str(manual)],check=True,capture_output=True,text=True)


def test_keyboard_keys_match_requested_rover_directions(tmp_path):
    manual=tmp_path/'manual.cjs'
    subprocess.run([str(ROOT/'third_party/velxio/frontend/node_modules/.bin/esbuild'),
                    str(ROOT/'frontend/rover-src/manual-control.js'),
                    '--bundle','--platform=node','--format=cjs','--target=node12',f'--outfile={manual}'],
                   check=True,capture_output=True,text=True)
    script=r'''
const assert=require('assert');const {createManualController}=require(process.argv[1]);
const tick=()=>new Promise(resolve=>setImmediate(resolve));
class Events{constructor(){this.events={}}addEventListener(k,f){(this.events[k]||(this.events[k]=[])).push(f)}removeEventListener(k,f){this.events[k]=(this.events[k]||[]).filter(x=>x!==f)}emit(k,e){(this.events[k]||[]).forEach(f=>f(e))}}
const doc=new Events(),win=new Events();doc.hidden=false;doc.body={};doc.documentElement={};
const host={querySelectorAll:()=>[],closest:()=>null,contains:()=>false};
let directions=[];const controller=createManualController({host,doc,win,validateMotion:async()=>true,stop:()=>{},run:d=>directions.push(d)});
(async()=>{
 for(const [code,direction] of [['KeyW','forward'],['ArrowUp','forward'],['KeyS','backward'],['ArrowDown','backward'],['KeyA','left'],['ArrowLeft','left'],['KeyD','right'],['ArrowRight','right']]){
  const event={code,target:doc.body,preventDefault(){}};
  doc.emit('keydown',event);await tick();assert.equal(directions[directions.length-1],direction,code);
  doc.emit('keyup',event);await tick();
 }
 controller.dispose();
})().catch(e=>{console.error(e);process.exit(1)});
'''
    subprocess.run(['node','-e',script,str(manual)],check=True,capture_output=True,text=True)
