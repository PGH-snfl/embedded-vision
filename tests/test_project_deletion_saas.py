import io
import json
from unittest.mock import patch

from PIL import Image

from backend.circuit.project_lock import project_lock
from test_saas import hosted, headers


def photo(client, wid):
    out=io.BytesIO();Image.new('RGB',(80,80),'white').save(out,format='PNG')
    response=client.post(f'/api/w/{wid}/projects',files={'image':('photo.png',out.getvalue(),'image/png')},headers=headers(client))
    assert response.status_code==201,response.text
    return response.json()['graph']


def test_hosted_delete_permission_conflict_jobs_and_drafts(hosted):
    app,repo,settings,a,b,alice,bob,wa,wb=hosted
    original=photo(a,wa);other=photo(b,wb);pid=original['project_id']
    url=f'/api/w/{wa}/projects/{pid}';params={'expected_revision':original['revision']}
    draft=f'/api/w/{wa}/workbench/projects/{pid}/'+('d'*64)
    body={'expected_revision':0,'payload':{'format':'velxio-project','value':'test'}}
    assert a.put(draft,json=body,headers=headers(a)).status_code==200
    with repo.connect(True) as conn:conn.execute('INSERT INTO members VALUES(?,?,?)',(wa,bob,'viewer'))
    assert b.delete(url,params=params,headers=headers(b)).status_code==403
    assert b.delete(url.replace(wa,wb),params=params,headers=headers(b)).status_code==404
    assert a.delete(url,params={'expected_revision':999},headers=headers(a)).status_code==409
    job=repo.enqueue(wa,alice,'inventory',{'project':pid})
    assert a.delete(url,params=params,headers=headers(a)).status_code==409
    with repo.connect(True) as conn:conn.execute("UPDATE jobs SET status='failed' WHERE id=?",(job['id'],))
    auto=settings.data/'tenants'/wa/'auto_jobs'/(pid+'.json')
    obj=json.loads(auto.read_text());obj.update(status='queued',queue_id=job['id']);auto.write_text(json.dumps(obj))
    with project_lock(settings.data/'tenants'/wa,pid):
        assert a.delete(url,params=params,headers=headers(a)).status_code==409
    result=a.delete(url,params=params,headers=headers(a))
    assert result.status_code==200,result.text
    assert result.json()=={'deleted_project':pid,'cleanup_pending':False}
    assert a.get(url).status_code==404 and b.get(f'/api/w/{wb}/projects/{other["project_id"]}').status_code==200
    with repo.connect() as conn:
        assert conn.execute('SELECT COUNT(*) FROM drafts WHERE workspace=? AND project=?',(wa,pid)).fetchone()[0]==0
        assert conn.execute('SELECT COUNT(*) FROM jobs WHERE id=?',(job['id'],)).fetchone()[0]==0
    assert not list((settings.data/'tenants'/wa/'.project-deletion-commits').glob('*'))


def test_saas_partial_file_cleanup_still_removes_server_draft(hosted):
    app,repo,settings,a,b,alice,bob,wa,wb=hosted
    graph=photo(a,wa);pid=graph['project_id'];draft='c'*64
    repo.save_draft(wa,alice,pid,draft,0,{'format':'velxio-project'})
    with patch('backend.circuit.project_deletion.shutil.rmtree',side_effect=OSError('denied')):
        response=a.delete(f'/api/w/{wa}/projects/{pid}',params={'expected_revision':graph['revision']},headers=headers(a))
    assert response.status_code==200 and response.json()['cleanup_pending'] is True
    assert repo.draft(wa,pid,draft)['payload'] is None
    assert list((settings.data/'tenants'/wa/'.project-trash').glob(pid+'-*'))


def test_saas_recovery_only_removes_records_with_deletion_marker(hosted):
    app,repo,settings,a,b,alice,bob,wa,wb=hosted
    graph=photo(a,wa);pid=graph['project_id'];other=photo(a,wa);otherid=other['project_id'];draft='e'*64
    repo.save_draft(wa,alice,pid,draft,0,{'format':'velxio-project','value':'delete'})
    repo.save_draft(wa,alice,otherid,draft,0,{'format':'velxio-project','value':'keep'})
    tenant=app.state.tenants.get(wa);markers=tenant.state.store.root/'.project-deletion-commits';markers.mkdir(exist_ok=True)
    (markers/pid).write_text('deletion-requested\n')
    with tenant.state.store.connect() as db:db.execute('DELETE FROM revisions WHERE project IN (?,?)',(pid,otherid))
    # Reconciliation touches the project with an explicit deletion marker only.
    app.state.tenants.get(wa)
    assert repo.draft(wa,pid,draft)['payload'] is None
    assert repo.draft(wa,otherid,draft)['payload']['value']=='keep'
    assert not (markers/pid).exists()


def test_saas_control_failure_reports_pending_then_recovers(hosted):
    app,repo,settings,a,b,alice,bob,wa,wb=hosted
    graph=photo(a,wa);pid=graph['project_id'];draft='a'*64
    repo.save_draft(wa,alice,pid,draft,0,{'format':'velxio-project'})
    with patch.object(repo,'cleanup_project_records',side_effect=OSError('control failure')):
        response=a.delete(f'/api/w/{wa}/projects/{pid}',params={'expected_revision':graph['revision']},headers=headers(a))
    assert response.status_code==200 and response.json()['cleanup_pending'] is True
    assert repo.draft(wa,pid,draft)['payload'] is not None
    marker=settings.data/'tenants'/wa/'.project-deletion-commits'/pid
    assert marker.exists()
    app.state.tenants.get(wa)
    assert repo.draft(wa,pid,draft)['payload'] is None and not marker.exists()


def test_saas_audit_failure_does_not_claim_deleted_project_survived(hosted):
    app,repo,settings,a,b,alice,bob,wa,wb=hosted
    graph=photo(a,wa);pid=graph['project_id']
    with patch.object(repo,'audit',side_effect=OSError('audit unavailable')):
        response=a.delete(f'/api/w/{wa}/projects/{pid}',params={'expected_revision':graph['revision']},headers=headers(a))
    assert response.status_code==200 and response.json()['deleted_project']==pid
    assert response.json()['cleanup_pending'] is True
    assert a.get(f'/api/w/{wa}/projects/{pid}').status_code==404


def test_cached_tenant_restores_uncommitted_staging(hosted):
    app,repo,settings,a,b,alice,bob,wa,wb=hosted
    graph=photo(a,wa);pid=graph['project_id'];tenant=app.state.tenants.get(wa)
    root=tenant.state.store.root;image=root/(pid+'.png')
    staged=root/'.project-trash'/(pid+'-interrupted');staged.mkdir(parents=True)
    (staged/'manifest.json').write_text(json.dumps({'project':pid,'paths':[image.name]}));image.rename(staged/'0')
    marker=root/'.project-deletion-commits'/pid;marker.parent.mkdir(exist_ok=True);marker.write_text('deletion-requested\n')
    app.state.tenants.get(wa)
    assert image.exists() and not staged.exists() and not marker.exists()
    assert a.get(f'/api/w/{wa}/projects/{pid}/image').status_code==200
