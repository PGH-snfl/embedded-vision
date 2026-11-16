"""Learning projects must agree with their real wires, materials and compiled code."""
import json
from fastapi.testclient import TestClient
import pytest
from services.editor.app import app
from services.editor.backend.examples import lesson_project,lesson_specs
from backend.workbench.server import CompileRequest,compile_edit

LESSONS=[spec['id'] for spec in lesson_specs()]

@pytest.mark.parametrize('lesson_id',LESSONS)
def test_learning_project_instructions_match_wires_and_firmware(lesson_id):
    project=lesson_project(lesson_id)
    guide=project['embeddedVision']['learning_guide']
    assert project['boards'][0]['boardKind']=='arduino-uno'
    assert {x['ref'] for x in guide['materials']}=={x['id'] for x in project['boards']+project['components']}
    assert guide['jumper_count']==sum(not w.get('bb') for w in project['wires'])
    actual={(w['start']['componentId']+'.'+w['start']['pinName'],w['end']['componentId']+'.'+w['end']['pinName'],'insert' if w.get('bb') else 'jumper') for w in project['wires']}
    steps=project['embeddedVision']['assembly']['steps']
    assert {(s['from'],s['to'],s['kind']) for s in steps}==actual
    code='\n'.join(f['content'] for group in project['fileGroups'].values() for f in group)
    assert all(note['token'] in code for note in guide['code_notes'])
    assert guide['goals'] and guide['run_steps'] and guide['checks']
    if lesson_id=='uno-lcd-message':
        assert next(c for c in project['components'] if c['id']=='LCD1')['properties']['color']=='white'
    assert project['embeddedVision']['standalone'] and not project['embeddedVision']['analysis_origin']
    # Reopening must restore this lesson's draft without merging it with another recipe.
    second=lesson_project(lesson_id)
    assert second['embeddedVision']['source_graph_sha256']==project['embeddedVision']['source_graph_sha256']
    second['embeddedVision']['learning_guide']['materials'].clear()
    assert lesson_project(lesson_id)['embeddedVision']['learning_guide']['materials']

@pytest.mark.parametrize('lesson_id',LESSONS)
def test_each_learning_sketch_compiles_in_the_editor(lesson_id):
    project=lesson_project(lesson_id)
    files=next(iter(project['fileGroups'].values()))
    result=compile_edit(CompileRequest(files=[{'name':x['name'],'content':x['content']} for x in files]))
    assert result['success'] and result['hex_content'].startswith(':')


def test_learning_project_api_opens_guide_and_preserves_user_file(tmp_path,monkeypatch):
    monkeypatch.setenv('EMBEDDED_EDITOR_DATA',str(tmp_path))
    with TestClient(app) as client:
        entries=client.get('/api/editor/lessons').json()
        assert [x['id'] for x in entries]==LESSONS
        assert client.get('/api/editor/lessons/not-registered').status_code==404
        keys=set()
        for entry in entries:
            project=client.get('/api/editor/lessons/'+entry['id']).json()
            key=project['embeddedVision']['source_graph_sha256'];assert key not in keys;keys.add(key)
            before=json.dumps(project,sort_keys=True)
            prepared=client.post('/api/editor/projects',json=project).json()
            assert '&guide=1' in prepared['editor_url']
            restored=client.get('/api/editor/projects/'+prepared['project_id']).json()
            for field in ['boards','components','wires','fileGroups']:
                assert restored[field]==project[field]
            assert restored['embeddedVision']['learning_guide']==project['embeddedVision']['learning_guide']
            assert json.dumps(project,sort_keys=True)==before
        assert len(client.get('/api/editor/examples').json())==4
        assert client.get('/api/projects').status_code==404
