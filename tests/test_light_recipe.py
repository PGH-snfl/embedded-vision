import json
import pytest
from fastapi.testclient import TestClient
from backend.api import create_app
from backend.circuit.profiles import readiness
from backend.design.hypotheses import infer_candidates
from backend.design.proposals import propose,compatible
from backend.design.recipes import LIGHT_RECIPE,new_graph
from backend.firmware import firmware
from backend.workbench.export import export_project
from backend.workbench.server import compile_edit,CompileRequest
from test_parts_first import setup
from test_function_hypotheses import led_inventory


def light_inventory(name='LDR photoresistor light sensor'):
    inv=led_inventory()
    inv.parts.append(inv.parts[-1].model_copy(update={'id':'sensor','kind':'sensor','name':name,'evidence':'조도 센서 후보가 보임'}))
    return inv


def test_light_candidate_requires_light_sensor_and_does_not_invent_observation():
    inv=light_inventory();h=next(h for h in infer_candidates(inv) if h.kind=='light_led')
    assert h.status=='INFERRED' and h.assumptions
    p=next(p for p in propose(inv)['proposals'] if p['recipe']==LIGHT_RECIPE)
    assert p['simulator_supported'] and not p['hardware_verified'] and not p['original_wiring_reused']
    assert '가상' in p['simulation_notice']
    assert p['assignments']['S1'] is None and 'S1' in p['added_parts']
    assert p['replacements'][0]['candidate_ids']==['sensor']
    assert not any(p['recipe']==LIGHT_RECIPE for p in propose(light_inventory('DHT22 temperature sensor'))['proposals'])


def test_light_function_can_propose_all_new_parts_without_inventing_sensor():
    inv=light_inventory('DHT22 temperature sensor')
    # Existing unrelated parts don't prohibit a new design when a function is
    # explicitly chosen; that is still not an observation of the photo.
    p=next(p for p in propose(inv,function_kind='light_led')['proposals'] if p['recipe']==LIGHT_RECIPE)
    assert p['assignments']['S1'] is None
    assert p['replacements'][0]['candidate_ids']==[]
    assert '2핀' in p['replacements'][0]['reason']


def test_two_pin_ldr_never_assigned_as_three_pin_module():
    from backend.design.recipes import recipe_info
    sensor=light_inventory().parts[-1]
    slot=recipe_info()[LIGHT_RECIPE]['slots']['S1']
    for name in ['LDR photoresistor','2-pin LDR sensor module','2핀 광저항']:
        assert not compatible(sensor.model_copy(update={'name':name,'model_candidates':[],'markings':[]}),LIGHT_RECIPE,slot)
    assert compatible(sensor.model_copy(update={'name':'LDR photoresistor sensor module','model_candidates':[],'markings':[]}),LIGHT_RECIPE,slot)


def test_light_graph_export_compiles_and_rejects_changed_wire():
    g,_=new_graph('a'*32,LIGHT_RECIPE);assert not readiness(g)
    p=export_project(g)
    assert next(c for c in p['components'] if c['id']=='S1')['metadataId']=='photoresistor-sensor'
    assert next(c for c in p['components'] if c['id']=='S1')['properties']['ldrModel']=='wokwi'
    assert p['embeddedVision']['assembly']['layout_version']=='full-breadboard-light-v1'
    assert not any(w.get('bb') and w['start']['componentId']=='S1' for w in p['wires'])
    assert {'AO','GND','VCC'}=={w['start']['pinName'] for w in p['wires'] if w['start']['componentId']=='S1'}
    code=firmware(g)['source'];assert 'reading > DARK_THRESHOLD' in code
    result=compile_edit(CompileRequest(files=[{'name':'sketch.ino','content':code}]))
    assert result['success'] and result['hex_content'].startswith(':')
    g.links[-1].to_terminal='U1.5V'
    assert readiness(g)
    with pytest.raises(ValueError):export_project(g)


def test_light_candidate_to_workbench(tmp_path):
    app=create_app(tmp_path)
    with TestClient(app) as c:
        original,url,_=setup(c,app,tmp_path)
        path=next((tmp_path/'planner'/original['project_id']).glob('*.json'))
        plan=json.loads(path.read_text());plan['inventory']=light_inventory().model_dump(mode='json');plan.pop('function_hypotheses',None);path.write_text(json.dumps(plan))
        endpoint=url.removesuffix('/design')
        r=c.post(endpoint+'/function-candidate',json={'expected_revision':original['revision'],'candidate_id':'light_led'})
        assert r.status_code==200,r.text
        data=r.json();assert data['recommended']==LIGHT_RECIPE
        result=c.get(endpoint+'/workbench',params={'recipe':LIGHT_RECIPE,'function_version':data['function_version']})
        assert result.status_code==200,result.text
        assert result.json()['embeddedVision']['recipe']==LIGHT_RECIPE
        proposal=data['proposals'][0]
        body=dict(expected_revision=original['revision'],recipe=LIGHT_RECIPE,assignments=proposal['assignments'],function_version=data['function_version'],function_confirmed=True,accept_added_parts=True,parts_verified=True,verification_note='가상 부품 사양 검토')
        design=c.post(url,json=body)
        assert design.status_code==201,design.text
        assert 'analogRead(LIGHT_PIN)' in design.json()['firmware']['source']
        assert c.get('/api/projects/'+original['project_id']).json()['graph']==original


def test_unknown_sensor_gets_inferred_design_without_claiming_compatibility(tmp_path):
    inv=light_inventory('종류 미상의 원판형 소자')
    inv.parts[-1]=inv.parts[-1].model_copy(update={'status':'UNKNOWN','model_candidates':['광저항(LDR)']})
    candidates=[h.model_dump(mode='json') for h in infer_candidates(inv)]
    assert candidates[0]['id']=='light_led'
    app=create_app(tmp_path)
    with TestClient(app) as c:
        original,url,_=setup(c,app,tmp_path)
        path=next((tmp_path/'planner'/original['project_id']).glob('*.json'))
        plan=json.loads(path.read_text());plan.update(inventory=inv.model_dump(mode='json'),function_hypotheses=candidates,hypothesis_source='multimodal_model')
        path.write_text(json.dumps(plan,ensure_ascii=False))
        for target in (tmp_path/'function_targets'/original['project_id']).glob('*.json'):target.unlink()
        endpoint=url.removesuffix('/design')
        offered=c.get(endpoint+'/proposals').json()
        preview=next(p for p in offered['hypothesis_previews'] if p['candidate_id']=='light_led')['proposal']
        assert offered['function']['status']=='UNKNOWN' and preview['function']['status']=='INFERRED'
        assert preview['assignments']['S1'] is None and 'S1' in preview['added_parts']
        assert preview['replacements'][0]['candidate_ids']==['sensor']
        assert inv.parts[-1].status=='UNKNOWN'
        assert c.get('/api/projects/'+original['project_id']).json()['graph']==original
        assert not list((tmp_path/'function_targets'/original['project_id']).glob('*.json'))
        response=c.post(endpoint+'/function-candidate',json={'expected_revision':original['revision'],'candidate_id':'light_led'})
        assert response.status_code==200,response.text
        selected=response.json();p=selected['proposals'][0]
        assert p['recipe']==LIGHT_RECIPE and p['assignments']['S1'] is None
        result=c.get(endpoint+'/workbench',params={'recipe':LIGHT_RECIPE,'function_version':selected['function_version']})
        assert result.status_code==200,result.text
        comparison=result.json()['embeddedVision']['part_comparison']
        assert comparison['assignments']['S1'] is None and 'S1' in comparison['added_parts']
        assert comparison['replacements'][0]['candidate_ids']==['sensor']
        body=dict(expected_revision=original['revision'],recipe=LIGHT_RECIPE,assignments=p['assignments'],function_version=selected['function_version'],function_confirmed=True,accept_added_parts=False,parts_verified=True,verification_note='가상 부품 사양 검토')
        assert c.post(url,json=body).status_code==422
        body['accept_added_parts']=True;body['parts_verified']=False
        assert c.post(url,json=body).status_code==422
        body['parts_verified']=True;body['assignments']={**p['assignments'],'S1':'sensor'}
        assert c.post(url,json=body).status_code==422
        body['assignments']=p['assignments']
        assert c.post(url,json=body).status_code==201
