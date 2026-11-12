"""The editor preserves actual terminal names and never invents pins."""
import json
import os
import shutil
import subprocess
from pathlib import Path
from backend.design.rover_circuit import default_rover_circuit

ROOT=Path(__file__).resolve().parents[1]

def test_circuit_editor_graph_operations(tmp_path):
    output=tmp_path/'robot-circuit.cjs'
    build=ROOT/'third_party/velxio/frontend/node_modules/.bin/esbuild'
    subprocess.run([str(build),str(ROOT/'frontend/robot-circuit.js'),'--bundle','--platform=node','--format=cjs',
                    '--target=node12',f'--outfile={output}'],check=True,capture_output=True)
    fixture=tmp_path/'circuit.json';fixture.write_text(json.dumps(default_rover_circuit()))
    script=r'''
const assert=require('assert');const m=require(process.argv[1]);const g=require(process.argv[2]);
const pins=m.robotCircuitPins(),pos=m.robotCircuitPositions(g);
assert.deepEqual(pins.U1,['U1.GPIO40','U1.USB_C']);
assert(pins.HAT1.includes('HAT1.M1.left'));assert(!pins.HAT1.includes('HAT1.GPIO17'));
assert.equal(pos['U1.GPIO40'].x,310);assert.equal(pos['U1.GPIO40'].y,180);
const removed=m.robotCircuitRemovePart(g,'MOTOR_L');assert(!removed.components.some(c=>c.id==='MOTOR_L'));
assert(!removed.connections.some(w=>w.from.startsWith('MOTOR_L.')||w.to.startsWith('MOTOR_L.')));
const restored=m.robotCircuitAddPart(removed,'MOTOR_L');assert.equal(restored.components.length,6);
const wire=m.robotCircuitConnect(restored,'MOTOR_L.black','HAT1.M1.left','W_TEST');assert.equal(wire.connections.length,7);
assert.throws(()=>m.robotCircuitConnect(wire,'HAT1.M1.left','MOTOR_L.black'));
assert.throws(()=>m.robotCircuitConnect(wire,'HAT1.not_a_pin','MOTOR_L.red'));
assert.throws(()=>m.robotCircuitConnect(wire,'MOTOR_L.black','MOTOR_L.black'));
const moved=m.robotCircuitReconnect(wire,'W_TEST','to','HAT1.M1.right');
assert.equal(moved.connections.find(w=>w.id==='W_TEST').to,'HAT1.M1.right');
assert.equal(wire.connections.find(w=>w.id==='W_TEST').to,'HAT1.M1.left');
assert.throws(()=>m.robotCircuitReconnect(wire,'W_TEST','to','missing.pin'));
assert.equal(g.connections.length,8);
'''
    subprocess.run(['node','-e',script,str(output),str(fixture)],check=True,capture_output=True,text=True)

def test_wire_endpoint_drag_and_click_to_connect_coexist(tmp_path):
    output=tmp_path/'robot-circuit.cjs'
    build=ROOT/'third_party/velxio/frontend/node_modules/.bin/esbuild'
    subprocess.run([str(build),str(ROOT/'frontend/robot-circuit.js'),'--bundle','--platform=node','--format=cjs',
                    '--target=node20',f'--outfile={output}'],check=True,capture_output=True)
    fixture=tmp_path/'circuit.json';fixture.write_text(json.dumps(default_rover_circuit()))
    preferred=Path(os.environ.get('WORKBENCH_NODE','/home/snowflower/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node'))
    node=str(preferred) if preferred.is_file() else shutil.which('node')
    script=r'''
const assert=require('assert');const {JSDOM}=require(process.argv[3]);
const win=new JSDOM('<!doctype html><body><div id="root"></div></body>').window;
global.document=win.document;global.window=win;
const {renderRobotCircuit}=require(process.argv[1]);const data=require(process.argv[2]);
let changed=[];const root=document.querySelector('#root');
const editor=renderRobotCircuit(root,{initialGraph:data,onChange:g=>changed.push(g),esc:x=>String(x)});
const svg=root.querySelector('svg');svg.createSVGPoint=()=>({x:0,y:0,matrixTransform(){return {x:this.x,y:this.y}}});
svg.getScreenCTM=()=>({inverse(){return {}}});svg.setPointerCapture=()=>{};svg.releasePointerCapture=()=>{};svg.hasPointerCapture=()=>true;
function ev(target,type,x,y){const e=new win.Event(type,{bubbles:true,cancelable:true});for(const [key,val] of Object.entries({button:0,pointerId:1,clientX:x,clientY:y}))Object.defineProperty(e,key,{value:val});target.dispatchEvent(e);}
// C3 was never selected; its MOTOR_L endpoint can be moved directly.
let end=root.querySelector('[data-wire-handle="C3"][data-end="from"]');assert(end);
ev(end,'pointerdown',720,110);ev(svg,'pointermove',640,270);ev(svg,'pointerup',640,270);
assert.equal(editor.getGraph().connections.find(x=>x.id==='C3').from,'HAT1.M2.right');
assert.equal(changed.length,1);
// A short click on an occupied endpoint starts connecting a new wire instead
// of moving the old endpoint. A second click completes the connection.
end=root.querySelector('[data-wire-handle="C3"][data-end="from"]');ev(end,'pointerdown',640,270);ev(svg,'pointerup',640,270);
end=root.querySelector('[data-wire-handle="C5"][data-end="from"]');ev(end,'pointerdown',720,290);ev(svg,'pointerup',720,290);
assert(editor.getGraph().connections.some(x=>x.from==='HAT1.M2.right'&&x.to==='MOTOR_R.black'));
assert.equal(changed.length,2);
// Dragging a component updates its attached line without changing connectivity.
const before=root.querySelector('[data-wire-path="C1"]').getAttribute('d');
let part=root.querySelector('[data-part="U1"]');ev(part,'pointerdown',140,170);ev(svg,'pointermove',180,220);ev(svg,'pointerup',180,220);
assert.equal(editor.getGraph().components.find(c=>c.id==='U1').x,160);
assert.equal(editor.getGraph().components.find(c=>c.id==='U1').y,200);
assert.notEqual(root.querySelector('[data-wire-path="C1"]').getAttribute('d'),before);
assert(editor.getGraph().connections.some(x=>x.id==='C1'));
// Deleting a selected component also removes every connected wire.
root.querySelector('[data-robot-delete]').click();assert(!editor.getGraph().components.some(c=>c.id==='U1'));
assert(!editor.getGraph().connections.some(w=>w.from.startsWith('U1.')||w.to.startsWith('U1.')));
'''
    jsdom=ROOT/'third_party/velxio/frontend/node_modules/jsdom'
    subprocess.run([node,'-e',script,str(output),str(fixture),str(jsdom)],check=True,capture_output=True,text=True)
