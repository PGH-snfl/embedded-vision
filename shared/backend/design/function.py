"""Behavior contracts precede circuit selection; keep possible behavior separate from observed facts."""
import hashlib,json
from typing import Literal
from pydantic import Field,model_validator
from ..circuit.schema import StrictModel
from .models import Inventory

class FunctionEvidence(StrictModel):
    asset_id:str
    observation:str=Field(min_length=1,max_length=1000)

class FunctionIntent(StrictModel):
    kind:Literal['lcd_text','voltage_readout','button_led','light_led','led_output','led_blink','led_brightness','unsupported','unknown']
    status:Literal['INFERRED','UNKNOWN','USER_DEFINED']
    summary:str=Field(min_length=1,max_length=1200)
    input_behavior:str=Field(max_length=1000)
    output_behavior:str=Field(max_length=1000)
    evidence:list[FunctionEvidence]=Field(max_length=12)
    unknowns:list[str]=Field(max_length=12)
    acceptance_criteria:list[str]=Field(max_length=12)
    display_text:str|None=Field(max_length=16)
    @model_validator(mode='after')
    def invariants(self):
        if self.status=='UNKNOWN' and self.kind not in {'unknown','unsupported'}:
            raise ValueError('UNKNOWN behavior cannot select a circuit')
        if self.kind=='lcd_text' and self.display_text is not None:
            import re
            if not re.fullmatch(r'[A-Za-z0-9 .,!?_-]{1,16}',self.display_text):
                raise ValueError('현재 LCD 문구는 16자 영문·숫자·기본 문장부호를 지원합니다.')
        return self

class FunctionHypothesis(StrictModel):
    id:str=Field(pattern=r'^[a-z][a-z0-9_-]{0,39}$')
    title:str=Field(min_length=1,max_length=120)
    kind:Literal['lcd_text','voltage_readout','button_led','light_led','led_output','led_blink','led_brightness','unsupported']
    status:Literal['INFERRED']
    plausibility:Literal['medium','low']
    rationale:str=Field(min_length=1,max_length=1000)
    part_ids:list[str]=Field(min_length=1,max_length=20)
    evidence:list[FunctionEvidence]=Field(min_length=1,max_length=12)
    input_behavior:str=Field(min_length=1,max_length=1000)
    output_behavior:str=Field(min_length=1,max_length=1000)
    assumptions:list[str]=Field(min_length=1,max_length=10)
    distinguishing_check:str=Field(min_length=1,max_length=700)
    display_text:str|None=Field(max_length=16)

class FunctionalInventory(Inventory):
    function:FunctionIntent
    function_hypotheses:list[FunctionHypothesis]=Field(max_length=3)

class HypothesisInput(StrictModel):
    expected_revision:int
    candidate_id:str=Field(pattern=r'^[a-z][a-z0-9_-]{0,39}$')

class FunctionInput(StrictModel):
    expected_revision:int
    kind:Literal['lcd_text','voltage_readout','button_led','light_led','led_output','led_blink','led_brightness','unsupported','unknown']
    description:str=Field(min_length=5,max_length=1200)
    display_text:str|None=Field(default=None,max_length=16)

CATALOG={
 'led_output':{'label':'LED 지속 점등','recipe':'arduino_led_output','input':'전원을 켭니다.',
   'output':'D5 출력으로 외부 LED를 계속 켭니다.','criteria':['실행 중 D5가 HIGH이고 LED가 켜진다.']},
 'led_blink':{'label':'LED 깜빡이기','recipe':'arduino_led_blink','input':'전원을 켜면 반복 실행합니다.',
   'output':'LED를 0.5초 켜고 0.5초 끄는 동작을 반복합니다.','criteria':['D5가 500ms 간격으로 HIGH/LOW를 반복한다.']},
 'led_brightness':{'label':'LED 밝기 자동 조절','recipe':'arduino_led_brightness','input':'별도 입력 장치 없이 프로그램이 밝기를 변경합니다.',
   'output':'PWM(빠른 점멸의 켜짐 비율) 값을 0~255로 올렸다 내리며 밝기를 반복 조절합니다.','criteria':['D5 PWM 값이 20ms마다 5씩 증가·감소하며 0과 255에 도달한다.']},
 'lcd_text':{'label':'LCD에 고정 문구 표시','recipe':'arduino_lcd','input':'전원을 켭니다.',
   'output':'LCD 첫째 줄에 지정한 문구를 유지합니다.','criteria':['전원을 켜면 지정 문구가 표시된다.','경과 시간·센서값 등 요청하지 않은 출력은 추가하지 않는다.']},
 'voltage_readout':{'label':'두 저항 사이 전압을 시리얼로 읽기','recipe':'arduino_voltage_divider','input':'보드 5V에 연결한 두 저항 사이 전압을 읽습니다.',
   'output':'USB 시리얼에 ADC 값과 추정 전압을 200ms 간격으로 출력합니다.','criteria':['저항값이 같으면 A0가 약 2.5V이다.','시리얼에 ADC 값과 추정 전압이 200ms 간격으로 출력된다.']},
 'light_led':{'label':'어두우면 LED 켜기','recipe':'arduino_light_led','input':'조도 센서에 비치는 빛을 바꿉니다.',
   'output':'센서의 아날로그 값이 임계값보다 높으면 LED를 켭니다.','criteria':['가상 센서가 어두워지면 LED가 켜지고 밝아지면 꺼진다.','실물에서는 센서의 AO 방향과 임계값을 측정하여 보정한다.']},
 'button_led':{'label':'버튼을 누르는 동안 LED 켜기','recipe':'arduino_led_button','input':'버튼을 누르거나 놓습니다.',
   'output':'누르는 동안 LED가 켜지고 놓으면 꺼집니다.','criteria':['버튼을 누르면 LED가 켜진다.','버튼을 놓으면 LED가 꺼진다. 토글·지연 동작은 추가하지 않는다.']}}

def simulation_behavior(intent):
    """Behavior actually implemented by the supported UNO recipe, not photo evidence."""
    if intent.kind=='lcd_text':
        return f'LCD 첫째 줄에 "{intent.display_text}" 문구를 고정 표시합니다.' if intent.display_text else ''
    return {
        'led_output':'LED를 계속 켭니다.',
        'led_blink':'LED를 0.5초 켜고 0.5초 끄는 동작을 반복합니다.',
        'led_brightness':'LED 밝기를 자동으로 올렸다 내립니다. PWM 값을 20ms마다 5씩 변경합니다.',
        'button_led':'버튼을 누르는 동안 LED를 켜고 놓으면 끕니다.',
        'light_led':'가상 조도 센서가 어두워져 A0 값이 512보다 크면 LED를 켜고, 그렇지 않으면 끕니다.',
        'voltage_readout':'5V와 10kΩ 저항 두 개의 분압을 A0에서 읽고 200ms마다 시리얼로 출력합니다.',
    }.get(intent.kind,'')

def unknown_function():
    return FunctionIntent(kind='unknown',status='UNKNOWN',summary='아래 후보를 바탕으로 어떤 기능인지 추정할 수 있습니다. 세부 동작은 아직 구분되지 않았습니다.',input_behavior='',output_behavior='',evidence=[],unknowns=['어떤 입력에 어떤 출력이 나오는지 확인해야 합니다.'],acceptance_criteria=[],display_text=None)

def user_function(body):
    item=CATALOG.get(body.kind)
    return FunctionIntent(kind=body.kind,status='USER_DEFINED' if body.kind!='unknown' else 'UNKNOWN',summary=body.description,
        input_behavior=item['input'] if item else '',output_behavior=item['output'] if item else '',
        evidence=[],unknowns=[] if item else ['이 기능을 구현할 회로·부품·제어 로직의 추가 설계가 필요합니다.'],
        acceptance_criteria=item['criteria'] if item else [],display_text=body.display_text if body.kind=='lcd_text' else None)

def version(intent):
    return hashlib.sha256(intent.model_dump_json().encode()).hexdigest()

def constrain(offered,intent):
    """Keep only an actual functional match; missing information never triggers fallback."""
    target=CATALOG.get(intent.kind)
    blockers=[]
    if not target:blockers.append('기능 후보를 비교하고 재현할 동작을 선택하세요.' if intent.kind=='unknown' else '아직 이 기능의 회로·코드 생성 규칙을 지원하지 않습니다.')
    if intent.kind=='lcd_text' and not intent.display_text:blockers.append('LCD에 표시할 문구를 확인하세요.')
    if intent.status=='INFERRED' and not intent.evidence:blockers.append('기능 추론의 관측 근거가 없습니다. 원하는 동작을 직접 지정하세요.')
    matches=[p for p in offered['proposals'] if target and (p['recipe']==target['recipe'] or (intent.kind=='button_led' and p['recipe']=='esp32_led_button'))] if not blockers else []
    matches.sort(key=lambda p:not p['simulator_supported'])
    if target and not matches and not blockers:blockers.append('기능에 맞는 보드·핵심 부품 구성을 확인하지 못했습니다. 다른 기능의 회로로 대체하지 않습니다.')
    for p in matches:
        # Do not label the generated code with a more general model inference.
        p['simulation_behavior']=simulation_behavior(intent) if p['simulator_supported'] else ''
        p['behavior']=p['simulation_behavior'] or target['output'];p['function']=intent.model_dump(mode='json')
        p['acceptance_criteria']=intent.acceptance_criteria
        p['reason']+=' 선택한 동작과 일치하는 연결·코드 규칙을 사용합니다.'
        if intent.kind=='lcd_text':
            from .recipes import new_graph
            from .firmware import lcd_firmware
            p['firmware']=lcd_firmware(new_graph('0'*32,p['recipe'])[0],intent.display_text,show_elapsed=False)
    return {**offered,'policy':'function-first-v1','function':intent.model_dump(mode='json'),
        'function_version':version(intent),'function_blockers':blockers,'function_options':[
            {'kind':k,'label':v['label']} for k,v in CATALOG.items()],
        'recommended':matches[0]['recipe'] if matches else None,'proposals':matches,
        'notice':'사진·영상에서 확인한 기능 또는 사용자가 지정한 동작을 새 배선으로 구현합니다. 기능 동등성과 실물 동작은 아직 검증되지 않았습니다.'}
