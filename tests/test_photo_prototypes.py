import json
import pytest
from fastapi.testclient import TestClient
from backend.api import create_app
from backend.design.prototype_match import prototype_kind
from test_parts_first import setup


@pytest.mark.parametrize('title,inputs,outputs,expected',[
    ('거리 측정 표시 및 근접 알림','대상 거리','LCD에 거리 표시','distance_indicator'),
    ('토양이 건조할 때 자동 급수','토양이 건조','건조할 때 급수','watering'),
    ('거리 감지 기반 장애물 회피 주행','전방 장애물','회피 주행','obstacle_rover'),
    ('정해진 일정으로 급수하며 토양 상태 감시','일정','급수','none'),
    ('자동 주차 로봇','빈 공간','주차','none'),
    ('물체와의 간격을 유지하는 주행','거리','간격 유지','none'),
])
def test_goal_classification_is_bounded(title,inputs,outputs,expected):
    result=prototype_kind({'kind':'unsupported','title':title,'input_behavior':inputs,'output_behavior':outputs})
    assert result==(None if expected=='none' else expected)


@pytest.mark.parametrize('title,inputs,outputs,expected',[
    ('거리 측정 표시 및 근접 알림','대상 거리','LCD에 거리 표시','distance_indicator'),
    ('토양이 건조할 때 자동 급수','토양 건조','급수','watering'),
    ('거리 감지 기반 장애물 회피 주행','장애물','회피 주행','obstacle_rover'),
])
def test_selected_photo_goal_opens_matching_project(tmp_path,title,inputs,outputs,expected):
    app=create_app(tmp_path)
    with TestClient(app) as client:
        original,url,_=setup(client,app,tmp_path);endpoint=url.removesuffix('/design')
        path=next((tmp_path/'planner'/original['project_id']).glob('*.json'))
        plan=json.loads(path.read_text())
        plan['function_hypotheses']=[{'id':'target','title':title,'kind':'unsupported','status':'INFERRED',
            'plausibility':'medium','rationale':'사진을 근거로 추정한 기능',
            'part_ids':[plan['inventory']['parts'][0]['id']],
            'evidence':[{'asset_id':'image','observation':'사진에 보이는 부품'}],
            'input_behavior':inputs,'output_behavior':outputs,'assumptions':['새 설계 가정'],
            'distinguishing_check':'추가 확인','display_text':None}]
        path.write_text(json.dumps(plan,ensure_ascii=False))
        offered=client.get(endpoint+'/proposals').json()
        assert offered['prototype_candidates']['target']==expected
        assert client.get(endpoint+'/prototype',params={'function_version':offered['function_version']}).status_code==422
        selected=client.post(endpoint+'/function-candidate',json={'expected_revision':original['revision'],'candidate_id':'target'}).json()
        assert selected['prototype_design']['kind']==expected
        response=client.get(endpoint+'/prototype',params={'function_version':selected['function_version']})
        assert response.status_code==200,response.text
        result=response.json()
        assert result['kind']==expected and result['workbench']['format']=='velxio-project'
        assert result['workbench']['fileGroups']['group-U1'][0]['content']
        assert not result['workbench']['embeddedVision']['physical_verified']
        assert client.get(endpoint+'/prototype',params={'function_version':'0'*64}).status_code==409
        assert client.get('/api/projects/'+original['project_id']).json()['graph']==original
