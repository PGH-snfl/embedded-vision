import base64,io,json,threading,time
from pathlib import Path
from PIL import Image
import pytest
from fastapi.testclient import TestClient
from backend.api import create_app
from backend.planner.models import Decision,Finding,DeepReview,Region,FocusedReview,FindingReview
from backend.planner.provider import PRIMARY,SPECIALIST,image_input
from backend.planner.service import create_plan,digest
from backend.circuit.profiles import reference
from backend.planner.jobs import ACTIVE

def decision():return Decision(summary='기본 분석',findings=[],unresolved=[],conflicts=[],actions=['review_evidence'],deep_review=[])
def uncertain():
    d=decision()
    d.findings=[Finding(subject='와이어 분기',status='INFERRED',hypothesis='R1.1 또는 R1.2 연결',asset_ids=['image'],evidence_ids=[],terminal_ids=[],rationale='사진의 두 경로 후보가 보임',verification_needed='실제 도통 확인'),
        Finding(subject='다른 부품',status='UNKNOWN',hypothesis=None,asset_ids=['image'],evidence_ids=[],terminal_ids=[],rationale='표식 안 보임',verification_needed='표식 확인')]
    d.deep_review=[DeepReview(finding_indices=[0],reason='competing_connections',alternatives=['R1.1','R1.2'],question='두 가시 경로 중 어느 것이 연결 후보인가?',visible_evidence='서로 다른 두 끝점으로 이어지는 선분이 보임',solvable_from_visible_evidence=True,region=Region(asset_id='image',x0=.1,y0=.1,x1=.5,y1=.5))]
    return d

def reviewed(index=0):return FocusedReview(summary='국소 검토 결과',reviews=[FindingReview(finding_index=index,status='INFERRED',hypothesis='R1.1 경로 후보',rationale='국소 선분 연속성',verification_needed='도통 측정 필요')],unresolved=[],conflicts=[])
class Provider:
    def __init__(self,*answers):self.answers=list(answers);self.calls=[]
    def infer(self,model,graph,prompt,task,assets,prior=None):
        self.calls.append({'model':model,'graph':graph,'assets':assets});a=self.answers.pop(0)
        if isinstance(a,Exception):raise a
        return a,{'model':'TEST '+model,'elapsed_seconds':.01,'usage':None}
def graph():return reference('a'*32,'rc_filter')[0]

def test_focus_only_crops_and_target_findings_are_sent():
    g=graph();before=digest(g);d=uncertain();p=Provider(d,reviewed())
    r=create_plan(g,'추론','circuit_inference',[('image',Path('photo.png'))],p)
    assert [c['model'] for c in p.calls]==[PRIMARY,SPECIALIST]
    assert [f['finding_index'] for f in p.calls[1]['graph']['findings']]==[0]
    assert not p.calls[1]['graph']['components'] and isinstance(p.calls[1]['assets'][0][1],tuple)
    assert r['decision']['findings'][1]==d.findings[1].model_dump(mode='json')
    assert r['decision']['findings'][0]['status']=='INFERRED' and digest(g)==before
    assert r['routing']['focused_finding_indices']==[0]

@pytest.mark.parametrize('case',['no_evidence','full_image','bad_index','duplicate_alternatives','wrong_asset'])
def test_no_unjustified_escalation(case):
    d=uncertain();issue=d.deep_review[0]
    if case=='no_evidence':issue.solvable_from_visible_evidence=False
    if case=='full_image':issue.region=Region(asset_id='image',x0=0,y0=0,x1=1,y1=1)
    if case=='bad_index':issue.finding_indices=[99]
    if case=='duplicate_alternatives':issue.alternatives=['same','same']
    if case=='wrong_asset':issue.region.asset_id='missing'
    p=Provider(d);r=create_plan(graph(),'추론','circuit_inference',[('image',Path('x'))],p)
    assert len(p.calls)==1 and r['routing']['skipped_reviews']

def test_invalid_primary_references_do_not_escalate():
    d=uncertain();d.findings[0].terminal_ids=['invented'];p=Provider(d)
    r=create_plan(graph(),'추론','circuit_inference',[('image',Path('x'))],p)
    assert len(p.calls)==1 and r['validation_errors']

@pytest.mark.parametrize('response',[RuntimeError('API unavailable'),reviewed(1)])
def test_failed_or_out_of_scope_specialist_preserves_primary(response):
    d=uncertain();p=Provider(d,response);r=create_plan(graph(),'推론','circuit_inference',[('image',Path('x'))],p)
    assert len(p.calls)==2 and r['routing']['specialist_error']
    assert r['decision']['findings']==d.model_dump()['findings']

def test_actual_crop_dimensions(tmp_path):
    p=tmp_path/'input.png';Image.new('RGB',(1000,800)).save(p)
    encoded=image_input((p,Region(asset_id='image',x0=.1,y0=.1,x1=.5,y1=.5)))
    im=Image.open(io.BytesIO(base64.b64decode(encoded['image_url'].split(',')[1])))
    assert im.size==(400,320)

def inventory():
    from backend.design.models import Inventory
    return Inventory(summary='부품 없음',parts=[],suggested_function='판단 불가',unknowns=['표식 없음'])

def upload(client):
    b=io.BytesIO();Image.new('RGB',(64,64),'red').save(b,format='PNG')
    response=client.post('/api/projects',files={'image':('photo.png',b.getvalue(),'image/png')})
    assert response.status_code==201;return response.json()
def wait_job(client,pid):
    deadline=time.monotonic()+3
    while time.monotonic()<deadline:
        j=client.get(f'/api/projects/{pid}/auto-analysis').json()['job']
        if j['status'] not in ACTIVE:return j
        time.sleep(.01)
    raise AssertionError('job did not complete')

def test_upload_alone_starts_background_analysis_and_deduplicates(tmp_path,monkeypatch):
    monkeypatch.setenv('EMBEDDED_VISION_AUTO_ANALYSIS','1');monkeypatch.setattr('backend.planner.jobs.status',lambda:{'configured':True})
    app=create_app(tmp_path);p=Provider(inventory());app.state.auto_analysis.provider_factory=lambda:p
    with TestClient(app) as client:
        result=upload(client);pid=result['graph']['project_id'];j=wait_job(client,pid)
        assert j['status']=='done' and len(p.calls)==1
        plan=client.get(f"/api/projects/{pid}/planner/{j['plan_id']}").json()['plan']
        assert not plan['executable']
        client.post(f'/api/projects/{pid}/auto-analysis',json={'expected_revision':1})
        assert len(p.calls)==1
        assert client.get(f'/api/projects/{pid}').json()['graph']==result['graph']

def test_missing_key_waits_then_resumes(tmp_path,monkeypatch):
    monkeypatch.setenv('EMBEDDED_VISION_AUTO_ANALYSIS','1');ready={'configured':False}
    monkeypatch.setattr('backend.planner.jobs.status',lambda:ready)
    app=create_app(tmp_path);p=Provider(inventory());app.state.auto_analysis.provider_factory=lambda:p
    with TestClient(app) as c:
        r=upload(c);pid=r['graph']['project_id'];assert r['auto_analysis']['status']=='waiting_credentials' and not p.calls
        ready['configured']=True
        c.post(f'/api/projects/{pid}/auto-analysis',json={'expected_revision':1})
        assert wait_job(c,pid)['status']=='done' and len(p.calls)==1

def test_restart_marks_inflight_interrupted_and_never_retries(tmp_path,monkeypatch):
    app=create_app(tmp_path)
    with TestClient(app) as c:r=upload(c)
    pid=r['graph']['project_id'];path=tmp_path/'auto_jobs'/(pid+'.json');data=json.loads(path.read_text());data['status']='sol';path.write_text(json.dumps(data))
    app2=create_app(tmp_path)
    with TestClient(app2) as c:
        assert c.get(f'/api/projects/{pid}/auto-analysis').json()['job']['status']=='interrupted'

def test_revision_change_marks_result_stale(tmp_path,monkeypatch):
    monkeypatch.setenv('EMBEDDED_VISION_AUTO_ANALYSIS','1');monkeypatch.setattr('backend.planner.jobs.status',lambda:{'configured':True})
    entered=threading.Event();release=threading.Event()
    class Slow(Provider):
        def infer(self,*a,**kw):entered.set();release.wait(3);return super().infer(*a,**kw)
    app=create_app(tmp_path);p=Slow(inventory());app.state.auto_analysis.provider_factory=lambda:p
    with TestClient(app) as c:
        r=upload(c);pid=r['graph']['project_id'];assert entered.wait(1)
        store=app.state.store;g=store.get(pid);g.title='edited';store.save(g,1,'test edit');release.set()
        j=wait_job(c,pid);assert j['status']=='stale'
        assert c.get(f"/api/projects/{pid}/planner/{j['plan_id']}").json()['plan']['stale']
