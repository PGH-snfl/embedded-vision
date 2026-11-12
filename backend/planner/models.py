from .selection import AnalysisModel,PRIMARY
from typing import Literal
from pydantic import Field, model_validator
from ..circuit.schema import StrictModel

Task = Literal['explain', 'circuit_inference', 'build_schematic']

class Finding(StrictModel):
    subject: str
    status: Literal['INFERRED', 'UNKNOWN']
    hypothesis: str | None
    asset_ids: list[str]
    evidence_ids: list[str]
    terminal_ids: list[str]
    rationale: str
    verification_needed: str

    @model_validator(mode='after')
    def unknown_has_no_value(self):
        if self.status == 'UNKNOWN' and self.hypothesis is not None:
            raise ValueError('UNKNOWN hypothesis must be null')
        if self.status == 'INFERRED' and not self.hypothesis:
            raise ValueError('INFERRED needs a hypothesis')
        return self

class Region(StrictModel):
    asset_id: str
    x0: float = Field(ge=0,le=1)
    y0: float = Field(ge=0,le=1)
    x1: float = Field(ge=0,le=1)
    y1: float = Field(ge=0,le=1)
    @model_validator(mode='after')
    def ordered(self):
        if self.x1<=self.x0 or self.y1<=self.y0:raise ValueError('Empty review region')
        return self

class DeepReview(StrictModel):
    finding_indices: list[int] = Field(min_length=1,max_length=4)
    reason: Literal['competing_connections','topology_conflict','power_signal_conflict']
    alternatives: list[str] = Field(min_length=2,max_length=4)
    question: str
    visible_evidence: str
    solvable_from_visible_evidence: bool
    region: Region

class Decision(StrictModel):
    summary: str
    findings: list[Finding] = Field(max_length=40)
    unresolved: list[str] = Field(max_length=40)
    conflicts: list[str] = Field(max_length=40)
    actions: list[Literal['review_evidence', 'build_schematic']] = Field(max_length=2)
    deep_review: list[DeepReview] = Field(max_length=3)

class FindingReview(StrictModel):
    finding_index: int = Field(ge=0)
    status: Literal['INFERRED','UNKNOWN']
    hypothesis: str | None
    rationale: str
    verification_needed: str
    @model_validator(mode='after')
    def consistent(self):
        if (self.status=='UNKNOWN' and self.hypothesis is not None) or (self.status=='INFERRED' and not self.hypothesis):
            raise ValueError('Invalid reviewed hypothesis')
        return self

class FocusedReview(StrictModel):
    summary: str
    reviews: list[FindingReview] = Field(max_length=12)
    unresolved: list[str] = Field(max_length=20)
    conflicts: list[str] = Field(max_length=20)

class PlanInput(StrictModel):
    expected_revision: int
    prompt: str = Field(min_length=1, max_length=2000)
    task: Task = 'circuit_inference'
    model: AnalysisModel = PRIMARY
    asset_ids: list[str] = Field(default_factory=list, max_length=6)

class ExecuteInput(StrictModel):
    expected_revision: int


class AutoAnalysisInput(ExecuteInput):
    model: AnalysisModel | None = None
