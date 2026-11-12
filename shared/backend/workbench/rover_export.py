"""Round-trip the reviewed rover through Velxio's editable visual components.

These custom chips are inert drawings, not Raspberry Pi/HAT emulators. GPIO40
represents the whole mated header, not one electrical pin. The only simulated
behavior is the separately labeled kinematic model.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from ..design.rover_circuit import COMPONENTS, TERMINALS, RoverCircuit
from ..design.robot_physical import robot_rover_design

_NAMES = {
    'U1': 'Raspberry Pi 4B', 'HAT1': 'Motor HAT #2348',
    'MOTOR_L': 'Left DC motor', 'MOTOR_R': 'Right DC motor',
    'BAT1': 'Motor power 5V', 'PS1': 'Pi USB-C power',
}
PHYSICAL_MODELS = {'U1':'rpi4b','HAT1':'adafruit-motor-hat-2348',
    'MOTOR_L':'adafruit-micro-dc-2941','MOTOR_R':'adafruit-micro-dc-2941',
    'BAT1':'dc-supply-generic','PS1':'usb-c-supply-generic'}

# Custom-chip's explicit pin coordinates: each is an interface connector,
# not a claim that the component's complete internal circuitry is modeled.
_PINS = {
    'U1': [('GPIO40', 160, 20), ('USB_C', 0, 42)],
    'HAT1': [('GPIO40', 0, 20), ('M1.left', 160, 20), ('M1.right', 160, 40),
             ('M2.left', 160, 60), ('M2.right', 160, 80),
             ('PWR.positive', 160, 100), ('PWR.negative', 160, 120)],
    'MOTOR_L': [('black', 0, 20), ('red', 0, 40)],
    'MOTOR_R': [('black', 0, 20), ('red', 0, 40)],
    'BAT1': [('red', 0, 20), ('black', 0, 40)],
    'PS1': [('USB_C', 160, 20)],
}


def _manifest(cid: str) -> dict:
    return {'name': _NAMES[cid] + ' (visual only)',
            'pins': [{'name': n, 'x': x, 'y': y} for n, x, y in _PINS[cid]]}


def export_rover_project(circuit: dict | RoverCircuit, provenance: dict | None = None) -> dict:
    """Build an editable VLX project from *this* saved circuit, not defaults."""
    current = RoverCircuit.model_validate(circuit)
    parts = []
    positions = {}
    groups = {}
    for part in current.components:
        manifest = json.dumps(_manifest(part.id), ensure_ascii=False, separators=(',', ':'))
        props = {'chipName': _NAMES[part.id] + ' (visual only)', 'chipJson': manifest,
                 'sourceC': '// Visual only: no device emulation.\n', 'wasmBase64': '',
                 'evRoverKind': part.kind, 'evRoverLabel': part.label,
                 'evPhysicalModel':PHYSICAL_MODELS[part.id]}
        parts.append({'id': part.id, 'metadataId': 'custom-chip', 'x': part.x, 'y': part.y,
                      'properties': props})
        groups['group-chip-' + part.id] = [
            {'name': 'chip.c', 'content': props['sourceC']},
            {'name': 'chip.json', 'content': manifest},
        ]
        positions[part.id] = {name: (part.x + 6 + x, part.y + 6 + y)
                              for name, x, y in _PINS[part.id]}

    design = robot_rover_design()
    # The Pi is represented by a visual custom chip, rather than a fabricated
    # executable board. A chip-owned group survives Velxio's VLX export, even
    # for projects with no boards. Keep chip.c/json for its visual definition.
    # An incomplete draft with U1 removed may still have another visual chip.
    code_group = 'group-chip-U1' if 'group-chip-U1' in groups else next(iter(groups), None)
    if code_group:
        groups[code_group].insert(0, {'name': 'pi_rover.py', 'content': design['code']['source']})

    colors = {w['id']: w['color'] for w in design['connections']}
    palette = {'red': '#d03434', 'black': '#343d45', 'green': '#24946a'}

    def endpoint(ref: str) -> dict:
        cid, pin = ref.split('.', 1)
        x, y = positions[cid][pin]
        return {'componentId': cid, 'pinName': pin, 'x': x, 'y': y}

    wires = [{'id': w.id, 'start': endpoint(w.source), 'end': endpoint(w.target),
              'color': palette.get(colors.get(w.id, ''), '#4e91d5'),
              'waypoints': [], 'autoRouted': True} for w in current.connections]
    source = {'basis': 'proposed_design_only', 'physical_verified': False,
              'original_wiring_reused': False, 'recipe': 'raspberry_pi_2wd_robot',
              'model_type': 'visual_interfaces_only',
              # Allows older browser drafts without pi_rover.py to add the initial
              # code without replacing a user's existing edited file.
              'robot_code': design['code'],
              'robot_code_group': code_group,
              'simulation_notice': 'Pi·모터 HAT·전원·모터는 편집 가능한 시각 전용 부품입니다. '
                 'GPIO40은 40핀 헤더 전체 결합을 뜻합니다. CPU·회로·모터의 전기 동작은 실행하지 않습니다.',
              **(provenance or {})}
    if source.get('photo_structure') is not None:
        from ..design.photo_structure import structure_components, scene_version
        parts.extend(structure_components(source['photo_structure']))
        source['photo_structure_version']=scene_version(source['photo_structure'])
    return {'format': 'velxio-project', 'version': 1,
            'exportedAt': datetime.now(timezone.utc).isoformat(),
            'name': 'Raspberry Pi · 2륜 로봇 새 설계', 'boards': [],
            'fileGroups': groups, 'components': parts, 'wires': wires,
            'activeBoardId': None, 'embeddedVision': source}


def import_rover_project(payload: dict) -> dict:
    """Recover only representable edits; refuse unknown hardware or altered pins.

    Pinless ev-structure objects are allowed as visual decoration. They must not
    be connected to electrical wires. Missing reviewed parts are retained as an
    incomplete draft, which the separate design validation rejects for motion.
    """
    if (not isinstance(payload, dict) or payload.get('format') != 'velxio-project'
            or type(payload.get('version')) is not int or payload.get('version') != 1):
        raise ValueError('Velxio 프로젝트 형식이 올바르지 않습니다.')
    if payload.get('boards') != []:
        raise ValueError('추가 보드는 이 로봇 연결 검사에서 지원하지 않습니다.')
    raw_parts, raw_wires = payload.get('components'), payload.get('wires')
    if not isinstance(raw_parts, list) or not isinstance(raw_wires, list):
        raise ValueError('부품 또는 배선 목록이 올바르지 않습니다.')
    components = []
    seen = set()
    for part in raw_parts:
        if not isinstance(part, dict): raise ValueError('부품 형식이 올바르지 않습니다.')
        cid, metadata, props = part.get('id'), part.get('metadataId'), part.get('properties')
        if not isinstance(cid, str) or cid in seen: raise ValueError('부품 ID가 없거나 중복되었습니다.')
        seen.add(cid)
        if metadata == 'ev-structure':
            if cid in COMPONENTS: raise ValueError('필수 부품을 구조물로 대체할 수 없습니다.')
            continue
        if cid not in COMPONENTS or metadata != 'custom-chip' or not isinstance(props, dict):
            raise ValueError('추가되거나 변경된 부품은 이 로봇 연결 검사에서 지원하지 않습니다.')
        if props.get('evRoverKind') != COMPONENTS[cid][0] or props.get('chipName') != _NAMES[cid] + ' (visual only)':
            raise ValueError('부품의 정체가 변경되었습니다. 검토된 부품을 사용하세요.')
        if props.get('evPhysicalModel') not in (None,PHYSICAL_MODELS[cid]):
            raise ValueError('부품의 실물 형상 모델이 다른 제품으로 변경되었습니다.')
        try: manifest = json.loads(props.get('chipJson', ''))
        except (TypeError, ValueError): raise ValueError('부품 단자 정의를 읽을 수 없습니다.') from None
        if manifest != _manifest(cid) or props.get('wasmBase64') or props.get('rotation', 0) not in (0, None):
            raise ValueError('부품 단자 또는 실행 모델이 변경되었습니다. 현재 로봇 모델로 변환할 수 없습니다.')
        components.append({'id': cid, 'kind': COMPONENTS[cid][0],
                           'label': props.get('evRoverLabel'), 'x': part.get('x'), 'y': part.get('y')})

    wires = []
    for wire in raw_wires:
        if not isinstance(wire, dict) or wire.get('bb'):
            raise ValueError('이 로봇 모델에서 지원하지 않는 연결입니다.')
        ends = []
        for key in ('start', 'end'):
            end = wire.get(key)
            if not isinstance(end, dict): raise ValueError('배선 끝점이 올바르지 않습니다.')
            cid, pin = end.get('componentId'), end.get('pinName')
            if not isinstance(cid, str) or not isinstance(pin, str) or cid not in TERMINALS or pin not in TERMINALS[cid]:
                raise ValueError('알 수 없는 부품 또는 단자에 연결된 배선입니다.')
            ends.append(cid + '.' + pin)
        wires.append({'id': wire.get('id'), 'from': ends[0], 'to': ends[1]})
    return RoverCircuit.model_validate({'version': 1, 'components': components,
                                        'connections': wires}).model_dump(by_alias=True, mode='json')
