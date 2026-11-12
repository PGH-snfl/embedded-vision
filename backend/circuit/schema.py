"""Evidence-first intermediate representation. No KiCad pin assignments are guessed."""
from enum import StrEnum
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Status(StrEnum):
    CONFIRMED = "CONFIRMED"
    INFERRED = "INFERRED"
    UNKNOWN = "UNKNOWN"


class Point(StrictModel):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)


class Claim(StrictModel):
    value: str | None = None
    status: Status = Status.UNKNOWN
    score: float | None = Field(default=None, ge=0, le=1)
    calibrated: Literal[False] = False
    evidence_ids: list[str] = Field(default_factory=list)
    candidates: list[str] = Field(default_factory=list)
    reason: str = "아직 확인하지 않았습니다."

    @model_validator(mode="after")
    def consistency(self):
        if self.status == Status.UNKNOWN and (self.value is not None or self.score is not None):
            raise ValueError("UNKNOWN must have null value and score; use candidates instead")
        if self.status != Status.UNKNOWN and not self.value:
            raise ValueError("Known claims require a value")
        if self.status == Status.CONFIRMED and not self.evidence_ids:
            raise ValueError("CONFIRMED requires supporting evidence")
        return self


class Asset(StrictModel):
    id: str
    sha256: str
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    filename: str
    synthetic: bool = False


class Evidence(StrictModel):
    id: str
    asset_id: str
    method: Literal["synthetic_fixture", "manual_annotation", "user_confirmation", "color_segmentation", "ocr", "geometry", "datasheet", "design_spec", "video_frame", "agent_edit", "vlm"]
    points: list[Point] = Field(default_factory=list)
    text: str
    source_url: str | None = None


class Terminal(StrictModel):
    id: str
    name: Claim = Field(default_factory=Claim)
    # A visual label is NOT a datasheet-verified electrical pin number.
    pin_mapping: Claim = Field(default_factory=Claim)
    image_position: Point | None = None


ComponentKind = Literal["board", "breadboard", "led", "resistor", "button", "sensor", "other", "capacitor", "source", "display", "potentiometer"]


class Component(StrictModel):
    id: str
    kind: ComponentKind
    catalog_id: str | None = None
    asset_id: str = "image"
    label: Claim = Field(default_factory=Claim)
    value: Claim = Field(default_factory=Claim)
    bbox: list[Point] = Field(min_length=2, max_length=2)
    terminals: list[Terminal] = Field(default_factory=list)

    @model_validator(mode="after")
    def ordered_box(self):
        a, b = self.bbox
        if a.x >= b.x or a.y >= b.y:
            raise ValueError("Bounding box must have positive width and height")
        return self


class Link(StrictModel):
    id: str
    from_terminal: str | None = None
    to_terminal: str | None = None
    path: list[Point] = Field(default_factory=list)
    connection: Claim = Field(default_factory=Claim)
    asset_id: str = "image"

    @model_validator(mode="after")
    def endpoints(self):
        if self.connection.status != Status.UNKNOWN:
            if not self.from_terminal or not self.to_terminal:
                raise ValueError("Known connections require both endpoints")
            if self.from_terminal == self.to_terminal:
                raise ValueError("A wire must connect different terminals")
            if self.connection.value != "connected":
                raise ValueError("Connection value must be connected")
        return self


class WireCandidate(StrictModel):
    id: str
    color: str
    bbox: list[Point] = Field(min_length=2, max_length=2)
    evidence_id: str
    # Color contours never imply an electrical connection.
    status: Literal["UNKNOWN"] = "UNKNOWN"
    path: list[Point] = Field(default_factory=list,max_length=200)
    endpoints: list[Point] = Field(default_factory=list,max_length=2)
    geometry: Literal["contour","segment","ambiguous"] = "contour"
    reason: str = "실제 전선·끝점·핀 연결을 확인하지 않았습니다."

    @model_validator(mode="after")
    def geometry_consistency(self):
        a,b=self.bbox
        if a.x>=b.x or a.y>=b.y:
            raise ValueError("Candidate bounding box must have positive dimensions")
        if self.geometry=='segment':
            if len(self.path)<2 or len(self.endpoints)!=2 or self.endpoints!=[self.path[0],self.path[-1]]:
                raise ValueError("Segment endpoints must match its path")
        elif self.endpoints or self.path:
            raise ValueError("Ambiguous contours cannot claim an ordered stroke")
        return self


class TextObservation(StrictModel):
    id: str
    asset_id: str
    text: str
    bbox: list[Point] = Field(min_length=2,max_length=2)
    score: float = Field(ge=0,le=1)
    evidence_id: str

    @model_validator(mode="after")
    def ordered_box(self):
        a,b=self.bbox
        if a.x>=b.x or a.y>=b.y:
            raise ValueError("Text bounding box must have positive dimensions")
        return self


class WireReview(StrictModel):
    """User correspondence across views, not an automatic electrical measurement."""
    id: str
    link_id: str
    asset_id: str
    from_terminal: str
    to_terminal: str
    points: list[Point] = Field(min_length=2, max_length=200)
    entire_wire_visible: bool
    evidence_id: str


class WireHypothesis(StrictModel):
    id: str
    asset_id: str
    evidence_id: str
    endpoint_ids: list[str] = Field(min_length=2, max_length=2)
    visible_paths: list[list[Point]] = Field(min_length=2, max_length=2)
    bridge: list[Point] = Field(min_length=2, max_length=2)
    color: str
    ranking_score: float = Field(ge=0, le=100)
    status: Literal['INFERRED'] = 'INFERRED'
    reasons: list[str]
    link_id: str | None = None

    @model_validator(mode='after')
    def geometry(self):
        a,b=self.visible_paths
        if len(a)<2 or len(b)<2 or len(a)>200 or len(b)>200 or self.bridge!=[a[-1],b[0]]:
            raise ValueError('Hypothesis bridge must join the oriented visible fragments')
        if self.endpoint_ids[0]==self.endpoint_ids[1]:
            raise ValueError('Hypothesis requires distinct fragment endpoints')
        return self


class Graph(StrictModel):
    schema_version: Literal["0.1.0"] = "0.1.0"
    project_id: str
    title: str = Field(max_length=200)
    revision: int = Field(ge=1)
    mode: Literal["synthetic_demo", "photo", "reference_design", "video"]
    profile: str | None = None
    parameters: dict[str, float] = Field(default_factory=dict)
    assets: list[Asset]
    evidence: list[Evidence] = Field(default_factory=list)
    components: list[Component] = Field(default_factory=list)
    links: list[Link] = Field(default_factory=list)
    wire_candidates: list[WireCandidate] = Field(default_factory=list)
    text_observations: list[TextObservation] = Field(default_factory=list)
    wire_reviews: list[WireReview] = Field(default_factory=list)
    wire_hypotheses: list[WireHypothesis] = Field(default_factory=list)

    @model_validator(mode="after")
    def references(self):
        def unique(items, label):
            ids = [i.id for i in items]
            if len(ids) != len(set(ids)):
                raise ValueError(f"Duplicate {label} ID")
            return set(ids)
        asset_ids = unique(self.assets, "asset")
        evidence_ids = unique(self.evidence, "evidence")
        unique(self.components, "component")
        terminal_ids = unique([t for c in self.components for t in c.terminals], "terminal")
        unique(self.links, "link")
        unique(self.wire_candidates, "candidate")
        unique(self.text_observations, "text observation")
        unique(self.wire_reviews, "wire review")
        unique(self.wire_hypotheses, "wire hypothesis")
        for evidence in self.evidence:
            if evidence.asset_id not in asset_ids:
                raise ValueError("Evidence references missing asset")
        for claim in self.claims():
            if not set(claim.evidence_ids) <= evidence_ids:
                raise ValueError("Claim references missing evidence")
        for component in self.components:
            if component.asset_id not in asset_ids:
                raise ValueError("Component references missing asset")
        for link in self.links:
            if link.asset_id not in asset_ids:
                raise ValueError("Link references missing asset")
            for terminal in (link.from_terminal, link.to_terminal):
                if terminal is not None and terminal not in terminal_ids:
                    raise ValueError("Link references missing terminal")
        for candidate in self.wire_candidates:
            if candidate.evidence_id not in evidence_ids:
                raise ValueError("Candidate references missing evidence")
        for observation in self.text_observations:
            if observation.asset_id not in asset_ids or observation.evidence_id not in evidence_ids:
                raise ValueError("Text observation references missing source")
            source=next(e for e in self.evidence if e.id==observation.evidence_id)
            if source.asset_id!=observation.asset_id or source.method!='ocr':
                raise ValueError("Text observation must reference OCR from the same asset")
        for review in self.wire_reviews:
            link = next((l for l in self.links if l.id == review.link_id), None)
            source = next((e for e in self.evidence if e.id == review.evidence_id), None)
            if not link or not source or source.asset_id != review.asset_id or source.method != 'manual_annotation':
                raise ValueError("Wire review requires its link and same-view manual evidence")
            if review.from_terminal == review.to_terminal or {review.from_terminal, review.to_terminal} != {link.from_terminal, link.to_terminal}:
                raise ValueError("Wire review terminal correspondence differs from link")
        for hypothesis in self.wire_hypotheses:
            source=next((e for e in self.evidence if e.id==hypothesis.evidence_id),None)
            if not source or source.asset_id!=hypothesis.asset_id or source.method!='geometry':
                raise ValueError('Hypothesis requires same-image geometry evidence')
            if hypothesis.link_id is not None and not any(l.id==hypothesis.link_id for l in self.links):
                raise ValueError('Hypothesis references missing link')
        return self

    def claims(self):
        for component in self.components:
            yield component.label
            yield component.value
            for terminal in component.terminals:
                yield terminal.name
                yield terminal.pin_mapping
        for link in self.links:
            yield link.connection
