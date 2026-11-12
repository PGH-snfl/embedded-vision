import json
from copy import deepcopy
from pathlib import Path
import httpx
import pytest
from backend.design.inventory import inventory_plan
from backend.design.component_completion import PhotoSystemAnalysis
from backend.design.recipes import new_graph
from backend.planner.provider import ResponsesProvider
from test_functional_build import build_inputs


def transport(monkeypatch,body):
    calls=[];client=httpx.Client
    def handle(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200,json={'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':json.dumps(body)}]}]})
    monkeypatch.setenv('OPENAI_API_KEY','fake-test-key')
    monkeypatch.setattr('backend.planner.provider.image_input',lambda _: {'type':'input_image','image_url':'data:image/jpeg;base64,TEST'})
    monkeypatch.setattr('backend.planner.provider.httpx.Client',lambda **kw:client(transport=httpx.MockTransport(handle)))
    return calls


def test_explicit_legacy_path_posts_one_image_request_for_the_complete_design(monkeypatch):
    observed,design,_=build_inputs();body={'inventory':observed.model_dump(mode='json'),'design':design}
    calls=transport(monkeypatch,body);graph,_=new_graph('a'*32,'arduino_lcd');before=graph.model_dump_json();saved=[]
    def checkpoint(plan):
        assert len(calls)==1 and plan['analysis_complete'] is False
        saved.append(deepcopy(plan))
    plan=inventory_plan(graph,[('image',Path('unused'))],on_inventory=checkpoint,single_call=True)
    assert len(calls)==1 and len(plan['attempts'])==1 and plan['model_call_count']==1
    assert plan['analysis_mode']=='single_call' and plan['functional_build']==design['functional_build']
    assert plan['inventory']==saved[0]['inventory']
    assert plan['component_datasheet']['implementation_design']['status']=='DESIGN_SELECTED'
    assert graph.model_dump_json()==before
    content=calls[0]['input'][0]['content']
    assert sum(p['type']=='input_image' for p in content)==1
    assert json.loads(content[0]['text'])['task']=='photo_system'
    assert calls[0]['text']['format']['schema']['required']==['inventory','design']


def test_invalid_combined_response_does_not_retry_or_make_a_second_request(monkeypatch):
    observed,design,_=build_inputs();design['functional_build']['parts'][0]['location']='invented'
    calls=transport(monkeypatch,{'inventory':observed.model_dump(mode='json'),'design':design});saved=[]
    with pytest.raises(RuntimeError,match='스키마'):
        inventory_plan(new_graph('a'*32,'arduino_lcd')[0],[('image',Path('unused'))],on_inventory=saved.append,single_call=True)
    assert len(calls)==1 and saved==[]


def test_combined_schema_requires_all_fields_and_forbids_extra_keys():
    s=PhotoSystemAnalysis.model_json_schema()
    for node in [s,*s['$defs'].values()]:
        if node.get('type')=='object':
            assert node['additionalProperties'] is False
            assert set(node['required'])==set(node['properties'])
