"""Deterministic peripheral-role mapping. No model is allowed to edit this circuit."""
from copy import deepcopy
import re

from ..design.board_profiles import profile_for
from ..design.functional_build import implementation_catalog

# GPIO choices avoid serial, boot-strapping and input-only output pins.
OUTPUTS = {
    'arduino-uno': ['5', '3', '6', '9', '10', '11'],
    'raspberry-pi-pico': ['GP15', 'GP13', 'GP11', 'GP9', 'GP7', 'GP5', 'GP3', 'GP1'],
    'esp32': ['18', '19', '23', '25', '26', '27', '32', '33'],
    'raspberry-pi-4': ['GPIO17', 'GPIO27', 'GPIO18', 'GPIO22', 'GPIO23', 'GPIO24', 'GPIO12', 'GPIO13'],
}
INPUTS = {
    'arduino-uno': ['2', '4', '7', '8', '12', '13'],
    'raspberry-pi-pico': ['GP14', 'GP16', 'GP17', 'GP18', 'GP19', 'GP20', 'GP21', 'GP22'],
    'esp32': ['19', '23', '25', '26', '27', '32', '33'],
    'raspberry-pi-4': ['GPIO27', 'GPIO22', 'GPIO23', 'GPIO24', 'GPIO25', 'GPIO16', 'GPIO20', 'GPIO21'],
}
SIGNALS = {
    'potentiometer': {'SIG': 'analog_input'},
    'soil-moisture-sen0193': {'SIG': 'analog_input'},
    'photoresistor-sensor': {'AO': 'analog_input', 'DO': 'digital_input'},
    'pushbutton-6mm': {p: 'digital_input' for p in ['1.l', '1.r', '2.l', '2.r']},
    'servo': {'PWM': 'servo_output'},
    'hc-sr04': {'TRIG': 'digital_output', 'ECHO': 'digital_input'},
    'led': {'A': 'pwm_output', 'C': 'pwm_output'},
    'buzzer': {'2': 'pwm_output'},
    'mosfet-irlz44n': {'G': 'pwm_output'},
    'lcd1602': {p: 'digital_output' for p in ['RS', 'E', *['D'+str(i) for i in range(8)]]},
}


def hardware_plan(project, context, target):
    # Imported lazily to avoid an import cycle with the endpoint module.
    from .system import _nets, _pin_number
    board = context['board']; bid = board['id']; source = board['boardKind']
    profile = profile_for(target); root = _nets(project)
    parts = context['parts']; catalog = implementation_catalog()
    def resistance(part):
        raw=str(part.get('properties', {}).get('value', '1000')).strip().lower()
        match=re.fullmatch(r'(\d+(?:\.\d+)?)\s*([km]?)\s*(?:ohms?|ω)?',raw)
        if not match: raise ValueError('분압 저항값을 읽을 수 없습니다: '+part['id'])
        return float(match[1])*{'':1,'k':1000,'m':1000000}[match[2]]
    ground = root((bid, 'GND'))
    voltages = {'5V': 5.0, 'VBUS': 5.0, '3V3': 3.3, '3.3V': 3.3}
    if source=='esp32':voltages['VIN']=5.0
    power_roots = {}
    for pin,voltage in voltages.items():
        if pin not in context['profile']['component']['pins']:continue
        net=root((bid,pin))
        if net in power_roots and power_roots[net]!=voltage:raise ValueError('서로 다른 전원 전압이 직접 연결돼 있습니다.')
        power_roots[net]=voltage
    for part in parts:
        if part['metadataId']!='dc-power-supply':continue
        net=root((part['id'],'+'));voltage=float(part.get('properties',{}).get('voltage',5))
        if net in power_roots and abs(power_roots[net]-voltage)>.01:raise ValueError('외부 전원과 보드 전압이 충돌합니다.')
        power_roots[net]=voltage
    if ground in power_roots:
        raise ValueError('전원과 접지가 단락돼 있습니다. 원본 배선을 먼저 수정하세요.')
    signal_pins = [p for p in context['board_pins'] if _pin_number(source, p) is not None]
    if any(root((bid, p)) == ground or root((bid, p)) in power_roots for p in signal_pins):
        raise ValueError('GPIO와 전원·접지가 직접 단락돼 있습니다. 원본 배선을 먼저 수정하세요.')
    if len({root((bid, p)) for p in signal_pins}) != len(signal_pins):
        raise ValueError('여러 GPIO가 같은 선에 연결돼 있습니다. 공유 버스 전환 규칙이 필요합니다.')

    # Follow series resistors to find the load, never cross a power/ground rail.
    def reachable(net):
        seen = {net}
        changed = True
        while changed:
            changed = False
            for part in parts:
                if part['metadataId'] != 'resistor': continue
                a, b = [root((part['id'], p)) for p in ['1', '2']]
                if a in seen or b in seen:
                    for end in [a, b]:
                        if end not in seen and end != ground and end not in power_roots:
                            seen.add(end); changed = True
        return seen

    bindings = []; used = set(); mapping = []
    for pin in sorted(signal_pins):
        nets = reachable(root((bid, pin)))
        matches = [(p, ep, role) for p in parts for ep, role in SIGNALS.get(p['metadataId'], {}).items()
                   if root((p['id'], ep)) in nets]
        roles = {r for _, _, r in matches}
        if not roles or len(roles) != 1:
            raise ValueError('핀 '+pin+'의 입출력 역할을 결정할 규칙이 없습니다. 부품 연결을 확인하세요.')
        role = next(iter(roles))
        choices = profile['analog_pins'] if role == 'analog_input' else INPUTS[target] if role == 'digital_input' else OUTPUTS[target]
        available = [p for p in choices if p not in used]
        if not available:
            raise ValueError(profile['component']['name']+'에 필요한 '+role+' 핀이 없습니다. 아날로그 입력에는 지원 ADC 부품이 필요합니다.')
        dest = available[0]; used.add(dest)
        mapping.append({'source': pin, 'target': dest, 'reason': role+' 역할 유지'})
        # High-voltage inputs require an explicitly modelled divider below.
        input_voltage = 0.0
        existing_scale = 1.0
        if role.endswith('input'):
            for part, endpoint, _ in matches:
                if part['metadataId'] == 'pushbutton-6mm': continue
                supply = root((part['id'], 'VCC'))
                input_voltage = max(input_voltage, power_roots.get(supply, context['profile']['logic_voltage']))
                sensor_net=root((part['id'],endpoint));board_net=root((bid,pin))
                if sensor_net != board_net:
                    high=[];low=[]
                    for resistor in [p for p in parts if p['metadataId']=='resistor']:
                        ends={root((resistor['id'],ep)) for ep in ['1','2']}
                        if ends=={sensor_net,board_net}:high.append(resistor)
                        if ends=={board_net,ground}:low.append(resistor)
                    if len(high)!=1 or len(low)!=1:raise ValueError('입력 '+pin+'의 기존 저항망 보정 규칙이 필요합니다.')
                    rh,rl=resistance(high[0]),resistance(low[0])
                    if rh<=0 or rl<=0:raise ValueError('분압 저항값은 양수여야 합니다.')
                    existing_scale=rl/(rh+rl)
            # A button can have an external 5V pull-up resistor.
            for resistor in [p for p in parts if p['metadataId']=='resistor']:
                ends=[root((resistor['id'],ep)) for ep in ['1','2']]
                if root((bid,pin)) in ends:
                    input_voltage=max(input_voltage,*[power_roots.get(ep,0) for ep in ends])
            input_voltage*=existing_scale
        bindings.append({'source_pin': pin, 'target_pin': dest, 'role': role,
                         'source_number': _pin_number(source, pin), 'target_number': _pin_number(target, dest),
                         'peripherals': sorted({context['canonical'][p['id']] for p, _, _ in matches}),
                         'input_voltage': input_voltage, 'source_input_scale': existing_scale, 'input_scale': existing_scale})

    for pin in context['board_pins']:
        if pin in signal_pins: continue
        if re.fullmatch(r'GND(?:[._]?\d+)?', pin): dest = profile['ground_pin']
        elif pin in voltages:
            if voltages[pin] == 3.3: dest = '3.3V' if target == 'arduino-uno' else '3V3'
            else: dest = 'VBUS' if target == 'raspberry-pi-pico' else 'VIN' if target == 'esp32' else '5V'
        else: raise ValueError('전환 규칙이 없는 보드 특수 핀입니다: '+pin)
        mapping.append({'source': pin, 'target': dest, 'reason': '동일 전원 전압·접지 유지'})
    pinmap = {p['source']: p['target'] for p in mapping}
    wires = deepcopy(project['wires']); selected = []
    for part in [board, *parts]:
        model = target if part is board else part['metadataId']
        keys = set(catalog[model]['properties']) | set(catalog[model]['defaults'])
        selected.append({'id': context['canonical'][part['id']], 'model_id': model,
                         'purpose': '현재 입출력 기능 유지', 'selection_reason': '기존 부품과 값을 보존하는 보드 전환',
                         'observed_part_ids': [], 'module_refs': [], 'enclosure_id': None, 'location': 'internal',
                         'parameters': [{'name': k, 'value': v} for k, v in part.get('properties', {}).items() if k in keys]})
    for wire in wires:
        for end in [wire['start'], wire['end']]:
            if end['componentId'] == bid:
                end['pinName'] = pinmap[end['pinName']]
                wire['waypoints'] = []; wire['autoRouted'] = True
    limitations = []; added = []; occupied = {p['id'] for p in project['components']} | {w['id'] for w in project['wires']} | set(context['canonical'].values()) | {bid}
    def unique(prefix):
        name = prefix
        while name in occupied: name += 'X'
        occupied.add(name); return name
    def edge(a, b):
        def ep(s):
            cid, pin = s.split('.', 1); return {'componentId': cid, 'pinName': pin, 'x': 0, 'y': 0}
        wires.append({'id': unique('PORT_W'), 'start': ep(a), 'end': ep(b), 'waypoints': [], 'autoRouted': True, 'color': '#267dba'})
    for binding in bindings:
        if binding['input_voltage'] <= profile['logic_voltage']: continue
        if binding['input_voltage']>5.01:raise ValueError('5V를 넘는 센서 입력에는 별도 전압 보호 규칙이 필요합니다.')
        # 2.2k / 3.3k: 5V becomes 3.0V. Include scaling in the AI code contract.
        high, low = unique('PORT_RH'), unique('PORT_RL'); dest = binding['target_pin']
        for wire in wires:
            for end in [wire['start'], wire['end']]:
                if end['componentId'] == bid and end['pinName'] == dest:
                    end.update(componentId=high, pinName='1')
        edge(high+'.2', low+'.1'); edge(high+'.2', bid+'.'+dest); edge(low+'.2', bid+'.'+profile['ground_pin'])
        for cid, value in [(high, '2200'), (low, '3300')]:
            selected.append({'id': cid, 'model_id': 'resistor', 'purpose': '5V 입력 분압 보호',
                             'selection_reason': '대상 3.3V 입력의 전압 범위 유지', 'observed_part_ids': [], 'module_refs': [],
                             'enclosure_id': None, 'location': 'internal', 'parameters': [{'name': 'value', 'value': value}]})
            added.append({'id': cid, 'metadataId': 'resistor'})
        binding['input_scale'] *= 0.6
        limitations.append(binding['source_pin']+' 입력에 2.2kΩ·3.3kΩ 분압을 추가했습니다. 코드에서 ADC 범위를 보정해야 합니다.')
    if len(selected) > 16: raise ValueError('전압 보호 부품까지 포함하면 현재 전환 한도 16개를 넘습니다.')
    if target == 'esp32' and any(p['target'] == 'VIN' for p in mapping):
        # VIN is a supply input, not a guaranteed regulated 5V output.
        supply = unique('PORT_5V')
        selected.append({'id': supply, 'model_id': 'dc-power-supply', 'purpose': '기존 5V 주변장치 전원',
                         'selection_reason': 'ESP32 VIN을 5V 출력으로 가정하지 않음', 'observed_part_ids': [], 'module_refs': [],
                         'enclosure_id': None, 'location': 'external', 'parameters': [{'name': 'voltage', 'value': 5}]})
        added.append({'id': supply, 'metadataId': 'dc-power-supply'})
        edge(supply+'.+', bid+'.VIN'); edge(supply+'.-', bid+'.'+profile['ground_pin'])
        limitations.append('ESP32와 기존 5V 주변장치를 위한 공통 접지의 외부 5V 전원을 추가했습니다.')
    if len(selected) > 16: raise ValueError('전원 보완 부품까지 포함하면 현재 전환 한도 16개를 넘습니다.')

    # Flatten breadboard internal conductors only for the logical design. Native
    # editor wires (with every breadboard hole and wire ID) are retained above.
    virtual = deepcopy(project); virtual['boards'][0]['boardKind'] = target
    virtual['components'].extend(added); virtual['wires'] = wires
    target_root = _nets(virtual); groups = {}
    canonical = {**context['canonical'], **{p['id']: p['id'] for p in added}}
    for wire in wires:
        for end in [wire['start'], wire['end']]:
            cid, pin = end['componentId'], end['pinName']
            if cid in canonical:
                group = groups.setdefault(target_root((cid, pin)), set())
                group.add(canonical[cid]+'.'+pin)
    connections = []
    for ends in groups.values():
        ends = sorted(ends)
        connections.extend({'source': ends[0], 'target': ep, 'purpose': '기존 전기 연결과 보드별 전압 규칙 유지'} for ep in ends[1:])
    touched={ep.split('.',1)[0] for wire in connections for ep in [wire['source'],wire['target']]}
    if touched!={p['id'] for p in selected}:raise ValueError('배선되지 않은 회로 부품이 있습니다. 코드 작성 전에 연결을 확인하세요.')
    if len(connections)>80 or len(wires)>256:raise ValueError('회로 전환의 배선 한도를 초과했습니다.')
    build = {'title': profile['component']['name']+' · 동일 기능 전환', 'hypothesis_id': 'conversion',
             'behavior': context['behavior'], 'parts': selected, 'connections': connections, 'structures': [],
             'firmware': '', 'design_choices': ['규칙으로 부품·연결을 확정한 후 AI가 대상 코드만 작성'],
             'acceptance_tests': ['원본과 동일한 입력에서 출력·조건·주기를 비교'], 'not_implemented': []}
    return {'build': build, 'pin_mapping': mapping, 'changes': ['제어 보드·GPIO 역할 전환', '기존 부품·배선·장착 위치 보존', '대상 코드만 AI 작성'],
            'limitations': limitations}, wires, {'version': 1, 'hardware_method': 'deterministic_rules', 'bindings': bindings,
                                               'source_logic_voltage': context['profile']['logic_voltage'], 'target_logic_voltage': profile['logic_voltage']}
