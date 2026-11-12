"""Board-specific design/runtime contracts shared by analysis and export.

Capability declarations are not execution results. No network calls or user code
execution happen while validating or exporting a design.
"""
import ast
import hashlib
from copy import deepcopy
import json
import re
from pathlib import Path

PROFILE_FILE = Path(__file__).resolve().parents[2] / 'data/board-profiles.json'


def board_profiles():
    return json.loads(PROFILE_FILE.read_text())


def board_catalog():
    return {key: deepcopy(value['component']) for key, value in board_profiles()['profiles'].items()}


def profile_for(model):
    profiles = board_profiles()['profiles']
    if model not in profiles:
        raise ValueError('설계 프로파일이 없는 제어 보드입니다: ' + model)
    return profiles[model]


def validate_firmware(source, profile):
    if profile['language_mode'] == 'arduino':
        if 'void setup(' not in source or 'void loop(' not in source:
            raise ValueError('선정 보드에서 실행할 setup/loop 코드가 필요합니다.')
    else:
        try:
            tree = ast.parse(source)
        except SyntaxError as exc:
            raise ValueError('선정 보드의 Python 코드 문법을 확인하세요.') from exc
        if not any(isinstance(node, (ast.While, ast.For)) for node in ast.walk(tree)):
            raise ValueError('입력과 출력을 계속 처리하는 Python 제어 반복문이 필요합니다.')
        imports = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
        imports.update(alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names)
        if not imports.intersection(profile['gpio_modules']):
            raise ValueError('선정 보드의 GPIO 제어 모듈을 사용하는 코드가 필요합니다.')
        if profile['family'] in {'pico','esp32'}:
            def gpio_number(pin):
                return {'VP':36,'VN':39}.get(pin, int(re.sub(r'^GP','',pin)) if re.fullmatch(r'(?:GP)?\d+',pin) else -1)
            supported={gpio_number(pin) for pin in profile['component']['pins']} - {-1}
            input_only={gpio_number(pin) for pin in profile['input_only_pins']}
            def call_name(node):
                return node.func.id if isinstance(node.func,ast.Name) else node.func.attr if isinstance(node.func,ast.Attribute) else ''
            for node in ast.walk(tree):
                if not isinstance(node,ast.Call):continue
                if call_name(node)=='Pin' and node.args and isinstance(node.args[0],ast.Constant) and type(node.args[0].value) is int:
                    number=node.args[0].value
                    if number not in supported:raise ValueError('선정 보드에 없는 GPIO 번호입니다: '+str(number))
                    mode=node.args[1] if len(node.args)>1 else next((k.value for k in node.keywords if k.arg=='mode'),None)
                    if number in input_only and isinstance(mode,ast.Attribute) and mode.attr in {'OUT','OPEN_DRAIN'}:
                        raise ValueError('입력 전용 GPIO를 출력으로 사용할 수 없습니다: '+str(number))
                if call_name(node)=='PWM' and node.args:
                    pin=node.args[0]
                    if isinstance(pin,ast.Call) and call_name(pin)=='Pin' and pin.args and isinstance(pin.args[0],ast.Constant) and pin.args[0].value in input_only:
                        raise ValueError('입력 전용 GPIO에 PWM 출력을 배정할 수 없습니다.')


def runtime_contract(model):
    profile = profile_for(model)
    return {'board_kind': model, 'language': profile['language'],
            'language_mode': profile['language_mode'], 'entry_file': profile['entry_file'],
            'engine': profile['runtime']['engine'],
            'availability': profile['runtime']['availability'],
            'requirements': deepcopy(profile['runtime']['requirements']),
            'execution_status': 'not_run', 'electrical_status': 'not_run',
            'io_test_status': 'not_run', 'physical_verified': False,
            'notice': profile['runtime']['notice']}


def board_example(model):
    profile_for(model)  # Whitelist the model before constructing a filename.
    folder = PROFILE_FILE.parent / 'examples/multiboard'
    raw=(folder / (model + '-button-led.vlx')).read_text()
    project=json.loads(raw)
    project['embeddedVision'].update(design_origin='board_example',source_graph_sha256=hashlib.sha256(raw.encode()).hexdigest(),inventory_plan='board-example-'+model,
        assembly={'layout_version':'board-example-v1','note':'양 끝의 부품·핀을 확인하고 한 단계에서 연결하세요. 선정 예제이며 실물 검증 전입니다.',
                  'steps':[{'from':w['start']['componentId']+'.'+w['start']['pinName'],'to':w['end']['componentId']+'.'+w['end']['pinName'],'kind':'jumper'} for w in project['wires']]})
    return project
