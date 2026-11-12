"""Identical intended behavior, different board pins/code/runtime, no paid calls."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from backend.design.board_profiles import board_profiles, runtime_contract
from backend.design.functional_build import build_workbench, validate_build
from backend.design.runtime_repairs import complete_missing_grounds
from backend.design.inventory import inventory_plan
from backend.design.recipes import new_graph
from backend.design.implementation import realize
from backend.workflow import workflow_definition, workflow_stamp
from backend.planner.provider import ResponsesProvider
from test_functional_build import build_inputs
from test_enclosure_analysis import study

SOURCES = {
    'arduino-uno': ('5', '2', 'GND', '#include <Arduino.h>\nvoid setup(){pinMode(5,OUTPUT);pinMode(2,INPUT_PULLUP);}\nvoid loop(){digitalWrite(5,!digitalRead(2));delay(10);}\n'),
    'raspberry-pi-pico': ('GP15', 'GP14', 'GND.1', 'from machine import Pin\nfrom time import sleep_ms\nled = Pin(15, Pin.OUT)\nbutton = Pin(14, Pin.IN, Pin.PULL_UP)\nwhile True:\n    led.value(not button.value())\n    sleep_ms(10)\n'),
    'esp32': ('18', '19', 'GND', 'from machine import Pin\nfrom time import sleep_ms\nled = Pin(18, Pin.OUT)\nbutton = Pin(19, Pin.IN, Pin.PULL_UP)\nwhile True:\n    led.value(not button.value())\n    sleep_ms(10)\n'),
    'raspberry-pi-4': ('GPIO17', 'GPIO27', 'GND', 'from gpiozero import LED, Button\nfrom time import sleep\nled = LED(17)\nbutton = Button(27, pull_up=True)\nwhile True:\n    led.value = button.is_pressed\n    sleep(0.01)\n'),
}


def selected_build(model):
    observed, raw, hypotheses = build_inputs()
    b = raw['functional_build']
    b['title'] = model + ' · 버튼 LED 제어'
    b['behavior'] = '버튼을 누르는 동안 LED를 켜고 놓으면 끕니다.'
    b['parts'][0]['model_id'] = model
    b['parts'][1]['model_id'] = 'pushbutton-6mm'
    b['parts'][1]['purpose'] = '사용자 버튼 입력'
    led, button, ground, code = SOURCES[model]
    b['firmware'] = code
    b['connections'] = [dict(source=a,target=z,purpose='버튼 입력과 LED 출력') for a,z in [
        ('U1.'+button,'S1.1.l'),('S1.2.l','U1.'+ground),
        ('U1.'+led,'R1.1'),('R1.2','D1.A'),('D1.C','U1.'+ground)]]
    b['design_choices'] = ['원본 복원이 아닌 기능 동등 설계', model+'의 핀·전압·언어를 함께 선정']
    b['acceptance_tests'] = ['버튼 해제 시 LED 꺼짐', '버튼 누르면 LED 켜짐']
    return observed, raw, hypotheses


@pytest.mark.parametrize('model', SOURCES)
def test_same_workflow_generates_board_specific_executable_design(model):
    observed, raw, hs = selected_build(model)
    before = deepcopy(raw)
    build = validate_build(raw['functional_build'],observed,hs,study())
    project = build_workbench(build,{},study())
    profile = board_profiles()['profiles'][model]
    assert raw == before
    board = project['boards'][0]
    assert board['boardKind'] == model
    assert board['languageMode'] == profile['native_language_mode']
    assert project['fileGroups']['group-U1'] == [{'name':profile['entry_file'],'content':SOURCES[model][3]}]
    runtime = project['embeddedVision']['implementation_design']['runtime']
    assert runtime == board['properties']['evBoardRuntime']
    assert runtime['execution_status'] == runtime['io_test_status'] == 'not_run'
    assert project['embeddedVision']['workflow'] == workflow_stamp()
    assert board['properties']['evAssembly']['host']['id'] == 'build-case-housing'
    assert len(project['wires']) == 5
    assert not project['embeddedVision']['physical_verified']


@pytest.mark.parametrize('model', SOURCES)
def test_inventory_precedes_board_profiles_and_keeps_its_selected_board(monkeypatch,model):
    observed, raw, _ = selected_build(model)
    observed.suggested_function=''
    calls = []
    def infer(self, chosen, context, prompt, task, assets, prior=None):
        calls.append(task)
        if task=='component_inventory':
            assert 'board_profiles' not in context and 'implementation_catalog' not in context
            assert 'board_workflow' not in context['workflow']
            return observed,{'model':'TEST','usage':None}
        assert task=='system_reasoning'
        assert context['board_profiles'] == board_profiles()
        assert context['observed_inventory']==observed.model_dump(mode='json')
        assert model in context['implementation_catalog']
        assert 'arduino-uno 한 개를 반드시' not in prompt
        return deepcopy(raw),{'model':'TEST','usage':None}
    monkeypatch.setattr(ResponsesProvider,'infer',infer)
    plan = inventory_plan(new_graph('a'*32,'arduino_lcd')[0],[('image',Path('unused'))],ResponsesProvider(component_inspection=False))
    assert calls == ['component_inventory','system_reasoning']
    assert plan['functional_build']['parts'][0]['model_id'] == model
    assert plan['component_datasheet']['functional_build']['parts'][0]['model_id'] == model


@pytest.mark.parametrize('model', ['raspberry-pi-pico','esp32','raspberry-pi-4'])
def test_arduino_code_cannot_be_mislabeled_as_other_board_code(model):
    inv, raw, hs = selected_build(model)
    raw['functional_build']['firmware'] = SOURCES['arduino-uno'][3]
    with pytest.raises(ValueError): validate_build(raw['functional_build'],inv,hs,study())


def test_pi_has_no_invented_adc_and_pico_uses_its_real_ground_label():
    inv, raw, hs = selected_build('raspberry-pi-4')
    raw['functional_build']['connections'][0]['source'] = 'U1.A0'
    with pytest.raises(ValueError): validate_build(raw['functional_build'],inv,hs,study())
    raw={'parts':[{'id':'U1','model_id':'raspberry-pi-pico'},{'id':'P','model_id':'potentiometer'}],'connections':[]}
    fixed, repairs = complete_missing_grounds(raw)
    assert fixed['connections'][0]['target'] == 'U1.GND.1'
    assert repairs and raw['connections'] == []


@pytest.mark.parametrize(('model','code'),[
    ('raspberry-pi-pico','from machine import Pin\nled=Pin(99,Pin.OUT)\nwhile True: led.on()\n'),
    ('esp32','from machine import Pin\nled=Pin(34,Pin.OUT)\nwhile True: led.on()\n'),
    ('esp32','from machine import Pin, PWM\nled=PWM(Pin(35))\nwhile True: led.duty(512)\n'),
])
def test_board_specific_gpio_constraints_reject_invalid_generated_code(model,code):
    inv,raw,hs=selected_build(model);raw['functional_build']['firmware']=code
    with pytest.raises(ValueError):validate_build(raw['functional_build'],inv,hs,study())


def test_contract_separates_local_engines_from_services_and_actual_results():
    d=workflow_definition()
    assert d['version'] >= 3 and d['board_workflow'] == board_profiles()
    assert runtime_contract('raspberry-pi-pico')['availability'] == 'local'
    for model in ['esp32','raspberry-pi-4']:
        runtime=runtime_contract(model)
        assert runtime['availability'] == 'requires_service'
        assert runtime['execution_status'] == runtime['electrical_status'] == runtime['io_test_status'] == 'not_run'


def test_invalid_non_arduino_design_cannot_silently_fall_back_to_uno(monkeypatch):
    observed, raw, _ = selected_build('raspberry-pi-pico')
    raw['functional_build']['connections'][0]['source']='U1.DOES_NOT_EXIST'
    def infer(self,model,context,prompt,task,assets,prior=None):
        return (observed if task=='component_inventory' else deepcopy(raw)),{'model':'TEST','usage':None}
    monkeypatch.setattr(ResponsesProvider,'infer',infer)
    plan=inventory_plan(new_graph('a'*32,'arduino_lcd')[0],[('image',Path('unused'))],ResponsesProvider(component_inspection=False))
    assert plan['functional_build'] is None
    assert plan['board_selection']['fallback_allowed'] is False
    assert realize(plan,plan['function_hypotheses'][0],{}) is None


def test_profile_and_example_routes_include_board_specific_code(tmp_path):
    from fastapi.testclient import TestClient
    from backend.application import create_app
    with TestClient(create_app(tmp_path)) as client:
        assert client.get('/api/board-profiles').json() == board_profiles()
        for model in SOURCES:
            response=client.get('/api/board-profiles/'+model+'/example')
            assert response.status_code==200
            project=response.json()
            assert project['boards'][0]['boardKind']==model
            assert project['fileGroups']['group-U1'][0]['content']==SOURCES[model][3]
        assert client.get('/api/board-profiles/unknown/example').status_code==404


def test_saas_preserves_workspace_and_serves_local_pico_firmware(tmp_path):
    from fastapi.testclient import TestClient
    from backend.saas.app import create_saas_app
    from backend.saas.settings import Settings
    settings=Settings(tmp_path/'saas',origin='http://127.0.0.1:8770',development=True,auth_enabled=False)
    with TestClient(create_saas_app(settings),base_url=settings.origin) as client:
        wid=client.get('/api/saas/me').json()['default_workspace']
        assert client.get(f'/api/w/{wid}/board-profiles').json()==board_profiles()
        assert client.get(f'/api/w/{wid}/board-profiles/raspberry-pi-pico/example').json()['boards'][0]['boardKind']=='raspberry-pi-pico'
        page=client.get(f'/w/{wid}/board-workflow.html')
        assert page.status_code==200 and 'src="/board-workflow.js' in page.text
        assert client.get(f"/w/{'a'*32}/board-workflow.html").status_code==404
        firmware=client.get('/firmware/micropython-rp2040.uf2')
        assert firmware.status_code==200 and firmware.content[:4]==bytes.fromhex('5546320a')
