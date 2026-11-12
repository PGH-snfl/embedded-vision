import io
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import pytest
from PIL import Image,ImageDraw
from pydantic import ValidationError
from fastapi.testclient import TestClient
from backend.api import create_app
from backend.circuit.schema import Claim,Graph,Status
from backend.circuit.connectivity import derive_nets
from backend.circuit.store import Store,Conflict
from backend.vision.demo import create_demo
from backend.vision.wires import detect_color_candidates


@pytest.fixture
def graph(): return create_demo("a"*32)[0]


@pytest.fixture
def client(tmp_path): return TestClient(create_app(tmp_path))


def image_bytes(color="white"):
    img=Image.new("RGB",(200,150),color)
    out=io.BytesIO();img.save(out,format="PNG");return out.getvalue()


@pytest.mark.parametrize("data",[
    {"value":"10k","status":"UNKNOWN"},
    {"score":.9,"status":"UNKNOWN"},
    {"value":"10k","status":"CONFIRMED"},
    {"status":"INFERRED"},
    {"value":"10k","status":"INFERRED","score":1.1},
    {"value":"10k","status":"INFERRED","score":float("nan")},
    {"value":"10k","status":"INFERRED","calibrated":True},
])
def test_bad_claim_rejected(data):
    with pytest.raises(ValidationError): Claim(**data)


def test_unknown_preserves_candidates():
    c=Claim(candidates=["1k","10k"])
    assert c.value is None and c.status==Status.UNKNOWN


@pytest.mark.parametrize("change",["missing_evidence","duplicate_terminal","missing_terminal","known_hidden","bad_box"])
def test_graph_integrity(graph,change):
    raw=graph.model_dump()
    if change=="missing_evidence":raw["components"][0]["label"]["evidence_ids"]=["absent"]
    elif change=="duplicate_terminal":raw["components"][0]["terminals"].append(raw["components"][0]["terminals"][0])
    elif change=="missing_terminal":raw["links"][0]["from_terminal"]="absent"
    elif change=="known_hidden":raw["links"][5]["connection"]={"value":"connected","status":"INFERRED"}
    elif change=="bad_box":raw["components"][0]["bbox"].reverse()
    with pytest.raises(ValidationError): Graph.model_validate(raw)


def group(nets,terminal): return next(set(n["terminals"]) for n in nets if terminal in n["terminals"])


def test_inferred_and_hidden_do_not_merge_confirmed_nets(graph):
    assert group(derive_nets(graph),"U1.GPIO18")=={"U1.GPIO18"}
    assert "SW1.1" in group(derive_nets(graph,True),"U1.GPIO18")
    assert group(derive_nets(graph,True),"SW1.2")=={"SW1.2"}


def test_geometric_crossing_does_not_join(graph):
    graph.links[0].path=graph.links[3].path
    assert "U1.3V3" not in group(derive_nets(graph),"U1.GPIO23")


def test_store_reload_history_and_conflict(tmp_path,graph):
    store=Store(tmp_path);store.save(graph,0,"create")
    saved=store.save(graph,1,"review")
    assert saved.revision==2
    with pytest.raises(Conflict):store.save(graph,1,"stale")
    assert Store(tmp_path).get(graph.project_id).revision==2
    assert Store(tmp_path).get(graph.project_id,1).revision==1
    assert len(store.history(graph.project_id))==2


def test_observations_immutable(tmp_path,graph):
    store=Store(tmp_path);store.save(graph,0,"create")
    graph.evidence[0].text="overwrite"
    with pytest.raises(ValueError):store.save(graph,1,"tamper")


def test_concurrent_edits_only_one_wins(tmp_path,graph):
    store=Store(tmp_path);store.save(graph,0,"create")
    def edit(_):
        try:store.save(graph,1,"race");return True
        except Conflict:return False
    with ThreadPoolExecutor(max_workers=2) as pool: assert sum(pool.map(edit,range(2)))==1


def test_color_candidates_are_not_connections():
    image=Image.new("RGB",(400,200),"white")
    ImageDraw.Draw(image).line((30,100,370,100),fill="red",width=6)
    evidence,candidates=detect_color_candidates(image,"image")
    assert len(candidates)==1 and candidates[0].status=="UNKNOWN"
    assert evidence[0].method=="color_segmentation"
    assert not hasattr(candidates[0],"from_terminal")


def test_blank_image_no_proposals():
    assert detect_color_candidates(Image.new("RGB",(200,200),"white"),"image")==([],[])


def demo(client):
    res=client.post("/api/projects/demo");assert res.status_code==201
    data=res.json();return data["graph"]["project_id"],data


def test_demo_truth_and_export_gates(client):
    pid,data=demo(client)
    assert data["graph"]["mode"]=="synthetic_demo"
    assert len(data["graph"]["components"])==6
    hidden=next(w for w in data["graph"]["links"] if w["id"]=="W6")
    assert hidden["to_terminal"] is None and hidden["connection"]["status"]=="UNKNOWN"
    assert not any(s["can_assemble"] for s in data["tutorial"]["steps"])
    assert client.get(f"/api/projects/{pid}/image").headers["content-type"]=="image/png"
    assert client.get(f"/api/projects/{pid}/kicad").status_code==409
    exported=client.get(f"/api/projects/{pid}/export")
    assert Graph.model_validate(exported.json()).revision==1


def test_upload_no_fabricated_components(client):
    data=client.post("/api/projects",files={"image":("fake-name.png",image_bytes(),"image/png")}).json()
    assert data["graph"]["mode"]=="photo"
    assert data["graph"]["components"]==[] and data["graph"]["links"]==[]
    assert data["capabilities"]["vision_model"]=="Qwen3-VL-2B_local"


@pytest.mark.parametrize("raw",[b"not an image",b"<svg></svg>",b"",b"GIF89a"])
def test_bad_upload(client,raw):
    assert client.post("/api/projects",files={"image":("x.png",raw,"image/png")}).status_code==422


def test_oversized_upload(client):
    assert client.post("/api/projects",files={"image":("x.png",b"x"*(12*1024*1024+1),"image/png")}).status_code==413


def test_manual_annotation_and_review_flow(client):
    pid,data=demo(client)
    original=data["graph"]["evidence"]
    body={"expected_revision":1,"status":"CONFIRMED","from_terminal":"U1.GPIO18","to_terminal":"SW1.1","note":"合成 예제 검토 테스트: 두 끝점을 확인했습니다."}
    r=client.post(f"/api/projects/{pid}/links/W7/review",json=body)
    assert r.status_code==200
    data=r.json();assert data["graph"]["revision"]==2
    assert data["graph"]["evidence"][:len(original)]==original
    assert data["validation"]["input_revision"]==2
    assert data["validation"]["erc"]=="NOT_RUN"
    assert client.post(f"/api/projects/{pid}/links/W7/review",json=body).status_code==409
    assert len(client.get(f"/api/projects/{pid}/history").json())==2


def test_cannot_confirm_missing_endpoint(client):
    pid,_=demo(client)
    r=client.post(f"/api/projects/{pid}/links/W6/review",json={"expected_revision":1,"status":"CONFIRMED","from_terminal":"SW1.2","note":"가려진 끝점은 아직 알 수 없습니다."})
    assert r.status_code==422
    assert client.get(f"/api/projects/{pid}").json()["graph"]["revision"]==1


def test_component_and_link_annotation(client):
    data=client.post("/api/projects",files={"image":("x.png",image_bytes(),"image/png")}).json();pid=data["graph"]["project_id"]
    body={"expected_revision":1,"kind":"led","label":"LED 후보","terminal_names":["A?","K?"],"bbox":[{"x":.2,"y":.2},{"x":.4,"y":.5}]}
    data=client.post(f"/api/projects/{pid}/components",json=body).json()
    c=data["graph"]["components"][0]
    assert c["label"]["status"]=="INFERRED" and c["terminals"][0]["pin_mapping"]["status"]=="UNKNOWN"
    cid=c["id"]
    r=client.post(f"/api/projects/{pid}/components/{cid}/review",json={"expected_revision":2,"label":"LED 표식 확인","value":None,"status":"CONFIRMED","note":"부품 표식을 확대해서 확인했습니다."})
    assert r.status_code==200
    assert r.json()["graph"]["components"][0]["value"]["status"]=="UNKNOWN"
    link={"expected_revision":3,"from_terminal":c["terminals"][0]["id"],"path":[{"x":.2,"y":.2},{"x":.6,"y":.5}]}
    r=client.post(f"/api/projects/{pid}/links",json=link)
    assert r.status_code==200 and r.json()["graph"]["links"][0]["connection"]["status"]=="UNKNOWN"


def test_cross_origin_mutation_blocked(client):
    assert client.post("/api/projects/demo",headers={"origin":"https://example.com"}).status_code==403
    assert client.post("/api/projects/demo",headers={"sec-fetch-site":"cross-site"}).status_code==403


def test_host_guard(client):
    assert client.get("/api/projects",headers={"host":"attacker.example"}).status_code==400


def test_missing_project_and_path(client):
    assert client.get("/api/projects/not-a-project").status_code==404
    assert client.get("/api/projects/"+"f"*32).status_code==404


def test_static_and_schema_endpoints(client):
    assert "통합 설계실" in client.get("/").text
    assert client.get("/app.js").status_code==200
    assert client.get("/api/health").json()["milestone"]=="integrated"
