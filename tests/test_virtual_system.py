"""Functional model is constrained data, not arbitrary code or hardware emulation."""

from copy import deepcopy
import json
import subprocess
import sys

import pytest
from pydantic import ValidationError

from backend.simulation.virtual_system import export_raspberry_pi_virtual_script, simulate_virtual_model, validate_virtual_model


@pytest.fixture
def parking_model():
    return {
        "target_board": "raspberry_pi",
        "inputs": [
            {"id": "distance", "label": "거리", "type": "number", "default": 50, "min": 0, "max": 300, "unit": "cm"},
            {"id": "space_free", "label": "빈 공간", "type": "boolean", "default": True},
        ],
        "outputs": [
            {"id": "drive", "label": "주행", "type": "boolean", "default": False},
            {"id": "alert", "label": "경고", "type": "boolean", "default": False},
        ],
        "rules": [
            {"id": "stop", "conditions": [{"input": "distance", "operator": "lte", "value": 10}], "set": {"drive": False, "alert": True}, "status": "INFERRED"},
            {"id": "proceed", "conditions": [{"input": "space_free", "operator": "eq", "value": True}, {"input": "distance", "operator": "gt", "value": 10}], "match": "all", "set": {"drive": True}, "status": "INFERRED"},
        ],
        "assumptions": ["가상 규칙이며 실제 차량 동작은 검증되지 않았습니다."],
        "unsupported_requirements": ["차량의 물리 운동과 장애물 위치는 재현하지 않습니다."],
    }


def test_threshold_and_priority_are_deterministic_and_board_independent(parking_model):
    near = simulate_virtual_model(parking_model, {"distance": 10})
    far = simulate_virtual_model(parking_model, {"distance": 10.1})
    assert near["outputs"] == {"drive": False, "alert": True}
    assert near["applied_rules"][0]["id"] == "stop"
    assert far["outputs"] == {"drive": True, "alert": False}
    assert far["output_sources"]["alert"]["source"] == "assumed_default"
    assert far["status"] == "partial"
    arduino = deepcopy(parking_model)
    arduino["target_board"] = "arduino"
    assert simulate_virtual_model(arduino, {"distance": 10})["outputs"] == near["outputs"]
    assert simulate_virtual_model(parking_model, {"distance": 10}) == near
    assert near["simulation_type"] == "abstract_functional"
    assert "펌웨어" in near["notice"]


def test_first_rule_wins_for_each_output(parking_model):
    parking_model["rules"].insert(0, {"id": "priority", "conditions": [{"input": "distance", "operator": "gt", "value": 0}], "set": {"drive": True}})
    result = simulate_virtual_model(parking_model, {"distance": 5})
    assert result["outputs"] == {"drive": True, "alert": True}
    assert result["output_sources"]["drive"]["rule_id"] == "priority"
    assert result["output_sources"]["alert"]["rule_id"] == "stop"


def test_unknown_rules_never_execute_and_uncovered_outputs_are_null(parking_model):
    parking_model["rules"] = [{"id": "unknown", "conditions": [{"input": "space_free", "operator": "eq", "value": True}], "set": {"drive": True}, "status": "UNKNOWN", "enabled": False}]
    result = simulate_virtual_model(parking_model)
    assert result["status"] == "unsupported"
    assert result["outputs"] == {"drive": None, "alert": None}
    assert result["unsupported_rules"] == ["unknown"]
    assert result["applied_rules"] == []


@pytest.mark.parametrize("values", [
    {"distance": -1}, {"distance": 301}, {"distance": True},
    {"distance": float("nan")}, {"distance": float("inf")},
    {"distance": 10**400},
    {"space_free": 1}, {"surprise": True},
])
def test_bad_input_values_are_rejected(parking_model, values):
    with pytest.raises(ValueError):
        simulate_virtual_model(parking_model, values)


@pytest.mark.parametrize("change", [
    lambda m: m["rules"][0]["conditions"][0].update(input="missing"),
    lambda m: m["rules"][0]["set"].update(missing=True),
    lambda m: m["rules"][0]["set"].update(drive=3),
    lambda m: m["rules"][0]["conditions"][0].update(operator="__import__('os').system('false')"),
    lambda m: m["rules"][0]["conditions"][0].update(value="__import__('os')"),
    lambda m: m["inputs"][0].update(id="__import__('os')"),
    lambda m: m["inputs"][1].update(id="distance"),
    lambda m: m["inputs"][0].update(default=float("inf")),
    lambda m: m.update(target_board="unsafe_device"),
])
def test_unsafe_or_invalid_model_rejected(parking_model, change):
    change(parking_model)
    with pytest.raises((ValidationError, ValueError)):
        validate_virtual_model(parking_model)


def test_any_conditions_and_no_state_is_carried_between_calls(parking_model):
    parking_model["rules"][0]["conditions"].append({"input": "space_free", "operator": "eq", "value": False})
    parking_model["rules"][0]["match"] = "any"
    assert simulate_virtual_model(parking_model, {"distance": 50, "space_free": False})["outputs"]["alert"] is True
    assert simulate_virtual_model(parking_model, {"distance": 50, "space_free": True})["outputs"]["alert"] is False


def test_raspberry_pi_python_export_matches_server_in_fresh_process(parking_model, tmp_path):
    script = tmp_path / "virtual_system.py"
    script.write_text(export_raspberry_pi_virtual_script(parking_model), encoding="utf-8")
    for inputs in ({}, {"distance": 10}, {"distance": 10.1}, {"space_free": False}):
        result = subprocess.run([sys.executable, "-I", str(script)], input=json.dumps(inputs), text=True, capture_output=True, check=True)
        assert json.loads(result.stdout) == simulate_virtual_model(parking_model, inputs)
    invalid = subprocess.run([sys.executable, "-I", str(script)], input='{"distance": NaN}', text=True, capture_output=True)
    assert invalid.returncode != 0
    assert not invalid.stdout
    assert "non-finite" in invalid.stderr


def test_export_serializes_untrusted_text_as_data(parking_model, tmp_path):
    marker = tmp_path / "must_not_exist"
    attack = "'); __import__('pathlib').Path(" + repr(str(marker)) + ").touch(); #"
    parking_model["inputs"][0]["label"] = "'); __import__('os').system('true'); #"
    parking_model["assumptions"] = [attack]
    script = tmp_path / "virtual_system.py"
    script.write_text(export_raspberry_pi_virtual_script(parking_model), encoding="utf-8")
    result = subprocess.run([sys.executable, "-I", str(script)], input="{}", text=True, capture_output=True, check=True)
    assert json.loads(result.stdout)["assumptions"] == [attack]
    assert not marker.exists()
    assert "eval(" not in script.read_text()
    assert "exec(" not in script.read_text()


def test_export_requires_raspberry_pi(parking_model):
    parking_model["target_board"] = "arduino"
    with pytest.raises(ValueError, match="Raspberry Pi"):
        export_raspberry_pi_virtual_script(parking_model)
