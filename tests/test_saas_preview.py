from fastapi.testclient import TestClient
import pytest
from backend.saas.app import create_saas_app
from backend.saas.settings import Settings
from backend.saas.worker import Worker

ORIGIN = "http://127.0.0.1:8770"


def preview_settings(tmp_path):
    return Settings(tmp_path/"preview",origin=ORIGIN,development=True,auth_enabled=False)


def test_preview_opens_without_login_and_keeps_workspace_after_restart(tmp_path):
    settings=preview_settings(tmp_path)
    with TestClient(create_saas_app(settings),base_url=ORIGIN) as client:
        me=client.get('/api/saas/me').json();wid=me['default_workspace']
        assert me['auth_enabled'] is False
        for path in ('/','/login','/workspaces'):
            response=client.get(path,follow_redirects=False)
            assert response.status_code == 303
            assert response.headers['location'] == f'/w/{wid}/'
        assert client.get(f'/w/{wid}/').status_code == 200
        created=client.post(f'/api/w/{wid}/projects/demo',headers={'origin':ORIGIN})
        assert created.status_code == 201
        pid=created.json()['graph']['project_id']
    with TestClient(create_saas_app(settings),base_url=ORIGIN) as client:
        assert client.get('/api/saas/me').json()['default_workspace'] == wid
        assert client.get(f'/api/w/{wid}/projects/{pid}').status_code == 200


def test_preview_keeps_existing_accounts_private_and_origin_guard(tmp_path):
    app=create_saas_app(preview_settings(tmp_path))
    uid,private=app.state.repository.provision('private@example.test','private-password-2026','Private')
    with TestClient(app,base_url=ORIGIN) as client:
        wid=client.get('/api/saas/me').json()['default_workspace']
        assert private != wid
        assert client.get(f'/api/w/{private}/projects').status_code == 404
        assert client.post(f'/api/w/{wid}/projects/demo',headers={'origin':'https://other.test'}).status_code == 403
        assert client.post('/api/saas/login',json={'email':'private@example.test','password':'private-password-2026'},headers={'origin':ORIGIN}).status_code == 409
    enabled=Settings(app.state.settings.data,origin=ORIGIN,development=True,auth_enabled=True)
    with TestClient(create_saas_app(enabled),base_url=ORIGIN) as client:
        assert client.get('/api/saas/me').status_code == 401
        assert client.post('/api/saas/login',json={'email':'private@example.test','password':'private-password-2026'},headers={'origin':ORIGIN}).status_code == 200

def test_only_workspace_editor_pages_can_be_embedded(tmp_path):
    with TestClient(create_saas_app(preview_settings(tmp_path)),base_url=ORIGIN) as client:
        wid=client.get('/api/saas/me').json()['default_workspace']
        for name in ('prototype-editor.html','rover-editor.html'):
            response=client.get(f'/w/{wid}/{name}')
            assert response.status_code==200
            assert response.headers['x-frame-options']=='SAMEORIGIN'
            assert "frame-ancestors 'self'" in response.headers['content-security-policy']
        analysis=client.get(f'/w/{wid}/')
        assert analysis.headers['x-frame-options']=='DENY'
        assert "frame-ancestors 'none'" in analysis.headers['content-security-policy']


def test_preview_actor_can_use_existing_worker_pipeline(tmp_path):
    settings=preview_settings(tmp_path);app=create_saas_app(settings)
    with TestClient(app,base_url=ORIGIN) as client:
        wid=client.get('/api/saas/me').json()['default_workspace']
        result=client.post(f'/api/w/{wid}/workbench/compile/start',json={'files':[{'name':'sketch.ino','content':'void setup(){} void loop(){}'}]},headers={'origin':ORIGIN})
        assert result.status_code == 200
        worker=Worker(settings,compiler=lambda request:{'success':True,'stdout':'unit-test-compiler','stderr':''})
        try:assert worker.run_once()
        finally:worker.close()
        job=client.get(f"/api/w/{wid}/workbench/compile/status/{result.json()['job_id']}").json()
        assert job['state']=='done' and job['result']['success']


def test_login_free_mode_cannot_be_enabled_on_public_origin(tmp_path,monkeypatch):
    with pytest.raises(ValueError,match='loopback'):
        Settings(tmp_path,origin='https://example.test',development=True,auth_enabled=False)
    monkeypatch.setenv('EV_SAAS_DATA',str(tmp_path))
    monkeypatch.setenv('EV_SAAS_DEVELOPMENT','1')
    monkeypatch.setenv('EV_SAAS_ORIGIN',ORIGIN)
    monkeypatch.delenv('EV_SAAS_AUTH_ENABLED',raising=False)
    assert Settings.from_env().auth_enabled is False
    monkeypatch.setenv('EV_SAAS_AUTH_ENABLED','1')
    assert Settings.from_env().auth_enabled is True
