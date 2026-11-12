from typing import Literal
from pydantic import Field,model_validator
from ..circuit.schema import StrictModel,ComponentKind
from ..planner.models import Region

class ObservedPart(StrictModel):
    id:str=Field(pattern=r'^[A-Za-z][A-Za-z0-9_-]{0,39}$')
    kind:ComponentKind
    name:str
    model_candidates:list[str]=Field(max_length=6)
    quantity:int=Field(ge=1,le=50)
    status:Literal['INFERRED','UNKNOWN']
    markings:list[str]=Field(max_length=15)
    regions:list[Region]=Field(min_length=1,max_length=6)
    evidence:str
    checks_needed:list[str]=Field(max_length=10)

class Inventory(StrictModel):
    summary:str
    parts:list[ObservedPart]=Field(max_length=40)
    suggested_function:str
    unknowns:list[str]=Field(max_length=30)
    @model_validator(mode='after')
    def unique_parts(self):
        ids=[p.id for p in self.parts]
        if len(ids)!=len(set(ids)):raise ValueError('Duplicate part ID')
        return self

class NewDesign(StrictModel):
    expected_revision:int
    function_version:str=Field(default='',max_length=64)
    function_confirmed:bool=False
    recipe:Literal['esp32_led_button','arduino_lcd','arduino_voltage_divider','arduino_led_output','arduino_led_blink','arduino_led_brightness','arduino_led_button','arduino_light_led']
    assignments:dict[str,str|None]
    accept_added_parts:bool
    parts_verified:bool
    verification_note:str=Field(min_length=5,max_length=1000)
    message:str=Field(default='Hello circuit!',min_length=1,max_length=16,pattern=r'^[A-Za-z0-9 .,!?_-]+$')

class ProposalSimulation(StrictModel):
    expected_revision:int
    recipe:Literal['arduino_voltage_divider']
    analysis:Literal['transient','dc']='transient'
