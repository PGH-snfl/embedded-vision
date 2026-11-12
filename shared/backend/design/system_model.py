"""Evidence-bounded system decomposition, independent of an executable circuit."""
from typing import Literal

from pydantic import Field

from ..circuit.schema import StrictModel
from .function import FunctionalInventory


class SystemElement(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=1000)
    evidence_asset_ids: list[str] = Field(max_length=12)
    status: Literal['INFERRED', 'UNKNOWN']

class BoardRecommendation(StrictModel):
    family: Literal['arduino', 'esp32', 'pico', 'raspberry_pi', 'unknown']
    reason: str = Field(min_length=1, max_length=1000)
    status: Literal['INFERRED', 'UNKNOWN']

class SystemModel(StrictModel):
    summary: str = Field(min_length=1, max_length=1200)
    inputs: list[SystemElement] = Field(max_length=12)
    logic: list[SystemElement] = Field(max_length=12)
    outputs: list[SystemElement] = Field(max_length=12)
    assumptions: list[str] = Field(max_length=20)
    unknowns: list[str] = Field(max_length=20)
    board_recommendation: BoardRecommendation


from .virtual_model_proposal import VirtualModelProposal
from .photo_structure import PhotoStructure

class ExtendedFunctionalInventory(FunctionalInventory):
    # Both fields are required (including null) in the strict API schema.
    system_model: SystemModel | None
    virtual_model: VirtualModelProposal | None
    photo_structure: PhotoStructure | None


def validate_system_model(raw, asset_ids):
    """Do not let generated descriptions cite images outside the submitted evidence."""
    if raw is None:
        return None
    model = SystemModel.model_validate(raw)
    if (model.board_recommendation.family == 'unknown') != (model.board_recommendation.status == 'UNKNOWN'):
        raise ValueError('보드 추천의 미확인 상태가 일치하지 않습니다.')
    if any(item.status == 'INFERRED' and not item.evidence_asset_ids
           for item in [*model.inputs, *model.logic, *model.outputs]):
        raise ValueError('추정한 시스템 항목의 이미지 근거가 없습니다.')
    if any(asset not in asset_ids for item in [*model.inputs, *model.logic, *model.outputs]
           for asset in item.evidence_asset_ids):
        raise RuntimeError('시스템 기능의 근거 이미지가 입력과 일치하지 않습니다.')
    return model.model_dump(mode='json')
