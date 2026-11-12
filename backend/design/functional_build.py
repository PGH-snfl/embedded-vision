"""Concrete implementation choices, independent of claims about the original interior."""
import hashlib
import json
import math
import re
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field
from ..circuit.schema import StrictModel
from .board_profiles import board_catalog, profile_for, validate_firmware, runtime_contract

CATALOG_PATH=Path(__file__).resolve().parents[2]/'data/implementation-parts.json'
Identifier=Annotated[str,Field(pattern=r'^[A-Za-z][A-Za-z0-9_-]{0,39}$')]
Coordinate=Annotated[float,Field(ge=-1000,le=1000)]
Dimension=Annotated[float,Field(ge=2,le=500)]


def implementation_catalog():
    return {**json.loads(CATALOG_PATH.read_text()), **board_catalog()}


class DesignParameter(StrictModel):
    name: str=Field(min_length=1,max_length=40)
    value: str | float | bool


class SelectedPart(StrictModel):
    id: Identifier
    model_id: str=Field(min_length=1,max_length=80)
    purpose: str=Field(min_length=1,max_length=500)
    selection_reason: str=Field(min_length=1,max_length=700)
    observed_part_ids: list[str]=Field(max_length=12)
    module_refs: list[str]=Field(max_length=12)
    enclosure_id: str | None
    location: Literal['internal','panel','external']
    parameters: list[DesignParameter]=Field(max_length=8)


class DesignConnection(StrictModel):
    source: str=Field(min_length=3,max_length=100)
    target: str=Field(min_length=3,max_length=100)
    purpose: str=Field(min_length=1,max_length=300)


class SelectedStructure(StrictModel):
    id: Identifier
    label: str=Field(min_length=1,max_length=100)
    role: Literal['support','platform','shaft','panel','bracket','other']
    shape: Literal['box','cylinder']
    size_mm: list[Dimension]=Field(min_length=3,max_length=3)
    position_mm: list[Coordinate]=Field(min_length=3,max_length=3)
    purpose: str=Field(min_length=1,max_length=500)


class FunctionalBuild(StrictModel):
    title: str=Field(min_length=1,max_length=140)
    hypothesis_id: str=Field(min_length=1,max_length=40)
    behavior: str=Field(min_length=1,max_length=1200)
    parts: list[SelectedPart]=Field(min_length=2,max_length=16)
    connections: list[DesignConnection]=Field(min_length=1,max_length=80)
    structures: list[SelectedStructure]=Field(max_length=12)
    firmware: str=Field(min_length=30,max_length=20000)
    design_choices: list[str]=Field(min_length=1,max_length=16)
    acceptance_tests: list[str]=Field(min_length=1,max_length=12)
    not_implemented: list[str]=Field(max_length=12)


BUILD_PROMPT='''functional_build에는 가장 가능성이 높은 기능 후보 하나를 실행하는 구체적 새 설계를 작성하세요.
가려진 내부를 UNKNOWN으로 끝내지 말고 그 기능에 필요한 부품, 개수, 값, 전원, 연결, 장착 구조와 선정 보드용 코드를 선정하세요.
관측 목록은 그대로 보존하되 새 설계의 선정값은 명시적으로 결정할 수 있습니다. 원본 내부와 같다고 주장할 필요는 없습니다.
implementation_catalog의 model_id와 pins만 사용하세요. 각 parts 레코드가 실제 부품 1개이며 중복 수량은 고유 ID로 나눕니다.
board_profiles에서 제어 보드 한 개를 U1로 선정하세요. 관측 보드가 기능을 구현할 수 있으면 우선 사용하며 Arduino로 무조건 교체하지 마세요. 모델이 모호하면 선정 이유를 명시하고 구체적 지원 보드를 선택합니다. 실행 서비스가 필요한 보드도 설계할 수 있지만 지원 상태를 숨기지 마세요.
저항·커패시터 값과 전압·초기 입력은 parameters에 구체적으로 선정하고 빈칸/미확인/후보로 남기지 마세요.
부품의 정확한 원본 제품을 몰라도 이 기능을 수행하는 카탈로그 부품으로 정합니다. 위치는 internal/panel/external로 결정하고 외장 ID와 모듈 경로(caseId.moduleId)를 연결하세요.
버튼은 INPUT_PULLUP 또는 외부 풀업/풀다운, LED는 직렬 저항, 모터·펌프는 드라이버·전원·보호 다이오드·공통 접지까지 구성하세요.
connections의 source/target은 partId.pinName이고 핀 이름은 제공한 모델 정의 그대로입니다. 전원·신호·GND 연결을 빠짐없이 작성하세요.
firmware에는 보드 프로파일의 언어와 같은 핀을 쓰는 완성 코드를 넣으세요. UNO는 setup/loop Arduino C++, Pico·ESP32는 machine 기반 MicroPython main.py, Raspberry Pi 4는 gpiozero 기반 Linux Python main.py를 작성합니다. TODO, 빈 함수나 가짜 센서값 출력으로 기능을 대신하지 마세요.
사용자 입력으로 센서/버튼 상태를 바꾸면 출력이 달라져야 합니다. UNO만 Arduino 코어를 사용하며 LiquidCrystal.h·Servo.h는 제공되지 않습니다. Pico·ESP32에 AVR 레지스터나 analogRead를 복사하지 마세요. GPIO 전압, 입력 전용 핀, ADC 유무와 범위, PWM API·범위가 보드마다 다릅니다. Pi에는 내장 ADC가 없으며 없는 A0를 만들지 마세요. 3.3V GPIO에 5V 센서 출력을 직접 연결하지 말고 분압/레벨 변환을 구성하세요. 같은 기능을 유지하면서 핀·전원·드라이버·배선·코드·시험을 함께 설계합니다.
구조적으로 필요한 지지대·장착판·브래킷·축은 structures에 선정 치수(mm)와 목적을 정하세요. 치수는 사진 측정치가 아니라 새 설계값입니다.
기능을 단순 LED 점멸로 바꾸지 마세요. 제공 모델로 실행할 수 없는 부분은 not_implemented에 정확히 쓰고 구현하는 부분을 behavior에 일치시킵니다.
기능과 무관한 사진, 또는 이 카탈로그로 의미 있는 실행 부분을 만들 수 없을 때에만 functional_build=null로 둡니다.
제조·실물 작동이 검증됐다고 주장하지 마세요. 디자인은 선정 완료 상태로 전달하며 최종 실물 확인은 사용자가 합니다.'''


def validate_build(raw,inventory,hypotheses,enclosure=None):
    if raw is None:return None
    build=FunctionalBuild.model_validate(raw);catalog=implementation_catalog()
    ids=[p.id for p in build.parts];objects={p.id:p for p in build.parts}
    if len(set(ids))!=len(ids) or len(set(s.id for s in build.structures))!=len(build.structures) or set(ids)&{s.id for s in build.structures}:
        raise ValueError('설계 부품·구조물 ID가 중복되었습니다.')
    if build.hypothesis_id not in {h.id for h in hypotheses}:raise ValueError('실행 설계의 기능 후보가 없습니다.')
    observed={p.id for p in inventory.parts}
    cases={c['id'] for c in (enclosure or {}).get('enclosures',[])}
    if (set(ids)|{s.id for s in build.structures})&{'build-case-'+c for c in cases}:raise ValueError('자동 외장 ID와 부품 ID가 겹칩니다.')
    modules={c['id']+'.'+m['id'] for c in (enclosure or {}).get('enclosures',[]) for m in c['modules']}
    boards=[p for p in build.parts if p.model_id in board_catalog()]
    if len(boards)!=1 or boards[0].id!='U1':raise ValueError('실행 설계에는 지원 제어 보드 U1이 하나 필요합니다.')
    for p in build.parts:
        if p.model_id not in catalog:raise ValueError('실행 모델이 없는 설계 부품입니다: '+p.model_id)
        if not set(p.observed_part_ids)<=observed or not set(p.module_refs)<=modules:raise ValueError('설계 부품의 분석 참조가 잘못되었습니다.')
        if p.enclosure_id is not None and p.enclosure_id not in cases:raise ValueError('장착할 외장이 없습니다.')
        keys=[v.name for v in p.parameters]
        if len(set(keys))!=len(keys) or any(not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,39}',key) for key in keys):raise ValueError('부품 설정 이름이 잘못되었습니다.')
        if any(isinstance(v.value,str) and (not v.value.strip() or len(v.value)>100 or v.value.casefold() in {'unknown','미확인','후보','tbd','todo'}) for v in p.parameters):raise ValueError('새 설계의 부품 값은 구체적으로 선정해야 합니다.')
    touched=set();edges=set()
    for wire in build.connections:
        for ep in [wire.source,wire.target]:
            ref,sep,pin=ep.partition('.')
            if not sep or ref not in objects or pin not in catalog[objects[ref].model_id]['pins']:raise ValueError('선정 부품에 없는 연결 핀입니다: '+ep)
            touched.add(ref)
        pair=tuple(sorted([wire.source,wire.target]))
        if wire.source==wire.target or pair in edges:raise ValueError('배선이 중복되거나 자기 자신에 연결됐습니다.')
        edges.add(pair)
    if touched!=set(ids):raise ValueError('배선되지 않은 선정 부품이 있습니다.')
    validate_firmware(build.firmware, profile_for(boards[0].model_id))
    return build.model_dump(mode='json')


def build_version(build):
    return hashlib.sha256(json.dumps(build,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def build_workbench(raw,provenance,enclosure=None,*,include_environment=True):
    from ..workflow import workflow_stamp
    build=FunctionalBuild.model_validate(raw);catalog=implementation_catalog();board_models=board_catalog();factor=96/25.4
    parts=[];boards=[];selected=[];shells=[]
    cases=(enclosure or {}).get('enclosures',[])
    grouped={c['id']:[] for c in cases};grouped[None]=[]
    for p in build.parts:grouped[p.enclosure_id].append(p)
    for index,(case_id,group) in enumerate(grouped.items()):
        inside=[p for p in group if p.location!='external'];outside=[p for p in group if p.location=='external']
        count=max(1,len(inside));cols=math.ceil(math.sqrt(count));rows=math.ceil(count/cols)
        w=cols*110+30;d=rows*95+30;h=90;cx=index*650;cz=0
        shell_id='build-case-'+case_id if case_id else None
        case=next((c for c in cases if c['id']==case_id),None)
        if case:
            shells.append({'id':shell_id,'metadataId':'ev-structure','x':(cx-w/2)*factor-6,'y':-d/2*factor-6,
                'properties':{'label':case['name'],'shape':'box','width':w,'height':h,'depth':d,'elevation':0,'color':'#8c9ca7',
                  'visualOnly':True,'dimensionsStatus':'DESIGN_SELECTED','designBasis':'functional_implementation',
                  'evEnclosure':{'id':case_id,'name':case['name'],'design_selected':True,'rationale':'선정 부품을 장착하고 배선 공간을 확보하도록 외장 치수를 정했습니다.','assumptions':build.design_choices,'unknowns':[]}}})
        for i,p in enumerate([*inside,*outside]):
            entry=catalog[p.model_id];external=p.location=='external';j=i-len(inside) if external else i
            x=cx+w/2+90+(j%3)*110 if external else cx-w/2+70+(j%cols)*110
            z=-d/2+65+(j//(3 if external else cols))*95;y=h+2 if p.location=='panel' else 12
            specifications={v.name:v.value for v in p.parameters}
            runtime_keys=set(entry['properties'])|set(entry['defaults'])
            configured={**deepcopy(entry['defaults']),**{k:v for k,v in specifications.items() if k in runtime_keys}}
            chosen={'status':'DESIGN_SELECTED','model_id':p.model_id,'name':entry['name'],'quantity':1,
                'purpose':p.purpose,'selection_reason':p.selection_reason,'module_refs':p.module_refs,
                'observed_part_ids':p.observed_part_ids,'enclosure_id':p.enclosure_id,
                'location':p.location,'parameters':{**{k:v for k,v in configured.items() if k in entry['properties'] or k in {'nominalVoltage','resistance','inductance'}},**specifications},'pin_basis':entry['basis']}
            selected.append({'id':p.id,**chosen})
            props={**configured,'label':entry['name'],'evSelectedDesign':chosen,'evDesignMount':p.location}
            is_board=p.model_id in board_models
            nx=(x-entry['size_mm'][0]/2)*factor-(0 if is_board else 6)
            nz=(z-entry['size_mm'][2]/2)*factor-(0 if is_board else 6)
            if case:
                props['evDesignEnclosure']=shell_id
                props['evAssembly']={'pose':{'position':[x,y,z],'rotation':[0,0,0]},'baseline':[nx,nz,0],
                    'host':{'id':shell_id,'center':[cx,h/2,cz]},'note':'기능 구현용 선정 배치 · 장착 및 배선 여유 포함'}
            if is_board:
                profile=profile_for(p.model_id)
                props['evBoardRuntime']=runtime_contract(p.model_id)
                boards.append({'id':p.id,'name':entry['name']+' · 기능 구현 설계','boardKind':p.model_id,
                'x':nx,'y':nz,'properties':props,'activeFileGroupId':'group-U1','languageMode':profile['native_language_mode'],
                'serialBaudRate':int(next(iter(re.findall(r'Serial\.begin\s*\(\s*(\d+)\s*\)',build.firmware)),'115200'))})
            else:parts.append({'id':p.id,'metadataId':p.model_id,'x':nx,'y':nz,'properties':props})
    for s in build.structures:
        w,h,d=s.size_mm;x,y,z=s.position_mm
        parts.append({'id':s.id,'metadataId':'ev-structure','x':(x-w/2)*factor-6,'y':(z-d/2)*factor-6,
            'properties':{'label':s.label,'shape':s.shape,'width':w,'height':h,'depth':d,'elevation':y-h/2,'color':'#a6adb1',
              'visualOnly':True,'dimensionsStatus':'DESIGN_SELECTED','evDesignedStructure':{'role':s.role,'reason':s.purpose},
              'evSelectedDesign':{'status':'DESIGN_SELECTED','name':s.label,'purpose':s.purpose,'selection_reason':s.purpose,'quantity':1}}})
    def endpoint(text):
        ref,pin=text.split('.',1);return {'componentId':ref,'pinName':pin,'x':0,'y':0}
    wires=[{'id':f'BUILD_W{i+1}','start':endpoint(w.source),'end':endpoint(w.target),'waypoints':[],
        'autoRouted':True,'color':'#263238' if any(t.endswith('.GND') for t in [w.source,w.target]) else '#267dba'} for i,w in enumerate(build.connections)]
    from .functional_environment import attach_watering_environment
    environment=attach_watering_environment(parts,wires) if include_environment else []
    for p in environment:
        props=p['properties'];selected.append({'id':p['id'],'model_id':p['metadataId'],**props['evSelectedDesign']})
    runtime=runtime_contract(boards[0]['boardKind']);profile=profile_for(boards[0]['boardKind'])
    implementation={'status':'DESIGN_SELECTED','hypothesis_id':build.hypothesis_id,'title':build.title,'behavior':build.behavior,'parts':selected,
        'structures':[s.model_dump(mode='json') for s in build.structures]+[{'id':p['id'],'label':p['properties']['label'],
            'size_mm':[p['properties'][k] for k in ['width','height','depth']],'purpose':p['properties']['evSelectedDesign']['purpose']} for p in environment],
        'connections':[w.model_dump(mode='json') for w in build.connections],
        'design_choices':build.design_choices,'acceptance_tests':build.acceptance_tests,'not_implemented':build.not_implemented,
        'runtime':runtime,'firmware':{'language':profile['language'],'entry_file':profile['entry_file'],'source':build.firmware}}
    return {'format':'velxio-project','version':1,'exportedAt':datetime.now(timezone.utc).isoformat(),'name':build.title,
        'boards':boards,'components':[*shells,*parts,*environment],'wires':wires,'activeBoardId':'U1',
        'fileGroups':{'group-U1':[{'name':profile['entry_file'],'content':build.firmware}]},
        'embeddedVision':{**provenance,'workflow':workflow_stamp(),'recipe':'ai_functional_build','basis':'selected_functional_implementation',
          'functional_build_version':build_version(raw),'implementation_design':implementation,'enclosure_analysis':enclosure,
          'physical_verified':False,'original_wiring_reused':False,'simulation_behavior':build.behavior,
          'simulation_notice':'기능을 실행하도록 부품·값·배선·코드를 선정한 새 설계입니다. 최종 실물 검증은 사용자가 진행합니다.'}}
