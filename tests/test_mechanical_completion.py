"""Whole geometry survives the strict motion contract and renders from both sides."""
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def test_motion_completion_and_two_sided_geometry(tmp_path):
    bundle=tmp_path/'mechanical.cjs'
    subprocess.run([str(ROOT/'third_party/velxio/frontend/node_modules/.bin/esbuild'),
        str(ROOT/'frontend/rover-src/mechanical-shape.js'),'--bundle','--platform=node',
        '--format=cjs','--target=node12',f'--outfile={bundle}'],check=True,capture_output=True)
    script=r'''
const assert=require('assert');const {completeMotionStructure,mechanicalMesh}=require(process.argv[1]);
const part=(id,shape,position,size)=>({id,shape,label:id,position,size,rotation:id.includes('wheel')?[Math.PI/2,0,0]:[0,0,0],color:'#444444'});
const input={version:1,objects:[part('photo-chassis-base','box',[0,.066,0],[.22,.0055,.143]),part('photo-wheel-near','cylinder',[-.0627,.0462,.0847],[.0924,.0165,.0924])]};
const result=completeMotionStructure(input);assert.equal(input.objects.length,2);
const other=result.objects.find(o=>o.id==='design-wheel-opposite');assert(other);assert.equal(other.position[2],-.0847);
assert(result.objects.some(o=>o.shape==='sphere'));assert.deepEqual(completeMotionStructure(result),result);
const deleted={...result,objects:result.objects.filter(o=>o.id!=='design-wheel-opposite')};assert.equal(completeMotionStructure(deleted),deleted);
const mesh=mechanicalMesh(other);assert(mesh.children.some(m=>m.position.y>.45));assert(mesh.children.some(m=>m.position.y<-.45));
assert.equal(mesh.position.z,-.0847);assert.equal(mesh.rotation.x,Math.PI/2);
const edited=mechanicalMesh(result.objects.find(o=>o.shape==='sphere'));assert.equal(edited.children[0].geometry.type,'SphereGeometry');
'''
    subprocess.run(['node','-e',script,str(bundle)],check=True,capture_output=True,text=True)
