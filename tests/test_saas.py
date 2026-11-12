"""Hosted boundaries: real HTTP auth, cross-tenant paths, durable workers, revision conflicts."""
import json
import time
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi.testclient import TestClient
from backend.saas.app import create_saas_app
from backend.saas.settings import Settings
from backend.saas.repository import Repository, Limited, Stale
from backend.saas.worker import Worker

ORIGIN = "https://circuits.example.test"
PASSWORD = "testing-only-passphrase-2026"


@pytest.fixture
def hosted(tmp_path):
    settings = Settings(tmp_path/"hosted", origin=ORIGIN)
    app = create_saas_app(settings)
    repo = app.state.repository
    alice, wa = repo.provision("alice@example.test",PASSWORD,"Alice Lab")
    bob, wb = repo.provision("bob@example.test",PASSWORD,"Bob Lab")
    with TestClient(app,base_url=ORIGIN) as a, TestClient(app,base_url=ORIGIN) as b:
        for client,email in [(a,"alice@example.test"),(b,"bob@example.test")]:
            assert client.post("/api/saas/login",json={"email":email,"password":PASSWORD},headers={"origin":ORIGIN}).status_code == 200
        yield app,repo,settings,a,b,alice,bob,wa,wb


def headers(client, **extra):
    return {"origin":ORIGIN,"X-EV-CSRF":client.cookies["ev_csrf"],**extra}


def demo(client,wid):
    response = client.post(f"/api/w/{wid}/projects/demo",headers=headers(client))
    assert response.status_code == 201,response.text
    return response.json()["graph"]


def test_hosted_settings_require_tls_and_separate_local_store(tmp_path):
    with pytest.raises(ValueError):Settings(tmp_path,origin="http://example.test")
    with pytest.raises(ValueError):Settings(tmp_path,origin="http://example.test",development=True)
    with pytest.raises(ValueError):Settings(tmp_path,origin="https://example.test/path")
    assert Settings(tmp_path,origin="http://localhost:8770",development=True).cookie == "ev_session"

def test_workspace_editor_framing_is_same_origin_only(hosted):
    app,repo,settings,a,b,alice,bob,wa,wb = hosted
    analysis=a.get(f'/w/{wa}/')
    assert analysis.headers['x-frame-options']=='DENY'
    assert "frame-ancestors 'none'" in analysis.headers['content-security-policy']
    editor=a.get(f'/w/{wa}/editor')
    assert editor.status_code==200
    assert editor.headers['x-frame-options']=='SAMEORIGIN'
    assert "frame-ancestors 'self'" in editor.headers['content-security-policy']
    assert b.get(f'/w/{wa}/editor').status_code==404
    for path in ('rover-editor.html','rover-motion.html'):
        assert a.get(f'/w/{wa}/{path}').status_code==200
        assert b.get(f'/w/{wa}/{path}').status_code==404


def test_hosted_factory_does_not_initialize_local_data_on_import(tmp_path,monkeypatch):
    import os,subprocess,sys
    local=tmp_path/"local-must-not-be-opened"
    monkeypatch.setenv("EMBEDDED_VISION_DATA",str(local))
    code = "from pathlib import Path; from backend.saas.settings import Settings; from backend.saas.repository import Repository; from backend.saas.tenancy import TenantApps; import sys; apps=TenantApps(Repository(Settings(Path(sys.argv[1]),origin='https://example.test'))); apps.get('a'*32); apps.close()"
    subprocess.run([sys.executable,"-c",code,str(tmp_path/"hosted")],check=True,env=os.environ.copy(),capture_output=True,timeout=20)
    assert not local.exists()


def test_session_cookie_origin_csrf_and_logout(hosted):
    app,repo,settings,a,b,alice,bob,wa,wb = hosted
    me = a.get("/api/saas/me").json()
    assert me["workspaces"] == [{"id":wa,"name":"Alice Lab","role":"owner"}]
    assert a.cookies.get("__Host-ev_session")
    assert a.post(f"/api/w/{wa}/projects/demo",headers={"origin":ORIGIN}).status_code == 403
    assert a.post(f"/api/w/{wa}/projects/demo",headers=headers(a,origin="https://elsewhere.test")).status_code == 403
    assert a.post(f"/api/w/{wa}/projects/demo",headers=headers(a,**{"sec-fetch-site":"cross-site"})).status_code == 403
    assert a.get("/api/saas/me",headers={"host":"other.test"}).status_code == 400
    assert a.post("/api/saas/logout",headers=headers(a)).status_code == 200
    assert a.get("/api/saas/me").status_code == 401
    with repo.connect() as c:
        assert c.execute("SELECT COUNT(*) FROM sessions WHERE user=?",(alice,)).fetchone()[0] == 0


def test_credentials_are_hashed_and_login_is_throttled(tmp_path):
    settings=Settings(tmp_path,origin=ORIGIN)
    repo=Repository(settings)
    repo.provision("a@example.test",PASSWORD,"Lab")
    with repo.connect() as c:
        assert PASSWORD not in c.execute("SELECT password FROM users").fetchone()[0]
        c.executemany("INSERT INTO login_attempts VALUES(?,?)",[("blocked",time.time())]*12)
    with pytest.raises(Limited):repo.login("a@example.test",PASSWORD,"blocked")
    assert repo.login("a@example.test","wrong-password","fresh") is None


def test_projects_images_history_exports_and_plans_are_tenant_scoped(hosted):
    app,repo,settings,a,b,alice,bob,wa,wb = hosted
    ga,gb=demo(a,wa),demo(b,wb)
    assert [p["project_id"] for p in a.get(f"/api/w/{wa}/projects").json()] == [ga["project_id"]]
    assert a.get(f"/api/w/{wb}/projects").status_code == 404
    for suffix in ("", "/image", "/history", "/export", "/planner", "/assets/image", "/artifacts/sch"):
        assert b.get(f"/api/w/{wb}/projects/{ga['project_id']}"+suffix).status_code == 404
    assert b.get(f"/api/w/{wa}/projects/{ga['project_id']}").status_code == 404
    assert a.get(f"/api/w/{wa}/projects/{ga['project_id']}/image").status_code == 200
    assert (settings.data/"tenants"/wa/(ga['project_id']+".png")).exists()
    assert not (settings.data/"tenants"/wb/(ga['project_id']+".png")).exists()
    assert a.get(f"/api/w/{wa}/projects/{gb['project_id']}").status_code == 404


def test_viewer_cannot_write_or_submit_compile(hosted):
    app,repo,settings,a,b,alice,bob,wa,wb = hosted
    demo(a,wa)
    with repo.connect(True) as c:c.execute("INSERT INTO members VALUES(?,?,?)",(wa,bob,"viewer"))
    assert b.get(f"/api/w/{wa}/projects").status_code == 200
    assert b.post(f"/api/w/{wa}/projects/demo",headers=headers(b)).status_code == 403
    assert b.post(f"/api/w/{wa}/workbench/compile/start",headers=headers(b),json={"files":[{"name":"x.ino","content":""}]}).status_code == 403


def test_cloud_draft_conflicts_and_cross_workspace_access(hosted):
    app,repo,settings,a,b,alice,bob,wa,wb = hosted
    ga=demo(a,wa);endpoint=f"/api/w/{wa}/workbench/projects/{ga['project_id']}/"+"d"*64
    assert a.get(endpoint).json()["revision"] == 0
    body={"expected_revision":0,"payload":{"format":"velxio-project","fileGroups":{"group-U1":[{"name":"sketch.ino","content":"void loop(){}"}]}}}
    assert a.put(endpoint,json=body,headers=headers(a)).json() == {"revision":1}
    assert a.put(endpoint,json=body,headers=headers(a)).status_code == 409
    assert a.get(endpoint).json()["payload"] == body["payload"]
    assert b.get(endpoint).status_code == 404
    assert b.put(endpoint.replace(wa,wb),json=body,headers=headers(b)).status_code == 404
    # A new repository instance (another API process/restart) sees the same revision.
    assert Repository(settings).draft(wa,ga['project_id'],"d"*64)["revision"] == 1


def test_compile_durable_queue_isolated_status_and_separate_worker(hosted):
    app,repo,settings,a,b,alice,bob,wa,wb = hosted
    endpoint=f"/api/w/{wa}/workbench/compile/start"
    body={"files":[{"name":"sketch.ino","content":"void setup(){} void loop(){}"}]}
    key={"Idempotency-Key":"compile-test-1"}
    jid=a.post(endpoint,json=body,headers=headers(a,**key)).json()["job_id"]
    assert a.post(endpoint,json=body,headers=headers(a,**key)).json()["job_id"] == jid
    assert a.post(endpoint,json={**body,"board":"other"},headers=headers(a,**key)).status_code == 409
    status=f"/api/w/{wa}/workbench/compile/status/{jid}"
    assert a.get(status).json()["state"] == "pending"
    assert b.get(status.replace(wa,wb)).status_code == 404
    calls=[]
    def compiler(request):
        calls.append(request.files[0].content)
        return {"success":True,"hex_content":":fake-for-unit-test-only","stdout":"","stderr":""}
    worker=Worker(settings,compiler=compiler)
    try:assert worker.run_once()
    finally:worker.close()
    assert calls == [body["files"][0]["content"]]
    assert a.get(status).json()["state"] == "done"
    assert a.get(status).json()["result"]["success"]
    assert Repository(settings).job(wa,jid)["status"] == "done"


def test_expensive_request_is_queued_and_original_revision_checks_remain(hosted):
    app,repo,settings,a,b,alice,bob,wa,wb = hosted
    ga=demo(a,wa)
    response=a.post(f"/api/w/{wa}/projects/{ga['project_id']}/agent",json={"expected_revision":999,"prompt":"설명해줘"},headers=headers(a))
    assert response.status_code == 202
    worker=Worker(settings)
    try:assert worker.run_once()
    finally:worker.close()
    result=a.get(response.json()["status_url"]).json()
    assert result["status"] == "failed" and result["result"]["status_code"] == 409
    assert a.get(f"/api/w/{wa}/projects/{ga['project_id']}").json()["graph"] == ga


def test_queue_atomic_claim_quota_and_no_replay_after_worker_loss(hosted):
    app,repo,settings,a,b,alice,bob,wa,wb = hosted
    job=repo.enqueue(wa,alice,"compile",{"files":[]})
    with ThreadPoolExecutor(max_workers=2) as pool:
        claims=list(pool.map(lambda _:Repository(settings).claim(),range(2)))
    assert sum(x is not None for x in claims) == 1
    with repo.connect(True) as c:c.execute("UPDATE jobs SET lease=? WHERE id=?",(time.time()-1,job["id"]))
    assert repo.job(wa,job["id"])["status"] == "interrupted"
    assert repo.claim() is None
    for _ in range(settings.max_pending):repo.enqueue(wa,alice,"compile",{})
    with pytest.raises(Limited):repo.enqueue(wa,alice,"compile",{})


def test_revoked_membership_blocks_previously_queued_jobs(hosted):
    app,repo,settings,a,b,alice,bob,wa,wb = hosted
    job=repo.enqueue(wa,alice,"compile",{})
    with repo.connect(True) as c:c.execute("DELETE FROM members WHERE user=? AND workspace=?",(alice,wa))
    worker=Worker(settings,compiler=lambda _:pytest.fail("revoked user must not execute"))
    try:worker.run_once()
    finally:worker.close()
    assert repo.job(wa,job["id"])["status"] == "failed"


def test_compile_failure_keeps_actionable_stderr_without_reusing_successful_hex(hosted):
    app,repo,settings,a,b,alice,bob,wa,wb = hosted
    job=repo.enqueue(wa,alice,"compile",{"files":[{"name":"broken.ino","content":"bad code"}]})
    def bad_compiler(_):raise ValueError("broken.ino:1: error: expected declaration")
    worker=Worker(settings,compiler=bad_compiler)
    try:worker.run_once()
    finally:worker.close()
    result=a.get(f"/api/w/{wa}/workbench/compile/status/{job['id']}").json()
    assert result["state"] == "done" and result["result"]["success"] is False
    assert "expected declaration" in result["result"]["stderr"]
    assert "hex_content" not in result["result"]


def test_public_assets_and_local_execution_are_not_exposed(hosted):
    app,repo,settings,a,b,alice,bob,wa,wb = hosted
    with TestClient(app,base_url=ORIGIN) as stranger:
        assert stranger.get("/api/saas/me").status_code == 401
        assert stranger.get(f"/w/{wa}/").status_code == 401
        assert stranger.get("/login").status_code == 200
        assert stranger.get("/saas/site.js").status_code == 200
        diagram=stranger.get('/watering-circuit.svg')
        assert diagram.status_code==200 and diagram.headers['content-type'].startswith('image/svg+xml')
        assert stranger.get("/control.sqlite3").status_code == 404
    g=demo(a,wa)
    assert a.post(f"/api/w/{wa}/projects/{g['project_id']}/build",json={"expected_revision":1},headers=headers(a)).status_code == 503
    assert a.post(f"/api/w/{wa}/planner/mcp/probe",headers=headers(a)).status_code == 503
    assert a.get(f"/api/w/{wa}/workbench/setup-status").json()["supported_boards"] == ["arduino:avr:uno"]


def test_streamed_oversize_json_is_rejected_before_job_creation(hosted):
    app,repo,settings,a,b,alice,bob,wa,wb = hosted
    def chunks():
        for _ in range(3):yield b"x"*(1024*1024)
    assert a.post(f"/api/w/{wa}/workbench/compile/start",content=chunks(),headers=headers(a)).status_code == 413


def test_upload_queues_analysis_without_api_credentials_and_worker_uses_tenant_asset(hosted,monkeypatch):
    import io
    from PIL import Image
    app,repo,settings,a,b,alice,bob,wa,wb = hosted
    monkeypatch.setenv("EMBEDDED_VISION_AUTO_ANALYSIS","1")
    repo.worker_heartbeat("mock-model-worker",True)
    image=io.BytesIO();Image.new("RGB",(64,64),"white").save(image,format="PNG")
    response=a.post(f"/api/w/{wa}/projects",files={"image":("photo.png",image.getvalue(),"image/png")},headers=headers(a))
    assert response.status_code == 201,response.text
    data=response.json();pid=data["graph"]["project_id"]
    assert data["auto_analysis"]["status"] == "queued"
    assert repo.job(wa,data["auto_analysis"]["queue_id"])["status"] == "queued"
    seen=[]
    def inventory(graph,assets,**kwargs):
        seen.extend(path for aid,path in assets)
        from backend.planner.service import digest
        return {"id":"a"*32,"graph_sha256":digest(graph),"task":"component_inventory"}
    monkeypatch.setattr("backend.planner.jobs.inventory_plan",inventory)
    worker=Worker(settings)
    try:assert worker.run_once()
    finally:worker.close()
    assert seen and str(settings.data/"tenants"/wa) in str(seen[0])
    assert a.get(f"/api/w/{wa}/projects/{pid}/auto-analysis").json()["job"]["status"] == "done"
    assert b.get(f"/api/w/{wb}/projects/{pid}/auto-analysis").status_code == 404
    assert "OPENAI_API_KEY" not in a.get("/api/saas/status").text
