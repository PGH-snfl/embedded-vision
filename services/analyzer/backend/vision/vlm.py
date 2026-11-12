"""Local camera-image VLM inference. Model output is untrusted evidence, never verification."""
from shared.paths import PROJECT_ROOT
import base64
import io
import json
import threading
import time
import uuid
from pathlib import Path
from typing import Annotated
import httpx
from PIL import Image
from pydantic import Field, model_validator
from ..circuit.schema import StrictModel, Component, ComponentKind, Claim, Evidence, Terminal, Link, Point, Status

MODEL = "Qwen3-VL-2B-Instruct-Q8_0"
URL = "http://127.0.0.1:8768"
_lock = threading.Lock()
KEYFILE=PROJECT_ROOT/".runtime/vlm/api-key"


def headers():
    return {"Authorization":"Bearer "+KEYFILE.read_text().strip()} if KEYFILE.exists() else {}


class SeenPart(StrictModel):
    id: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_]{0,15}$")
    kind: ComponentKind
    label: str = Field(min_length=1, max_length=160)
    bbox: list[int] = Field(min_length=4, max_length=4)
    markings: str = Field(max_length=120)
    terminals: list[str] = Field(max_length=40)

    @model_validator(mode="after")
    def bounds(self):
        x1,y1,x2,y2=self.bbox
        if not (0<=x1<x2<=1000 and 0<=y1<y2<=1000):
            raise ValueError("Invalid image box")
        if len(set(self.terminals))!=len(self.terminals) or any(not t or len(t)>40 for t in self.terminals):
            raise ValueError("Invalid terminal labels")
        return self


class SeenWire(StrictModel):
    from_part: str = Field(max_length=16)
    from_pin: str = Field(max_length=40)
    to_part: str = Field(max_length=16)
    to_pin: str = Field(max_length=40)
    both_endpoints_visible: bool
    reason: str = Field(min_length=1, max_length=400)


class Observation(StrictModel):
    summary: str = Field(max_length=400)
    components: list[SeenPart] = Field(max_length=6)
    connections: list[SeenWire] = Field(max_length=8)
    unknowns: list[Annotated[str,Field(max_length=160)]] = Field(max_length=5)



def health():
    try:
        with httpx.Client(timeout=2, trust_env=False, headers=headers()) as client:
            response=client.get(URL+"/health")
        return {"ready":response.status_code==200, "model":MODEL, "local":True}
    except httpx.HTTPError:
        return {"ready":False, "model":MODEL, "local":True}


class VisionFailure(ValueError):
    def __init__(self,message,report):
        super().__init__(message)
        self.report=report


def request_json(image, prompt, schema, max_tokens=1600):
    image=image.copy().convert("RGB")
    image.thumbnail((1008,1008))
    buf=io.BytesIO();image.save(buf,format="JPEG",quality=92)
    payload={"model":MODEL,"temperature":0,"max_tokens":max_tokens,
             "messages":[{"role":"user","content":[{"type":"text","text":prompt},
                 {"type":"image_url","image_url":{"url":"data:image/jpeg;base64,"+base64.b64encode(buf.getvalue()).decode()}}]}],
             "response_format":{"type":"json_object","schema":schema.model_json_schema()}}
    start=time.monotonic()
    with _lock, httpx.Client(timeout=httpx.Timeout(600,connect=5), trust_env=False, headers=headers()) as client:
        try:
            response=client.post(URL+"/v1/chat/completions",json=payload)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ValueError("로컬 VLM 응답 실패. run_vlm.sh 실행 상태를 확인하세요.") from exc
    data=response.json()
    raw=data["choices"][0]["message"]["content"]
    report={"engine":MODEL, "elapsed_seconds":round(time.monotonic()-start,2),
            "input_size":list(image.size), "raw_text":raw, "usage":data.get("usage",{}), "status":"INFERRED"}
    if data["choices"][0].get("finish_reason")=="length":
        raise VisionFailure("모델 응답이 길이 제한에 도달했습니다. 부분 결과는 반영하지 않았습니다.",report)
    try:observation=schema.model_validate_json(raw)
    except ValueError as exc:raise VisionFailure("모델 출력 형식 검증 실패. 원본 응답을 보존했습니다.",report) from exc
    report['raw']=json.loads(raw)
    return observation,report


def infer(path: Path, progress=None):
    from .staged import inspect_photo
    return inspect_photo(path, request_json, progress)


def merge_observation(graph, asset_id, observation, report):
    """Add new hypotheses, preserving all earlier user decisions and observations."""
    run_id=uuid.uuid4().hex[:8]
    existing_ids={p.id for p in observation.components}
    if len(existing_ids)!=len(observation.components):raise ValueError("모델 부품 ID가 중복되었습니다.")
    parts={}; pins={}; added=[]; skipped=[]; warnings=[]
    for part in observation.components:
        cid=f"V_{run_id}_{part.id}";eid=f"vlm_{run_id}_{part.id}"
        x1,y1,x2,y2=part.bbox
        points=[Point(x=x1/1000,y=y1/1000),Point(x=x2/1000,y=y2/1000)]
        graph.evidence.append(Evidence(id=eid,asset_id=asset_id,method="vlm",points=points,
            text=f"{MODEL} 모델 추정 · 실물 미검증. 후보: {part.label}. 판독 표식: {part.markings or '없음'}."))
        if part.markings.strip()==part.id:
            warnings.append(f"{part.id}: 표식이 모델의 임시 ID와 같습니다. 실제 인쇄 문자로 인정하지 않습니다.")
        terminals=[]
        for i,name in enumerate(part.terminals):
            tid=f"{cid}.T{i+1}";pins[(part.id,name)]=tid
            terminals.append(Terminal(id=tid,name=Claim(value=name,status=Status.INFERRED,
                evidence_ids=[eid],reason="VLM 단자 라벨 후보. 실제 핀 번호는 UNKNOWN")))
        graph.components.append(Component(id=cid,kind=part.kind,asset_id=asset_id,bbox=points,
            label=Claim(value=part.label,status=Status.INFERRED,evidence_ids=[eid],
                        reason="실제 사진의 VLM 후보. 모델과 영역 모두 사용자 검토 필요"),
            terminals=terminals))
        parts[part.id]=cid;added.append(cid)
    for i,wire in enumerate(observation.connections):
        a=pins.get((wire.from_part,wire.from_pin));b=pins.get((wire.to_part,wire.to_pin))
        if not a or not b or a==b:
            skipped.append(f"연결 {i+1}: 식별 가능한 단자 참조 부족 — {wire.reason}")
            continue
        eid=f"vlm_{run_id}_wire{i}"
        graph.evidence.append(Evidence(id=eid,asset_id=asset_id,method="vlm",
            text="VLM 연결 후보 · 사진/측정 대조 필요: "+wire.reason))
        # A model's own "visible" assertion is not independent endpoint evidence.
        # Keep the hypothesis as UNKNOWN until the user or geometric observations establish it.
        claim=Claim(evidence_ids=[eid],reason="VLM 배선 가설 · 독립적인 끝점 근거 부족: "+wire.reason)
        graph.links.append(Link(id=f"VW_{run_id}_{i}",asset_id=asset_id,from_terminal=a,
                               to_terminal=b,connection=claim))
    report.update(asset_id=asset_id,component_ids=added,
                  review_questions=list(dict.fromkeys(observation.unknowns+report.get('detail_questions',[])+skipped+warnings)),
                  summary=observation.summary,auto_confirmed=0,
                  connection_policy="VLM 단독 배선 제안은 UNKNOWN. 사진 끝점/사용자 확인 필요.")
    report['wiring']={"status":"UNRESOLVED", "proposed":len(observation.connections),
                      "rejected":len(skipped), "retained_unknown":len(observation.connections)-len(skipped),
                      "note":"연결 0개는 복원 완료가 아닙니다. 핀 위치와 실제 선 끝점을 확인하세요."}
    return graph,report
