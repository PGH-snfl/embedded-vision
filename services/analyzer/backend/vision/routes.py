"""Asynchronous per-project photo/frame analysis, with optimistic save and persisted reports."""
from shared.paths import PROJECT_ROOT
import hashlib
import io
import json
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from fastapi import HTTPException
from PIL import Image
from pydantic import Field
from ..circuit.schema import Asset, Graph, Evidence, StrictModel, Terminal, Claim, Status
from ..circuit.store import Conflict
from .vlm import infer, health, merge_observation
from ..circuit.project_lock import project_lock

ROOT=PROJECT_ROOT
SOURCE="https://commons.wikimedia.org/wiki/File:Arduino_Uno_with_breadboard.jpg"

class VisionRequest(StrictModel):
    expected_revision:int
    asset_ids:list[str]=Field(min_length=1,max_length=6)

class CandidateEdit(StrictModel):
    expected_revision:int
    note:str=Field(min_length=5,max_length=500)
    terminal_names:list[str]=Field(default_factory=list,max_length=40)


def vision_routes(app,store,get,save,view):
    pool=ThreadPoolExecutor(max_workers=1)
    app.state.vision_pool=pool
    jobs={};lock=threading.Lock()
    app.state.vision_jobs=jobs

    @app.get("/api/vision/status")
    def status():return health()

    def candidate(project,cid,body):
        graph=get(project)
        if graph.revision!=body.expected_revision:raise HTTPException(409,"리비전이 바뀌었습니다.")
        part=next((c for c in graph.components if c.id==cid),None)
        if not part or not any(e.method=='vlm' and e.id in part.label.evidence_ids for e in graph.evidence):
            raise HTTPException(422,"VLM으로 추가된 부품 후보가 아닙니다.")
        return graph,part

    @app.post("/api/projects/{project}/vision/candidates/{cid}/reject")
    def reject(project:str,cid:str,body:CandidateEdit):
        graph,part=candidate(project,cid,body);pins={t.id for t in part.terminals}
        graph.components.remove(part)
        graph.links=[w for w in graph.links if w.from_terminal not in pins and w.to_terminal not in pins]
        graph.evidence.append(Evidence(id='reject_'+uuid.uuid4().hex[:8],asset_id=part.asset_id,
                                      method='user_confirmation',text=f'{cid} 후보 제외: {body.note}'))
        return view(save(graph,body.expected_revision,'VLM 오인식 후보 제외 · 이전 리비전 보존'))

    @app.post("/api/projects/{project}/vision/candidates/{cid}/terminals")
    def add_terminals(project:str,cid:str,body:CandidateEdit):
        graph,part=candidate(project,cid,body)
        names=[n.strip() for n in body.terminal_names]
        if not names or any(not n or len(n)>40 for n in names) or len(names)!=len(set(names)):
            raise HTTPException(422,"중복되지 않는 단자 라벨을 입력하세요.")
        eid='terminal_'+uuid.uuid4().hex[:8]
        graph.evidence.append(Evidence(id=eid,asset_id=part.asset_id,method='manual_annotation',text=body.note))
        existing={t.name.value for t in part.terminals}
        for name in names:
            if name in existing:continue
            part.terminals.append(Terminal(id=f'{part.id}.T{len(part.terminals)+1}',name=Claim(
                value=name,status=Status.INFERRED,evidence_ids=[eid],reason='사용자가 추가한 단자 라벨. 카탈로그 대조 필요')))
        return view(save(graph,body.expected_revision,'VLM 후보의 단자 라벨 보완'))

    @app.post("/api/projects/camera-example",status_code=201)
    def camera_example():
        path=ROOT/"data/photos/arduino-camera.jpg"
        if not path.exists():raise HTTPException(503,"실사 예제 파일이 없습니다.")
        image=Image.open(path).convert("RGB");buf=io.BytesIO();image.save(buf,format="PNG");data=buf.getvalue()
        pid=uuid.uuid4().hex
        (store.root/f"{pid}.png").write_bytes(data)
        graph=Graph(project_id=pid,title="실사 · Arduino 브레드보드 사진",mode="photo",revision=1,
            assets=[Asset(id="image",sha256=hashlib.sha256(data).hexdigest(),width=image.width,
                          height=image.height,filename="arduino-camera.jpg",synthetic=False)],
            evidence=[Evidence(id="photo_source",asset_id="image",method="manual_annotation",source_url=SOURCE,
              text="실제 카메라 사진: Thctamm, Arduino Uno with breadboard, CC BY-SA 3.0. EXIF 제거/재인코딩. 이미지 라이선스 https://creativecommons.org/licenses/by-sa/3.0/")])
        return view(save(graph,0,"실제 촬영 사진 열기 · 부품/연결 정답을 미리 넣지 않음"))

    def worker(job_id,graph,asset_ids):
        with project_lock(store.root, graph.project_id, wait=True):
            try: get(graph.project_id)
            except Exception:
                jobs[job_id].update(status='error',error='프로젝트가 삭제되었습니다.')
                return
            return worker_locked(job_id,graph,asset_ids)

    def worker_locked(job_id,graph,asset_ids):
        job=jobs[job_id];reports=[]
        try:
            for i,aid in enumerate(asset_ids):
                job.update(status="running",progress=f"{i+1}/{len(asset_ids)} 사진 분석 중")
                path=store.root/(f"{graph.project_id}.png" if aid=="image" else f"{graph.project_id}-{aid}.png")
                observation,report=infer(path,progress=lambda stage:job.update(progress=f"{i+1}/{len(asset_ids)} 사진 · {stage}"))
                graph,report=merge_observation(graph,aid,observation,report);reports.append(report)
            report_path=store.root/f"{graph.project_id}-vlm-{job_id}.json"
            report_path.write_text(json.dumps(reports,ensure_ascii=False,indent=2))
            graph=store.save(graph,graph.revision,"실사 VLM 후보 분석 · 확정 없음")
            result={"revision":graph.revision,"model":reports[0]["engine"],"frames":reports,"job_id":job_id}
            (store.root/f"{graph.project_id}-vision.json").write_text(json.dumps(result,ensure_ascii=False,indent=2))
            job.update(status="done",progress="분석 완료 · 추정 후보를 검토하세요.",revision=graph.revision)
        except Conflict:
            job.update(status="error",error="분석 중 회로가 수정되어 후보를 저장하지 않았습니다. 원시 분석 기록은 보존했습니다.")
        except Exception as exc:
            if hasattr(exc,'report'):
                (store.root/f"{graph.project_id}-vlm-{job_id}-error.json").write_text(
                    json.dumps({'completed_frames':reports,'failure':exc.report},ensure_ascii=False,indent=2))
            job.update(status="error",error=str(exc)[:1000])

    @app.post("/api/projects/{project}/vision",status_code=202)
    def start(project:str,body:VisionRequest):
        graph=get(project)
        if graph.mode not in {"photo","video"}:raise HTTPException(422,"실제 사진·영상 프로젝트에서 실행하세요.")
        if graph.revision!=body.expected_revision:raise HTTPException(409,"리비전이 바뀌었습니다.")
        if len(set(body.asset_ids))!=len(body.asset_ids) or not set(body.asset_ids)<=set(a.id for a in graph.assets):
            raise HTTPException(422,"유효한 사진 목록이 필요합니다.")
        if not health()["ready"]:raise HTTPException(503,"로컬 VLM이 꺼져 있습니다. run_vlm.sh를 실행하세요.")
        with lock:
            if any(j["status"] in {"queued","running"} for j in jobs.values()):
                raise HTTPException(409,"다른 VLM 분석이 실행 중입니다. 완료 후 다시 요청하세요.")
            jid=uuid.uuid4().hex
            jobs[jid]={"id":jid,"project_id":project,"status":"queued","progress":"분석 대기"}
            pool.submit(worker,jid,graph,body.asset_ids)
        return dict(jobs[jid])

    @app.get("/api/projects/{project}/vision/jobs/{job_id}")
    def job(project:str,job_id:str):
        get(project)
        if job_id not in jobs or jobs[job_id]["project_id"]!=project:raise HTTPException(404,"분석 작업이 없습니다.")
        return dict(jobs[job_id])
