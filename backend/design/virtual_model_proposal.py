"""Strict AI response shape, translated into the bounded virtual simulator format."""
from typing import Literal

from pydantic import Field

from ..circuit.schema import StrictModel
from ..simulation.virtual_system import Identifier, SignalValue, validate_virtual_model


class ProposedInput(StrictModel):
    id: Identifier
    label: str
    type: Literal['boolean', 'number']
    default: SignalValue
    min: float | None
    max: float | None
    unit: str


class ProposedOutput(StrictModel):
    id: Identifier
    label: str
    type: Literal['boolean', 'number']
    default: SignalValue
    unit: str


class ProposedCondition(StrictModel):
    input: Identifier
    operator: Literal['eq', 'ne', 'lt', 'lte', 'gt', 'gte']
    value: SignalValue


class ProposedAssignment(StrictModel):
    output: Identifier
    value: SignalValue


class ProposedRule(StrictModel):
    id: Identifier
    conditions: list[ProposedCondition] = Field(max_length=16)
    match: Literal['all', 'any']
    set: list[ProposedAssignment] = Field(max_length=16)
    status: Literal['INFERRED', 'UNKNOWN']
    enabled: bool


class VirtualModelProposal(StrictModel):
    target_board: Literal['arduino', 'raspberry_pi']
    inputs: list[ProposedInput] = Field(max_length=32)
    outputs: list[ProposedOutput] = Field(max_length=32)
    rules: list[ProposedRule] = Field(max_length=128)
    assumptions: list[str] = Field(max_length=31)
    unsupported_requirements: list[str] = Field(max_length=32)


def normalize_virtual_model(raw):
    if raw is None:
        return None
    data = VirtualModelProposal.model_validate(raw).model_dump(mode='json')
    for rule in data['rules']:
        assignments = rule['set']
        if len({item['output'] for item in assignments}) != len(assignments):
            raise ValueError('중복된 가상 출력 지정')
        rule['set'] = {item['output']: item['value'] for item in assignments}
        if rule['status'] == 'UNKNOWN':
            rule['enabled'] = False
    data['assumptions'].append('가상 규칙과 입력값은 새 프로토타입의 가정이며 원본 동작의 증거가 아닙니다.')
    return validate_virtual_model(data).model_dump(mode='json')
