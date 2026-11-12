import hashlib,json
import pytest
from fastapi.testclient import TestClient
from backend.api import create_app
from backend.design.recipes import new_graph
from backend.emulator.service import emulate,saved_result,parse_execution
from backend.emulator import service
from backend.firmware import firmware
from test_design_proposals import prepare


@pytest.mark.parametrize('scenario',['circuit','input_steps'])
def test_real_uno_instructions_adc_uart_and_timers(tmp_path,scenario):
    g,_=new_graph('0'*32,'arduino_voltage_divider');r=emulate(g,tmp_path,scenario)
    assert r['status']=='PASS' and r['compiled'] and r['firmware_executed']
    assert not r['hardware_tested'] and r['mcu']=='ATmega328P'
    assert r['execution']['cycles']>=24000000 and len(r['samples'])==7
    assert r['firmware_sha256']==hashlib.sha256(firmware(g)['source'].encode()).hexdigest()
    assert (tmp_path/r['run_id']/'firmware/firmware.elf').read_bytes()[:4]==b'\x7fELF'
    assert (tmp_path/r['run_id']/'firmware/firmware.hex').read_text().startswith(':')
    assert {s['raw'] for s in r['samples']}==({511} if scenario=='circuit' else {255,511,767})
    assert saved_result(g,tmp_path)['elf_sha256']==r['elf_sha256']
    g.revision+=1;assert saved_result(g,tmp_path) is None


def test_wrong_adc_pin_really_fails_in_emulator(tmp_path,monkeypatch):
    g,_=new_graph('0'*32,'arduino_voltage_divider');code=firmware(g)
    code['source']=code['source'].replace('analogRead(SENSE_PIN)','analogRead(A1)')
    monkeypatch.setattr(service,'firmware',lambda _:code)
    r=emulate(g,tmp_path)
    assert r['status']=='FAIL' and all(s['channel']==1 for s in r['samples'])
    assert all(s['raw']==0 for s in r['samples'])


def test_compiler_failure_does_not_reuse_old_pass(tmp_path,monkeypatch):
    g,_=new_graph('0'*32,'arduino_voltage_divider')
    assert emulate(g,tmp_path)['status']=='PASS'
    monkeypatch.setattr(service,'firmware',lambda _:{'source':'THIS IS NOT C++'})
    with pytest.raises(ValueError,match='컴파일'):emulate(g,tmp_path)
    assert not (tmp_path/'latest.json').exists()


def test_missing_events_never_pass():
    r=parse_execution([{'event':'complete','ms':1500,'cycles':24000000,'adc_count':0,'crashed':False}],'circuit')
    assert r['status']=='FAIL' and not r['samples']


def test_proposal_api_execution_keeps_physical_claims_unchanged(tmp_path):
    app=create_app(tmp_path)
    with TestClient(app) as c:
        original,url,_=prepare(c,app,tmp_path);base=url.removesuffix('/design')+'/emulator'
        assert c.get(base).json()['result'] is None
        r=c.post(base,json={'expected_revision':1,'scenario':'circuit'})
        assert r.status_code==200,r.text
        assert r.json()['status']=='PASS' and r.json()['basis']=='proposed_design_only'
        assert not r.json()['physical_parts_verified']
        assert c.get(base).json()['result']==r.json()
        assert c.get('/api/projects/'+original['project_id']).json()['graph']==original
        for changes,code in [({'expected_revision':999},409),({'scenario':'arbitrary'},422),({'source':'malicious'},422),({'duration':9999999},422)]:
            assert c.post(base,json={'expected_revision':1,**changes}).status_code==code
        p=next((tmp_path/'planner'/original['project_id']).glob('*.json'));d=json.loads(p.read_text());d['graph_sha256']='old';p.write_text(json.dumps(d))
        assert c.get(base).status_code==409


def test_current_design_route_and_unsupported_board(tmp_path):
    app=create_app(tmp_path)
    with TestClient(app) as c:
        original,url,body=prepare(c,app,tmp_path)
        assert c.post('/api/projects/'+original['project_id']+'/emulator',json={'expected_revision':1}).status_code==422
        pid=c.post(url,json=body).json()['project_id'];base=f'/api/projects/{pid}/emulator'
        result=c.post(base,json={'expected_revision':1,'scenario':'input_steps'})
        assert result.status_code==200,result.text
        assert result.json()['status']=='PASS' and result.json()['basis']=='current_design'


def test_unverified_wiring_cannot_execute(tmp_path):
    g,_=new_graph('0'*32,'arduino_voltage_divider');g.links[1].to_terminal='U1.GND'
    with pytest.raises(ValueError):emulate(g,tmp_path)
    assert not (tmp_path/'latest.json').exists()
