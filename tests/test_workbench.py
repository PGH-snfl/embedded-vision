import pytest
from fastapi.testclient import TestClient
from backend.design.recipes import new_graph
from backend.workbench.export import export_project
from backend.workbench.server import app,compile_edit,CompileRequest
from backend.circuit.connectivity import derive_nets
from backend.workbench.breadboard import projected_nets


def test_export_preserves_connections_and_source():
    graph,_=new_graph('a'*32,'arduino_voltage_divider');before=graph.model_dump_json()
    payload=export_project(graph,{'source_revision':7})
    assert payload['embeddedVision']['physical_verified'] is False
    assert payload['embeddedVision']['original_wiring_reused'] is False
    assert payload['embeddedVision']['source_revision']==7
    actual=projected_nets(payload['wires'])
    assert actual=={frozenset(n['terminals']) for n in derive_nets(graph)}
    assert 'analogRead(SENSE_PIN)' in payload['fileGroups']['group-U1'][0]['content']
    assert graph.model_dump_json()==before


def test_lcd_export_requires_message_and_preserves_wiring():
    graph,_=new_graph('a'*32,'arduino_lcd')
    with pytest.raises(ValueError):export_project(graph)
    payload=export_project(graph,{'function':{'display_text':'Javalab.org'}})
    assert {c['metadataId'] for c in payload['components']} == {'breadboard','lcd1602','potentiometer','resistor'}
    assert 'lcd.print("Javalab.org")' in payload['fileGroups']['group-U1'][0]['content']
    assert 'Elapsed' not in payload['fileGroups']['group-U1'][0]['content']
    assert len({e['pinName'] for w in payload['wires'] for e in (w['start'],w['end']) if e['componentId']=='BB1'}) == 11
    assert payload['embeddedVision']['physical_verified'] is False


def request(code,**kwargs):
    return CompileRequest(files=[{'name':'sketch.ino','content':code}],**kwargs)


def test_real_edited_compilation_and_failure():
    a=compile_edit(request('void setup(){Serial.begin(115200);Serial.println("first");} void loop(){}'))
    b=compile_edit(request('void setup(){Serial.begin(115200);Serial.println("changed");} void loop(){}'))
    assert a['success'] and b['success'] and a['hex_content']!=b['hex_content']
    with pytest.raises(ValueError):compile_edit(request('broken code !'))


def test_compiler_cannot_read_host_files(tmp_path):
    secret=tmp_path/'sentinel.h';secret.write_text('static const char sentinel[]="host-only";')
    with pytest.raises(ValueError,match='No such file'):
        compile_edit(request(f'#include "{secret}"\nvoid setup(){{}} void loop(){{}}'))


def test_unsupported_board_and_path():
    with pytest.raises(ValueError):compile_edit(request('',board_fqbn='esp32:esp32:esp32'))
    with pytest.raises(ValueError):compile_edit(CompileRequest(files=[{'name':'../escape.cpp','content':''}]))


def test_origin_and_compile_api():
    with TestClient(app) as client:
        body={'files':[{'name':'sketch.ino','content':'void setup(){} void loop(){}'}],'board_fqbn':'arduino:avr:uno'}
        assert client.post('/api/compile/start',json=body,headers={'origin':'https://other.example'}).status_code==403
        job=client.post('/api/compile/start',json=body).json()['job_id']
        assert client.get('/api/compile/status/'+job).json()['result']['success']
        bad=client.post('/api/compile/start',json={**body,'files':[{'name':'sketch.ino','content':'invalid'}]}).json()['job_id']
        result=client.get('/api/compile/status/'+bad).json()['result']
        assert not result['success'] and 'hex_content' not in result


def test_export_api_is_read_only_and_rejects_stale_inventory(tmp_path):
    from backend.api import create_app
    from test_design_proposals import prepare
    import json
    app=create_app(tmp_path)
    with TestClient(app) as client:
        original,url,_=prepare(client,app,tmp_path)
        endpoint=url.removesuffix('/design')+'/workbench'
        response=client.get(endpoint)
        assert response.status_code==200,response.text
        assert len(response.json()['wires'])==7
        assert client.get('/api/projects/'+original['project_id']).json()['graph']==original
        assert client.get(endpoint+'?recipe=esp32_led_button').status_code==422
        path=next((tmp_path/'planner'/original['project_id']).glob('*.json'))
        plan=json.loads(path.read_text());plan['graph_sha256']='stale';path.write_text(json.dumps(plan))
        assert client.get(endpoint).status_code==409
