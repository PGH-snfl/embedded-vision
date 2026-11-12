"""Tenant apps bind all existing domain modules to a dedicated repository root.

No mutable global/current-tenant variable is used to choose a data directory.
The request context below supplies only the audit actor for queued uploads.
"""
import re
from contextvars import ContextVar
from ..circuit.project_lock import project_lock, ProjectBusy

actor = ContextVar("saas_actor", default=None)
ID = re.compile(r"^[a-f0-9]{32}$")


class TenantApps:
    def __init__(self, repository):
        self.repository = repository
        self.apps = {}

    def root(self, wid):
        if not ID.fullmatch(wid):
            raise ValueError("Invalid workspace ID")
        base = (self.repository.settings.data / "tenants").resolve()
        target = (base / wid).resolve()
        if target.parent != base:
            raise ValueError("Invalid workspace path")
        target.mkdir(parents=True, exist_ok=True, mode=0o700)
        return target

    def get(self, wid):
        if wid not in self.apps:
            # Keep the single-host adapter bounded; no in-process work runs in these apps.
            if len(self.apps) >= 32:
                old = self.apps.pop(next(iter(self.apps)))
                old.state.auto_analysis.close()
                old.state.vision_pool.shutdown(wait=False,cancel_futures=True)
            from ..application import create_app

            def dispatch(job):
                uid = actor.get()
                if not uid:
                    raise RuntimeError("Missing authenticated task actor")
                return self.repository.enqueue(wid, uid, "inventory", {
                    "project": job["project_id"], "analysis_id": job["id"],
                    "revision": job["revision"], "graph_sha256": job["graph_sha256"],
                    "analysis_model": job["analysis_model"],
                }, "inventory:"+job["id"], job_id=job['id'])

            self.apps[wid] = create_app(self.root(wid), local_only=False, analysis_dispatch=dispatch,
                                       provider_ready=lambda:self.repository.worker_status()['model_ready'])
            self.apps[wid].state.auto_analysis.queue_lookup=lambda jid:self.repository.job(wid,jid)
        # An interrupted deletion can be observed by a long-lived gateway
        # after initial startup; retry staged-file recovery on each access.
        from ..circuit.project_deletion import recover_project_deletions
        recover_project_deletions(self.apps[wid].state.store)
        self.reconcile_deletions(wid,self.apps[wid])
        return self.apps[wid]

    def reconcile_deletions(self, wid, app):
        markers=app.state.store.root/'.project-deletion-commits'
        if not markers.is_dir() or markers.is_symlink(): return
        for marker in markers.iterdir():
            pid=marker.name
            if not ID.fullmatch(pid) or not marker.is_file() or marker.is_symlink(): continue
            try:
                with project_lock(app.state.store.root,pid,exclusive=True):
                    try:
                        app.state.store.get(pid)
                    except KeyError:
                        with self.repository.connect(True) as conn:
                            # A formerly queued worker may still be using its
                            # lease; preserve records until it is finished.
                            if conn.execute("SELECT 1 FROM jobs WHERE workspace=? AND status IN ('queued','running') LIMIT 1",(wid,)).fetchone():
                                continue
                            self.repository.cleanup_project_records(conn,wid,pid)
                    marker.unlink(missing_ok=True)
            except (ProjectBusy,OSError):
                continue

    def close(self):
        for app in self.apps.values():
            app.state.auto_analysis.close()
            app.state.vision_pool.shutdown(wait=False,cancel_futures=True)


async def forward(app, request, path):
    """Forward a validated request; original body and query are retained."""
    scope = dict(request.scope)
    scope["path"] = path
    scope["raw_path"] = path.encode()
    scope["root_path"] = ""
    body = await request.body()
    sent = False

    async def receive():
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        return await request.receive()

    from starlette.responses import Response
    chunks, headers, status = [], [], 500

    async def send(message):
        nonlocal status, headers
        if message["type"] == "http.response.start":
            status, headers = message["status"], message["headers"]
        elif message["type"] == "http.response.body":
            chunks.append(message.get("body", b""))

    await app(scope, receive, send)
    response = Response(b"".join(chunks), status_code=status)
    response.raw_headers = headers
    return response
