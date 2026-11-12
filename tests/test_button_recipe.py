import json
import pytest
from fastapi.testclient import TestClient
from backend.api import create_app
from backend.circuit.profiles import readiness
from backend.design.hypotheses import infer_candidates
from backend.design.proposals import propose
from backend.design.recipes import BUTTON_RECIPE,new_graph
from backend.firmware import firmware
from backend.workbench.export import export_project
from backend.workbench.server import compile_edit,CompileRequest
from test_parts_first import setup
from test_function_hypotheses import led_inventory


def button_inventory():
    inv=led_inventory()
    inv.parts.append(inv.parts[-1].model_copy(update={'id':'sw','kind':'button','name':'버튼','evidence':'버튼이 보임'}))
    return inv


def test_button_candidate_is_inferred_and_recipe_does_not_invent_photo_wiring():
    inv=button_inventory()
    candidate=next(c for c in infer_candidates(inv) if c.kind=='button_led')
    assert candidate.status=='INFERRED' and candidate.assumptions
    proposal=next(p for p in propose(inv)['proposals'] if p['recipe']==BUTTON_RECIPE)
    assert proposal['simulator_supported'] and not proposal['hardware_verified']
    assert not proposal['original_wiring_reused']


def test_button_wiring_export_compile_and_reject_changed_circuit():
    graph,_=new_graph('a'*32,BUTTON_RECIPE)
    assert not readiness(graph)
    project=export_project(graph)
    assert [c['metadataId'] for c in project['components']]==['breadboard','resistor','led','pushbutton-6mm','resistor']
    assert next(c for c in project['components'] if c['id']=='R2')['properties']['value']=='10000'
    seats={w['start']['pinName']:w['end']['pinName'] for w in project['wires'] if w.get('bb') and w['start']['componentId']=='SW1'}
    assert seats=={'1.l':'42t.e','1.r':'42b.f','2.l':'40t.e','2.r':'40b.f'}
    holes=[e['pinName'] for w in project['wires'] for e in (w['start'],w['end']) if e['componentId']=='BB1']
    assert len(holes)==len(set(holes))
    code=firmware(graph)['source']
    assert 'digitalRead(BUTTON_PIN) == LOW ? HIGH : LOW' in code
    result=compile_edit(CompileRequest(files=[{'name':'sketch.ino','content':code}]))
    assert result['success'] and result['hex_content'].startswith(':')
    graph.links[-1].to_terminal='U1.5V'
    assert readiness(graph)
    with pytest.raises(ValueError):export_project(graph)


def test_button_goal_to_workbench_api(tmp_path):
    app=create_app(tmp_path)
    with TestClient(app) as c:
        original,url,_=setup(c,app,tmp_path)
        path=next((tmp_path/'planner'/original['project_id']).glob('*.json'))
        plan=json.loads(path.read_text());plan['inventory']=button_inventory().model_dump(mode='json');plan.pop('function_hypotheses',None);path.write_text(json.dumps(plan))
        endpoint=url.removesuffix('/design')
        response=c.post(endpoint+'/function-candidate',json={'expected_revision':original['revision'],'candidate_id':'button_led'})
        assert response.status_code==200,response.text
        result=response.json();assert result['recommended']==BUTTON_RECIPE
        project=c.get(endpoint+'/workbench',params={'recipe':BUTTON_RECIPE,'function_version':result['function_version']})
        assert project.status_code==200,project.text
        assert project.json()['embeddedVision']['recipe']==BUTTON_RECIPE
        assert c.get('/api/projects/'+original['project_id']).json()['graph']==original
