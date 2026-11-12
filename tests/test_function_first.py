import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from backend.api import create_app
from backend.design.function import FunctionIntent,FunctionalInventory,unknown_function,constrain
from backend.design.inventory import inventory_plan
from backend.design.proposals import propose
from backend.design.recipes import new_graph
from test_parts_first import inventory,setup
from test_design_proposals import uno_resistors,prepare


def lcd_intent(**changes):
    return FunctionIntent(kind='lcd_text',status='INFERRED',summary='LCD에 Javalab.org 문구가 보임',input_behavior='전원 공급',output_behavior='LCD에 Javalab.org 표시',evidence=[{'asset_id':'image','observation':'LCD 표시 문구 Javalab.org'}],unknowns=['숨겨진 추가 동작은 알 수 없음'],acceptance_criteria=['전원을 켜면 LCD에 Javalab.org가 표시된다.'],display_text='Javalab.org',**changes)


def test_unknown_behavior_never_defaults_to_divider():
    r=constrain(propose(uno_resistors()),unknown_function())
    assert not r['proposals'] and r['recommended'] is None
    assert r['function_blockers']


def test_observed_lcd_function_exact_text_no_extra_clock():
    r=constrain(propose(inventory()),lcd_intent())
    assert [p['recipe'] for p in r['proposals']]==['arduino_lcd']
    source=r['proposals'][0]['firmware']['source']
    assert 'lcd.print("Javalab.org")' in source
    assert 'Elapsed' not in source and 'millis()' not in source


def test_unsupported_robot_is_not_replaced_by_simple_circuit():
    spec=unknown_function().model_copy(update={'kind':'unsupported','summary':'주차 공간으로 차량을 운반한다.'})
    assert not constrain(propose(uno_resistors()),spec)['proposals']


def test_bad_function_evidence_or_model_user_confirmation_rejected():
    class Provider:
        def __init__(self,spec):self.spec=spec
        def infer(self,*args):return {**inventory().model_dump(mode='json'),'function':self.spec},{}
    g,_=new_graph('a'*32,'arduino_lcd')
    bad=lcd_intent().model_dump(mode='json');bad['evidence'][0]['asset_id']='invented'
    with pytest.raises(RuntimeError):inventory_plan(g,[('image',Path('unused'))],Provider(bad))
    bad=lcd_intent().model_dump(mode='json');bad['status']='USER_DEFINED'
    with pytest.raises(RuntimeError):inventory_plan(g,[('image',Path('unused'))],Provider(bad))


def test_function_api_creation_gates_and_same_code_everywhere(tmp_path):
    with TestClient(create_app(tmp_path)) as c:
        original,url,body=setup(c,c.app,tmp_path)
        endpoint=url.removesuffix('/design')
        target=c.post(endpoint+'/function',json={'expected_revision':original['revision'],'kind':'lcd_text','description':'LCD에 Javalab.org를 고정 표시한다.','display_text':'Javalab.org'}).json()
        assert target['proposals'][0]['simulator_supported'] is True
        preview=c.get(endpoint+'/workbench',params={'recipe':'arduino_lcd','function_version':target['function_version']})
        assert preview.status_code==200,preview.text
        assert 'lcd.print("Javalab.org")' in preview.json()['fileGroups']['group-U1'][0]['content']
        assert preview.json()['embeddedVision']['physical_verified'] is False
        # Reject a stale function contract even if the graph revision is unchanged.
        assert c.post(url,json=body).status_code==409
        body.update(function_version=target['function_version'],function_confirmed=False)
        assert c.post(url,json=body).status_code==422
        body.update(function_confirmed=True)
        result=c.post(url,json=body);assert result.status_code==201,result.text
        pid=result.json()['project_id']
        for code in [result.json()['firmware'],c.get(f'/api/projects/{pid}/firmware').json(),c.get(f'/api/projects/{pid}/new-design').json()['firmware']]:
            assert 'Javalab.org' in code['source'] and 'Elapsed' not in code['source']
        assert result.json()['provenance']['functional_equivalence_verified'] is False
        assert c.get('/api/projects/'+original['project_id']).json()['graph']==original
        stopped=c.post(endpoint+'/function',json={'expected_revision':original['revision'],'kind':'unsupported','description':'자동차를 빈 주차장으로 옮기는 로봇'}).json()
        body['function_version']=stopped['function_version']
        assert not stopped['proposals'] and c.post(url,json=body).status_code==422


def test_function_provider_schema_has_required_fields():
    schema=FunctionalInventory.model_json_schema()
    for node in [schema,*schema['$defs'].values()]:
        if node.get('type')=='object':assert set(node['required'])==set(node['properties'])
