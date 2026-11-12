"""Standard-library functional evaluator shared by the service and export.

The model must already have been validated. This does not use GPIO, execute
firmware, model electrical behavior, or reproduce physical systems.
"""

from math import isfinite


def _validate_runtime_input(value, signal):
    if signal["type"] == "boolean":
        if not isinstance(value, bool):
            raise ValueError(f"{signal['id']}: boolean value required")
        return
    try:
        valid = not isinstance(value, bool) and isinstance(value, (int, float)) and isfinite(value)
    except OverflowError:
        valid = False
    if not valid:
        raise ValueError(f"{signal['id']}: finite numeric value required")
    if ((signal.get("min") is not None and value < signal["min"])
            or (signal.get("max") is not None and value > signal["max"])):
        raise ValueError(f"{signal['id']}: input value is outside its bounds")


def _matches(value, condition):
    other = condition["value"]
    return {
        "eq": lambda: value == other,
        "ne": lambda: value != other,
        "lt": lambda: value < other,
        "lte": lambda: value <= other,
        "gt": lambda: value > other,
        "gte": lambda: value >= other,
    }[condition["operator"]]()


def evaluate_virtual_model(model, input_values=None):
    """Evaluate one stateless step. First matching rule wins per output."""
    if input_values is None:
        input_values = {}
    if not isinstance(input_values, dict):
        raise ValueError("input_values must be an object")
    inputs = {signal["id"]: signal for signal in model["inputs"]}
    if input_values.keys() - inputs.keys():
        raise ValueError("unknown input signal")
    state = {}
    for signal in model["inputs"]:
        value = input_values.get(signal["id"], signal["default"])
        _validate_runtime_input(value, signal)
        state[signal["id"]] = value

    executable = [r for r in model["rules"] if r["enabled"] and r["status"] != "UNKNOWN"]
    unsupported_rules = [r["id"] for r in model["rules"] if r["status"] == "UNKNOWN"]
    covered = {output_id for rule in executable for output_id in rule["set"]}
    values = {signal["id"]: signal["default"] if signal["id"] in covered else None for signal in model["outputs"]}
    sources = {signal["id"]: {"source": "assumed_default" if signal["id"] in covered else "unsupported"} for signal in model["outputs"]}
    written = set()
    applied = []
    for rule in executable:
        checks = [_matches(state[c["input"]], c) for c in rule["conditions"]]
        if (all(checks) if rule["match"] == "all" else any(checks)):
            applied_outputs = []
            for output_id, value in rule["set"].items():
                if output_id not in written:
                    values[output_id] = value
                    sources[output_id] = {"source": "rule", "rule_id": rule["id"], "status": rule["status"]}
                    written.add(output_id)
                    applied_outputs.append(output_id)
            if applied_outputs:
                applied.append({"id": rule["id"], "status": rule["status"], "outputs": applied_outputs})

    uncovered = [signal["id"] for signal in model["outputs"] if signal["id"] not in covered]
    if not covered:
        status = "unsupported"
    elif uncovered or unsupported_rules or model["unsupported_requirements"]:
        status = "partial"
    else:
        status = "ready"
    return {
        "status": status,
        "target_board": model["target_board"],
        "inputs": state,
        "outputs": values,
        "output_sources": sources,
        "applied_rules": applied,
        "unsupported_outputs": uncovered,
        "unsupported_rules": unsupported_rules,
        "unsupported_requirements": model["unsupported_requirements"],
        "assumptions": model["assumptions"],
        "simulation_type": "abstract_functional",
        "notice": "가정한 규칙을 평가한 가상 기능 시뮬레이션입니다. CPU, 펌웨어, 전기 회로, 주변 장치 및 물리 동작을 재현하지 않습니다.",
    }
