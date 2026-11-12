"""Service boundaries, minimal editor runtime and lossless project handoff."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess

from fastapi.testclient import TestClient
import pytest

from shared.paths import PROJECT_ROOT,EDITOR_ROOT,ANALYZER_ROOT,DATA_ROOT
from services.editor.app import app


def test_code_and_data_have_canonical_service_directories():
    assert (PROJECT_ROOT/'backend/application.py').resolve().is_relative_to(ANALYZER_ROOT/'backend')
    assert (PROJECT_ROOT/'backend/workbench/server.py').resolve().is_relative_to(EDITOR_ROOT/'backend')
    assert (PROJECT_ROOT/'backend/circuit/schema.py').resolve().is_relative_to(PROJECT_ROOT/'shared/backend')
    assert (PROJECT_ROOT/'frontend').resolve()==ANALYZER_ROOT/'frontend'
    assert (PROJECT_ROOT/'data').resolve()==DATA_ROOT
    assert (PROJECT_ROOT/'patches').resolve()==EDITOR_ROOT/'patches'


def test_editor_works_without_analyzer_imports_or_credentials():
    script='''
import sys,json
from fastapi.testclient import TestClient
from services.editor.app import app
with TestClient(app) as client:
 assert client.get('/api/health').json()['service']=='editor'
 assert client.get('/').status_code==200
 p=client.get('/api/editor/examples/arduino-uno').json()
 assert p['embeddedVision']['standalone'] and len(p['wires'])==5 and p['fileGroups']
 assert client.get('/api/projects').status_code==404
assert not any(n in sys.modules for n in ['backend.application','backend.api','backend.planner.jobs','cv2','onnxruntime'])
print('editor isolated')
'''
    env={k:v for k,v in os.environ.items() if k not in {'OPENAI_API_KEY','EMBEDDED_VISION_DATA','EV_SAAS_MODE'}}
    result=subprocess.run([str(EDITOR_ROOT/'.venv/bin/python'),'-c',script],cwd=PROJECT_ROOT,env=env,capture_output=True,text=True,timeout=20)
    assert result.returncode==0,result.stderr


def test_analyzer_catalogue_does_not_require_an_editor_checkout(tmp_path,monkeypatch):
    from backend.design import simulator_catalog
    monkeypatch.setattr(simulator_catalog,'FRONTEND',tmp_path/'not-installed')
    catalog=simulator_catalog.load_simulator_catalog()
    assert catalog['source']=='shared_catalog_snapshot' and catalog['status']=='available'
    assert len(catalog['entries'])==192
    assert simulator_catalog.load_simulator_catalog(tmp_path/'explicit-missing')['status']=='unavailable'


def test_editor_home_and_example_are_local_and_keep_the_vlx_contract():
    with TestClient(app) as client:
        assert '아두이노 편집기 열기' in client.get('/').text
        assert client.get('/workspace-assets/home.js').status_code==200
        for entry in client.get('/api/editor/examples').json():
            project=client.get('/api/editor/examples/'+entry['id']).json()
            assert project['format']=='velxio-project' and project['embeddedVision']['standalone']
            assert project['boards'] and project['components'] and project['wires'] and project['fileGroups']
        assert client.get('/api/editor/examples/not-a-board').status_code==404


def launcher_fixture(tmp_path,monkeypatch,service,*,failed=None):
    monkeypatch.chdir(PROJECT_ROOT)
    monkeypatch.setenv('EMBEDDED_EDITOR_DATA',str(tmp_path/'.runtime/editor'))
    monkeypatch.setenv('EMBEDDED_ANALYZER_DATA',str(tmp_path/'.runtime/analyzer'))
    spec=importlib.util.spec_from_file_location('split_launch',PROJECT_ROOT/'scripts/launch.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    names=['editor','analyzer'] if service=='all' else [service]
    for name in names:
        p=tmp_path/f'services/{name}/.venv/bin/python';p.parent.mkdir(parents=True);p.touch()
    if 'editor' in names:
        p=tmp_path/'services/editor/vendor/velxio/frontend/dist/index.html';p.parent.mkdir(parents=True);p.touch()
    monkeypatch.setattr(module,'ROOT',tmp_path)
    monkeypatch.setattr('sys.argv',['launch.py','--service',service,'--no-open'])
    monkeypatch.setattr(module,'wait_ready',lambda *a,**kw:None)
    class Socket:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def setsockopt(self,*args):pass
        def bind(self,*args):pass
    monkeypatch.setattr(module.socket,'socket',lambda *a,**kw:Socket())
    created=[]
    class Child:
        def __init__(self,name):self.name=name;self.terminated=False
        def poll(self):return 1 if self.name==failed or self.terminated else None
        def terminate(self):self.terminated=True
        def wait(self,**kw):return 0
    def popen(args,**kwargs):
        child=Child('editor' if 'services.editor.app:app' in args else 'analyzer')
        created.append((child,args,kwargs));return child
    monkeypatch.setattr(module.subprocess,'Popen',popen)
    def stop(_):
        assert all(not child.terminated for child,_,_ in created)
        raise KeyboardInterrupt
    monkeypatch.setattr(module.time,'sleep',stop)
    return module,created


@pytest.mark.parametrize('service',['editor','analyzer'])
def test_launcher_only_starts_the_selected_service(tmp_path,monkeypatch,service):
    module,created=launcher_fixture(tmp_path,monkeypatch,service)
    module.main()
    assert [c.name for c,_,_ in created]==[service]
    assert created[0][0].terminated
    assert created[0][2]['env']['EMBEDDED_VISION_DATA']==str(tmp_path/f'.runtime/{service}')


def test_a_service_failure_does_not_stop_the_other_service(tmp_path,monkeypatch):
    module,created=launcher_fixture(tmp_path,monkeypatch,'all',failed='analyzer')
    module.main()
    assert created[0][0].name=='editor' and created[0][0].terminated
    assert created[1][0].name=='analyzer' and not created[1][0].terminated


def test_editor_project_storage_preserves_wiring_code_and_structure(tmp_path,monkeypatch):
    monkeypatch.setenv('EMBEDDED_EDITOR_DATA',str(tmp_path))
    with TestClient(app) as client:
        original=client.get('/api/editor/examples/arduino-uno').json()
        original['embeddedVision']['assembly']={'parts':[{'id':'case','position':[1,2,3]}]}
        before=json.dumps(original,sort_keys=True)
        response=client.post('/api/editor/projects',json=original)
        assert response.status_code==201
        data=response.json();stored=client.get('/api/editor/projects/'+data['project_id'])
        assert stored.status_code==200 and stored.headers['cache-control']=='private, no-store'
        restored=stored.json()
        for key in ['boards','components','wires','fileGroups']:
            assert restored[key]==original[key]
        assert restored['embeddedVision']['assembly']==original['embeddedVision']['assembly']
        assert restored['embeddedVision']['standalone']
        assert json.dumps(original,sort_keys=True)==before
        assert (tmp_path/'projects'/(data['project_id']+'.json')).stat().st_mode & 0o777==0o600
        assert 'editor_project='+data['project_id'] in data['editor_url']
        assert client.post('/api/editor/projects',json=original,headers={'Origin':'https://other.example'}).status_code==403
        assert client.post('/api/editor/projects',json={'format':'velxio-project'}).status_code==422
        assert client.post('/api/editor/projects',content='invalid json').status_code==422
        assert client.get('/api/editor/projects/invalid-id').status_code==404
        symlink=tmp_path/'projects'/('a'*32+'.json');symlink.symlink_to(tmp_path/'secret.json')
        assert client.get('/api/editor/projects/'+'a'*32).status_code==404


def test_legacy_editor_installation_moves_without_losing_edits(tmp_path):
    from scripts.migrate_editor_layout import migrate
    old=tmp_path/'third_party/velxio';old.mkdir(parents=True)
    (old/'user-edit.txt').write_text('local changes')
    avr=tmp_path/'.tools/avr';avr.mkdir(parents=True);(avr/'manifest.json').write_text('{}')
    migrate(tmp_path);migrate(tmp_path)
    assert old.is_symlink() and (old/'user-edit.txt').read_text()=='local changes'
    assert (tmp_path/'services/editor/vendor/velxio/user-edit.txt').read_text()=='local changes'
    assert avr.is_symlink() and (avr/'manifest.json').is_file()


def test_migration_preserves_both_existing_installations(tmp_path):
    from scripts.migrate_editor_layout import migrate
    for name in ['third_party/velxio','services/editor/vendor/velxio']:
        path=tmp_path/name;path.mkdir(parents=True);(path/'edit.txt').write_text(name)
    migrate(tmp_path)
    for name in ['third_party/velxio','services/editor/vendor/velxio']:
        assert (tmp_path/name/'edit.txt').read_text()==name
