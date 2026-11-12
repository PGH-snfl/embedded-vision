"""Upload-triggered default selection is inferred and never overwrites a user."""
import json
import pytest
from fastapi.testclient import TestClient
from backend.api import create_app
from backend.design.function import unknown_function
from test_auto_analysis import upload,wait_job
from test_parts_first import inventory
from test_function_hypotheses import led_inventory


def candidate(title,inputs,outputs,id='top',kind='unsupported',rank='medium',part='board'):
    return {'id':id,'title':title,'kind':kind,'status':'INFERRED','plausibility':rank,
        'rationale':'사진의 구성에 근거한 기능 후보','part_ids':[part],
        'evidence':[{'asset_id':'image','observation':'보이는 구성'}],
        'input_behavior':inputs,'output_behavior':outputs,
        'assumptions':['원본 동작은 미확인'],'distinguishing_check':'입력별 출력을 확인',
        'display_text':None}


def make_app(tmp_path,monkeypatch,candidates,inv=None):
    monkeypatch.setenv('EMBEDDED_VISION_AUTO_ANALYSIS','1')
    monkeypatch.setattr('backend.planner.jobs.status',lambda:{'configured':True})
    app=create_app(tmp_path)
    class Provider:
        def infer(self,*args):
            return {**(inv or inventory()).model_dump(mode='json'),
                    'function':unknown_function().model_dump(mode='json'),
                    'function_hypotheses':candidates},{'model':'mock','elapsed_seconds':0}
    app.state.auto_analysis.provider_factory=Provider
    return app


@pytest.mark.parametrize('title,inputs,outputs,expected',[
    ('거리 측정 표시','대상 거리','LCD에 거리 표시','distance_indicator'),
    ('토양 건조 자동 급수','토양 건조','급수','watering'),
    ('장애물 회피 주행','장애물 거리','회피 주행','obstacle_rover')])
def test_auto_upload_prepares_matching_prototype_without_manual_selection(tmp_path,monkeypatch,title,inputs,outputs,expected):
    app=make_app(tmp_path,monkeypatch,[candidate(title,inputs,outputs)])
    with TestClient(app) as c:
        photo=upload(c)['graph'];pid=photo['project_id'];job=wait_job(c,pid)
        assert job['status']=='done'
        base=f"/api/projects/{pid}/inventory/{job['plan_id']}"
        result=c.get(base+'/proposals').json()
        assert result['selection_origin']=='automatic'
        assert result['selected_hypothesis_id']=='top' and result['function']['status']=='INFERRED'
        assert result['prototype_design']['kind']==expected
        version=result['function_version']
        project=c.get(base+'/prototype',params={'function_version':version})
        assert project.status_code==200,project.text
        assert project.json()['workbench']['embeddedVision']['function']['status']=='INFERRED'
        assert not list((tmp_path/'function_targets'/pid).glob('*.json'))
        assert c.get('/api/projects/'+pid).json()['graph']==photo


def test_existing_runnable_led_recipe_also_prepares_automatically(tmp_path,monkeypatch):
    h=candidate('LED 켜기','전원 켜기','LED 켜짐',kind='led_output')
    app=make_app(tmp_path,monkeypatch,[h],led_inventory())
    with TestClient(app) as c:
        pid=upload(c)['graph']['project_id'];job=wait_job(c,pid);base=f"/api/projects/{pid}/inventory/{job['plan_id']}"
        result=c.get(base+'/proposals').json()
        assert result['selection_origin']=='automatic' and result['function']['status']=='INFERRED'
        assert result['recommended']=='arduino_led_output'
        assert c.get(base+'/workbench',params={'recipe':result['recommended'],'function_version':result['function_version']}).status_code==200


def test_automatic_plain_rover_preserves_wheel_evidence(tmp_path,monkeypatch):
    from backend.design.models import ObservedPart
    inv=inventory()
    inv.parts.append(ObservedPart(id='wheel',kind='other',name='바퀴',model_candidates=['바퀴'],quantity=1,
        status='INFERRED',markings=[],regions=[dict(asset_id='image',x0=0,y0=0,x1=.5,y1=.5)],
        evidence='바퀴 후보',checks_needed=['구동 방식 확인']))
    h=candidate('외부 명령에 따른 이동 로봇','주행 또는 정지 명령','바퀴로 차체 이동',part='wheel')
    app=make_app(tmp_path,monkeypatch,[h],inv)
    with TestClient(app) as c:
        pid=upload(c)['graph']['project_id'];job=wait_job(c,pid);base=f"/api/projects/{pid}/inventory/{job['plan_id']}"
        result=c.get(base+'/proposals').json()
        assert result['selection_origin']=='automatic' and result['function']['status']=='INFERRED'
        assert result['robot_design']['selected_candidate_id']=='top'
        assert c.get(base+'/robot-design/workbench',params={'function_version':result['function_version']}).status_code==200


def test_unsupported_top_never_silently_becomes_lower_ranked_recipe(tmp_path,monkeypatch):
    hs=[candidate('정해진 일정으로 급수','일정','급수'),
        candidate('토양 건조 자동 급수','토양 건조','급수',id='other',rank='low')]
    app=make_app(tmp_path,monkeypatch,hs)
    with TestClient(app) as c:
        pid=upload(c)['graph']['project_id'];job=wait_job(c,pid);base=f"/api/projects/{pid}/inventory/{job['plan_id']}"
        result=c.get(base+'/proposals').json()
        assert result['recommended_hypothesis_id']=='top' and result['selection_origin'] is None
        assert result['function']['status']=='UNKNOWN' and result['prototype_design'] is None
        assert result['prototype_candidates']['other']=='watering'


def test_manual_selection_overrides_automatic_and_old_versions_are_rejected(tmp_path,monkeypatch):
    hs=[candidate('거리 표시','대상 거리','LCD 거리 표시'),
        candidate('토양 건조 자동 급수','토양 건조','급수',id='other',rank='low')]
    app=make_app(tmp_path,monkeypatch,hs)
    with TestClient(app) as c:
        photo=upload(c)['graph'];pid=photo['project_id'];job=wait_job(c,pid);base=f"/api/projects/{pid}/inventory/{job['plan_id']}"
        auto=c.get(base+'/proposals').json();assert auto['selection_origin']=='automatic'
        manual=c.post(base+'/function-candidate',json={'expected_revision':1,'candidate_id':'other'}).json()
        assert manual['selection_origin']=='user' and manual['function']['status']=='USER_DEFINED'
        assert manual['prototype_design']['kind']=='watering'
        assert c.get(base+'/prototype',params={'function_version':auto['function_version']}).status_code==409
        again=c.get(base+'/proposals').json();assert again['selected_hypothesis_id']=='other'
        # When the source graph changes, neither auto nor manual design can be
        # reopened with the old analysis.
        g=app.state.store.get(pid);g.title='수정';app.state.store.save(g,1,'test')
        assert c.get(base+'/proposals').status_code==409
