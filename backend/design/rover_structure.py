"""Stored 3D visual geometry; it is not an electrical or motion model."""
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from .photo_structure import RelativeGeometry

Coordinate = Annotated[float, Field(ge=-2, le=2, allow_inf_nan=False)]
Dimension = Annotated[float, Field(ge=.002, le=1, allow_inf_nan=False)]
Rotation = Annotated[float, Field(ge=-6.283185307179586, le=6.283185307179586, allow_inf_nan=False)]

class StructureObject(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, allow_inf_nan=False)
    id: str = Field(pattern=r'^[A-Za-z][A-Za-z0-9_-]{0,63}$')
    shape: Literal['box', 'cylinder', 'sphere']
    label: str = Field(min_length=1,max_length=60)
    position: list[Coordinate] = Field(min_length=3,max_length=3)
    size: list[Dimension] = Field(min_length=3,max_length=3)
    rotation: list[Rotation] = Field(default_factory=lambda:[0,0,0],min_length=3,max_length=3)
    color: str = Field(pattern=r'^#[0-9a-fA-F]{6}$')
    photoGeometry: RelativeGeometry | None = None
    @field_validator('label')
    @classmethod
    def nonblank_label(cls,value):
        if not value.strip():raise ValueError('구조물 이름을 입력하세요.')
        return value

class RoverStructure(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    version: Literal[1]
    completion_version: Literal['whole-structure-v1'] | None = None
    objects: list[StructureObject] = Field(max_length=50)
    @model_validator(mode='after')
    def unique_ids(self):
        if len({o.id for o in self.objects})!=len(self.objects):
            raise ValueError('구조물 ID가 중복되었습니다.')
        return self

class SaveRoverStructure(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    function_version: str = Field(pattern=r'^[a-f0-9]{64}$')
    expected_revision: int = Field(ge=0)
    structure: RoverStructure
