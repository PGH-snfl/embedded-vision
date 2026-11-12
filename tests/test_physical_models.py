from copy import deepcopy
import pytest
from backend.design.rover_circuit import default_rover_circuit
from backend.workbench.rover_export import export_rover_project,import_rover_project,PHYSICAL_MODELS


def test_product_model_metadata_preserves_circuit_and_legacy_drafts():
    circuit=default_rover_circuit()
    exported=export_rover_project(circuit)
    assert {p['id']:p['properties']['evPhysicalModel'] for p in exported['components']}==PHYSICAL_MODELS
    assert import_rover_project(exported)==circuit
    legacy=deepcopy(exported)
    for p in legacy['components']:p['properties'].pop('evPhysicalModel')
    assert import_rover_project(legacy)==circuit
    altered=deepcopy(exported)
    altered['components'][0]['properties']['evPhysicalModel']='adafruit-motor-shield-v2'
    with pytest.raises(ValueError,match='형상'):import_rover_project(altered)
