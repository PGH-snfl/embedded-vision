import json
import pytest
from fastapi.testclient import TestClient
from backend.api import create_app
from backend.design.proposals import propose,family
from backend.design.recipes import new_graph
from backend.firmware import firmware
from backend.planner.executor import compile_graph
from backend.circuit.profiles import readiness,named_nets
from backend.tutorial.generate import tutorial
from test_parts_first import inventory,setup


def uno_resistors(count=5):
    inv=inventory();board=inv.parts[0]
    resistor=board.model_copy(update={'id':'resistors','kind':'resistor','name':'축형 저항','model_candidates':[],'quantity':count})
    unknown=board.model_copy(update={'id':'hidden','kind':'other','name':'가려진 부품','status':'UNKNOWN','model_candidates':[]})
    inv.parts=[board,resistor,unknown]
    return inv


def test_inventory_auto_composes_uno_divider_without_inventing_observations():
    inv=uno_resistors();before=inv.model_dump();result=propose(inv)
    assert result['recommended']=='arduino_voltage_divider'
    p=result['proposals'][0]
    assert p['assignments']=={'U1':'board','R1':'resistors','R2':'resistors'}
    assert not p['added_parts'] and not p['hardware_verified']
    assert next(x for x in p['remaining_parts'] if x['id']=='resistors')['quantity']==3
    assert next(x for x in p['remaining_parts'] if x['id']=='hidden')['quantity']==1
    assert inv.model_dump()==before and len(p['connections'])==4
    assert p['specifications']['R1']['value']=='10k'
    assert 'analogRead(SENSE_PIN)' in p['firmware']['source']


@pytest.mark.parametrize('name',['Raspberry Pi Pico','Arduino UNO R4','ESP32-S3','ESP32-C3','Arduino Nano','unknown board','UNO or ESP32'])
def test_unsupported_or_ambiguous_board_never_becomes_uno(name):
    inv=uno_resistors();inv.parts[0].name=name;inv.parts[0].model_candidates=[name]
    assert not propose(inv)['proposals']


def test_missing_resistor_marked_added_and_unknown_not_used():
    inv=uno_resistors(1);p=propose(inv)['proposals'][0]
    assert p['assignments']['R1']=='resistors' and p['assignments']['R2'] is None
    assert p['added_parts']==['R2']
    inv.parts[0].status='UNKNOWN';assert not propose(inv)['proposals']


def test_lcd_inventory_selects_lcd_and_not_esp32():
    inv=inventory();assert propose(inv)['recommended']=='arduino_lcd'
    inv.parts[1].name='I2C LCD'
    assert 'arduino_lcd' not in [x['recipe'] for x in propose(inv)['proposals']]


def test_divider_graph_code_schematic_and_guide_agree():
    g,_=new_graph('d'*32,'arduino_voltage_divider')
    assert not readiness(g)
    spec,_=compile_graph(g);assert len(spec['symbols'])==3
    assert any(n['name']=='TP_DIVIDER' and len(n['pins'])==3 for n in spec['nets'])
    assert firmware(g)['compiled'] is False
    guide=tutorial(g)
    assert len(guide['steps'])==4
    assert all('pull-up' not in s['why'] and 'LED' not in s['caution'] for s in guide['steps'])
    g.links[1].to_terminal='U1.GND'
    with pytest.raises(ValueError):firmware(g)


@pytest.mark.parametrize('change',['value','pin','catalog'])
def test_divider_rejects_changed_contract(change):
    g,_=new_graph('d'*32,'arduino_voltage_divider')
    if change=='value':g.components[1].value.value='1'
    if change=='pin':g.components[0].terminals[-1].pin_mapping.value='A1'
    if change=='catalog':g.components[0].catalog_id='esp32_devkitc_v4'
    with pytest.raises(ValueError):firmware(g)


def prepare(c,app,path):
    original,url,body=setup(c,app,path)
    plan_path=next((path/'planner'/original['project_id']).glob('*.json'))
    from test_parts_first import seal_fixture_inventory
    plan=json.loads(plan_path.read_text());plan['inventory']=uno_resistors().model_dump(mode='json');plan.pop('function_hypotheses',None);plan_path.write_text(json.dumps(seal_fixture_inventory(plan)))
    body.update(recipe='arduino_voltage_divider',assignments={'U1':'board','R1':'resistors','R2':'resistors'},accept_added_parts=False)
    target=c.post(url.removesuffix('/design')+'/function',json={'expected_revision':original['revision'],'kind':'voltage_readout','description':'두 저항 사이 전압을 시리얼로 출력한다.'}).json()
    body.update(function_version=target['function_version'],function_confirmed=True)
    return original,url,body


def test_proposal_endpoint_read_only_then_reviewed_design(tmp_path):
    app=create_app(tmp_path)
    with TestClient(app) as c:
        original,url,body=prepare(c,app,tmp_path)
        r=c.get(url.removesuffix('/design')+'/proposals');assert r.status_code==200
        assert r.json()['recommended']=='arduino_voltage_divider'
        assert c.get('/api/projects/'+original['project_id']).json()['graph']==original
        blocked={**body,'parts_verified':False}
        assert c.post(url,json=blocked).status_code==422
        result=c.post(url,json=body);assert result.status_code==201,result.text
        pid=result.json()['project_id']
        assert 'analogRead' in c.get(f'/api/projects/{pid}/firmware').json()['source']
        assert c.post(f'/api/projects/{pid}/build',json={'expected_revision':1}).status_code==422
        assert c.get('/api/projects/'+original['project_id']).json()['graph']==original


def test_incompatible_board_cannot_bypass_ui(tmp_path):
    app=create_app(tmp_path)
    with TestClient(app) as c:
        _,url,body=prepare(c,app,tmp_path)
        body.update(recipe='esp32_led_button',assignments={'U1':'board','R1':'resistors','R2':'resistors','D1':None,'SW1':None},accept_added_parts=True)
        r=c.post(url,json=body);assert r.status_code==422 and '호환' in r.text
