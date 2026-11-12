"""Bounded new-design corrections. Existing wired pins and firmware are preserved."""
from copy import deepcopy
from .board_profiles import board_profiles

GROUND_PINS={'servo':'GND','hc-sr04':'GND','potentiometer':'GND',
             'soil-moisture-sen0193':'GND','photoresistor-sensor':'GND','lcd1602':'VSS','buzzer':'1'}

def complete_missing_grounds(raw):
    if not isinstance(raw,dict):return raw,[]
    project=deepcopy(raw);parts=project.get('parts',[]);wires=project.get('connections',[])
    if not isinstance(parts,list) or not isinstance(wires,list):return raw,[]
    if any(not isinstance(p,dict) for p in [*parts,*wires]):return raw,[]
    profiles=board_profiles()['profiles']
    boards=[p for p in parts if p.get('model_id') in profiles and p.get('id')=='U1']
    if len(boards)!=1:return raw,[]
    board_ground='U1.'+profiles[boards[0]['model_id']]['ground_pin']
    connected={w.get(k) for w in wires for k in ('source','target')};repairs=[]
    for part in parts:
        if not isinstance(part.get('id'),str) or not isinstance(part.get('model_id'),str):continue
        ground=GROUND_PINS.get(part.get('model_id'))
        if not ground:continue
        pin=part.get('id','')+'.'+ground
        if pin in connected:continue
        # The prescribed module ground has no connection at all. Do not alter
        # a wired ground, choose a GPIO, or modify the user's control program.
        wires.append({'source':pin,'target':board_ground,'purpose':'새 실행 설계의 누락된 공통 접지 보완'})
        connected.add(pin);repairs.append({'kind':'missing_ground','source':pin,'target':board_ground,
            'basis':'selected_module_pinout','message':pin+'의 비어 있는 접지를 '+board_ground+'에 연결했습니다.'})
    return project,repairs
