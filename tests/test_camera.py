import json,time
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from backend.api import create_app
from backend.circuit.schema import Status
from backend.vision.vlm import Observation,merge_observation
import backend.vision.routes as vision


def observation(visible=True):
    return Observation.model_validate({
        "summary":"검토가 필요한 실제 사진 후보",
        "components":[
            {"id":"U1","kind":"board","label":"Arduino 후보","bbox":[100,100,400,400],"markings":"UNO","terminals":["GND"]},
            {"id":"R1","kind":"resistor","label":"저항 후보","bbox":[600,600,700,800],"markings":"","terminals":["1"]}],
        "connections":[{"from_part":"U1","from_pin":"GND","to_part":"R1","to_pin":"1",
                        "both_endpoints_visible":visible,"reason":"모델 연결 제안 · 사용자 검토 필요"}],
        "unknowns":["보드 헤더를 가까이 촬영하세요."]})


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path)) as client:yield client


def camera(client):
    r=client.post('/api/projects/camera-example')
    assert r.status_code==201
    return r.json()['graph']


def test_camera_example_is_real_and_has_no_seeded_circuit(client):
    g=camera(client)
    assert g['mode']=='photo' and not g['assets'][0]['synthetic']
    assert g['components']==[] and g['links']==[]
    assert 'CC BY-SA' in g['evidence'][0]['text']


@pytest.mark.parametrize('visible',[True,False])
def test_vlm_never_confirms_or_guesses_values(client,visible):
    from backend.circuit.schema import Graph
    g=Graph.model_validate(camera(client))
    g,report=merge_observation(g,'image',observation(visible),{'engine':'test'})
    assert all(c.label.status==Status.INFERRED for c in g.components)
    assert all(c.value.status==Status.UNKNOWN for c in g.components)
    assert all(t.pin_mapping.status==Status.UNKNOWN for c in g.components for t in c.terminals)
    assert g.links[0].connection.status==Status.UNKNOWN
    assert report['auto_confirmed']==0
    Graph.model_validate(g.model_dump())


def test_invalid_model_coordinates_and_schema_are_rejected():
    raw=observation().model_dump();raw['components'][0]['bbox']=[900,0,100,400]
    with pytest.raises(ValueError):Observation.model_validate(raw)
    raw=observation().model_dump();raw['components'][0]['status']='CONFIRMED'
    with pytest.raises(ValueError):Observation.model_validate(raw)


def test_missing_terminal_reference_is_not_fabricated(client):
    from backend.circuit.schema import Graph
    o=observation();o.connections[0].to_pin='MADE_UP'
    g,r=merge_observation(Graph.model_validate(camera(client)),'image',o,{})
    assert g.links==[] and len(r['review_questions'])==2


def test_async_analysis_real_graph_commit_and_model_failure(client,monkeypatch):
    monkeypatch.setattr(vision,'health',lambda:{'ready':True})
    monkeypatch.setattr(vision,'infer',lambda path, **kwargs:(observation(),{'engine':'test','elapsed_seconds':0}))
    g=camera(client);pid=g['project_id']
    r=client.post(f'/api/projects/{pid}/vision',json={'expected_revision':1,'asset_ids':['image']})
    assert r.status_code==202
    jid=r.json()['id']
    for _ in range(100):
        job=client.get(f'/api/projects/{pid}/vision/jobs/{jid}').json()
        if job['status'] in {'done','error'}:break
        time.sleep(.01)
    assert job['status']=='done'
    result=client.get(f'/api/projects/{pid}').json()
    assert result['graph']['revision']==2
    assert result['integrated']['vision']['frames'][0]['auto_confirmed']==0
    assert result['integrated']['readiness']
    monkeypatch.setattr(vision,'health',lambda:{'ready':False})
    assert client.post(f'/api/projects/{pid}/vision',json={'expected_revision':2,'asset_ids':['image']}).status_code==503


def test_unknown_asset_and_synthetic_analysis_blocked(client,monkeypatch):
    monkeypatch.setattr(vision,'health',lambda:{'ready':True})
    g=camera(client);pid=g['project_id']
    assert client.post(f'/api/projects/{pid}/vision',json={'expected_revision':1,'asset_ids':['../other']}).status_code==422
    demo=client.post('/api/projects/demo').json()['graph']
    assert client.post(f"/api/projects/{demo['project_id']}/vision",json={'expected_revision':1,'asset_ids':['image']}).status_code==422


def test_candidate_rejection_preserves_history_and_terminal_addition(client,monkeypatch):
    from backend.circuit.schema import Graph
    from backend.circuit.store import Store
    g=camera(client)
    # Exercise the public job interface to add model candidates.
    monkeypatch.setattr(vision,'health',lambda:{'ready':True})
    monkeypatch.setattr(vision,'infer',lambda path, **kwargs:(observation(),{'engine':'test','elapsed_seconds':0}))
    base=f"/api/projects/{g['project_id']}"
    jid=client.post(base+'/vision',json={'expected_revision':1,'asset_ids':['image']}).json()['id']
    for _ in range(100):
        j=client.get(base+'/vision/jobs/'+jid).json()
        if j['status'] in {'done','error'}:break
        time.sleep(.01)
    assert j['status']=='done'
    cid=client.get(base).json()['graph']['components'][0]['id']
    r=client.post(base+f'/vision/candidates/{cid}/terminals',json={'expected_revision':2,'note':'보드의 3V3 라벨을 관측함','terminal_names':['3V3']})
    assert r.status_code==200 and len(r.json()['graph']['components'][0]['terminals'])==2
    r=client.post(base+f'/vision/candidates/{cid}/reject',json={'expected_revision':3,'note':'부품 오인식으로 제외함'})
    assert r.status_code==200 and len(r.json()['graph']['components'])==1
    assert r.json()['graph']['links']==[]
    assert len(client.get(base+'/history').json())==4


def test_multiple_frames_keep_separate_component_identities(client,monkeypatch):
    monkeypatch.setattr(vision,'health',lambda:{'ready':True})
    monkeypatch.setattr(vision,'infer',lambda path, **kwargs:(observation(),{'engine':'test','elapsed_seconds':0}))
    g=camera(client);base=f"/api/projects/{g['project_id']}"
    data=client.post(base+'/assets?expected_revision=1',files={'image':('angle.jpg',(vision.ROOT/'data/photos/arduino-camera.jpg').read_bytes(),'image/jpeg')}).json()
    assets=[a['id'] for a in data['graph']['assets']]
    jid=client.post(base+'/vision',json={'expected_revision':2,'asset_ids':assets}).json()['id']
    for _ in range(100):
        j=client.get(base+'/vision/jobs/'+jid).json()
        if j['status'] in {'done','error'}:break
        time.sleep(.01)
    assert j['status']=='done'
    data=client.get(base).json()
    parts=data['graph']['components']
    assert len(parts)==len({p['id'] for p in parts})==4
    assert {p['asset_id'] for p in parts}==set(assets)
    assert len(data['integrated']['vision']['frames'])==2


def test_concurrent_user_edit_is_not_overwritten(client,monkeypatch):
    import threading
    started=threading.Event();release=threading.Event()
    def delayed(path, **kwargs):
        started.set();release.wait(5)
        return observation(),{'engine':'test','elapsed_seconds':0}
    monkeypatch.setattr(vision,'health',lambda:{'ready':True})
    monkeypatch.setattr(vision,'infer',delayed)
    g=camera(client);base=f"/api/projects/{g['project_id']}"
    jid=client.post(base+'/vision',json={'expected_revision':1,'asset_ids':['image']}).json()['id']
    assert started.wait(2)
    try:
        r=client.post(base+'/components',json={'expected_revision':1,'kind':'other','label':'사용자 직접 지정',
            'bbox':[{'x':.1,'y':.1},{'x':.2,'y':.2}]})
        assert r.status_code==200
    finally:release.set()
    for _ in range(100):
        j=client.get(base+'/vision/jobs/'+jid).json()
        if j['status'] in {'done','error'}:break
        time.sleep(.01)
    assert j['status']=='error'
    graph=client.get(base).json()['graph']
    assert graph['revision']==2 and len(graph['components'])==1
    assert graph['components'][0]['label']['value']=='사용자 직접 지정'
