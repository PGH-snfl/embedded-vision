from shared.paths import PROJECT_ROOT
from shared.paths import ANALYZER_FRONTEND
import hashlib
import base64
import io
import os
import uuid
import warnings
from pathlib import Path
from typing import Literal
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from .planner.selection import AnalysisModel,PRIMARY
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from PIL import Image, UnidentifiedImageError
from pydantic import Field, model_validator
from .circuit.schema import Claim, Component, Evidence, Graph, Link, Point, Status, StrictModel, Terminal, Asset, ComponentKind
from .circuit.connectivity import derive_nets, validation
from .circuit.store import Conflict, Store
from .vision.demo import create_demo
from .vision.wires import detect_color_candidates
from .vision.review_assist import review_assist
from .vision.single_view import pin_matches
from .tutorial.generate import tutorial
from .integration import routes, integrated_state
from .upload_files import PendingUploadFiles

ROOT=PROJECT_ROOT
MAX_UPLOAD=12*1024*1024
Image.MAX_IMAGE_PIXELS=20_000_000


class ComponentInput(StrictModel):
    expected_revision: int
    asset_id:str='image'
    kind: ComponentKind
    label: str = Field(min_length=1,max_length=200)
    value: str | None = Field(default=None,max_length=100)
    terminal_names: list[str] = Field(default_factory=list,max_length=40)
    bbox: list[Point] = Field(min_length=2,max_length=2)

    @model_validator(mode="after")
    def ordered_box(self):
        a,b=self.bbox
        if a.x>=b.x or a.y>=b.y: raise ValueError("Bounding box must have positive width and height")
        return self


class LinkInput(StrictModel):
    expected_revision: int
    asset_id:str='image'
    from_terminal: str
    to_terminal: str | None = None
    path: list[Point] = Field(min_length=2,max_length=100)


class ReviewInput(StrictModel):
    expected_revision: int
    status: Status
    from_terminal: str | None = None
    to_terminal: str | None = None
    note: str = Field(min_length=5,max_length=1000)


class ComponentReviewInput(StrictModel):
    expected_revision: int
    label: str | None = Field(default=None,max_length=200)
    value: str | None = Field(default=None,max_length=100)
    status: Status
    note: str = Field(min_length=5,max_length=1000)


def create_app(data_root: Path | None = None, *, local_only=True, analysis_dispatch=None, provider_ready=None):
    editor_port=int(os.environ.get('EMBEDDED_VISION_EDITOR_PORT','8768'))
    if not 1 <= editor_port <= 65535: raise ValueError('Invalid editor port')
    app=FastAPI(title="Embedded Vision · Integrated Prototype",version="0.3.0")
    store=Store(data_root or Path(os.environ.get("EMBEDDED_VISION_DATA",ROOT/".runtime")))
    app.state.store=store
    app.state.analysis_dispatch=analysis_dispatch
    app.state.provider_ready=provider_ready
    from .translation.system import conversion_routes
    conversion_routes(app)

    @app.middleware("http")
    async def local_guard(request: Request, call_next):
        host=request.headers.get("host","").split(":")[0]
        if local_only and host not in {"127.0.0.1","localhost","testserver"}:
            return JSONResponse({"detail":"Local hosts only"},status_code=400)
        # Local, single-user prototype. Reject cross-origin mutations (no CORS).
        if local_only and request.method not in {"GET","HEAD","OPTIONS"}:
            origin=request.headers.get("origin")
            if origin and origin != f"{request.url.scheme}://{request.headers.get('host')}":
                return JSONResponse({"detail":"Cross-origin writes are disabled"},status_code=403)
            if request.headers.get("sec-fetch-site") == "cross-site":
                return JSONResponse({"detail":"Cross-site writes are disabled"},status_code=403)
        response=await call_next(request)
        response.headers["X-Content-Type-Options"]="nosniff"
        response.headers["Referrer-Policy"]="no-referrer"
        # Only the internal editor views can be placed in the analysis page.
        # They remain inaccessible to third-party origins.
        embedded_editor=request.url.path in {'/prototype-editor.html','/rover-editor.html'}
        ancestors="'self'" if embedded_editor else "'none'"
        if embedded_editor:response.headers['Cache-Control']='no-store'
        if request.url.path=='/tutorial':
            import re
            text=(ROOT/'tutorial.html').read_text()
            allowed={tag:' '.join("'sha256-"+base64.b64encode(hashlib.sha256(block.encode()).digest()).decode()+"'" for block in re.findall(r'<'+tag+r'>(.*?)</'+tag+r'>',text,re.S)) for tag in ('style','script')}
            response.headers['Content-Security-Policy']=f"default-src 'none'; style-src {allowed['style']}; script-src {allowed['script']}; frame-ancestors 'none'; base-uri 'none'"
        else:
            response.headers["Content-Security-Policy"]=f"default-src 'self'; img-src 'self' blob:; style-src 'self'; script-src 'self'; connect-src 'self'; frame-src 'self' http://127.0.0.1:{editor_port} http://localhost:{editor_port}; frame-ancestors {ancestors}; base-uri 'none'"
        return response

    def get(project):
        if len(project)!=32 or any(c not in "0123456789abcdef" for c in project):
            raise HTTPException(404,"Project not found")
        try: return store.get(project)
        except KeyError: raise HTTPException(404,"Project not found")

    def save(graph,expected,note):
        try: return store.save(graph,expected,note)
        except Conflict as exc: raise HTTPException(409,str(exc))
        except ValueError as exc: raise HTTPException(422,str(exc))

    def view(graph):
        integrated=integrated_state(store,graph)
        checks=validation(graph)
        if integrated['eda']:
            checks.update({k:integrated['eda'][k] for k in ['erc','drc','connectivity']})
            checks['kicad']='GENERATED'
        if integrated['simulation']:checks['spice']='PASS'
        return {"graph":graph.model_dump(mode="json"),"hypothesis_pins":{h.id:pin_matches(graph,h) for h in graph.wire_hypotheses},"review_assist":review_assist(graph),"confirmed_nets":derive_nets(graph),
                "draft_nets":derive_nets(graph,True),"validation":checks,"tutorial":tutorial(graph),"integrated":integrated,
                "capabilities":{"component_detection":"ocr_marking_proposals_and_manual_review","wire_detection":"color_contour_candidates_only", "vision_model":"Qwen3-VL-2B_local","ocr":"RapidOCR_ONNX_CPU","kicad":"schematic_erc_pcb_drc","spice":"libngspice","agent":"sol_focused_astra_planner","automatic_photo_analysis":True}}

    @app.get("/api/health")
    def health(): return {"status":"ok","service":"analyzer","version":"0.3.0","milestone":"integrated"}

    @app.get('/runtime-config.js',include_in_schema=False)
    def runtime_config():
        return Response(f'window.EMBEDDED_VISION_EDITOR_PORT={editor_port};',media_type='text/javascript',headers={'Cache-Control':'no-store'})

    @app.get('/tutorial',include_in_schema=False)
    def project_tutorial():
        return FileResponse(ROOT/'tutorial.html')

    @app.get("/api/workflow")
    def common_workflow():
        from .workflow import workflow_definition
        return workflow_definition()

    @app.get('/api/board-profiles')
    def embedded_board_profiles():
        from .design.board_profiles import board_profiles
        return board_profiles()

    @app.get('/api/board-profiles/{model}/example')
    def embedded_board_example(model:str):
        from .design.board_profiles import board_example
        try:return board_example(model)
        except (ValueError,FileNotFoundError):raise HTTPException(404,'지원하는 보드 예제가 없습니다.')

    @app.get("/api/projects")
    def projects(): return store.list()

    @app.post("/api/projects/demo",status_code=201)
    def demo():
        pid=uuid.uuid4().hex
        graph,data,image=create_demo(pid)
        e,c=detect_color_candidates(image,"image")
        graph.evidence.extend(e);graph.wire_candidates=c
        (store.root/f"{pid}.png").write_bytes(data)
        return view(save(graph,0,"합성 예제 생성 (AI 인식 결과 아님)"))

    @app.post("/api/projects",status_code=201)
    async def upload(image: UploadFile=File(...),analysis_model:AnalysisModel=Form(PRIMARY)):
        raw=await image.read(MAX_UPLOAD+1)
        if len(raw)>MAX_UPLOAD: raise HTTPException(413,"12 MB 이하의 PNG/JPEG 사진을 선택하세요.")
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error",Image.DecompressionBombWarning)
                picture=Image.open(io.BytesIO(raw))
                if picture.format not in {"PNG","JPEG"}: raise ValueError("PNG/JPEG only")
                picture.load()
                from PIL import ImageOps
                picture=ImageOps.exif_transpose(picture).convert("RGB")
                if picture.width<32 or picture.height<32: raise ValueError("Image is too small")
        except (UnidentifiedImageError,OSError,ValueError,Image.DecompressionBombError,Image.DecompressionBombWarning):
            raise HTTPException(422,"유효한 PNG/JPEG 사진(최대 2천만 화소)이 필요합니다.")
        pid=uuid.uuid4().hex
        # Normalize orientation and strip EXIF metadata. Coordinates reference this image.
        output=io.BytesIO();picture.save(output,format="PNG");data=output.getvalue()
        asset=Asset(id="image",sha256=hashlib.sha256(data).hexdigest(),width=picture.width,height=picture.height,filename="uploaded-image.png")
        evidence,candidates=detect_color_candidates(picture,"image")
        graph=Graph(project_id=pid,title="사진 배선 검토",revision=1,mode="photo",assets=[asset],evidence=evidence,wire_candidates=candidates)
        with PendingUploadFiles() as upload_files:
            upload_files.write(store.root/f"{pid}.png",data)
            graph=save(graph,0,"실사 사진 업로드 · 자동 멀티모델 분석")
            upload_files.commit()
        job=app.state.auto_analysis.start(graph,model=analysis_model)
        result=view(graph);result["auto_analysis"]=job
        return result

    @app.get("/api/projects/{project}")
    def project(project:str): return view(get(project))

    @app.get("/api/projects/{project}/image")
    def project_image(project:str):
        get(project)
        return FileResponse(store.root/f"{project}.png",media_type="image/png")

    @app.get("/api/projects/{project}/history")
    def history(project:str): get(project);return store.history(project)

    @app.get("/api/projects/{project}/export")
    def export(project:str):
        graph=get(project)
        return Response(graph.model_dump_json(indent=2),media_type="application/json",headers={"Content-Disposition":f'attachment; filename="circuit-{project}-r{graph.revision}.json"'})

    @app.get("/api/projects/{project}/kicad")
    def kicad(project:str):
        data=view(get(project))
        if data['integrated']['eda']:return data['integrated']['eda']
        return JSONResponse({"detail":"현재 버전의 회로도를 먼저 생성하세요.","blockers":data['integrated']['readiness']},status_code=409)

    @app.post("/api/projects/{project}/components")
    def add_component(project:str,body:ComponentInput):
        graph=get(project)
        cid=f"C_{uuid.uuid4().hex[:8]}";eid=f"manual_{uuid.uuid4().hex[:8]}"
        evidence=Evidence(id=eid,asset_id=body.asset_id,method="manual_annotation",points=body.bbox,text="사용자가 사진에서 부품 영역과 라벨을 직접 지정했습니다. 데이터시트 검증은 아닙니다.")
        graph.evidence.append(evidence)
        def inferred(v): return Claim(value=v,status=Status.INFERRED,evidence_ids=[eid],reason="사용자 수동 입력 · 별도 검증 필요")
        graph.components.append(Component(id=cid,kind=body.kind,asset_id=body.asset_id,label=inferred(body.label),value=inferred(body.value) if body.value else Claim(),bbox=body.bbox,
            terminals=[Terminal(id=f"{cid}.T{i+1}",name=inferred(name)) for i,name in enumerate(body.terminal_names) if name.strip()]))
        return view(save(graph,body.expected_revision,f"부품 수동 지정: {cid}"))

    @app.post("/api/projects/{project}/components/{component_id}/review")
    def review_component(project:str,component_id:str,body:ComponentReviewInput):
        graph=get(project)
        component=next((c for c in graph.components if c.id==component_id),None)
        if not component: raise HTTPException(404,"Component not found")
        eid=f"review_{uuid.uuid4().hex[:8]}"
        graph.evidence.append(Evidence(id=eid,asset_id=component.asset_id,method="user_confirmation",points=component.bbox,text=body.note))
        def revised(value,old):
            return Claim(value=value if body.status!=Status.UNKNOWN else None,
                         status=body.status if value and body.status!=Status.UNKNOWN else Status.UNKNOWN,
                         evidence_ids=[*old.evidence_ids,eid],reason=body.note)
        component.label=revised(body.label,component.label)
        component.value=revised(body.value,component.value)
        return view(save(graph,body.expected_revision,f"부품 정보 검토: {component_id}"))

    @app.post("/api/projects/{project}/links")
    def add_link(project:str,body:LinkInput):
        graph=get(project);eid=f"manual_{uuid.uuid4().hex[:8]}"
        graph.evidence.append(Evidence(id=eid,asset_id=body.asset_id,method="manual_annotation",points=body.path,text="사용자가 지정한 배선 끝점 후보입니다."))
        claim=Claim(value="connected",status=Status.INFERRED,evidence_ids=[eid],reason="사용자 지정 연결 후보 · 사진/측정 확인 필요") if body.to_terminal else Claim(evidence_ids=[eid],reason="도착 단자 미확인")
        try:
            graph.links.append(Link(id=f"W_{uuid.uuid4().hex[:8]}",from_terminal=body.from_terminal,to_terminal=body.to_terminal,path=body.path,connection=claim,asset_id=body.asset_id))
            graph=Graph.model_validate(graph.model_dump())
        except ValueError as exc: raise HTTPException(422,str(exc))
        return view(save(graph,body.expected_revision,"배선 후보 수동 지정"))

    @app.post("/api/projects/{project}/links/{link_id}/review")
    def review(project:str,link_id:str,body:ReviewInput):
        graph=get(project)
        link=next((w for w in graph.links if w.id==link_id),None)
        if not link: raise HTTPException(404,"Link not found")
        eid=f"review_{uuid.uuid4().hex[:8]}"
        graph.evidence.append(Evidence(id=eid,asset_id=link.asset_id,method="user_confirmation",points=link.path,text=body.note))
        link.from_terminal=body.from_terminal;link.to_terminal=body.to_terminal
        link.connection=Claim(value="connected" if body.status!=Status.UNKNOWN else None,status=body.status,
                              evidence_ids=[*link.connection.evidence_ids,eid],reason=body.note)
        try: graph=Graph.model_validate(graph.model_dump())
        except ValueError as exc: raise HTTPException(422,str(exc))
        return view(save(graph,body.expected_revision,f"배선 검토: {link_id} → {body.status}"))

    routes(app,store,get,save,view)
    from .circuit.project_deletion import install_project_deletion
    install_project_deletion(app,store,get,saas=analysis_dispatch is not None)
    app.mount("/",StaticFiles(directory=ANALYZER_FRONTEND,html=True),name="frontend")
    return app
