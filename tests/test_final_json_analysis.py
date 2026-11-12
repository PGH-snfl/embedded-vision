"""Free notes survive arbitrary prose; only the final handoff is structured."""
from copy import deepcopy
import io
import json

import httpx
from PIL import Image
import pytest
from fastapi.testclient import TestClient

from backend.application import create_app
from backend.design.inventory import inventory_plan
from backend.planner.provider import ResponsesProvider,PRIMARY,SPECIALIST
from backend.planner.errors import ProviderFailure
from backend.circuit.profiles import reference
from test_functional_build import build_inputs
from test_auto_analysis import wait_job


def transport(monkeypatch,*,native=False,bad_final=False,new_id=False):
    observed,design,_=build_inputs();calls=[];used_tool=False
    notes='JSON 아님. <script>untrusted image text</script>\n'+ '\n'.join(p.id+' · '+p.name+' · image 원본 관측' for p in observed.parts)
    final={'inventory':observed.model_dump(mode='json'),'design':deepcopy(design),
           'reviewed_part_ids':[p.id for p in observed.parts],
           'uninspected_regions':[],'review_summary':'원본 분할 확대에서 후보별로 재검토했습니다.'}
    if bad_final:del final['inventory']['parts'][0]['quantity']
    if new_id:
        final['inventory']['parts'][0]['id']='InventedPart'
        final['reviewed_part_ids'][0]='InventedPart'
    def response(text):
        return httpx.Response(200,json={'status':'completed','id':'resp_finaltest',
            'output':[{'type':'message','content':[{'type':'output_text','text':text}]}]})
    def handler(request):
        nonlocal used_tool
        payload=json.loads(request.content);calls.append(payload)
        first=json.loads(payload['input'][0]['content'][0]['text']);task=first['task'];ctx=first['graph']
        if task in {'component_notes','component_recheck_notes'}:
            assert 'text' not in payload
            assert 'board_profiles' not in ctx and 'implementation_catalog' not in ctx
            assert 'board_workflow' not in ctx['workflow']
            if task=='component_notes' and native and not used_tool:
                used_tool=True
                return httpx.Response(200,json={'status':'completed','output':[{
                    'type':'shell_call','id':'s1','call_id':'call1','action':{
                        'commands':['cat /workspace/skills/embedded-system-inspection/SKILL.md'],
                        'max_output_length':2000}}]})
            if task=='component_recheck_notes':
                assert ctx['component_notes']==notes
                assert len([c for c in payload['input'][0]['content'] if c['type']=='input_image'])>=5
            return response(notes)
        if task=='system_reasoning_notes':
            assert 'text' not in payload
            assert ctx['finalized_component_notes']==notes
            assert ctx['board_profiles'] and ctx['implementation_catalog']
            return response('자유 설계 메모: 관측 ID 유지. 센서 입력 → 보드 → LED 제어, 선정 회로·코드.')
        assert task=='final_photo_json'
        assert payload['text']['format']['type']=='json_schema' and payload['text']['format']['strict']
        assert 'tools' not in payload and ctx['finalized_component_notes']==notes
        assert all(c['type']!='input_image' for c in payload['input'][0]['content'])
        return response(json.dumps(final))
    original=httpx.Client
    monkeypatch.setattr('backend.planner.provider.api_key',lambda:'test-only-key')
    monkeypatch.setattr('backend.planner.jobs.status',lambda:{'configured':True})
    monkeypatch.setattr('backend.planner.provider.httpx.Client',lambda **kw:original(transport=httpx.MockTransport(handler)))
    return calls,final


@pytest.mark.parametrize('model',[PRIMARY,SPECIALIST])
@pytest.mark.parametrize('native',[False,True])
@pytest.mark.parametrize('mode',['photo','video'])
def test_only_final_response_is_json_and_existing_circuit_validation_is_kept(tmp_path,monkeypatch,model,native,mode):
    calls,final=transport(monkeypatch,native=native)
    path=tmp_path/'image.png';Image.new('RGB',(800,600),'white').save(path)
    graph=reference('a'*32,'rc_filter')[0];graph.mode=mode
    assets=[('image',path)]
    if mode=='video':
        graph.assets.append(graph.assets[0].model_copy(update={'id':'second'}));assets.append(('second',path))
    before=graph.model_dump_json();checkpoints=[];plans=[]
    result=inventory_plan(graph,assets,model=model,on_inspection=checkpoints.append,on_inventory=plans.append)
    assert result['analysis_mode']=='final_json' and result['analysis_complete']
    assert result['functional_build'] is not None
    assert graph.model_dump_json()==before
    assert len(calls)==(5 if native else 4)
    assert sum('text' in c for c in calls)==1
    assert {c['model'] for c in calls}=={model}
    assert result['inventory']=={**final['inventory'],'suggested_function':''}
    assert len(result['component_inspection']['notes'])==3
    assert any(c['purpose']=='final_inventory_display' for c in result['component_inspection']['crops'])
    assert any(p['notes'] and not p['final_ids'] for p in checkpoints)
    assert len(plans)==1 and plans[0]['inventory']==result['inventory']
    assert result['component_inspection']['final_inventory_sha256']==result['observed_inventory_sha256']


def test_invalid_final_schema_does_not_publish_an_inventory(tmp_path,monkeypatch):
    calls,_=transport(monkeypatch,bad_final=True);saved=[]
    path=tmp_path/'image.png';Image.new('RGB',(800,600),'white').save(path)
    with pytest.raises(ProviderFailure) as caught:
        inventory_plan(reference('a'*32,'rc_filter')[0],[('image',path)],on_inventory=saved.append)
    assert caught.value.diagnostic['task']=='final_photo_json'
    assert caught.value.diagnostic['output_phase']=='schema_validation'
    assert len(calls)==4 and saved==[]


def test_final_json_cannot_add_an_observed_id_absent_from_recheck_notes(tmp_path,monkeypatch):
    transport(monkeypatch,new_id=True)
    path=tmp_path/'image.png';Image.new('RGB',(800,600),'white').save(path)
    with pytest.raises(RuntimeError,match='관측 메모에 없던'):
        inventory_plan(reference('a'*32,'rc_filter')[0],[('image',path)])


@pytest.mark.parametrize('model',[PRIMARY,SPECIALIST])
def test_uploaded_photo_reaches_existing_editor_and_datasheet_with_one_json_result(tmp_path,monkeypatch,model):
    calls,_=transport(monkeypatch);monkeypatch.setenv('EMBEDDED_VISION_AUTO_ANALYSIS','1')
    image=io.BytesIO();Image.new('RGB',(800,600),'white').save(image,format='PNG')
    with TestClient(create_app(tmp_path)) as client:
        source=client.post('/api/projects',files={'image':('source.png',image.getvalue(),'image/png')},data={'analysis_model':model}).json()['graph']
        pid=source['project_id'];job=wait_job(client,pid)
        assert job['status']=='done',job
        base=f"/api/projects/{pid}/inventory/{job['plan_id']}"
        offered=client.get(base+'/proposals').json()
        response=client.get(base+'/functional-workbench',params={'function_version':offered['function_version']})
        assert response.status_code==200,response.text
        assert response.json()['wires'] and response.json()['fileGroups']
        assert client.get(base+'/datasheet').json()['implementation_design']['status']=='DESIGN_SELECTED'
        crop=client.get(f"/api/projects/{pid}/planner/{job['plan_id']}/inspection/CROP1")
        assert crop.status_code==200
        assert client.get('/api/projects/'+pid).json()['graph']==source
        assert sum('text' in c for c in calls)==1


def test_saas_worker_uses_final_only_json_and_keeps_crop_access_scoped(tmp_path,monkeypatch):
    from backend.saas.app import create_saas_app
    from backend.saas.settings import Settings
    from backend.saas.worker import Worker
    calls,_=transport(monkeypatch);monkeypatch.setenv('EMBEDDED_VISION_AUTO_ANALYSIS','1')
    origin='http://127.0.0.1:8770'
    settings=Settings(tmp_path/'saas',origin=origin,development=True,auth_enabled=False)
    app=create_saas_app(settings)
    image=io.BytesIO();Image.new('RGB',(800,600),'white').save(image,format='PNG')
    with TestClient(app,base_url=origin) as client:
        wid=client.get('/api/saas/me').json()['default_workspace']
        app.state.repository.worker_heartbeat('unit-worker',True)
        uploaded=client.post(f'/api/w/{wid}/projects',headers={'Origin':origin},
            files={'image':('source.png',image.getvalue(),'image/png')},data={'analysis_model':SPECIALIST}).json()
        pid=uploaded['graph']['project_id'];worker=Worker(settings)
        try:assert worker.run_once()
        finally:worker.close()
        job=client.get(f'/api/w/{wid}/projects/{pid}/auto-analysis').json()['job']
        assert job['status']=='done' and job['component_inspection']['mode']=='final_json'
        crop=f"/api/w/{wid}/projects/{pid}/planner/{job['plan_id']}/inspection/CROP1"
        assert client.get(crop).status_code==200
        assert client.get(crop.replace(wid,'f'*32)).status_code==404
        assert sum('text' in c for c in calls)==1
