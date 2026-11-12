"""A bounded, deterministic evaluator for *proposed* system behavior.

This is not an emulator: it does not run firmware, model physics, or connect to
hardware. Only the explicitly supplied signal rules are executed. No expression
strings, Python code, network, or file access are accepted.
"""

from __future__ import annotations

from math import isfinite
import json
from pathlib import Path

from .virtual_runtime import evaluate_virtual_model
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator

Identifier = Annotated[str, Field(pattern=r"^[A-Za-z][A-Za-z0-9_]{0,63}$")]
SignalValue = StrictBool | float
Board = Literal["arduino", "raspberry_pi"]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class InputSignal(_StrictModel):
    id: Identifier
    label: str = Field(min_length=1, max_length=120)
    type: Literal["boolean", "number"]
    default: SignalValue
    min: float | None = None
    max: float | None = None
    unit: str = Field(default="", max_length=40)

    @model_validator(mode="after")
    def validate_signal(self):
        _validate_value(self.default, self.type, self.id)
        if self.type == "boolean" and (self.min is not None or self.max is not None):
            raise ValueError(f"{self.id}: boolean inputs cannot have numeric bounds")
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError(f"{self.id}: min must not exceed max")
        _validate_bounds(self.default, self)
        return self


class OutputSignal(_StrictModel):
    id: Identifier
    label: str = Field(min_length=1, max_length=120)
    type: Literal["boolean", "number"]
    default: SignalValue
    unit: str = Field(default="", max_length=40)

    @model_validator(mode="after")
    def validate_signal(self):
        _validate_value(self.default, self.type, self.id)
        return self


class Condition(_StrictModel):
    input: Identifier
    operator: Literal["eq", "ne", "lt", "lte", "gt", "gte"]
    value: SignalValue


class Rule(_StrictModel):
    id: Identifier
    conditions: list[Condition] = Field(min_length=1, max_length=16)
    match: Literal["all", "any"] = "all"
    set: dict[Identifier, SignalValue] = Field(min_length=1, max_length=16)
    status: Literal["CONFIRMED", "INFERRED", "UNKNOWN"] = "INFERRED"
    enabled: bool = True


class VirtualSystemModel(_StrictModel):
    target_board: Board
    inputs: list[InputSignal] = Field(min_length=1, max_length=32)
    outputs: list[OutputSignal] = Field(min_length=1, max_length=32)
    rules: list[Rule] = Field(default_factory=list, max_length=128)
    assumptions: list[str] = Field(default_factory=list, max_length=32)
    unsupported_requirements: list[str] = Field(default_factory=list, max_length=32)

    @model_validator(mode="after")
    def validate_references(self):
        inputs = {item.id: item for item in self.inputs}
        outputs = {item.id: item for item in self.outputs}
        if len(inputs) != len(self.inputs) or len(outputs) != len(self.outputs):
            raise ValueError("signal IDs must be unique within each category")
        if inputs.keys() & outputs.keys():
            raise ValueError("input and output IDs must be distinct")
        if len({rule.id for rule in self.rules}) != len(self.rules):
            raise ValueError("rule IDs must be unique")
        for rule in self.rules:
            for condition in rule.conditions:
                signal = inputs.get(condition.input)
                if signal is None:
                    raise ValueError(f"{rule.id}: unknown input {condition.input}")
                _validate_value(condition.value, signal.type, condition.input)
                if signal.type == "boolean" and condition.operator not in ("eq", "ne"):
                    raise ValueError(f"{rule.id}: boolean signals support eq/ne only")
            for output_id, value in rule.set.items():
                signal = outputs.get(output_id)
                if signal is None:
                    raise ValueError(f"{rule.id}: unknown output {output_id}")
                _validate_value(value, signal.type, output_id)
        return self


def _validate_value(value: SignalValue, signal_type: str, signal_id: str) -> None:
    if signal_type == "boolean":
        if not isinstance(value, bool):
            raise ValueError(f"{signal_id}: boolean value required")
    else:
        try:
            valid = not isinstance(value, bool) and isinstance(value, (int, float)) and isfinite(value)
        except OverflowError:
            valid = False
        if not valid:
            raise ValueError(f"{signal_id}: finite numeric value required")


def _validate_bounds(value: SignalValue, signal: InputSignal) -> None:
    if signal.type == "number" and (
        (signal.min is not None and value < signal.min)
        or (signal.max is not None and value > signal.max)
    ):
        raise ValueError(f"{signal.id}: input value is outside its bounds")


def validate_virtual_model(model: dict | VirtualSystemModel) -> VirtualSystemModel:
    """Validate all types, rule references and limits; never interpret code."""
    return VirtualSystemModel.model_validate(model)



def simulate_virtual_model(model: dict | VirtualSystemModel, input_values: dict | None = None) -> dict:
    """Evaluate one independent control step, without firmware or hardware."""
    validated = validate_virtual_model(model)
    return evaluate_virtual_model(validated.model_dump(mode="json"), input_values)


def export_raspberry_pi_virtual_script(model: dict | VirtualSystemModel) -> str:
    """Return a standalone Python script for Raspberry Pi virtual I/O.

    Model text is JSON encoded and then represented as a Python string literal;
    no model-provided content is interpreted as source code. The exported script
    shares the exact same standard-library evaluator as the server.
    """
    validated = validate_virtual_model(model)
    if validated.target_board != "raspberry_pi":
        raise ValueError("Python export requires a Raspberry Pi target")
    encoded = json.dumps(validated.model_dump(mode="json"), ensure_ascii=True, allow_nan=False, separators=(",", ":"))
    runtime = Path(__file__).with_name("virtual_runtime.py").read_text(encoding="utf-8")
    return runtime + "\n" + _STANDALONE_MAIN.replace("__MODEL_JSON_LITERAL__", repr(encoded))


_STANDALONE_MAIN = r'''

# Virtual I/O only. No GPIO, wiring, firmware, electronics or physics.
import json
import sys

MODEL = json.loads(__MODEL_JSON_LITERAL__)

def _reject_constant(value):
    raise ValueError("non-finite JSON number: " + value)

def main():
    try:
        data = sys.stdin.read(1048577)
        if len(data) > 1048576:
            raise ValueError("input JSON is too large")
        inputs = json.loads(data, parse_constant=_reject_constant)
        if not isinstance(inputs, dict):
            raise ValueError("input JSON must be an object")
        result = evaluate_virtual_model(MODEL, inputs)
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    except (ValueError, TypeError, OverflowError) as exc:
        print("Invalid virtual input: " + str(exc), file=sys.stderr)
        return 2
    return 0

if __name__ == "__main__":
    sys.exit(main())
'''
