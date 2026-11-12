"""Editable, bounded wiring for the reviewed Pi/HAT two-wheel proposal.

This is a logical drawing, not proof of electrical, motor or physical safety.
Only its connectivity is checked against the proposed design used by the
kinematic visualization. No arbitrary executable content or invented parts.
"""
from __future__ import annotations

from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from .robot_physical import robot_rover_design

COMPONENTS = {
    'U1': ('pi4', 'Raspberry Pi 4B', 120, 150),
    'HAT1': ('motor_hat', '모터 HAT #2348', 430, 150),
    'MOTOR_L': ('motor_left', '왼쪽 모터', 720, 80),
    'MOTOR_R': ('motor_right', '오른쪽 모터', 720, 260),
    'BAT1': ('motor_power', '모터 전원 5V', 720, 480),
    'PS1': ('pi_power', 'Pi USB-C 전원', 120, 420),
}
TERMINALS = {
    'U1': ('GPIO40', 'USB_C'),
    'HAT1': ('GPIO40', 'M1.left', 'M1.right', 'M2.left', 'M2.right', 'PWR.positive', 'PWR.negative'),
    'MOTOR_L': ('black', 'red'),
    'MOTOR_R': ('black', 'red'),
    'BAT1': ('red', 'black'),
    'PS1': ('USB_C',),
}
ALL_TERMINALS = {f'{cid}.{pin}' for cid,pins in TERMINALS.items() for pin in pins}
IDENT = Annotated[str,Field(pattern=r'^[A-Za-z][A-Za-z0-9_-]{0,63}$')]


class CircuitComponent(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, allow_inf_nan=False)
    id: IDENT
    kind: Literal['pi4', 'motor_hat', 'motor_left', 'motor_right', 'motor_power', 'pi_power']
    label: str = Field(min_length=1, max_length=60)
    x: float = Field(ge=20, le=980, allow_inf_nan=False)
    y: float = Field(ge=20, le=680, allow_inf_nan=False)

    @field_validator('label')
    @classmethod
    def nonblank_label(cls, value):
        if not value.strip(): raise ValueError('부품 이름을 입력하세요.')
        return value

    @model_validator(mode='after')
    def role_matches(self):
        if self.id not in COMPONENTS or COMPONENTS[self.id][0] != self.kind:
            raise ValueError('부품 ID와 역할이 검토된 설계에 맞지 않습니다.')
        return self


class CircuitWire(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    id: IDENT
    source: str = Field(alias='from', min_length=1, max_length=80)
    target: str = Field(alias='to', min_length=1, max_length=80)


class RoverCircuit(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    version: Literal[1]
    components: list[CircuitComponent] = Field(max_length=6)
    connections: list[CircuitWire] = Field(max_length=24)

    @field_validator('version',mode='before')
    @classmethod
    def exact_version_type(cls,value):
        if type(value) is not int: raise ValueError('회로 형식 버전이 올바르지 않습니다.')
        return value

    @model_validator(mode='after')
    def consistent_references(self):
        ids = {c.id for c in self.components}
        if len(ids) != len(self.components): raise ValueError('부품 ID가 중복되었습니다.')
        seen_ids, seen_pairs = set(), set()
        for wire in self.connections:
            if wire.id in seen_ids: raise ValueError('배선 ID가 중복되었습니다.')
            seen_ids.add(wire.id)
            if wire.source not in ALL_TERMINALS or wire.target not in ALL_TERMINALS:
                raise ValueError('정의되지 않은 단자입니다.')
            if wire.source.split('.', 1)[0] not in ids or wire.target.split('.', 1)[0] not in ids:
                raise ValueError('없는 부품의 단자를 연결할 수 없습니다.')
            pair = frozenset((wire.source, wire.target))
            if len(pair) != 2 or pair in seen_pairs: raise ValueError('같은 단자 또는 중복 배선입니다.')
            seen_pairs.add(pair)
        return self


def default_rover_circuit() -> dict:
    """The reviewed new design, never a statement about the source photo."""
    components = [{'id':cid,'kind':kind,'label':label,'x':x,'y':y}
                  for cid,(kind,label,x,y) in COMPONENTS.items()]
    connections = [{k:c[k] for k in ('id','from','to')}
                   for c in robot_rover_design()['connections']]
    return RoverCircuit.model_validate({'version':1,'components':components,'connections':connections}).model_dump(by_alias=True,mode='json')


def _nets(circuit: RoverCircuit) -> set[frozenset[str]]:
    parent: dict[str,str] = {}
    def root(x):
        parent.setdefault(x,x)
        if parent[x]!=x: parent[x]=root(parent[x])
        return parent[x]
    for wire in circuit.connections:
        left,right=root(wire.source),root(wire.target)
        if left!=right: parent[left]=right
    groups: dict[str,set[str]]={}
    for pin in parent: groups.setdefault(root(pin),set()).add(pin)
    return {frozenset(group) for group in groups.values()}


def validate_rover_circuit(raw: dict | RoverCircuit) -> dict:
    """Compare required component identities and normalized electrical nets.

    Status only means the drawing matches the documented *proposed* wiring;
    it does not validate voltage/current, firmware, or real-world operation.
    """
    circuit=RoverCircuit.model_validate(raw)
    expected=RoverCircuit.model_validate(default_rover_circuit())
    missing=sorted(set(COMPONENTS)-{c.id for c in circuit.components})
    actual_nets, expected_nets=_nets(circuit), _nets(expected)
    missing_nets=expected_nets-actual_nets
    unexpected_nets=actual_nets-expected_nets
    errors=[]
    if missing:errors.append('필수 부품이 빠졌습니다: '+', '.join(missing))
    if missing_nets:errors.append('검토된 설계와 다른 또는 빠진 연결이 있습니다.')
    if unexpected_nets:errors.append('추가되거나 잘못 연결된 단자가 있습니다.')
    return {'allowed':not errors,'errors':errors,
        'missing_components':missing,
        'missing_nets':[sorted(n) for n in sorted(missing_nets,key=lambda n:sorted(n))],
        'unexpected_nets':[sorted(n) for n in sorted(unexpected_nets,key=lambda n:sorted(n))],
        'notice':'기존 새 로봇 설계의 연결 일치만 확인합니다. 실제 전압·전류·하드웨어·코드 실행은 검증하지 않았습니다.'}
