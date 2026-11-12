"""Same-origin SaaS gateway: sessions -> membership -> tenant domain app/worker."""
import hmac
import json
import re
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field
from .repository import Repository, Limited, Stale, digest
from .settings import Settings, ROOT
from .tenancy import TenantApps, actor, forward, ID
from ..circuit.project_lock import project_lock, ProjectBusy
from ..circuit.project_deletion import terminal_queue_jobs
from shared.paths import EDITOR_FRONTEND,ANALYZER_FRONTEND

PUBLIC = ANALYZER_FRONTEND
DIST = EDITOR_FRONTEND/'dist'
PROJECT = re.compile(r"^/api/projects/([a-f0-9]{32})(?:/|$)")
EXPENSIVE = re.compile(r"^/api/projects/[a-f0-9]{32}/(?:build|simulate|analyze|parameters|agent|vision|planner|emulator|planner/[a-f0-9]{32}/execute|inventory/[a-f0-9]{32}/(?:simulate|emulator))$")


class BodyLimit:
    """Bound chunked and content-length bodies before FastAPI JSON/multipart parsing."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] in {"GET","HEAD","OPTIONS"}:
            return await self.app(scope, receive, send)
        path = scope["path"]
        cap = 66*1024*1024 if path.endswith(("/projects/video", "/projects", "/assets")) else 2*1024*1024
        data = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            data.extend(message.get("body", b""))
            if len(data) > cap:
                return await JSONResponse({"detail":"요청 크기 제한을 초과했습니다."},413)(scope, receive, send)
            if not message.get("more_body", False):
                break
        sent = False

        async def limited_receive():
            nonlocal sent
            if not sent:
                sent = True
                return {"type":"http.request","body":bytes(data),"more_body":False}
            return await receive()
        return await self.app(scope, limited_receive, send)


class Login(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class WorkspaceInput(BaseModel):
    name: str = Field(min_length=1,max_length=100)


class DraftInput(BaseModel):
    expected_revision: int = Field(ge=0)
    payload: dict


def create_saas_app(settings: Settings):
    repo = Repository(settings)
    tenants = TenantApps(repo)
    preview = repo.preview_identity() if not settings.auth_enabled else None

    @asynccontextmanager
    async def lifespan(app):
        yield
        tenants.close()

    app = FastAPI(title="Embedded Vision SaaS", version="0.5.0", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.repository, app.state.tenants, app.state.settings = repo, tenants, settings

    @app.exception_handler(Limited)
    async def limited(request, exc):
        return JSONResponse({"detail":str(exc)},429,headers={"Retry-After":"60"})

    @app.exception_handler(Stale)
    async def stale(request, exc):
        return JSONResponse({"detail":str(exc)},409)

    @app.middleware("http")
    async def guard(request: Request, call_next):
        from urllib.parse import urlsplit
        if request.headers.get("host", "").lower() != urlsplit(settings.origin).netloc.lower():
            return JSONResponse({"detail":"Invalid service host"},400)
        if request.method not in {"GET","HEAD","OPTIONS"}:
            if request.headers.get("origin") != settings.origin or request.headers.get("sec-fetch-site") == "cross-site":
                return JSONResponse({"detail":"Same-origin request required"},403)
        session = preview or repo.session(request.cookies.get(settings.cookie))
        request.state.identity = session
        if settings.auth_enabled and session and request.method not in {"GET","HEAD","OPTIONS"} and request.url.path != "/api/saas/login":
            if not hmac.compare_digest(digest(request.headers.get("X-EV-CSRF", "")), session["csrf"]):
                return JSONResponse({"detail":"CSRF token required"},403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        # The workspace editor alone may be embedded by a page on this same
        # service. All other pages remain protected from framing.
        workspace_editor = bool(re.fullmatch(r'/w/[a-f0-9]{32}/(?:editor/?|prototype-editor\.html|rover-editor\.html)', request.url.path))
        response.headers["X-Frame-Options"] = "SAMEORIGIN" if workspace_editor else "DENY"
        frame_ancestors = "'self'" if workspace_editor else "'none'"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self'; worker-src 'self' blob:; frame-src 'self' blob:; object-src 'none'; frame-ancestors " + frame_ancestors + "; base-uri 'self'"
        if request.url.path.startswith(("/api/", "/w/", "/login", "/workspaces")):
            response.headers["Cache-Control"] = "no-store"
            response.headers["Vary"] = "Cookie"
        return response

    def identity(request):
        if not request.state.identity:
            raise HTTPException(401,"로그인이 필요합니다.")
        return request.state.identity

    def member(request, wid, write=False):
        user = identity(request)
        if preview and wid != preview["workspace"]:
            raise HTTPException(404,"작업공간이 없습니다.")
        role = repo.role(wid,user["user"]) if ID.fullmatch(wid) else None
        if not role:
            raise HTTPException(404,"작업공간이 없습니다.")
        if write and role not in {"owner","editor"}:
            raise HTTPException(403,"편집 권한이 필요합니다.")
        return user

    def project(wid, pid):
        if not ID.fullmatch(pid):
            raise HTTPException(404,"Project not found")
        try:
            return tenants.get(wid).state.store.get(pid)
        except KeyError:
            raise HTTPException(404,"Project not found")

    def json_job(wid, jid):
        job = repo.job(wid,jid)
        if not job:
            raise HTTPException(404,"작업이 없습니다.")
        return {"id":job["id"],"status":job["status"],"created":job["created"],"updated":job["updated"],
                "result":json.loads(job["result"]) if job["result"] else None}

    @app.get("/api/health")
    def health():
        return {"status":"ok","mode":"saas","version":"0.5.0"}

    @app.get("/api/saas/status")
    def service_status(request: Request):
        identity(request)
        return {"worker":repo.worker_status(),"eda_enabled":settings.allow_eda,"storage":"sqlite+tenant-filesystem","deployment":"single-host"}

    @app.post("/api/saas/login")
    def login(body: Login, request: Request):
        if preview:
            raise HTTPException(409,"현재 로그인 기능이 비활성화되어 있습니다.")
        result = repo.login(body.email,body.password,request.client.host if request.client else "unknown")
        if not result:
            raise HTTPException(401,"이메일 또는 비밀번호를 확인하세요.")
        token, csrf = result
        response = JSONResponse({"ok":True})
        response.set_cookie(settings.cookie, token, max_age=settings.session_seconds, secure=settings.secure, httponly=True, samesite="strict", path="/")
        response.set_cookie("ev_csrf", csrf, max_age=settings.session_seconds, secure=settings.secure, samesite="strict", path="/")
        return response

    @app.post("/api/saas/logout")
    def logout(request: Request):
        if preview:
            raise HTTPException(409,"현재 로그인 기능이 비활성화되어 있습니다.")
        identity(request)
        repo.logout(request.cookies.get(settings.cookie, ""))
        response = JSONResponse({"ok":True})
        response.delete_cookie(settings.cookie, path="/",secure=settings.secure,httponly=True,samesite="strict")
        response.delete_cookie("ev_csrf",path="/",secure=settings.secure,samesite="strict")
        return response

    @app.get("/api/saas/me")
    def me(request: Request):
        user = identity(request)
        return {"email":user["email"],"workspaces":repo.workspaces(user["user"]),"mode":"saas",
                "auth_enabled":settings.auth_enabled,"default_workspace":preview["workspace"] if preview else None}

    @app.post("/api/saas/workspaces",status_code=201)
    def create_workspace(body: WorkspaceInput, request: Request):
        if preview:
            raise HTTPException(409,"로그인 없이 사용하는 동안에는 기본 작업공간을 사용하세요.")
        user = identity(request)
        if not body.name.strip():
            raise HTTPException(422,"작업공간 이름을 입력하세요.")
        if len(repo.workspaces(user["user"])) >= 10:
            raise Limited("작업공간은 계정당 최대 10개입니다.")
        return {"id":repo.add_workspace(user["user"],body.name.strip())}

    @app.get("/api/w/{wid}/jobs/{jid}")
    def job(wid: str, jid: str, request: Request):
        member(request,wid)
        return json_job(wid,jid)

    @app.get("/api/w/{wid}/workbench/projects/{pid}/{draft}")
    def get_draft(wid: str, pid: str, draft: str, request: Request):
        member(request,wid);project(wid,pid)
        if not re.fullmatch(r"[a-f0-9]{64}",draft):
            raise HTTPException(422,"Invalid draft ID")
        return repo.draft(wid,pid,draft)

    @app.put("/api/w/{wid}/workbench/projects/{pid}/{draft}")
    def put_draft(wid: str, pid: str, draft: str, body: DraftInput, request: Request):
        user = member(request,wid,True)
        if not re.fullmatch(r"[a-f0-9]{64}",draft) or body.payload.get("format") != "velxio-project":
            raise HTTPException(422,"유효한 편집 프로젝트가 필요합니다.")
        try:
            with project_lock(tenants.root(wid),pid):
                project(wid,pid)
                result = repo.save_draft(wid,user["user"],pid,draft,body.expected_revision,body.payload)
        except ProjectBusy as exc:
            raise HTTPException(409,str(exc))
        repo.audit(wid,user["user"],"draft.saved",pid)
        return result

    @app.post("/api/w/{wid}/workbench/compile/start")
    def compile_start(wid: str, body: dict, request: Request):
        from ..workbench.server import CompileRequest
        user = member(request,wid,True)
        try:
            validated = CompileRequest.model_validate(body)
        except ValueError:
            raise HTTPException(422,"컴파일 입력을 확인하세요.")
        key = request.headers.get("Idempotency-Key")
        if key and (len(key)>128 or not key.isascii()):
            raise HTTPException(422,"Invalid idempotency key")
        queued = repo.enqueue(wid,user["user"],"compile",validated.model_dump(),key)
        repo.audit(wid,user["user"],"compile.queued",queued["id"])
        return {"job_id":queued["id"]}

    @app.get("/api/w/{wid}/workbench/compile/status/{jid}")
    def compile_status(wid: str, jid: str, request: Request):
        member(request,wid)
        raw = repo.job(wid,jid)
        if not raw or raw["kind"] != "compile":
            raise HTTPException(404,"컴파일 작업이 없습니다.")
        job = json_job(wid,jid)
        state = {"queued":"pending","running":"running","done":"done","failed":"error","interrupted":"error"}[job["status"]]
        return {"state":state,"stage":"queued" if state=="pending" else "done" if state=="done" else "compiling",
                "stdout":"","result":job["result"],"error":"작업이 중단되었습니다. 자동 재실행하지 않습니다." if job["status"]=="interrupted" else None,
                "started_at":job["created"],"finished_at":job["updated"] if state in {"done","error"} else None}

    @app.get("/api/w/{wid}/workbench/setup-status")
    def setup_status(wid: str, request: Request):
        member(request,wid)
        from ..design.board_profiles import board_profiles
        return {"ready":True,"supported_boards":["arduino:avr:uno"],"board_workflow":board_profiles()}

    @app.api_route("/api/w/{wid}/{path:path}",methods=["GET","POST","PUT","PATCH","DELETE"])
    async def domain(wid: str, path: str, request: Request):
        write = request.method not in {"GET","HEAD"}
        user = member(request,wid,write)
        if path.startswith(("workbench/","jobs/")):
            raise HTTPException(404,"지원하지 않는 서비스입니다.")
        target = "/api/"+path
        match = PROJECT.match(target)
        if match:
            project(wid,match[1])
        if not settings.allow_eda and (target.endswith("/build") or target.endswith("/execute") or target == "/api/planner/mcp/probe"):
            raise HTTPException(503,"SaaS 전용 격리 KiCad 작업 환경을 먼저 구성해야 합니다.")
        if target.endswith("/vision") or target == "/api/vision/status":
            raise HTTPException(503,"SaaS 전용 VLM 작업 환경은 아직 연결하지 않았습니다.")
        if write and (EXPENSIVE.fullmatch(target) or target in {"/api/planner/mcp/probe","/api/system-conversions/preview"}):
            body = await request.body()
            try:
                payload = json.loads(body) if body else {}
            except ValueError:
                raise HTTPException(422,"JSON 입력이 필요합니다.")
            key = request.headers.get("Idempotency-Key")
            if key and (len(key)>128 or not key.isascii()):
                raise HTTPException(422,"Invalid idempotency key")
            try:
                if match:
                    with project_lock(tenants.root(wid),match[1]):
                        project(wid,match[1])
                        queued = repo.enqueue(wid,user["user"],"http",{"path":target,"query":request.url.query,"body":payload},key)
                else:
                    queued = repo.enqueue(wid,user["user"],"http",{"path":target,"query":request.url.query,"body":payload},key)
            except ProjectBusy as exc:
                raise HTTPException(409,str(exc))
            repo.audit(wid,user["user"],"task.queued",target)
            return JSONResponse({"job_id":queued["id"],"status_url":f"/api/w/{wid}/jobs/{queued['id']}"},202)
        token = actor.set(user["user"])
        try:
            if request.method == 'DELETE' and match and target == '/api/projects/'+match[1]:
                # Keep enqueue/claim/draft writes serialized across worker and
                # gateway processes until deletion and draft cleanup finish.
                tenant_app = tenants.get(wid)  # reconcile before control DB write lock
                response = None
                try:
                    with repo.connect(True) as conn:
                        if conn.execute("SELECT 1 FROM jobs WHERE workspace=? AND status IN ('queued','running') LIMIT 1", (wid,)).fetchone():
                            raise HTTPException(409,'작업공간에서 분석 또는 컴파일이 진행 중입니다. 완료 후 삭제하세요. 작업이 멈춘 경우 작업 서버 상태를 확인하세요.')
                        terminal = frozenset(row['id'] for row in conn.execute("SELECT id FROM jobs WHERE workspace=? AND status IN ('done','failed','interrupted')",(wid,)).fetchall())
                        queue_token = terminal_queue_jobs.set(terminal)
                        try: response = await forward(tenant_app,request,target)
                        finally: terminal_queue_jobs.reset(queue_token)
                        if response.status_code < 400:
                            repo.cleanup_project_records(conn,wid,match[1])
                except Exception:
                    if response is None or response.status_code >= 400: raise
                    # The photo project is already gone. Preserve the durable
                    # marker and report remaining server-side cleanup honestly.
                    response = JSONResponse({'deleted_project':match[1],'cleanup_pending':True})
                else:
                    if response.status_code < 400:
                    # Only remove after the control database commit; a crash
                    # leaves the marker for tenant startup reconciliation.
                        try:(tenants.root(wid)/'.project-deletion-commits'/match[1]).unlink(missing_ok=True)
                        except OSError:pass
            else:
                response = await forward(tenants.get(wid),request,target)
        finally:
            actor.reset(token)
        if write and response.status_code < 400:
            try: repo.audit(wid,user["user"],"domain.write",target)
            except Exception:
                # Never imply the deletion was rolled back merely because the
                # separate audit write failed after it had already completed.
                if request.method == 'DELETE' and match and target == '/api/projects/'+match[1]:
                    return JSONResponse({'deleted_project':match[1],'cleanup_pending':True})
                raise
        return response

    @app.get("/login")
    def login_page():
        if preview:
            return RedirectResponse(f"/w/{preview['workspace']}/",303)
        return FileResponse(PUBLIC/"saas/login.html")

    @app.get("/")
    def home(request: Request):
        if preview:
            return RedirectResponse(f"/w/{preview['workspace']}/",303)
        return RedirectResponse("/workspaces" if request.state.identity else "/login",303)

    @app.get("/workspaces")
    def workspace_page(request: Request):
        if preview:
            return RedirectResponse(f"/w/{preview['workspace']}/",303)
        if not request.state.identity:
            return RedirectResponse("/login",303)
        return FileResponse(PUBLIC/"saas/workspaces.html")

    @app.get("/w/{wid}/")
    def analysis(wid: str, request: Request):
        member(request,wid)
        return FileResponse(PUBLIC/"index.html")

    @app.get("/w/{wid}/editor")
    def editor(wid: str, request: Request):
        member(request,wid)
        if not (DIST/"index.html").is_file():
            raise HTTPException(503,"편집기 빌드가 필요합니다.")
        return FileResponse(DIST/"index.html")

    @app.get('/w/{wid}/board-workflow.html')
    def board_workflow_page(wid:str,request:Request):
        member(request,wid)
        return FileResponse(PUBLIC/'board-workflow.html')

    @app.get("/w/{wid}/rover-editor.html")
    def rover_editor_page(wid: str, request: Request):
        member(request,wid)
        return FileResponse(PUBLIC/"rover-editor.html")

    @app.get("/w/{wid}/rover-motion.html")
    def rover_motion_page(wid: str, request: Request):
        member(request,wid)
        return FileResponse(PUBLIC/"rover-motion.html")

    @app.get("/w/{wid}/prototype-editor.html")
    def prototype_editor_page(wid: str, request: Request):
        member(request,wid)
        return FileResponse(PUBLIC/"prototype-editor.html")

    @app.get("/{path:path}")
    def static(path: str):
        # Only application assets are public. Never serve data roots or source trees.
        roots = [PUBLIC] if path.startswith("saas/") or path.endswith((".js",".css")) else []
        if path=="watering-circuit.svg":roots.append(PUBLIC)
        if path.split("/")[0] in {"assets","boards","components","component-svgs","wasm","monaco","fonts","bus-chips","firmware"} or path in {"components-metadata.json","favicon.ico","favicon.svg"}:
            roots.append(DIST)
        for root in roots:
            target = (root/path).resolve()
            if target.is_relative_to(root.resolve()) and target.is_file():
                return FileResponse(target)
        raise HTTPException(404,"Not found")

    app.add_middleware(BodyLimit)
    return app
