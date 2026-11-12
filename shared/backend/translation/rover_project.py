"""Create a separate, bounded board-and-wiring conversion of the Pi rover.

Only the reviewed Pi/HAT wiring can be converted; no arbitrary circuit is
silently discarded. The new Motor Shield is a drawing, not an I2C emulator.
"""
from copy import deepcopy
from datetime import datetime, timezone
import json
import uuid

from ..design.rover_circuit import validate_rover_circuit
from ..workbench.rover_export import import_rover_project
from .rover import UnsupportedTranslation

SHIELD_REFERENCE = 'https://learn.adafruit.com/adafruit-motor-shield-v2-for-arduino'
POWER_REFERENCE = 'https://learn.adafruit.com/adafruit-motor-shield-v2-for-arduino/powering-motors'


def _chip(cid, name, pins, x, y):
    manifest = json.dumps({'name':name+' (visual only)', 'pins':[{'name':n,'x':px,'y':py} for n,px,py in pins]}, ensure_ascii=False, separators=(',',':'))
    props = {'chipName':name+' (visual only)', 'chipJson':manifest,
             'sourceC':'// Visual only: no device emulation.\n', 'wasmBase64':''}
    return ({'id':cid,'metadataId':'custom-chip','x':x,'y':y,'properties':props},
            [{'name':'chip.c','content':props['sourceC']},{'name':'chip.json','content':manifest}])


def translate_rover_project(project: dict, source: str, target: str, result: dict) -> dict:
    try:
        circuit = import_rover_project(project)
        validation = validate_rover_circuit(circuit)
    except (ValueError, TypeError, KeyError, RecursionError) as exc:
        raise UnsupportedTranslation('현재 회로에 지원하지 않는 부품이나 배선이 있습니다. 원본 회로를 확인하세요.') from exc
    if not validation['allowed']:
        raise UnsupportedTranslation('현재 회로가 검토된 Raspberry Pi 로봇 배선과 다릅니다. 연결을 먼저 확인하세요.')
    groups = project.get('fileGroups')
    if not isinstance(groups, dict) or not any(
        isinstance(f,dict) and f.get('name')=='pi_rover.py' and f.get('content')==source
        for group in groups.values() if isinstance(group,list) for f in group
    ):
        raise UnsupportedTranslation('현재 편집기의 Python 코드가 변환 요청과 일치하지 않습니다.')
    provenance=deepcopy(project.get('embeddedVision'))
    if not isinstance(provenance,dict):
        raise UnsupportedTranslation('회로 출처 정보를 확인할 수 없습니다.')
    provenance.update({'physical_verified':False,'original_wiring_reused':False,
        'translated_from':'raspberry_pi_2wd_robot','translation_target':target,
        'source_code_sha256':result['source_sha256'],'translation_instance':uuid.uuid4().hex})
    if target=='raspberry_pi_c':
        converted=deepcopy(project)
        converted['name']='Raspberry Pi · C 코드 변환 회로'
        # Insert C in the same chip-owned group; keep original Python for comparison.
        group=next(g for g in converted['fileGroups'].values() if any(isinstance(f,dict) and f.get('name')=='pi_rover.py' and f.get('content')==source for f in g))
        group[:]=[f for f in group if not (isinstance(f,dict) and f.get('name')=='pi_rover.c')]
        group.insert(0,{'name':'pi_rover.c','content':result['code']})
        provenance.update({'recipe':'translated_pi_rover_c','simulation_notice':'Pi·모터 HAT·전원·모터는 시각 전용입니다. C 코드 및 모터 동작은 시뮬레이터가 실행하지 않습니다.'})
        converted['embeddedVision']=provenance
        changes=['Raspberry Pi 4B와 Motor HAT 회로 및 기존 배선을 유지합니다.', '변환한 C 코드를 추가하고 Python 원본도 보존합니다.']
        return {'workbench':converted,'changes':changes,'circuit_notice':provenance['simulation_notice']}
    if target!='arduino_cpp': raise UnsupportedTranslation('지원하지 않는 변환 대상입니다.')
    positions={p['id']:(p['x'],p['y']) for p in circuit['components']}
    # Target parts have explicit terminals; they are not electrical models.
    specifications={
      'SHIELD1':('Adafruit Motor Shield V2', [('SDA',0,20),('SCL',0,40),('5V',0,60),('GND',0,80),('M1.left',160,20),('M1.right',160,40),('M2.left',160,60),('M2.right',160,80),('PWR.positive',160,100),('PWR.negative',160,120)],positions['HAT1']),
      'MOTOR_L':('왼쪽 DC 모터',[('black',0,20),('red',0,40)],positions['MOTOR_L']),
      'MOTOR_R':('오른쪽 DC 모터',[('black',0,20),('red',0,40)],positions['MOTOR_R']),
      'BAT1':('모터용 별도 전원 · 정격 미확인',[('red',0,20),('black',0,40)],positions['BAT1']),
    }
    parts=[];file_groups={'group-U1':[{'name':'sketch.ino','content':result['code']}]}
    for cid,(name,pins,(x,y)) in specifications.items():
        part,group=_chip(cid,name,pins,x,y)
        part['properties']['evPhysicalModel']={'SHIELD1':'adafruit-motor-shield-v2','MOTOR_L':'adafruit-micro-dc-2941','MOTOR_R':'adafruit-micro-dc-2941','BAT1':'dc-supply-generic'}[cid]
        parts.append(part);file_groups['group-chip-'+cid]=group
    # Preserve purely decorative 3D structures; import_rover_project ensured no
    # wires from them are present. Their unrelated executable data is not run.
    parts.extend(deepcopy(p) for p in project['components'] if p.get('metadataId')=='ev-structure')
    connections=[('U1.A4','SHIELD1.SDA'),('U1.A5','SHIELD1.SCL'),('U1.5V','SHIELD1.5V'),('U1.GND.2','SHIELD1.GND'),
       ('SHIELD1.M1.left','MOTOR_L.black'),('SHIELD1.M1.right','MOTOR_L.red'),
       ('SHIELD1.M2.left','MOTOR_R.black'),('SHIELD1.M2.right','MOTOR_R.red'),
       ('SHIELD1.PWR.positive','BAT1.red'),('SHIELD1.PWR.negative','BAT1.black')]
    def ep(ref):
        cid,pin=ref.split('.',1)
        return {'componentId':cid,'pinName':pin,'x':0,'y':0}
    wires=[{'id':f'TR{i}','start':ep(a),'end':ep(b),'color':'#c52f2f' if a in ('U1.5V','SHIELD1.PWR.positive') else '#263238' if a in ('U1.GND.2','SHIELD1.PWR.negative') else '#159957','waypoints':[],'autoRouted':True} for i,(a,b) in enumerate(connections,1)]
    provenance.update({'recipe':'translated_uno_motor_shield_rover','model_type':'visual_interfaces_only',
       'simulation_notice':'Arduino Uno 코드는 편집할 수 있습니다. 모터 실드·모터·전원은 시각 부품으로 전기 동작과 3D 주행을 시뮬레이션하지 않습니다.',
       'hardware_references':[SHIELD_REFERENCE,POWER_REFERENCE]})
    converted={'format':'velxio-project','version':1,'exportedAt':datetime.now(timezone.utc).isoformat(),
       'name':'Arduino Uno · Motor Shield V2 변환 회로',
       'boards':[{'id':'U1','name':'Arduino Uno','boardKind':'arduino-uno','x':positions['U1'][0],'y':positions['U1'][1],
                  'activeFileGroupId':'group-U1','languageMode':'arduino','serialBaudRate':115200}],
       'components':parts,'wires':wires,'fileGroups':file_groups,'activeBoardId':'U1','embeddedVision':provenance}
    changes=['Raspberry Pi 4B와 Motor HAT를 Arduino Uno와 Adafruit Motor Shield V2로 교체합니다.',
       'UNO A4 → SDA, A5 → SCL, 5V → 5V, GND → GND로 실드 논리를 연결합니다.',
       '왼쪽 모터를 M1, 오른쪽 모터를 M2에 연결합니다.',
       '모터용 별도 전원을 실드 PWR에 연결하고 분리 전원 시 VIN 점퍼를 제거합니다. 모터·전원 정격은 미확인입니다.',
       '실드는 공개 V2.3 PCB에 맞춘 간략 제품 형상으로 표시합니다. 실제 조립은 실드를 Uno에 겹쳐 꽂는 방식입니다.']
    return {'workbench':converted,'changes':changes,'circuit_notice':provenance['simulation_notice']}
