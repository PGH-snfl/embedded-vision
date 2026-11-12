"""Validation of the persisted visual-only structure model."""
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def test_structure_contract_and_independent_copy(tmp_path):
    output=tmp_path/'structure.cjs'
    esbuild=ROOT/'third_party/velxio/frontend/node_modules/.bin/esbuild'
    subprocess.run([str(esbuild),str(ROOT/'frontend/rover-src/structure.js'),
      '--bundle','--platform=node','--format=cjs','--target=node12',f'--outfile={output}'],check=True,capture_output=True,text=True)
    script=r'''
const assert=require('assert');
const {defaultStructure,validStructure,cloneStructure}=require(process.argv[1]);
const data=defaultStructure();assert(validStructure(data));assert.equal(data.objects.length,9);
const copy=cloneStructure(data);copy.objects[0].position[0]=.2;assert.notEqual(data.objects[0].position[0],.2);
const old=cloneStructure(data);delete old.objects[0].rotation;assert(validStructure(old));assert.deepEqual(cloneStructure(old).objects[0].rotation,[0,0,0]);
assert(validStructure({version:1,objects:[]}));
const sphere=cloneStructure(data);sphere.objects[0].shape='sphere';assert(validStructure(sphere));
for(const modify of [
 x=>x.objects.push({...x.objects[0]}),
 x=>x.objects[0].shape='text', x=>x.objects[0].size[0]=0,
 x=>x.objects[0].position[1]=Infinity, x=>x.objects[0].position[1]=2.1,
 x=>x.objects[0].label=' ', x=>x.objects[0].color='red',
 x=>x.objects[0].id='..',x=>x.objects[0].onclick='alert(1)',x=>x.objects[0].rotation[1]=2*Math.PI+.1,
 x=>x.objects.push(...Array(51).fill({...x.objects[0]}))]) {
 const candidate=cloneStructure(data);modify(candidate);assert(!validStructure(candidate));
}
'''
    subprocess.run(['node','-e',script,str(output)],check=True,capture_output=True,text=True)


def test_spherical_caster_can_be_saved():
    from backend.design.rover_structure import RoverStructure
    saved=RoverStructure.model_validate({'version':1,'completion_version':'whole-structure-v1','objects':[{
        'id':'design-caster-ball','label':'볼 캐스터','shape':'sphere',
        'position':[.08,.012,0.0],'size':[.024,.024,.024],
        'rotation':[0.0,0.0,0.0],'color':'#242424'}]})
    assert saved.objects[0].shape=='sphere'
    assert saved.model_dump()['completion_version']=='whole-structure-v1'
