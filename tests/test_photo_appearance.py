"""Photo shape is shared; circuit state and authored draft edits stay intact."""
from copy import deepcopy
import asyncio,io,json
import httpx
from PIL import Image

from backend.application import create_app
from backend.design.photo_appearance import attach_photo_appearance
from backend.design.photo_structure import PhotoStructure,structure_components,motion_structure
from backend.design.rover_structure import RoverStructure
from backend.design.implementation import realize
from backend.design.prototype_match import prototype_kind
from backend.design.inventory import inventory_plan
from test_photo_structure import scene
from test_parts_first import Provider
from test_functional_build import build_inputs
from test_auto_prototype import candidate


def detailed_scene():
    s=scene();g=s['objects'][0]['geometry']
    g.update(outline=[[-.5,-.5],[.5,-.5],[.4,.5],[-.4,.5]],
        holes=[[[-.1,-.3],[-.1,.3],[.1,.3],[.1,-.3]]],details=[{
            'shape':'cylinder','position':[0,.6,0],'size':[.1,.05,.1],
            'rotation':[0,0,0],'color':'#ffffff'}])
    return s


def test_photo_appearance_keeps_electrical_state_and_geometry_roundtrip():
    original={'boards':[{'id':'U1'}],'components':[{'id':'D1'}],
        'wires':[{'id':'W1'}],'fileGroups':{'main':'edited code'},'embeddedVision':{'recipe':'native'}}
    before=deepcopy(original);s=detailed_scene();p=attach_photo_appearance(original,s)
    assert original==before
    for key in ['boards','wires','fileGroups']:assert p[key] is original[key]
    assert p['components'][0] is original['components'][0]
    assert p['embeddedVision']['focus_photo_on_open']
    assert p['embeddedVision']['recipe']=='native'
    assert p['embeddedVision']['photo_assembly']['part_ids']==[part['id'] for part in structure_components(s)]
    assert p['embeddedVision']['photo_assembly']['pose_basis']=='assembled'
    assert p['embeddedVision']['photo_assembly']['explosion']=='viewer_only'
    assert attach_photo_appearance(p,s)['components']==p['components']
    expected=s['objects'][0]['geometry']
    assert p['components'][1]['properties']['evPhotoGeometry']==expected
    motion=motion_structure(s)
    assert motion['objects'][0]['photoGeometry']==expected
    saved=RoverStructure.model_validate(motion).model_dump(mode='json')
    assert saved['objects'][0]['photoGeometry']==expected
    schema=PhotoStructure.model_json_schema()
    for node in [schema,*schema['$defs'].values()]:
        if node.get('type')=='object':assert set(node['required'])==set(node['properties'])


def test_functional_design_receives_photo_parts_without_replacing_implementation():
    observed,raw,_=build_inputs();plan={**raw,'inventory':observed.model_dump(mode='json'),
        'asset_ids':['image'],'photo_structure':detailed_scene()}
    before=deepcopy(plan);out=realize(plan,raw['function_hypotheses'][0],{'source_graph_sha256':'a'*64})
    assert plan==before
    work=out['workbench']
    assert work['embeddedVision']['recipe']=='ai_functional_build'
    assert len(work['wires'])==len(raw['functional_build']['connections'])
    assert work['fileGroups']['group-U1'][0]['content']==raw['functional_build']['firmware']
    assert len([p for p in work['components'] if p['properties'].get('evPhotoGeometry')])==2


def test_biped_with_obstacle_sensor_is_not_converted_to_wheel_robot():
    assert prototype_kind({'kind':'unsupported','title':'초음파 이족 보행 로봇',
        'input_behavior':'장애물 거리 측정','output_behavior':'다리로 전진하고 장애물 회피'}) is None


def test_photo_editor_available_even_without_supported_firmware(tmp_path,monkeypatch):
    monkeypatch.setenv('EMBEDDED_VISION_AUTO_ANALYSIS','0');app=create_app(tmp_path)
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver') as c:
            b=io.BytesIO();Image.new('RGB',(64,64)).save(b,format='PNG')
            g=(await c.post('/api/projects',files={'image':('p.png',b.getvalue(),'image/png')})).json()['graph']
            source=app.state.store.get(g['project_id']);plan=inventory_plan(source,[('image',tmp_path/'unused')],Provider())
            plan['photo_structure']=detailed_scene();plan['function_hypotheses']=[candidate('이족 보행 로봇','거리 입력','다리로 보행')];plan['functional_build']=None
            folder=tmp_path/'planner'/source.project_id;folder.mkdir(exist_ok=True)
            path=folder/(plan['id']+'.json');path.write_text(json.dumps(plan));before=path.read_bytes()
            r=await c.get(f'/api/projects/{source.project_id}/inventory/{plan["id"]}/photo-workbench')
            assert r.status_code==200,r.text
            result=r.json();assert result['embeddedVision']['recipe']=='photo_appearance_view'
            assert result['components']==structure_components(detailed_scene())
            assert not result['boards'] and not result['wires']
            assert path.read_bytes()==before
    asyncio.run(run())
