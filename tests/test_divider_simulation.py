import json
import pytest
from fastapi.testclient import TestClient
from backend.api import create_app
from backend.design.recipes import new_graph
from backend.simulation.service import simulate
from backend.simulation.validation import validate_divider
from backend.simulation import worker
from test_design_proposals import prepare


@pytest.mark.parametrize('mode',['transient','dc'])
def test_real_divider_spice_metrics_and_scope(tmp_path,mode):
    g,_=new_graph('0'*32,'arduino_voltage_divider');r=simulate(g,tmp_path,mode)
    assert r['engine']=='libngspice' and r['validation']['status']=='PASS'
    m=r['validation']['metrics']
    assert m['a0_voltage_v']==pytest.approx(2.5)
    assert m['resistor_current_ma']==pytest.approx(.25)
    assert m['r1_power_mw']==pytest.approx(.625)
    assert r['scope']=={'analog':'SIMULATED','firmware':'NOT_RUN','adc':'NOT_EMULATED','hardware':'NOT_TESTED'}
    assert len(r['vectors']['tp_divider'])>=100
    assert 'R1 VCC_5V TP_DIVIDER 10000.0' in r['deck']
    assert 'R2 TP_DIVIDER 0 10000.0' in r['deck']
    assert json.loads((tmp_path/'simulation.json').read_text())['graph_sha256']==r['graph_sha256']


@pytest.mark.parametrize('broken',['wire','value','voltage'])
def test_changed_model_cannot_get_pass(tmp_path,broken):
    g,_=new_graph('0'*32,'arduino_voltage_divider')
    if broken=='wire':g.links[1].to_terminal='U1.GND'
    elif broken=='value':g.components[1].value.value='1'
    else:g.parameters['supply_voltage']=12
    with pytest.raises(ValueError):simulate(g,tmp_path)
    assert not (tmp_path/'simulation.json').exists()


def test_numerically_wrong_results_fail_and_missing_vectors_error():
    v={'time':[0.,.005],'vcc_5v':[0.,5.],'tp_divider':[0.,4.9],'vsupply#branch':[0.,-.00025]}
    assert validate_divider(v,'transient',{'R1':10000,'R2':10000})['status']=='FAIL'
    v['tp_divider']=[0.,float('nan')]
    with pytest.raises(ValueError):validate_divider(v,'transient',{'R1':10000,'R2':10000})
    del v['tp_divider']
    with pytest.raises(ValueError):validate_divider(v,'transient',{'R1':10000,'R2':10000})


def test_missing_engine_never_returns_synthetic_success(monkeypatch,tmp_path):
    monkeypatch.setattr(worker.ctypes.util,'find_library',lambda _:None)
    with pytest.raises(RuntimeError,match='libngspice'):worker.run(tmp_path/'none','tran 1u 1m')


def test_proposal_simulates_without_claiming_physical_review(tmp_path):
    app=create_app(tmp_path)
    with TestClient(app) as c:
        original,url,body=prepare(c,app,tmp_path);base=url.removesuffix('/design')
        assert c.get(base+'/simulation').json()=={'simulation':None}
        response=c.post(base+'/simulate',json={'expected_revision':1,'recipe':'arduino_voltage_divider'})
        assert response.status_code==200,response.text
        r=response.json();assert r['validation']['status']=='PASS' and not r['physical_parts_verified']
        assert r['basis']=='proposed_design_only'
        assert c.get(base+'/simulation').json()['simulation']==r
        assert c.get('/api/projects/'+original['project_id']).json()['graph']==original
        # Raw decks, unsupported recipes and stale inputs cannot be sent to ngspice.
        for change,code in [({'expected_revision':999},409),({'recipe':'arduino_lcd'},422),({'deck':'.control\nshell whatever'},422)]:
            request={'expected_revision':1,'recipe':'arduino_voltage_divider',**change}
            assert c.post(base+'/simulate',json=request).status_code==code
        assert c.get(base+'/simulation?recipe=../../outside').status_code==422
        plan_path=next((tmp_path/'planner'/original['project_id']).glob('*.json'))
        data=json.loads(plan_path.read_text());data['graph_sha256']='stale';plan_path.write_text(json.dumps(data))
        assert c.get(base+'/simulation').status_code==409


def test_saved_design_simulation_available_in_output(tmp_path):
    app=create_app(tmp_path)
    with TestClient(app) as c:
        _,url,body=prepare(c,app,tmp_path)
        design=c.post(url,json=body).json();pid=design['project_id']
        r=c.post(f'/api/projects/{pid}/simulate',json={'expected_revision':1,'analysis':'dc'})
        assert r.status_code==200,r.text
        assert r.json()['integrated']['simulation']['validation']['status']=='PASS'
        assert c.post(f'/api/projects/{pid}/simulate',json={'expected_revision':1,'analysis':'ac'}).status_code==422
