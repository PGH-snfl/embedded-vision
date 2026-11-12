"""The same processing contract crosses upload, analysis and design boundaries."""
from copy import deepcopy
import io
import time

from fastapi.testclient import TestClient
from PIL import Image
import pytest

from backend.application import create_app
from backend.workflow import workflow_definition, workflow_stamp, STAGE_ORDER
from backend.planner.provider import ResponsesProvider
from backend.planner.jobs import ACTIVE
from backend.design.implementation import realize
from backend.design.photo_appearance import attach_photo_appearance
from backend.saas.app import create_saas_app
from backend.saas.settings import Settings
from test_functional_build import build_inputs
from test_photo_structure import scene


def test_contract_is_ordered_versioned_and_not_mutable_by_callers():
    stamp=workflow_stamp();definition=workflow_definition()
    assert [s['id'] for s in definition['stages']]==list(STAGE_ORDER)
    assert definition['input_modes']==['photo','video']
    assert definition['sha256']==stamp['sha256'] and len(stamp['sha256'])==64
    assert stamp['kind']=='processing_contract' and 'completed' not in stamp
    definition['stages'].clear();stamp['viewer']['views'].clear()
    assert len(workflow_definition()['stages'])==11
    assert workflow_stamp()['viewer']['views']==['assembled','exploded','circuit']


@pytest.mark.parametrize('mode',['photo','video'])
@pytest.mark.parametrize('kind',['dimmer','servo'])
def test_staged_upload_finishes_inventory_before_board_design_and_editor(tmp_path,monkeypatch,mode,kind):
    observed,design,_=build_inputs(kind);design['photo_structure']=scene();calls=[]
    observed.suggested_function=''
    def infer(self,model,context,prompt,task,assets,prior=None):
        calls.append((context,prompt,task,assets))
        if task=='component_inventory':
            assert 'board_workflow' not in context['workflow']
            assert 'board_profiles' not in context and 'implementation_catalog' not in context
            return observed,{'model':'TEST','usage':None}
        assert context['workflow']==workflow_stamp()
        assert context['observed_inventory']==observed.model_dump(mode='json')
        assert '공통 워크플로우 v'+str(workflow_definition()['version']) in prompt
        assert prompt.index('관측 구성품 목록')<prompt.index('목록 기반 기능 추론')
        assert task=='system_reasoning'
        return deepcopy(design),{'model':'TEST','usage':None}
    monkeypatch.setattr(ResponsesProvider,'infer',infer)
    monkeypatch.setattr('backend.planner.jobs.status',lambda:{'configured':True})
    monkeypatch.setenv('EMBEDDED_VISION_AUTO_ANALYSIS','1')
    monkeypatch.setattr('backend.integration.keyframes',lambda _: [(0.,Image.new('RGB',(64,64),'red')),(1.,Image.new('RGB',(64,64),'blue'))])
    app=create_app(tmp_path)
    app.state.auto_analysis.provider_factory=lambda:ResponsesProvider(component_inspection=False)
    with TestClient(app) as client:
        if mode=='photo':
            picture=io.BytesIO();Image.new('RGB',(64,64),'red').save(picture,format='PNG')
            response=client.post('/api/projects',files={'image':('camera.png',picture.getvalue(),'image/png')})
        else:response=client.post('/api/projects/video',files={'video':('system.mp4',b'controlled-test-frames','video/mp4')})
        assert response.status_code==201,response.text
        source=response.json()['graph'];pid=source['project_id']
        deadline=time.monotonic()+5
        while True:
            job=client.get(f'/api/projects/{pid}/auto-analysis').json()['job']
            if job['status'] not in ACTIVE:break
            assert time.monotonic()<deadline
            time.sleep(.01)
        assert job['status']=='done' and job['workflow']==workflow_stamp()
        plan=client.get(f"/api/projects/{pid}/planner/{job['plan_id']}").json()['plan']
        assert len(calls)==2 and calls[0][0]['mode']==mode
        assert len(calls[0][3])==(2 if mode=='video' else 1)
        assert plan['workflow']==workflow_stamp() and plan['model_call_count']==2
        assert client.get(f'/api/projects/{pid}').json()['graph']==source
        result=realize(plan,plan['function_hypotheses'][0],{})
        native=result['workbench']
        assert native['embeddedVision']['workflow']==workflow_stamp()
        assert native['fileGroups']['group-U1'][0]['content']==design['functional_build']['firmware']
        assert len(native['wires'])==len(design['functional_build']['connections'])
        assert native['embeddedVision']['photo_assembly']['explosion']=='viewer_only'
        assert any(p['properties'].get('evPhotoStructure') for p in native['components'])


def test_local_and_workspace_endpoints_expose_the_same_contract(tmp_path):
    with TestClient(create_app(tmp_path/'local')) as client:
        assert client.get('/api/workflow').json()==workflow_definition()
    settings=Settings(tmp_path/'saas',origin='http://127.0.0.1:8770',development=True,auth_enabled=False)
    with TestClient(create_saas_app(settings),base_url=settings.origin) as client:
        wid=client.get('/api/saas/me').json()['default_workspace']
        response=client.get(f'/api/w/{wid}/workflow')
        assert response.status_code==200 and response.json()==workflow_definition()
        assert client.get(f"/api/w/{'a'*32}/workflow").status_code==404


def test_attaching_contract_does_not_change_saved_electrical_or_code_data():
    original={'components':[{'id':'D1','properties':{'label':'edited'}}],'wires':[{'id':'user-wire'}],
        'boards':[{'id':'U1'}],'fileGroups':{'main':'user edited code'},'embeddedVision':{'custom':True}}
    before=deepcopy(original)
    updated=attach_photo_appearance(original,None)
    assert original==before
    assert updated['embeddedVision']['workflow']==workflow_stamp()
    for key in ('components','wires','boards','fileGroups'):assert updated[key] is original[key]
    assert updated['embeddedVision']['custom'] is True
