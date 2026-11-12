import json
import pytest
from fastapi.testclient import TestClient
from backend.api import create_app
from backend.design.recipes import new_graph, LED_RECIPES
from backend.design.proposals import propose
from backend.circuit.profiles import readiness
from backend.firmware import firmware
from backend.workbench.export import export_project
from backend.workbench.server import compile_edit, CompileRequest
from test_parts_first import setup,seal_fixture_inventory
from test_function_hypotheses import led_inventory


def unknown_board_inventory():
    inv=led_inventory()
    inv.parts[0]=inv.parts[0].model_copy(update={'name':'DFRobot 제어 보드','model_candidates':['세부 모델 UNKNOWN'],'markings':['DFRobot']})
    return inv


@pytest.mark.parametrize('kind',['led_output','led_blink','led_brightness'])
def test_goal_to_simulator_and_reviewed_design(tmp_path,kind):
    app=create_app(tmp_path)
    with TestClient(app) as c:
        original,url,body=setup(c,app,tmp_path)
        path=next((tmp_path/'planner'/original['project_id']).glob('*.json'))
        plan=json.loads(path.read_text());plan['inventory']=unknown_board_inventory().model_dump(mode='json');plan.pop('function_hypotheses',None)
        seal_fixture_inventory(plan)
        path.write_text(json.dumps(plan))
        endpoint=url.removesuffix('/design')
        response=c.post(endpoint+'/function-candidate',json={'expected_revision':original['revision'],'candidate_id':kind})
        assert response.status_code==200,response.text
        selected=response.json();proposal=selected['proposals'][0]
        assert selected['function']['kind']==kind and selected['function']['status']=='USER_DEFINED'
        assert proposal['recipe']=='arduino_'+kind and proposal['simulator_supported']
        assert proposal['assignments']['U1'] is None and 'U1' in proposal['added_parts']
        assert '새 설계 사양' in proposal['simulation_notice']
        params={'recipe':proposal['recipe'],'function_version':selected['function_version']}
        payload=c.get(endpoint+'/workbench',params=params)
        assert payload.status_code==200,payload.text
        data=payload.json()
        assert not data['embeddedVision']['physical_verified']
        assert data['embeddedVision']['function_version']==params['function_version']
        assert data['wires'][0]['start']['pinName']=='5'
        assert data['wires'][-1]['start']['pinName']=='C'
        assert [p['metadataId'] for p in data['components']]==['breadboard','resistor','led']
        assert data['components'][1]['properties']['value']=='220'
        assert c.get('/api/projects/'+original['project_id']).json()['graph']==original
        assert c.get(endpoint+'/workbench',params={**params,'function_version':'stale'}).status_code==409
        assert c.get(endpoint+'/workbench?recipe=arduino_voltage_divider').status_code==422
        body.update(recipe=proposal['recipe'],assignments=proposal['assignments'],function_version=selected['function_version'],function_confirmed=True,accept_added_parts=True,parts_verified=False)
        assert c.post(url,json=body).status_code==422  # Simulator preview doesn't bypass hardware review.
        body['parts_verified']=True
        made=c.post(url,json=body)
        assert made.status_code==201,made.text
        assert made.json()['firmware']['source']==data['fileGroups']['group-U1'][0]['content']
        graph=c.get('/api/projects/'+made.json()['project_id']).json()['graph']
        assert graph['profile']==proposal['recipe']


@pytest.mark.parametrize('recipe',sorted(LED_RECIPES))
def test_generated_led_code_compiles_and_contract_rejects_bad_wiring(recipe):
    graph,_=new_graph('a'*32,recipe)
    assert not readiness(graph)
    code=firmware(graph)['source']
    result=compile_edit(CompileRequest(files=[{'name':'sketch.ino','content':code}]))
    assert result['success'] and result['hex_content'].startswith(':')
    graph.links[0].to_terminal='U1.GND'
    assert readiness(graph)
    with pytest.raises(ValueError):export_project(graph)


def test_led_recipe_requires_observed_led():
    inv=unknown_board_inventory();inv.parts=[p for p in inv.parts if p.kind!='led']
    assert not any(p['recipe'] in LED_RECIPES for p in propose(inv)['proposals'])


@pytest.fixture(scope='module')
def gpio_probe(tmp_path_factory):
    from pathlib import Path
    from backend.emulator.toolchain import ROOT,command
    folder=tmp_path_factory.mktemp('gpio-probe');binary=folder/'probe'
    lib=ROOT/'lib/x86_64-linux-gnu'
    command(['cc','-O2','-Wall','-Wextra','-I'+str(ROOT/'include/simavr'),Path(__file__).parent/'fixtures/led_probe.c','-L'+str(lib),'-Wl,-rpath,'+str(lib),'-lsimavr','-o',binary])
    return binary


@pytest.mark.parametrize('recipe',sorted(LED_RECIPES))
def test_real_mcu_d5_waveform(recipe,tmp_path,gpio_probe):
    from backend.emulator.toolchain import compile_firmware,command
    graph,_=new_graph('a'*32,recipe)
    build=compile_firmware(firmware(graph)['source'],tmp_path)
    result=json.loads(command([gpio_probe,build['elf']]).splitlines()[-1])
    assert result['cycles']>=40_000_000
    changes=result['changes']
    if recipe.endswith('output'):
        assert result['level']==1 and result['edges']==2
    elif recipe.endswith('blink'):
        assert [state for _,state in changes]==[0,1,0,1,0,1]
        periods=[changes[i][0]-changes[i-1][0] for i in range(2,len(changes))]
        assert all(499<=period<=502 for period in periods),periods
    else:
        assert result['edges']>1000
        # analogWrite endpoints 0/255 use digitalWrite, intermediate values use OCR0B.
        assert result['pwm_values']==list(range(0,255,5))
