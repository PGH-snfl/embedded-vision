import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from backend.api import create_app
from backend.circuit.profiles import reference
from backend.circuit.schema import Status
from backend.planner.models import Decision,Finding
from backend.planner.service import create_plan,digest
from backend.planner.provider import PRIMARY,SPECIALIST,ResponsesProvider
from backend.planner.executor import execute,compile_graph,verify_netlist,verdict

def decision():return Decision(summary='검토 결과',findings=[],unresolved=[],conflicts=[],actions=['review_evidence'],deep_review=[])
class FakeProvider:
    def __init__(self,*answers):self.answers=list(answers);self.calls=[]
    def infer(self,model,*args,**kwargs):
        self.calls.append(model);answer=self.answers.pop(0)
        if isinstance(answer,Exception):raise answer
        return answer,{'model':model,'elapsed_seconds':.01,'usage':{'total_tokens':12}}
def graph():return reference('a'*32,'rc_filter')[0]

def test_routine_explanation_never_escalates():
    g=graph();g.links[0].connection.status=Status.INFERRED
    p=FakeProvider(decision());r=create_plan(g,'설명','explain',[],p)
    assert p.calls==[PRIMARY] and not r['executable']

def test_hidden_evidence_does_not_escalate_or_confirm():
    g=graph();before=digest(g);first=decision();first.unresolved=['끝점 가려짐']
    p=FakeProvider(first,decision());r=create_plan(g,'연결 추론','circuit_inference',[],p)
    assert p.calls==[PRIMARY] and not r['routing']['specialist_called']
    assert not r['executable'] and digest(g)==before

def test_empty_photo_graph_alone_does_not_escalate():
    g=graph();g.mode='photo';g.links=[];p=FakeProvider(decision(),decision())
    create_plan(g,'추론','circuit_inference',[],p)
    assert p.calls==[PRIMARY]

def test_clear_circuit_does_not_escalate():
    p=FakeProvider(decision());create_plan(graph(),'추론','circuit_inference',[],p)
    assert p.calls==[PRIMARY]

def test_unknown_and_confirmed_outputs_rejected():
    base={'subject':'wire','status':'UNKNOWN','hypothesis':'U1.1 -> R1.1','asset_ids':[],
          'evidence_ids':[],'terminal_ids':[],'rationale':'guess','verification_needed':'test'}
    with pytest.raises(ValidationError):Finding(**base)
    base.update(status='CONFIRMED')
    with pytest.raises(ValidationError):Finding(**base)
    with pytest.raises(ValidationError):Decision(summary='x',findings=[],unresolved=[],conflicts=[],actions=['run_shell'])

def test_fabricated_terminal_ids_block_build():
    d=decision();d.actions=['build_schematic'];d.findings=[Finding(subject='wire',status='INFERRED',hypothesis='candidate',
        asset_ids=['image'],evidence_ids=['imaginary'],terminal_ids=['U99.1'],rationale='guess',verification_needed='check')]
    p=FakeProvider(d);r=create_plan(graph(),'생성','build_schematic',[('image',Path('x'))],p)
    assert r['validation_errors'] and not r['executable'] and p.calls==[PRIMARY]

def test_unrequested_action_blocked():
    d=decision();d.actions=['build_schematic'];r=create_plan(graph(),'설명','explain',[],FakeProvider(d))
    assert r['validation_errors'] and not r['executable']

def test_verified_build_plan_and_unknown_gate():
    g=graph();d=decision();d.actions=['build_schematic']
    assert create_plan(g,'생성','build_schematic',[],FakeProvider(d))['executable']
    g.links[0].connection.status=Status.INFERRED
    with pytest.raises(ValueError):compile_graph(g)

def test_missing_key_does_not_call_network(monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY',raising=False)
    with pytest.raises(RuntimeError,match='OPENAI_API_KEY'):ResponsesProvider().infer(PRIMARY,graph(),'x','explain',[])

def test_stale_plan_and_replay_blocked(tmp_path,monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','test-only')
    import backend.planner.routes as routes
    d=decision();d.actions=['build_schematic']
    monkeypatch.setattr(routes,'create_plan',lambda g,p,t,a,**kwargs:create_plan(g,p,t,a,FakeProvider(d),**kwargs))
    client=TestClient(create_app(tmp_path));project=client.post('/api/projects/reference',json={'profile':'rc_filter'}).json()
    g=project['graph'];url=f"/api/projects/{g['project_id']}/planner"
    plan=client.post(url,json={'expected_revision':g['revision'],'prompt':'생성','task':'build_schematic'}).json()['plan']
    assert client.get(f"/api/projects/{g['project_id']}").json()['graph']==g
    endpoint=url+'/'+plan['id']+'/execute'
    assert client.post(endpoint,json={'expected_revision':g['revision']+1}).status_code==409
    path=tmp_path/'planner'/g['project_id']/plan['id'];path.mkdir()
    assert client.post(endpoint,json={'expected_revision':g['revision']}).status_code==409
    assert client.get(url+'/bad/artifacts/sch').status_code==404

def test_schema_has_required_fields_for_structured_output():
    schema=Decision.model_json_schema()
    for node in [schema,*schema['$defs'].values()]:
        assert node['additionalProperties'] is False
        assert set(node['required'])==set(node['properties'])

def test_netlist_comparison_detects_wrong_wiring(tmp_path):
    path=tmp_path/'netlist.net';path.write_text('(export (nets (net (name N) (node (ref R1) (pin 1)) (node (ref C1) (pin 2)))))')
    spec={'nets':[{'pins':[{'reference':'R1','pin':'1'},{'reference':'C1','pin':'2'}]}]}
    verify_netlist(path,spec)
    spec['nets'][0]['pins'][1]['pin']='1'
    with pytest.raises(ValueError,match='불일치'):verify_netlist(path,spec)

def test_erc_unknown_never_passes():
    assert verdict({'content':[{'text':'looks fine'}]})=='UNKNOWN'
    assert verdict({'structuredContent':{'verdict':'WARN'}})=='WARN'

def test_failed_mcp_stops_and_records(tmp_path):
    class Broken:
        def __init__(self,root):pass
        def __enter__(self):raise RuntimeError('unavailable')
        def __exit__(self,*args):pass
    result=execute(graph(),tmp_path/'run',Broken)
    assert result['status']=='FAILED' and result['erc']=='NOT_RUN'
    assert json.loads((tmp_path/'run/execution.json').read_text())==result

@pytest.mark.parametrize('http_status,response,error',[
    (200,{'status':'incomplete','output':[]},'완료되지'),
    (200,{'status':'completed','output':[{'type':'message','content':[{'type':'refusal','refusal':'no'}]}]},'거절'),
    (401,{},'HTTP 401'),
    (200,{'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':'{}'}]}]},'스키마'),
])
def test_provider_errors_do_not_fallback(monkeypatch,http_status,response,error):
    import httpx
    import backend.planner.provider as mod
    real_client=httpx.Client;calls=[]
    def handle(request):calls.append(request);return httpx.Response(http_status,json=response)
    monkeypatch.setenv('OPENAI_API_KEY','test-key')
    monkeypatch.setattr(mod.httpx,'Client',lambda **kwargs:real_client(transport=httpx.MockTransport(handle)))
    with pytest.raises(RuntimeError,match=error):create_plan(graph(),'분석','circuit_inference',[])
    assert len(calls)==1

def test_responses_multimodal_contract(monkeypatch,tmp_path):
    import httpx
    from PIL import Image
    import backend.planner.provider as mod
    real_client=httpx.Client;calls=[]
    def handle(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200,json={'id':'response-test','status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':decision().model_dump_json()}]}],'usage':{'total_tokens':42}})
    monkeypatch.setenv('OPENAI_API_KEY','test-key')
    monkeypatch.setattr(mod.httpx,'Client',lambda **kwargs:real_client(transport=httpx.MockTransport(handle)))
    path=tmp_path/'photo.png';Image.new('RGB',(16,16)).save(path)
    d,usage=ResponsesProvider().infer(PRIMARY,graph(),'설명','explain',[('image',path)])
    payload=calls[0]
    assert payload['model']==PRIMARY and payload['store'] is False and 'tools' not in payload
    assert payload['text']['format']['strict'] is True
    assert payload['input'][0]['content'][-1]['image_url'].startswith('data:image/jpeg;base64,')
    assert usage['usage']['total_tokens']==42

def test_component_analysis_requests_visible_parts_before_function_reasoning(monkeypatch):
    import httpx
    import backend.planner.provider as mod
    from backend.design.models import Inventory
    from backend.design.inventory import PROMPT
    sample=Inventory(summary='사진에서 보이는 구성품 후보',parts=[],suggested_function='',unknowns=[])
    real_client=httpx.Client;calls=[]
    def handle(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200,json={'id':'response-test','status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':sample.model_dump_json()}]}]})
    monkeypatch.setenv('OPENAI_API_KEY','test-key')
    monkeypatch.setattr(mod.httpx,'Client',lambda **kwargs:real_client(transport=httpx.MockTransport(handle)))
    result,_=ResponsesProvider().infer(PRIMARY,{'mode':'photo'},PROMPT,'component_inventory',[])
    request=calls[0];instructions=request['instructions']
    assert 'stage 1' in instructions and 'Do not infer' in instructions
    assert 'hidden components' in instructions and 'only' in instructions.casefold()
    assert 'function' not in request['text']['format']['schema']['properties']
    assert request['store'] is False and result.suggested_function==''

def test_server_key_file_permissions_and_env_priority(tmp_path,monkeypatch):
    from backend.planner.provider import api_key,status
    monkeypatch.setenv('EMBEDDED_VISION_DATA',str(tmp_path));monkeypatch.delenv('OPENAI_API_KEY',raising=False)
    path=tmp_path/'openai-api-key';path.write_text('file-test-key');path.chmod(0o600)
    assert api_key()=='file-test-key' and status()['configured']
    assert 'file-test-key' not in json.dumps(status())
    path.chmod(0o644);assert not api_key()
    monkeypatch.setenv('OPENAI_API_KEY','env-test-key');assert api_key()=='env-test-key'
