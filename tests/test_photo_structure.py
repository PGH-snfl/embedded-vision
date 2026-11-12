import asyncio
from copy import deepcopy
import io
import json
from pathlib import Path
import subprocess

import httpx
from PIL import Image
import pytest

from backend.application import create_app
from backend.design.photo_structure import (PhotoStructure, validate_photo_structure,
    structure_components, motion_structure)
from backend.design.rover_circuit import default_rover_circuit
from backend.design.inventory import inventory_plan
from backend.workbench.rover_export import export_rover_project, import_rover_project
from test_parts_first import Provider

ROOT=Path(__file__).resolve().parents[1]


def scene():
    return {'summary':'사진의 판과 한쪽 바퀴만 근사', 'objects':[
        {'id':'plate','label':'빨간 차체','role':'chassis','status':'INFERRED','confidence':'medium',
         'regions':[dict(asset_id='image',x0=.1,y0=.2,x1=.8,y1=.7)],
         'observation':'사진에서 보이는 빨간 판','assumptions':['두께와 깊이는 추정'],
         'geometry':{'shape':'box','position':[0,.25,0],'size':[1,.03,.6],'rotation':[0,.3,0],'color':'#c93737'}},
        {'id':'wheel','label':'보이는 바퀴','role':'wheel','status':'INFERRED','confidence':'medium',
         'regions':[dict(asset_id='image',x0=.5,y0=.5,x1=.9,y1=.95)],
         'observation':'검은 바퀴 하나','assumptions':['축 방향 근사'],
         'geometry':{'shape':'cylinder','position':[-.2,.15,.4],'size':[.3,.05,.3],'rotation':[1.5707963267948966,0,0],'color':'#242424'}},
        {'id':'hidden','label':'가려진 반대쪽','role':'wheel','status':'UNKNOWN','confidence':'low',
         'regions':[dict(asset_id='image',x0=.1,y0=.2,x1=.8,y1=.7)],
         'observation':'반대쪽은 보이지 않음','assumptions':[],'geometry':None}],
        'unknowns':['실제 치수와 뒷면 미확인']}


def test_scene_grounding_and_unknown_geometry_are_enforced():
    raw=scene()
    assert validate_photo_structure(raw,{'image'})==raw
    with pytest.raises(ValueError):validate_photo_structure(raw,{'different'})
    invalid=deepcopy(raw);invalid['objects'][2]['geometry']=raw['objects'][0]['geometry']
    with pytest.raises(ValueError):PhotoStructure.model_validate(invalid)
    invalid=deepcopy(raw);invalid['objects'][0]['geometry']['size'][0]=float('nan')
    with pytest.raises(ValueError):PhotoStructure.model_validate(invalid)
    invalid=deepcopy(raw);invalid['objects'].append(raw['objects'][0])
    with pytest.raises(ValueError):PhotoStructure.model_validate(invalid)


def test_upload_inventory_returns_structure_after_component_identification():
    from backend.design.recipes import new_graph
    base=Provider()
    class PhotoInventoryProvider:
        calls=0
        def infer(self,*args):
            self.calls+=1
            inventory,usage=base.infer(*args)
            return {**inventory.model_dump(mode='json'),'photo_structure':scene()},usage
    provider=PhotoInventoryProvider();graph,_=new_graph('a'*32,'arduino_lcd')
    result=inventory_plan(graph,[('image',Path('not-read'))],provider)
    assert provider.calls==2 and result['photo_structure']==scene()


def test_photo_objects_never_create_hidden_geometry_or_electrical_nets():
    circuit=default_rover_circuit();raw=scene()
    project=export_rover_project(circuit,{'photo_structure':raw})
    parts=structure_components(raw)
    assert [p['id'] for p in parts]==['photo-chassis-plate','photo-wheel-wheel']
    assert all(p['properties']['dimensionsStatus']=='UNKNOWN' for p in parts)
    assert project['components'][-2:]==parts
    assert len(project['wires'])==len(circuit['connections'])
    assert import_rover_project(project)==circuit
    assert len(motion_structure(raw)['objects'])==2
    assert structure_components({'summary':'구조물 없음','objects':[],'unknowns':[]})==[]


def test_editor_and_motion_share_positions_sizes_and_rotations(tmp_path):
    project=export_rover_project(default_rover_circuit(),{'photo_structure':scene()})
    fixture=tmp_path/'project.json';fixture.write_text(json.dumps(project))
    expected=tmp_path/'motion.json';expected.write_text(json.dumps(motion_structure(scene())))
    target=tmp_path/'scene.cjs'
    subprocess.run([str(ROOT/'third_party/velxio/frontend/node_modules/.bin/esbuild'),str(ROOT/'frontend/photo-structure.js'),
                    '--bundle','--platform=node','--format=cjs','--target=node12',f'--outfile={target}'],check=True,capture_output=True)
    script=r'''
const assert=require('assert'),fs=require('fs');
const {editorStructure,loadPhotoWorkbench}=require(process.argv[1]);
const project=JSON.parse(fs.readFileSync(process.argv[2])),expected=JSON.parse(fs.readFileSync(process.argv[3]));
const actual=editorStructure(project);
assert.equal(actual.objects.length,2);
for(let i=0;i<2;i++)for(const key of ['position','size','rotation'])actual.objects[i][key].forEach((n,j)=>assert(Math.abs(n-expected.objects[i][key][j])<1e-8));
assert.equal(editorStructure({components:[]}),null);
assert.deepStrictEqual(editorStructure({...project,components:[]}),{version:1,objects:[]});
let gets=0,posts=0;
(async()=>{
 const old={project:{embeddedVision:{source_revision:1}}};
 const result=await loadPhotoWorkbench(async(u,o)=>{if(o){posts++;return {};}return ++gets===1?old:{project};},'/api/projects/test/inventory/test','v');
 assert.equal(result.project,project);assert.equal(posts,1);assert.equal(gets,2);
 gets=0;await loadPhotoWorkbench(async()=>{gets++;return {project};},'/api/test','v');assert.equal(gets,1);
})().catch(e=>{console.error(e);process.exit(1)});
'''
    subprocess.run(['node','-e',script,str(target),str(fixture),str(expected)],check=True,capture_output=True)


def test_photo_structure_api_caches_once_and_keeps_original_analysis(tmp_path,monkeypatch):
    monkeypatch.setenv('EMBEDDED_VISION_AUTO_ANALYSIS','0')
    class SceneProvider:
        calls=0
        def infer(self,model,context,prompt,task,assets):
            self.calls+=1
            assert task=='photo_structure' and len(assets)==1
            return scene(),{'model':'TEST ONLY'}
    provider=SceneProvider();app=create_app(tmp_path)
    app.state.photo_structure_provider_factory=lambda:provider
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver') as c:
            image=io.BytesIO();Image.new('RGB',(60,60)).save(image,format='PNG')
            created=await c.post('/api/projects',files={'image':('photo.png',image.getvalue(),'image/png')})
            graph=created.json()['graph'];source=app.state.store.get(graph['project_id'])
            plan=inventory_plan(source,[('image',tmp_path/'unused')],Provider())
            folder=tmp_path/'planner'/source.project_id;folder.mkdir(exist_ok=True)
            path=folder/(plan['id']+'.json');path.write_text(json.dumps(plan));before=path.read_bytes()
            url=f"/api/projects/{source.project_id}/inventory/{plan['id']}/photo-structure"
            assert (await c.get(url)).json()['photo_structure'] is None
            assert (await c.post(url,json={'expected_revision':99})).status_code==409
            first=await c.post(url,json={'expected_revision':source.revision})
            assert first.status_code==200,first.text
            assert first.json()['cached'] is False
            again=await c.post(url,json={'expected_revision':source.revision})
            assert again.json()['cached'] is True and provider.calls==1
            assert (await c.get(url)).json()['photo_structure']==scene()
            assert path.read_bytes()==before
            assert app.state.store.get(source.project_id).model_dump(mode='json')==graph
    asyncio.run(run())
