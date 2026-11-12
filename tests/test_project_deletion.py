import io
import json
import shutil
import threading
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image

from backend.api import create_app
from backend.circuit.project_deletion import recover_project_deletions
from backend.circuit.project_lock import project_lock
from backend.circuit.schema import Graph


def photo(client):
    out = io.BytesIO()
    Image.new('RGB', (80, 80), 'white').save(out, format='PNG')
    response = client.post('/api/projects', files={'image': ('input.png', out.getvalue(), 'image/png')})
    assert response.status_code == 201
    return response.json()['graph']


def test_delete_only_one_photo_project_and_own_files(tmp_path):
    app = create_app(tmp_path)
    with TestClient(app) as client:
        one, other = photo(client), photo(client)
        pid = one['project_id']; other_id = other['project_id']
        (tmp_path / (pid+'-view_a.png')).write_bytes(b'additional')
        (tmp_path / (pid+'.video')).write_bytes(b'video')
        for parent in ['planner', 'artifacts', 'function_targets', 'proposal_simulations', 'emulations']:
            directory = tmp_path / parent / pid
            directory.mkdir(parents=True)
            (directory / 'data').write_text('content')
        unrelated = tmp_path / 'designs' / other_id
        unrelated.mkdir(parents=True)
        (unrelated / 'provenance.json').write_text(json.dumps({'source_project':pid}))
        url = '/api/projects/' + pid
        assert client.delete(url, params={'expected_revision': one['revision']+1}).status_code == 409
        assert (tmp_path / (pid+'.png')).exists()
        result = client.delete(url, params={'expected_revision': one['revision']})
        assert result.status_code == 200, result.text
        assert result.json() == {'deleted_project':pid,'cleanup_pending':False}
        assert client.get(url).status_code == 404
        assert client.get('/api/projects/'+other_id).status_code == 200
        assert (tmp_path/(other_id+'.png')).exists() and unrelated.exists()
        assert not list(tmp_path.glob(pid+'*'))
        for parent in ['planner', 'artifacts', 'function_targets', 'proposal_simulations', 'emulations']:
            assert not (tmp_path / parent / pid).exists()


def test_active_worker_and_process_lock_block_deletion(tmp_path):
    app = create_app(tmp_path)
    with TestClient(app) as client:
        graph = photo(client); pid=graph['project_id']; url='/api/projects/'+pid
        params={'expected_revision':graph['revision']}
        job=tmp_path/'auto_jobs'/(pid+'.json')
        original=json.loads(job.read_text());job.write_text(json.dumps({**original,'status':'queued'}))
        assert client.delete(url,params=params).status_code == 409
        job.write_text(json.dumps(original))
        app.state.vision_jobs['test']={'project_id':pid,'status':'running'}
        assert client.delete(url,params=params).status_code == 409
        app.state.vision_jobs.clear()
        with project_lock(tmp_path,pid):
            assert client.delete(url,params=params).status_code == 409
        assert client.get(url).status_code == 200
        assert client.delete(url,params=params).status_code == 200


def test_running_analysis_cannot_recreate_deleted_files(tmp_path, monkeypatch):
    import time
    started=threading.Event(); release=threading.Event()
    def analysis(graph, assets, **kwargs):
        from backend.planner.service import digest
        started.set(); assert release.wait(5)
        return {'id':'a'*32,'graph_sha256':digest(graph),'task':'component_inventory'}
    monkeypatch.setenv('EMBEDDED_VISION_AUTO_ANALYSIS','1')
    monkeypatch.setattr('backend.planner.jobs.inventory_plan',analysis)
    app=create_app(tmp_path)
    app.state.auto_analysis.provider_ready=lambda:True
    with TestClient(app) as client:
        graph=photo(client);pid=graph['project_id'];url='/api/projects/'+pid
        assert started.wait(3)
        assert client.delete(url,params={'expected_revision':graph['revision']}).status_code==409
        release.set()
        for _ in range(100):
            if app.state.auto_analysis.read(pid)['status']=='done':break
            time.sleep(.02)
        assert app.state.auto_analysis.read(pid)['status']=='done'
        assert client.delete(url,params={'expected_revision':graph['revision']}).status_code==200
        # A late queued worker in a second process must not recreate reports.
        app.state.auto_analysis._worker({'project_id':pid},Graph.model_validate(graph))
        assert not (tmp_path/'auto_jobs'/(pid+'.json')).exists()
        assert not (tmp_path/'planner'/pid).exists()


def test_non_photo_project_is_not_deleted(tmp_path):
    app=create_app(tmp_path)
    with TestClient(app) as client:
        graph=client.post('/api/projects/demo').json()['graph']
        assert client.delete('/api/projects/'+graph['project_id'],params={'expected_revision':graph['revision']}).status_code == 422
        assert client.get('/api/projects/'+graph['project_id']).status_code == 200


def test_interrupted_staging_recovers_or_removes_on_restart(tmp_path):
    app=create_app(tmp_path)
    with TestClient(app) as client:
        graph=photo(client);pid=graph['project_id']
        image=tmp_path/(pid+'.png');trash=tmp_path/'.project-trash'/(pid+'-test')
        trash.mkdir(parents=True)
        (trash/'manifest.json').write_text(json.dumps({'project':pid,'paths':[image.name]}))
        image.rename(trash/'0')
        recover_project_deletions(app.state.store)
        assert image.exists() and not trash.exists()
        trash.mkdir();(trash/'manifest.json').write_text(json.dumps({'project':pid,'paths':[image.name]}));image.rename(trash/'0')
        with app.state.store.connect() as db:db.execute('DELETE FROM revisions WHERE project=?',(pid,))
        recover_project_deletions(app.state.store)
        assert not image.exists() and not trash.exists()


def test_cleanup_failure_reports_partial_and_recovers(tmp_path):
    app=create_app(tmp_path)
    with TestClient(app) as client:
        graph=photo(client);pid=graph['project_id']
        with patch('backend.circuit.project_deletion.shutil.rmtree',side_effect=OSError('denied')):
            response=client.delete('/api/projects/'+pid,params={'expected_revision':graph['revision']})
        assert response.status_code == 200 and response.json()['cleanup_pending']
        assert client.get('/api/projects/'+pid).status_code==404
        assert list((tmp_path/'.project-trash').glob(pid+'-*'))
        recover_project_deletions(app.state.store)
        assert not list((tmp_path/'.project-trash').glob(pid+'-*'))
