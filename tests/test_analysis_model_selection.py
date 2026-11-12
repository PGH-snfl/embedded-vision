"""No paid calls: exercise chosen model through photo/video upload, jobs and SaaS."""
import io
import json
from copy import deepcopy
from pathlib import Path
import threading

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from backend.application import create_app
from backend.design.inventory import inventory_plan
from backend.planner.provider import PRIMARY,SPECIALIST,ResponsesProvider
from backend.planner.service import create_plan
from test_auto_analysis import Provider,inventory,wait_job,graph,uncertain,decision
from test_single_call_analysis import transport
from test_functional_build import build_inputs


def photo():
    buffer=io.BytesIO();Image.new('RGB',(64,64),'white').save(buffer,format='PNG')
    return {'image':('input.png',buffer.getvalue(),'image/png')}


@pytest.mark.parametrize('model',[PRIMARY,SPECIALIST])
def test_explicit_legacy_full_photo_schema_for_either_model(monkeypatch,model):
    observed,design,_=build_inputs();calls=transport(monkeypatch,{'inventory':observed.model_dump(mode='json'),'design':design})
    result=inventory_plan(graph(),[('image',Path('unused'))],model=model,single_call=True)
    assert len(calls)==1 and calls[0]['model']==model
    assert calls[0]['text']['format']['schema']['required']==['inventory','design']
    assert calls[0]['reasoning']['effort']==('high' if model==SPECIALIST else 'medium')
    assert result['analysis_model']==result['routing']['primary']==model
    assert result['model_call_count']==1 and result['functional_build']==design['functional_build']


@pytest.mark.parametrize('model',[PRIMARY,SPECIALIST])
def test_upload_and_completed_result_record_actual_selected_model(tmp_path,monkeypatch,model):
    monkeypatch.setattr('backend.planner.jobs.status',lambda:{'configured':True})
    monkeypatch.setenv('EMBEDDED_VISION_AUTO_ANALYSIS','1')
    app=create_app(tmp_path);provider=Provider(inventory());app.state.auto_analysis.provider_factory=lambda:provider
    with TestClient(app) as client:
        response=client.post('/api/projects',files=photo(),data={'analysis_model':model})
        assert response.status_code==201
        value=response.json();pid=value['graph']['project_id'];job=wait_job(client,pid)
        assert value['auto_analysis']['analysis_model']==job['analysis_model']==model and job['status']=='done'
        plan=client.get(f"/api/projects/{pid}/planner/{job['plan_id']}").json()['plan']
        assert plan['analysis_model']==plan['routing']['primary']==model
        assert [call['model'] for call in provider.calls]==[model]
        # Completed analysis is not silently re-billed by model-only changes.
        same=client.post(f'/api/projects/{pid}/auto-analysis',json={'expected_revision':1,'model':SPECIALIST if model==PRIMARY else PRIMARY})
        assert same.json()['job']['id']==job['id'] and len(provider.calls)==1


def test_invalid_upload_model_is_rejected_before_any_input_or_job_is_saved(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        response=client.post('/api/projects',files=photo(),data={'analysis_model':'arbitrary-model'})
        assert response.status_code==422 and client.get('/api/projects').json()==[]
        assert not list((tmp_path/'auto_jobs').glob('*.json'))


def test_credential_resume_retains_astra_even_when_request_omits_model(tmp_path,monkeypatch):
    ready={'configured':False};monkeypatch.setattr('backend.planner.jobs.status',lambda:ready)
    monkeypatch.setenv('EMBEDDED_VISION_AUTO_ANALYSIS','1')
    app=create_app(tmp_path);provider=Provider(inventory());app.state.auto_analysis.provider_factory=lambda:provider
    with TestClient(app) as client:
        value=client.post('/api/projects',files=photo(),data={'analysis_model':SPECIALIST}).json();pid=value['graph']['project_id']
        assert value['auto_analysis']['status']=='waiting_credentials'
        ready['configured']=True
        client.post(f'/api/projects/{pid}/auto-analysis',json={'expected_revision':1})
        assert wait_job(client,pid)['analysis_model']==SPECIALIST
        assert [call['model'] for call in provider.calls]==[SPECIALIST]


def test_explicit_model_reanalysis_preserves_previous_plan_and_source_graph(tmp_path,monkeypatch):
    monkeypatch.setattr('backend.planner.jobs.status',lambda:{'configured':True})
    monkeypatch.setenv('EMBEDDED_VISION_AUTO_ANALYSIS','1')
    app=create_app(tmp_path);provider=Provider(inventory(),inventory());app.state.auto_analysis.provider_factory=lambda:provider
    with TestClient(app) as client:
        value=client.post('/api/projects',files=photo()).json();pid=value['graph']['project_id'];first=wait_job(client,pid)
        original=client.get(f'/api/projects/{pid}').json()['graph']
        path=f"/api/projects/{pid}/planner/{first['plan_id']}";old=client.get(path).json()['plan']
        reply=client.post(f'/api/projects/{pid}/auto-analysis?retry=true',json={'expected_revision':1,'model':SPECIALIST})
        assert reply.status_code==200;second=wait_job(client,pid)
        assert second['plan_id']!=first['plan_id'] and second['analysis_model']==SPECIALIST
        assert client.get(path).json()['plan']==old
        assert client.get(f'/api/projects/{pid}').json()['graph']==original
        assert [call['model'] for call in provider.calls]==[PRIMARY,SPECIALIST]


def test_inflight_job_cannot_switch_model_or_make_a_second_call(tmp_path,monkeypatch):
    monkeypatch.setattr('backend.planner.jobs.status',lambda:{'configured':True})
    monkeypatch.setenv('EMBEDDED_VISION_AUTO_ANALYSIS','1');entered=threading.Event();release=threading.Event()
    class Slow(Provider):
        def infer(self,*args,**kwargs):entered.set();release.wait(4);return super().infer(*args,**kwargs)
    app=create_app(tmp_path);provider=Slow(inventory());app.state.auto_analysis.provider_factory=lambda:provider
    with TestClient(app) as client:
        try:
            value=client.post('/api/projects',files=photo(),data={'analysis_model':SPECIALIST}).json();pid=value['graph']['project_id'];assert entered.wait(1)
            response=client.post(f'/api/projects/{pid}/auto-analysis?retry=true',json={'expected_revision':1,'model':PRIMARY})
            assert response.status_code==422 and '진행 중' in response.text
        finally:release.set()
        assert wait_job(client,pid)['analysis_model']==SPECIALIST
        assert len(provider.calls)==1


def test_video_frames_receive_the_selected_model(tmp_path,monkeypatch):
    monkeypatch.setenv('EMBEDDED_VISION_AUTO_ANALYSIS','0')
    monkeypatch.setattr('backend.integration.keyframes',lambda path:[(0,Image.new('RGB',(64,64),'white'))])
    with TestClient(create_app(tmp_path)) as client:
        response=client.post('/api/projects/video',files={'video':('input.mp4',b'synthetic-unit-video','video/mp4')},data={'analysis_model':SPECIALIST})
        assert response.status_code==201 and response.json()['auto_analysis']['analysis_model']==SPECIALIST


def test_direct_astra_circuit_plan_does_not_call_astra_a_second_time():
    provider=Provider(uncertain())
    result=create_plan(graph(),'회로 검토','circuit_inference',[('image',Path('unused'))],provider,model=SPECIALIST)
    assert len(provider.calls)==1 and result['routing']['primary']==SPECIALIST
    assert result['routing']['max_specialist_calls']==0 and not result['routing']['specialist_called']


def test_astra_full_explanation_uses_decision_schema_not_focused_review(monkeypatch):
    calls=transport(monkeypatch,decision().model_dump(mode='json'))
    reply,_=ResponsesProvider().infer(SPECIALIST,{},'설명','explain',[])
    assert 'findings' in calls[0]['text']['format']['schema']['properties'] and reply.summary


def test_saas_worker_keeps_model_bound_to_job_and_workspace(tmp_path,monkeypatch):
    from backend.saas.app import create_saas_app
    from backend.saas.settings import Settings
    from backend.saas.worker import Worker
    origin='http://127.0.0.1:8770';settings=Settings(tmp_path/'saas',origin=origin,development=True,auth_enabled=False)
    monkeypatch.setenv('EMBEDDED_VISION_AUTO_ANALYSIS','1');seen=[]
    def analyze(g,assets,**kwargs):
        seen.append((kwargs['model'],str(assets[0][1])))
        from backend.planner.service import digest
        return {'id':'a'*32,'graph_sha256':digest(g),'analysis_model':kwargs['model']}
    monkeypatch.setattr('backend.planner.jobs.inventory_plan',analyze)
    app=create_saas_app(settings)
    with TestClient(app,base_url=origin) as client:
        wid=client.get('/api/saas/me').json()['default_workspace'];app.state.repository.worker_heartbeat('mock-ready',True)
        response=client.post(f'/api/w/{wid}/projects',headers={'Origin':origin},files=photo(),data={'analysis_model':SPECIALIST})
        assert response.status_code==201;value=response.json();pid=value['graph']['project_id']
        queued=app.state.repository.job(wid,value['auto_analysis']['queue_id'])
        assert json.loads(queued['payload'])['analysis_model']==SPECIALIST
        worker=Worker(settings)
        try:assert worker.run_once()
        finally:worker.close()
        assert seen==[(SPECIALIST,str(settings.data/'tenants'/wid/(pid+'.png')))]
        assert client.get(f'/api/w/{wid}/projects/{pid}/auto-analysis').json()['job']['status']=='done'
        assert client.get(f'/api/w/{"b"*32}/projects/{pid}/auto-analysis').status_code==404
