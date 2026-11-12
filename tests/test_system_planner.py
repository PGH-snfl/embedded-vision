"""Large-system inference is a proposal, never proof of physical behavior."""
import json
from pathlib import Path

import httpx

from backend.design.function import unknown_function
from backend.design.inventory import inventory_plan
from backend.design.recipes import new_graph
from backend.design.component_completion import SystemReasoning
from backend.design.models import Inventory
from backend.planner.provider import PRIMARY, ResponsesProvider
from backend.simulation.virtual_system import simulate_virtual_model


def proposed():
    item = lambda name: {'name': name, 'description': name + ' 가능성',
                         'evidence_asset_ids': ['image'], 'status': 'INFERRED'}
    return {
        'summary': '빈 공간에 차량을 안내하는 축소 시스템 후보',
        'inputs': [item('빈 공간 감지')], 'logic': [item('빈 공간 선택')],
        'outputs': [item('안내 표시')], 'assumptions': ['차량 위치 입력이 필요함'],
        'unknowns': ['실제 운반 방식과 제어 로직'],
        'board_recommendation': {'family': 'raspberry_pi', 'reason': '영상 처리 가정', 'status': 'INFERRED'},
    }


def virtual():
    return {'target_board': 'raspberry_pi',
            'inputs': [{'id':'free', 'label':'빈 공간', 'type':'boolean', 'default':False, 'min':None, 'max':None, 'unit':''}],
            'outputs': [{'id':'indicator', 'label':'안내 표시', 'type':'boolean', 'default':False, 'unit':''}],
            'rules': [{'id':'show', 'conditions':[{'input':'free','operator':'eq','value':True}],
                       'match':'all', 'set':[{'output':'indicator','value':True}], 'status':'INFERRED','enabled':True}],
            'assumptions':['빈 공간이면 표시한다고 가정'],
            'unsupported_requirements':['차량 이동과 카메라 영상 처리']}


def payload():
    return {'summary':'주차장 사진', 'parts':[{'id':'scene','kind':'other','name':'주차 공간 구조',
            'model_candidates':[],'quantity':1,'status':'INFERRED','markings':[],
            'regions':[{'asset_id':'image','x0':0,'y0':0,'x1':1,'y1':1}],
            'evidence':'구획된 주차 공간이 보임','checks_needed':['실제 센서 구성 확인']}], 'suggested_function':'', 'unknowns':[],
            'function':unknown_function().model_dump(mode='json'), 'function_hypotheses':[],
            'required_parts':[],'photo_structure':None,'enclosure_analysis':None,'functional_build':None,'system_model':proposed(), 'virtual_model':virtual()}


class Provider:
    def __init__(self, data): self.data = data
    def infer(self, *args): return self.data, {'model':'FAKE'}


def plan(data):
    graph,_ = new_graph('a'*32, 'arduino_lcd')
    return inventory_plan(graph, [('image',Path('unused'))], Provider(data))


def test_inferred_proposal_is_bounded_and_runs_only_in_abstract_engine():
    result = plan(payload())
    assert result['system_model']['board_recommendation']['family'] == 'raspberry_pi'
    assert result['system_model']['logic'][0]['status'] == 'INFERRED'
    model = result['virtual_model']
    assert model['rules'][0]['set'] == {'indicator': True}
    assert simulate_virtual_model(model, {'free':True})['outputs']['indicator'] is True
    assert simulate_virtual_model(model, {'free':False})['outputs']['indicator'] is False
    assert simulate_virtual_model(model)['status'] == 'partial'
    assert not result['executable']


def test_invalid_proposals_do_not_break_original_inventory():
    data = payload()
    data['system_model']['logic'][0]['evidence_asset_ids'] = ['invented']
    data['virtual_model']['rules'][0]['set'][0]['output'] = 'missing'
    result = plan(data)
    assert result['inventory']['summary'] == '주차장 사진'
    assert result['system_model'] is None and result['virtual_model'] is None
    assert len(result['system_model_warnings']) == 2


def test_unknown_rule_never_executes_and_legacy_data_remains_usable():
    data = payload()
    data['virtual_model']['rules'][0]['status'] = 'UNKNOWN'
    result = plan(data)
    assert not result['virtual_model']['rules'][0]['enabled']
    assert simulate_virtual_model(result['virtual_model'], {'free':True})['outputs']['indicator'] is None
    del data['system_model'], data['virtual_model']
    assert plan(data)['virtual_model'] is None


def test_virtual_model_requires_valid_grounded_system_model():
    for invalid in (None, {**proposed(), 'inputs':[{'name':'입력','description':'추정',
                                                  'evidence_asset_ids':['invented'],'status':'INFERRED'}]},
                    {**proposed(), 'inputs':[], 'logic':[], 'outputs':[]}):
        data = payload()
        data['system_model'] = invalid
        result = plan(data)
        assert result['virtual_model'] is None
        assert any('시스템 기능 추론이 없어' in warning for warning in result['system_model_warnings'])


def test_api_schema_is_strict_and_multimodal_result_is_parsed(monkeypatch):
    schema = SystemReasoning.model_json_schema()
    for node in [schema, *schema['$defs'].values()]:
        if node.get('type') == 'object':
            assert node['additionalProperties'] is False
            assert set(node['required']) == set(node['properties'])
    calls = []
    real_client = httpx.Client
    def handle(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200, json={'status':'completed','output':[{'type':'message', 'content':[
            {'type':'output_text','text':json.dumps({k:v for k,v in payload().items() if k in SystemReasoning.model_fields},ensure_ascii=False)}]}]})
    monkeypatch.setenv('OPENAI_API_KEY','fake-test-key')
    monkeypatch.setattr('backend.planner.provider.httpx.Client',lambda **kw:real_client(transport=httpx.MockTransport(handle)))
    parsed,_ = ResponsesProvider().infer(PRIMARY, {'observed_inventory':{k:v for k,v in payload().items() if k in Inventory.model_fields}}, '분석', 'system_reasoning', [])
    assert parsed.system_model.board_recommendation.family == 'raspberry_pi'
    assert parsed.virtual_model.rules[0].status == 'INFERRED'
    assert calls[0]['text']['format']['strict'] is True


def test_invalid_ai_model_does_not_discard_valid_component_inventory(monkeypatch):
    data = payload()
    data['virtual_model']['target_board'] = 'unsupported-board'
    real_client = httpx.Client
    calls=[]
    def handle(request):
        task=json.loads(json.loads(request.content)['input'][0]['content'][0]['text'])['task']
        calls.append(task)
        result={k:v for k,v in data.items() if k in (Inventory.model_fields if task=='component_inventory' else SystemReasoning.model_fields)}
        return httpx.Response(200, json={'status':'completed','output':[{'type':'message','content':[
            {'type':'output_text','text':json.dumps(result,ensure_ascii=False)}]}]})
    monkeypatch.setenv('OPENAI_API_KEY','fake-test-key')
    monkeypatch.setattr('backend.planner.provider.image_input',lambda _: {'type':'input_image','image_url':'data:image/jpeg;base64,TEST'})
    monkeypatch.setattr('backend.planner.provider.httpx.Client',lambda **kw:real_client(transport=httpx.MockTransport(handle)))
    import pytest
    graph,_=new_graph('a'*32,'arduino_lcd');saved=[]
    with pytest.raises(RuntimeError,match='스키마'):
        inventory_plan(graph,[('image',Path('unused'))],ResponsesProvider(),on_inventory=saved.append,single_call=False)
    assert calls==['component_inventory','system_reasoning']
    assert saved[0]['inventory']['parts'][0]['id']=='scene'
    assert saved[0]['analysis_complete'] is False
