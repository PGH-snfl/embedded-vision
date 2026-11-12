"""Exercise native Skills payloads and real pixel crops without external calls."""
import base64
from copy import deepcopy
import io
import json
from pathlib import Path

import httpx
from PIL import Image,ImageDraw
import pytest
from fastapi.testclient import TestClient

from backend.application import create_app
from backend.circuit.profiles import reference
from backend.design.inventory import inventory_plan
from backend.planner.inspection_skill import InspectionBudget,InspectionRuntime,VIRTUAL_ROOT
from backend.planner.models import Region
from backend.planner.provider import ResponsesProvider,PRIMARY,SPECIALIST
from backend.vision.component_crops import crop_image
from test_functional_build import build_inputs
from test_auto_analysis import ACTIVE,wait_job


def image(path):
    im=Image.new('RGB',(1600,1000),'white');draw=ImageDraw.Draw(im)
    draw.rectangle((200,200,700,700),fill='red');draw.text((240,240),'TEST 123',fill='black');im.save(path)


def transport(monkeypatch,*,native=False,addition=False,missing_review=False,uninspected=False,duplicate=False):
    observed,design,_=build_inputs();inventory=observed.model_dump(mode='json');calls=[];used_native=False
    def reply(body):return httpx.Response(200,json={'status':'completed','id':'unit-response','output':[{'type':'message','content':[{'type':'output_text','text':json.dumps(body)}]}],'usage':{}})
    def handler(request):
        nonlocal used_native
        payload=json.loads(request.content);calls.append(payload)
        first=json.loads(payload['input'][0]['content'][0]['text']);task=first['task'];context=first['graph']
        if task=='component_inventory':
            assert context['stage']=='component_observation'
            assert 'board_profiles' not in context and 'implementation_catalog' not in context
            assert 'board_workflow' not in context['workflow']
            assert all(e['placement'] not in {'board','board_artwork_only'} for e in context['simulator_catalog']['entries'])
            if native and not used_native:
                used_native=True
                return httpx.Response(200,json={'status':'completed','id':'native-unit','output':[{'type':'shell_call','id':'shell1','call_id':'unit-call','action':{'commands':[
                    'cat '+VIRTUAL_ROOT+'/SKILL.md',
                    'python3 '+VIRTUAL_ROOT+'/scripts/crop.py --asset image --part P1 --box 0.1 0.2 0.4 0.6 --original'],'max_output_length':2000}}]})
            if native:
                for item in payload['input']:
                    if item.get('type')=='shell_call_output':
                        assert item['max_output_length']==2000
            return reply(inventory)
        if task=='component_review':
            rows=[{'part_id':p['id'],'disposition':'visible','kind':p['kind'],'name':p['name'],
                   'model_candidates':p['model_candidates'],'markings':['ZOOM_READ'], 'quantity':p['quantity'],
                   'evidence':'원본 확대에서 보이는 표식 재검토','checks_needed':p['checks_needed']} for p in context['candidates']]
            if missing_review:rows=rows[:-1]
            return reply({'reviews':rows})
        if task=='component_coverage':
            new={**deepcopy(inventory['parts'][0]),'id':'NEW_LED','kind':'led','name':'누락 검사의 추가 LED','model_candidates':['LED'],'quantity':1}
            ids=[p['id'] for p in context['reviewed_inventory']]
            return reply({'summary':'원본 분할 확대와 목록 대조','added_parts':[new] if addition else [],
                          'duplicates':[{'duplicate_id':ids[-1],'keep_id':ids[0],'reason':'같은 물체의 중복 후보'}] if duplicate else [],
                          'uninspected_regions':[inventory['parts'][0]['regions'][0]] if uninspected else []})
        if task=='system_reasoning':
            assert context['stage']=='circuit_design_after_inventory'
            assert context['board_profiles'] and context['implementation_catalog']
            assert all(p['markings']==['ZOOM_READ'] for p in context['observed_inventory']['parts'])
            if addition:assert any(p['id']=='NEW_LED' for p in context['observed_inventory']['parts'])
            return reply(design)
        raise AssertionError('Unexpected task '+task)
    client=httpx.Client
    monkeypatch.setattr('backend.planner.provider.api_key',lambda:'unit-test-only')
    monkeypatch.setattr('backend.planner.provider.httpx.Client',lambda **kwargs:client(transport=httpx.MockTransport(handler)))
    return calls,inventory


@pytest.mark.parametrize('model',[PRIMARY,SPECIALIST])
def test_native_skill_original_zoom_per_id_review_and_final_design(tmp_path,monkeypatch,model):
    path=tmp_path/'source.png';image(path);calls,initial=transport(monkeypatch,native=True);progress=[];checkpoints=[]
    g=reference('a'*32,'rc_filter')[0];before=g.model_dump_json()
    result=inventory_plan(g,[('image',path)],model=model,progress=lambda s,m:progress.append(s),on_inspection=checkpoints.append)
    assert g.model_dump_json()==before
    assert result['analysis_mode']=='skill_inspection' and result['functional_build']
    report=result['component_inspection'];ids={p['id'] for p in initial['parts']}
    assert ids==set(report['reviewed_ids'])==set(report['final_ids'])
    assert report['skill']['binding']=='responses_shell_local'
    assert {e['operation'] for e in report['skill']['tool_events']}=={'read_skill','crop'}
    assert result['model_call_count']==len(calls)==5
    assert {p['model'] for p in calls}=={model}
    assert all(p['text']['format']['type']=='json_schema' and p['text']['format']['strict'] is True for p in calls)
    tools=calls[0]['tools'][0];assert tools['type']=='shell' and tools['environment']['type']=='local'
    assert tools['environment']['skills'][0]['path']==VIRTUAL_ROOT
    follow=calls[1]['input'];assert any(i.get('type')=='shell_call_output' for i in follow)
    assert any(c.get('type')=='input_image' for item in follow[1:] for c in item.get('content',[]))
    reviews=[p for p in calls if json.loads(p['input'][0]['content'][0]['text'])['task']=='component_review']
    assert all(p['tool_choice']=='none' and p['tools'] for p in reviews)
    audits=[p for p in calls if json.loads(p['input'][0]['content'][0]['text'])['task']=='component_coverage']
    assert all(p['tool_choice']=='none' and p['tools'] for p in audits)
    crops=[c for c in report['crops'] if c['purpose']=='component_review']
    assert len(crops)==len(ids) and len(reviews)==1
    review_images=[c for c in reviews[0]['input'][0]['content'] if c['type']=='input_image']
    assert len(review_images)==len(ids)
    for content,crop in zip(review_images,crops):
        im=Image.open(io.BytesIO(base64.b64decode(content['image_url'].split(',')[1])))
        assert list(im.size)==crop['display_size']
    assert 'component_review' in progress and 'coverage' in progress and checkpoints
    assert result['observed_inventory_sha256']==report['final_inventory_sha256']


def test_omission_candidates_are_also_cropped_and_reviewed(tmp_path,monkeypatch):
    path=tmp_path/'source.png';image(path);calls,_=transport(monkeypatch,addition=True,uninspected=True)
    result=inventory_plan(reference('a'*32,'rc_filter')[0],[('image',path)])
    report=result['component_inspection']
    assert 'NEW_LED' in report['added_ids'] and 'NEW_LED' in report['reviewed_ids']
    assert any(c['part_ids']==['NEW_LED'] for c in report['crops'])
    assert report['status']=='partial' and report['uninspected_regions']
    assert len(calls)==5


def test_missing_review_id_stops_before_audit_and_design(tmp_path,monkeypatch):
    path=tmp_path/'source.png';image(path);calls,_=transport(monkeypatch,missing_review=True);saved=[]
    with pytest.raises(RuntimeError,match='부품 ID'):
        inventory_plan(reference('a'*32,'rc_filter')[0],[('image',path)],on_inspection=saved.append)
    assert len(calls)==2 and saved[-1]['initial_ids']


@pytest.mark.parametrize('command',[
    'cat /etc/passwd','curl https://example.com','rm -rf /workspace',
    'cat '+VIRTUAL_ROOT+'/SKILL.md; cat /etc/passwd',
    'python3 '+VIRTUAL_ROOT+'/scripts/crop.py --asset ../../secret --part P1 --box 0 0 1 1 --original',
    'python3 '+VIRTUAL_ROOT+'/scripts/crop.py --asset image --part P1 --box -1 0 1 1 --original',
])
def test_native_shell_rejects_undeclared_commands_and_assets(tmp_path,command):
    path=tmp_path/'source.png';image(path);runtime=InspectionRuntime([('image',path)])
    result=runtime.execute({'call_id':'unit','action':{'commands':[command]}})
    assert result[0]['output'][0]['outcome']['exit_code']==1 and len(result)==1
    assert runtime.events[-1]['allowed'] is False


def test_call_budget_stops_before_an_additional_request():
    budget=InspectionBudget(max_calls=2);budget.charge();budget.charge()
    with pytest.raises(RuntimeError,match='한도'):budget.charge()
    assert budget.calls==2


@pytest.mark.parametrize('limit',[0,2000,12000,50000,None])
def test_shell_result_echoes_requested_limit_and_bounds_actual_output(limit):
    runtime=InspectionRuntime([])
    result=runtime.execute({'call_id':'unit','action':{'commands':[
        'cat '+VIRTUAL_ROOT+'/SKILL.md'],'max_output_length':limit}})[0]
    assert result['max_output_length']==limit
    actual=sum(len(item['stdout'])+len(item['stderr']) for item in result['output'])
    assert actual<=min(12000,limit if limit is not None else 12000)


def test_shell_result_does_not_invent_an_unspecified_limit():
    result=InspectionRuntime([]).execute({'call_id':'unit','action':{
        'commands':['cat '+VIRTUAL_ROOT+'/SKILL.md']}})[0]
    assert 'max_output_length' not in result


def test_crop_uses_original_pixels_and_returns_reproducible_metadata(tmp_path):
    path=tmp_path/'source.png';image(path)
    region=Region(asset_id='image',x0=.2,y0=.3,x1=.3,y1=.5)
    raw,meta=crop_image(path,region);im=Image.open(io.BytesIO(raw))
    assert meta['original_size']==[1600,1000]
    assert meta['display_size'][0]==meta['source_crop_size'][0]*2
    assert im.getpixel((im.width//2,im.height//2))[0]>240
    assert im.getpixel((im.width//2,im.height//2))[1]<20
    assert crop_image(path,region)[0]==raw


def test_job_checkpoint_and_authenticated_crop_endpoint(tmp_path,monkeypatch):
    monkeypatch.setenv('EMBEDDED_VISION_AUTO_ANALYSIS','1')
    monkeypatch.setattr('backend.planner.jobs.status',lambda:{'configured':True})
    calls,_=transport(monkeypatch);app=create_app(tmp_path/'data')
    path=tmp_path/'source.png';image(path)
    with TestClient(app) as client:
        response=client.post('/api/projects',files={'image':('source.png',path.read_bytes(),'image/png')})
        assert response.status_code==201;pid=response.json()['graph']['project_id'];job=wait_job(client,pid)
        assert job['status']=='done' and job['component_inspection']['reviewed_ids']
        plan=client.get(f"/api/projects/{pid}/planner/{job['plan_id']}").json()['plan']
        crop=plan['component_inspection']['crops'][0]
        url=f"/api/projects/{pid}/planner/{job['plan_id']}/inspection/{crop['crop_id']}"
        r=client.get(url);assert r.status_code==200 and r.headers['content-type']=='image/jpeg'
        assert client.get(url.replace(crop['crop_id'],'CROP999')).status_code==404
        assert client.get(url.replace(pid,'f'*32)).status_code==404
        source=app.state.store.root/(pid+'.png');Image.new('RGB',(64,64),'black').save(source)
        assert client.get(url).status_code==409


def test_saas_worker_applies_native_skill_and_isolates_crop_access(tmp_path,monkeypatch):
    from backend.saas.app import create_saas_app
    from backend.saas.settings import Settings
    from backend.saas.worker import Worker
    monkeypatch.setenv('EMBEDDED_VISION_AUTO_ANALYSIS','1');calls,_=transport(monkeypatch,native=True)
    origin='http://127.0.0.1:8770';settings=Settings(tmp_path/'saas',origin=origin,development=True,auth_enabled=False)
    app=create_saas_app(settings);path=tmp_path/'source.png';image(path)
    with TestClient(app,base_url=origin) as client:
        wid=client.get('/api/saas/me').json()['default_workspace'];app.state.repository.worker_heartbeat('unit-worker',True)
        value=client.post(f'/api/w/{wid}/projects',headers={'Origin':origin},files={'image':('source.png',path.read_bytes(),'image/png')},data={'analysis_model':SPECIALIST}).json()
        pid=value['graph']['project_id'];worker=Worker(settings)
        try:assert worker.run_once()
        finally:worker.close()
        job=client.get(f'/api/w/{wid}/projects/{pid}/auto-analysis').json()['job']
        assert job['status']=='done' and job['component_inspection']['skill']['binding']=='responses_shell_local'
        url=f"/api/w/{wid}/projects/{pid}/planner/{job['plan_id']}/inspection/CROP1"
        assert client.get(url).status_code==200
        assert client.get(url.replace(wid,'f'*32)).status_code==404
        assert {c['model'] for c in calls}=={SPECIALIST}
