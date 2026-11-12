"""Keep image observations immutable; propose missing design parts separately."""
import hashlib
import json
import re
from typing import Literal

from pydantic import Field

from ..circuit.schema import StrictModel, ComponentKind
from ..datasheet.catalog import CATALOG
from .function import FunctionIntent, FunctionHypothesis
from .system_model import SystemModel
from .virtual_model_proposal import VirtualModelProposal
from .photo_structure import PhotoStructure
from .enclosure_analysis import EnclosureAnalysis
from .functional_build import FunctionalBuild
from .models import Inventory


class RequiredPart(StrictModel):
    id: str = Field(pattern=r'^[A-Za-z][A-Za-z0-9_-]{0,39}$')
    kind: ComponentKind
    name: str = Field(min_length=1, max_length=160)
    quantity: int = Field(ge=1, le=50)
    model_candidates: list[str] = Field(max_length=6)
    status: Literal['INFERRED']
    photo_presence: Literal['UNKNOWN']
    reason_type: Literal['not_visible', 'missing_for_function', 'new_design_support']
    purpose: str = Field(min_length=1, max_length=1000)
    reason: str = Field(min_length=1, max_length=1000)
    basis_part_ids: list[str] = Field(min_length=1, max_length=20)
    hypothesis_ids: list[str] = Field(min_length=1, max_length=3)
    checks_needed: list[str] = Field(min_length=1, max_length=12)


class SystemReasoning(StrictModel):
    function: FunctionIntent
    function_hypotheses: list[FunctionHypothesis] = Field(max_length=3)
    required_parts: list[RequiredPart] = Field(max_length=30)
    system_model: SystemModel | None
    virtual_model: VirtualModelProposal | None
    photo_structure: PhotoStructure | None
    enclosure_analysis: EnclosureAnalysis | None
    functional_build: FunctionalBuild | None


class PhotoSystemAnalysis(StrictModel):
    inventory: Inventory
    design: SystemReasoning


def inventory_digest(inventory):
    return hashlib.sha256(json.dumps(inventory.model_dump(mode='json',exclude={'suggested_function'}),
        sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def validate_required_parts(raw, inventory, hypotheses):
    observed = {p.id for p in inventory.parts}
    candidate_ids = {h.id for h in hypotheses}
    seen = set()
    result = []
    for item in raw or []:
        part = RequiredPart.model_validate(item)
        if part.id in observed or part.id in seen:
            raise ValueError('보완 부품 ID는 관측 부품 및 다른 보완 부품과 구분해야 합니다.')
        if not set(part.basis_part_ids) <= observed:
            raise ValueError('보완 부품의 근거가 저장된 관측 부품 목록과 일치하지 않습니다.')
        if not set(part.hypothesis_ids) <= candidate_ids:
            raise ValueError('보완 부품이 참조한 기능 후보가 없습니다.')
        seen.add(part.id)
        result.append(part.model_dump(mode='json'))
    return result


def reference_candidates(kind, names):
    normalize = lambda s: re.sub(r'[^a-z0-9가-힣]', '', s.casefold())
    names = {normalize(n) for n in names if n}
    references = []
    for key, entry in CATALOG.items():
        if entry['kind'] != kind:
            continue
        if not ({normalize(key), normalize(entry['name'])} & names):
            continue
        references.append({'catalog_id': key, 'name': entry['name'],
            'url': entry['source'], 'source_type': entry.get('source_type', 'unknown'),
            'note': entry['note'], 'physical_match_verified': False})
    return references


def component_datasheet(inventory, additions, hypotheses, complete):
    """Generated summary, not a manufacturer's datasheet or recovered hidden BOM."""
    observed = [{**p.model_dump(mode='json'), 'origin': 'photo_observation',
        'references': reference_candidates(p.kind, [p.name, *p.model_candidates, *p.markings])}
        for p in inventory.parts]
    inferred = [{**p, 'origin': 'inferred_addition',
        'references': reference_candidates(p['kind'], [p['name'], *p['model_candidates']])}
        for p in additions]
    return {'version': 1, 'analysis_complete': complete,
        'observed_inventory_sha256': inventory_digest(inventory),
        'observed_parts': observed, 'inferred_parts': inferred,
        'function_hypotheses': [h.model_dump(mode='json') for h in hypotheses],
        'unknowns': inventory.unknowns,
        'notice': '사진의 관측 후보를 먼저 정리한 시스템 부품 요약입니다. 보완 부품은 기능 구현을 위한 추정이며 원본에 있었다는 뜻이 아닙니다. 제조사 원본 데이터시트 및 실물 모델 일치는 별도 확인이 필요합니다.'}
