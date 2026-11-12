"""Functional hypotheses inside opaque housings. Never recovered interior observations."""
import hashlib
import json
import math
from datetime import datetime, timezone
from typing import Annotated, Literal
from pydantic import Field, model_validator
from ..circuit.schema import StrictModel

Identifier=Annotated[str,Field(pattern=r'^[A-Za-z][A-Za-z0-9_-]{0,39}$')]

class InternalModule(StrictModel):
    id: Identifier
    parent_id: Identifier | None
    name: str=Field(min_length=1,max_length=120)
    role: Literal['controller','power','driver','sensor','interface','protection','passive','connector','mechanical']
    candidate_parts: list[str]=Field(max_length=8)
    required_part_ids: list[str]=Field(max_length=12)
    purpose: str=Field(min_length=1,max_length=600)
    rationale: str=Field(min_length=1,max_length=800)
    confidence: Literal['low','medium','high']
    status: Literal['INFERRED']
    photo_presence: Literal['UNKNOWN']
    alternatives: list[str]=Field(max_length=5)

class EnclosureHypothesis(StrictModel):
    id: Identifier
    name: str=Field(min_length=1,max_length=100)
    observed_part_ids: list[str]=Field(min_length=1,max_length=12)
    structure_object_id: str | None
    hypothesis_ids: list[str]=Field(min_length=1,max_length=3)
    rationale: str=Field(min_length=1,max_length=1000)
    modules: list[InternalModule]=Field(min_length=1,max_length=24)
    assumptions: list[str]=Field(min_length=1,max_length=12)
    unknowns: list[str]=Field(min_length=1,max_length=12)

    @model_validator(mode='after')
    def tree(self):
        nodes={m.id:m for m in self.modules}
        if len(nodes)!=len(self.modules):raise ValueError('내부 모듈 ID 중복')
        for m in self.modules:
            seen={m.id};parent=m.parent_id;depth=0
            while parent is not None:
                if parent not in nodes or parent in seen:raise ValueError('내부 모듈의 부모 참조 또는 순환 오류')
                seen.add(parent);parent=nodes[parent].parent_id;depth+=1
                if depth>3:raise ValueError('내부 분해 깊이는 4단계 이내입니다.')
        if any(len(s)>180 for m in self.modules for s in m.candidate_parts+m.alternatives):raise ValueError('부품 후보 설명이 너무 깁니다.')
        return self

class EnclosureAnalysis(StrictModel):
    summary: str=Field(min_length=1,max_length=1000)
    enclosures: list[EnclosureHypothesis]=Field(max_length=4)
    limitations: list[str]=Field(min_length=1,max_length=12)
    @model_validator(mode='after')
    def unique(self):
        if len({e.id for e in self.enclosures})!=len(self.enclosures):raise ValueError('외장 ID 중복')
        return self

ENCLOSURE_PROMPT='''외장·케이스·구조체로 가려진 시스템은 enclosure_analysis에서 가상 분해하세요.
이것은 불투명 재질 너머를 관측하거나 내부 사진을 복원하는 기능이 아니라 기능 기반 내부 구성 가설입니다.
observed_inventory에는 보이는 외장·외부 단자·센서·구동부만 유지하세요. 보이지 않는 내부 부품을 관측 목록에 넣지 마세요.
외부 구성품과 기능 후보를 근거로 전원부·제어부·센서 입력부·드라이버·통신부·보호부를 추론하세요.
모듈 아래에 IC·트랜지스터·다이오드·저항·커패시터·커넥터 등의 부품 후보를 parent_id로 세분화할 수 있습니다. 전체 모듈은 가급적 24개 이내, 설명은 각각 한 문장으로 작성하세요.
전원부→레귤레이터·평활 커패시터, 구동부→MOSFET·역기전력 다이오드 같은 구체적 역할을 설명하세요.
원본에 대한 내부 모듈의 관측 상태는 status=INFERRED, photo_presence=UNKNOWN으로 보존합니다. 여기서 분석을 끝내지 말고 functional_build에 기능 실행용 부품·수량·값·핀 배치를 구체적으로 선정하세요.
후보 모델을 제안할 때는 예시임을 설명하고 대안과 assumptions·unknowns를 남기세요. confidence는 정성적 판단입니다.
observed_part_ids와 hypothesis_ids는 저장된 실제 목록 ID만 참조하세요. structure_object_id는 photo_structure의 해당 외장 ID 또는 null입니다.
required_part_ids는 required_parts의 ID만 참조하고, 아직 구체 부품으로 선정하지 않은 기능 블록은 []를 사용하세요.
parent_id는 같은 외장 내 부모 모듈 ID 또는 null이며 순환 없이 최대 4단계로 구성하세요. 외장마다 보통 4~12개, 최대 24개 모듈을 제안하세요.
실제 보이는 형상은 기존 photo_structure에만 유지하고 가려진 형상을 관측으로 추가하지 마세요.
외장이나 기능 문맥이 없으면 enclosure_analysis=null로 둡니다. 최종 실물 확인은 사용자가 수행하므로 합리적인 가설을 제시하는 것이 목표입니다.'''

def validate_enclosure_analysis(raw, inventory, hypotheses, additions, photo_structure):
    if raw is None:return None
    model=EnclosureAnalysis.model_validate(raw)
    observed={p.id for p in inventory.parts};functions={h.id for h in hypotheses};required={p['id'] for p in additions}
    structures={p['id']:p for p in (photo_structure or {}).get('objects',[])}
    for case in model.enclosures:
        if not set(case.observed_part_ids)<=observed or not set(case.hypothesis_ids)<=functions:raise ValueError('내부 추론의 구성품·기능 근거 ID가 없습니다.')
        if case.structure_object_id is not None:
            shell=structures.get(case.structure_object_id)
            if not shell or shell['role'] not in {'housing','chassis','frame','platform','other'}:raise ValueError('외장 구조 참조가 잘못되었습니다.')
        if any(not set(m.required_part_ids)<=required for m in case.modules):raise ValueError('보완 부품 참조가 잘못되었습니다.')
    return model.model_dump(mode='json')

COLORS={'controller':'#397a61','power':'#c19d44','driver':'#4b86a4','sensor':'#64958a',
        'interface':'#6572a5','protection':'#c57966','passive':'#b29476','connector':'#727c81','mechanical':'#909ca3'}

def enclosure_workbench(analysis, provenance, photo_structure=None):
    """A separate pinless inspection project. Does not mutate the photographed circuit."""
    model=EnclosureAnalysis.model_validate(analysis);parts=[];factor=96/25.4
    photo={o['id']:o for o in (photo_structure or {}).get('objects',[])}
    def part(id,label,center,size,color,properties):
        w,h,d=size;x,y,z=center
        return {'id':id,'metadataId':'ev-structure','x':(x-w/2)*factor-6,'y':(z-d/2)*factor-6,
            'properties':{'label':label,'shape':'box','width':w,'height':h,'depth':d,'elevation':y-h/2,
              'rotation':0,'rotationX':0,'rotationZ':0,'color':color,'visualOnly':True,'dimensionsStatus':'UNKNOWN',**properties}}
    for index,case in enumerate(model.enclosures):
        case_id='case-'+case.id;center=[index*320,45,0];size=[160,90,115]
        observed=photo.get(case.structure_object_id)
        if observed and observed.get('geometry'):
            raw=observed['geometry']['size'];ratio=max(raw)
            size=[max(45,min(160,n/ratio*160)) for n in raw]
            center[1]=size[1]/2
        parts.append(part(case_id,case.name,center,size,'#8c9ca7',{'evEnclosure':{'id':case.id,'name':case.name,'rationale':case.rationale,'assumptions':case.assumptions,'unknowns':case.unknowns,'observed_part_ids':case.observed_part_ids},'designBasis':'illustrative_enclosure_proxy'}))
        children={parent:[m for m in case.modules if m.parent_id==parent] for parent in [None,*[m.id for m in case.modules]]}
        def place(parent,rect,depth=0):
            nodes=children[parent];cols=max(1,math.ceil(math.sqrt(len(nodes)*size[0]/size[2])));rows=max(1,math.ceil(len(nodes)/cols))
            x,z,w,d=rect
            for i,m in enumerate(nodes):
                cw=w/cols;cd=d/rows;mx=x-w/2+(i%cols+.5)*cw;mz=z-d/2+(i//cols+.5)*cd
                h=max(1,min(5,size[1]*.07));pos=[mx,size[1]*(.12+depth*.17),mz]
                props={'evInternalHypothesis':{**m.model_dump(mode='json'),'enclosure_id':case.id,'enclosure_component_id':case_id,'depth':depth,'hypothesis_ids':case.hypothesis_ids},'designBasis':'function_based_internal_hypothesis'}
                parts.append(part('inside-'+case.id+'-'+m.id,m.name,pos,[max(2,cw*.78),h,max(2,cd*.75)],COLORS[m.role],props))
                if children[m.id]:place(m.id,(mx,mz,cw*.78,cd*.75),depth+1)
        place(None,(center[0],0,size[0]*.83,size[2]*.83))
    version=hashlib.sha256(json.dumps(analysis,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    return {'format':'velxio-project','version':1,'exportedAt':datetime.now(timezone.utc).isoformat(),
      'name':'외장 내부 구성 · AI 추정 분해도','boards':[],'components':parts,'wires':[],'fileGroups':{},
      'embeddedVision':{**provenance,'recipe':'enclosure_hypothesis_view','enclosure_analysis':analysis,'enclosure_analysis_version':version,
        'function_version':version,'physical_verified':False,'original_wiring_reused':False,
        'simulation_notice':'외장을 근거로 기능상 가능한 내부 구성을 추론한 분해도입니다. 실제 내부 관측·제작 치수·전기 회로가 아니며 사용자가 최종 확인합니다.'}}
