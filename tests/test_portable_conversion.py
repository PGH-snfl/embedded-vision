"""Hardware is authored by rules; an untrusted model may only author firmware."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from backend.design.board_profiles import board_example
from backend.translation.portable import hardware_plan
from backend.translation.system import convert_system, source_context, button_source


def fixture(name):
    return json.loads(Path('third_party/velxio/frontend/src/__tests__/fixtures/functional-'+name+'.json').read_text())['project']


class CodeWriter:
    def __init__(self): self.calls=[]
    def infer(self,model,payload,prompt,task,assets):
        self.calls.append(deepcopy(payload))
        assert task=='system_code_conversion' and assets==[]
        assert set(payload)=={'target_board','target_profile','source_profile','source_project','target_circuit','pin_mapping','portable_model'}
        bindings=payload['portable_model']['bindings']
        # This stub tests boundaries, never claims equivalent behavior.
        target=payload['target_board'];out=next((b for b in bindings if b['role'].endswith('output')),bindings[0])
        if target=='arduino-uno':
            source=f'#include <Arduino.h>\nvoid setup(){{pinMode({out["target_number"]},OUTPUT);}}\nvoid loop(){{delay(10);}}\n'
        elif target=='raspberry-pi-4':
            source=f'from gpiozero import LED\nfrom time import sleep\nled = LED({out["target_number"]})\nwhile True:\n    sleep(0.01)\n'
        else:
            source=f'from machine import Pin\nfrom time import sleep_ms\nled = Pin({out["target_number"]}, Pin.OUT)\nwhile True:\n    sleep_ms(10)\n'
        return {'firmware':source,'used_gpio_pins':[b['target_pin'] for b in bindings],
                'acceptance_tests':['테스트 대역 · 실행 동등성 검증 아님'],'limitations':['모의 코드 작성 경로 검사'],
                'unsupported_requirements':[]},{}


@pytest.mark.parametrize('name',['dimmer','servo','watering-live','biped','lcd','buzzer'])
@pytest.mark.parametrize('target',['raspberry-pi-pico','esp32'])
def test_multiple_peripherals_convert_without_ai_touching_circuit(name,target):
    project=fixture(name);before=deepcopy(project);provider=CodeWriter()
    plan,wires,model=hardware_plan(project,source_context(project),target)
    response=convert_system(project,target,allow_ai=True,provider=provider)
    result=response['workbench']
    assert project==before and len(provider.calls)==1
    assert response['method']=='circuit_rules_ai_code'
    assert result['wires']==wires
    assert result['embeddedVision']['portable_system']['bindings']==model['bindings']
    assert result['embeddedVision']['system_conversion']['hardware_method']=='deterministic_rules'
    originals={p['id']:p for p in project['components']}
    for part in result['components']:
        if part['id'] in originals:
            original=originals[part['id']]
            assert part['metadataId']==original['metadataId']
            for key in ['x','y','rotation']: assert part.get(key)==original.get(key)
    assert response['validation']['behavior']=='not_verified'
    assert {(p['id'],p['model_id']) for p in plan['build']['parts']}=={(p['id'],p['model_id']) for p in provider.calls[0]['target_circuit']['parts']}


def test_ai_is_called_even_for_known_button_code_when_user_selects_ai():
    provider=CodeWriter();response=convert_system(board_example('arduino-uno'),'raspberry-pi-pico',allow_ai=True,provider=provider)
    assert len(provider.calls)==1 and response['provider_calls']==1
    assert response['workbench']['embeddedVision']['system_conversion']['code_method']=='ai'


def test_pi_missing_adc_is_rejected_before_any_paid_code_request():
    provider=CodeWriter()
    with pytest.raises(ValueError,match='ADC'): convert_system(fixture('dimmer'),'raspberry-pi-4',allow_ai=True,provider=provider)
    assert provider.calls==[]


def test_old_portable_metadata_is_never_trusted_after_current_code_changes():
    source=board_example('arduino-uno');source['embeddedVision']['portable_system']={'bindings':[{'target_pin':'GP99'}]}
    source['fileGroups']['group-U1'][0]['content']+='\n// current user behavior\n'
    provider=CodeWriter();response=convert_system(source,'raspberry-pi-pico',allow_ai=True,provider=provider)
    assert 'current user behavior' in provider.calls[0]['source_project']['files'][0]['content']
    assert {b['target_pin'] for b in response['workbench']['embeddedVision']['portable_system']['bindings']}=={'GP15','GP14'}


def test_existing_divider_is_reused_during_repeated_3v3_conversion():
    first=convert_system(fixture('dimmer'),'raspberry-pi-pico',allow_ai=True,provider=CodeWriter())['workbench']
    second=convert_system(first,'esp32',allow_ai=True,provider=CodeWriter())['workbench']
    dividers=lambda p:[c for c in p['components'] if c['id'].startswith(('PORT_RH','PORT_RL'))]
    assert len(dividers(first))==len(dividers(second))==2
    analog=next(b for b in second['embeddedVision']['portable_system']['bindings'] if b['role']=='analog_input')
    assert analog['input_scale']==pytest.approx(.6)


def test_non_board_wires_and_breadboard_holes_remain_unchanged():
    source=board_example('arduino-uno')
    source['components'].append({'id':'BB1','metadataId':'breadboard','x':500,'y':100,'properties':{}})
    # Split output wire through an electrically common breadboard strip.
    wire=next(w for w in source['wires'] if w['start']['componentId']=='U1' and w['start']['pinName']=='5')
    endpoint=deepcopy(wire['end']);wire['end']={'componentId':'BB1','pinName':'10t.a'}
    source['wires'].append({'id':'original-strip','start':{'componentId':'BB1','pinName':'10t.e'},'end':endpoint,'waypoints':[{'x':111,'y':222}],'color':'red'})
    result=convert_system(source,'raspberry-pi-pico',allow_ai=True,provider=CodeWriter())['workbench']
    assert next(w for w in result['wires'] if w['id']=='original-strip')==source['wires'][-1]
    assert result['wires'][0]['id']==source['wires'][0]['id']


def test_model_context_mutation_cannot_change_server_hardware_plan():
    class Mutator(CodeWriter):
        def infer(self,*args):
            response=super().infer(*args)
            args[1]['target_circuit']['parts'][0]['model_id']='esp32'
            args[1]['pin_mapping'].clear()
            return response
    result=convert_system(board_example('arduino-uno'),'raspberry-pi-pico',allow_ai=True,provider=Mutator())
    assert result['workbench']['boards'][0]['boardKind']=='raspberry-pi-pico'
    assert len(result['pin_mapping'])==3


def test_pico_pwm_outputs_use_different_slices_for_servo_and_led():
    result=convert_system(fixture('watering-live'),'raspberry-pi-pico',allow_ai=True,provider=CodeWriter())
    outputs=[b['target_number'] for b in result['workbench']['embeddedVision']['portable_system']['bindings'] if b['role'].endswith('output')]
    assert len({(p//2)%8 for p in outputs})==len(outputs)
