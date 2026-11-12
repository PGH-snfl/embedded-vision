from copy import deepcopy

import pytest

from backend.design.rover_circuit import default_rover_circuit, validate_rover_circuit
from backend.design.robot_physical import robot_rover_design
from backend.workbench.rover_export import export_rover_project, import_rover_project


def test_rover_project_round_trip_preserves_current_positions_wires_and_identities():
    circuit = default_rover_circuit()
    circuit['components'][0].update(x=500, y=510, label='내 라즈베리파이')
    circuit['connections'][2].update(id='edited_wire', to='HAT1.M1.right')
    circuit['connections'].pop(3)  # edited but incomplete draft
    project = export_rover_project(circuit, {'source_graph_sha256': 'abc'})
    assert project['boards'] == []  # never substitute an Arduino or claim a Pi CPU
    assert len(project['components']) == 6
    assert all(p['metadataId'] == 'custom-chip' for p in project['components'])
    assert import_rover_project(project) == circuit
    assert not validate_rover_circuit(import_rover_project(project))['allowed']
    assert project['embeddedVision']['model_type'] == 'visual_interfaces_only'


def test_reviewed_wiring_and_visual_structure_round_trip():
    circuit = default_rover_circuit()
    project = export_rover_project(circuit)
    project['components'].append({'id': 'chassis', 'metadataId': 'ev-structure',
                                  'x': 200, 'y': 100, 'properties': {}})
    recovered = import_rover_project(project)
    assert recovered == circuit
    assert validate_rover_circuit(recovered)['allowed']
    assert project['wires'][0]['start']['pinName'] == 'GPIO40'
    assert '40핀 헤더 전체' in project['embeddedVision']['simulation_notice']


def test_rover_code_is_editable_in_the_pi_visual_component_group():
    project = export_rover_project(default_rover_circuit())
    files = project['fileGroups']['group-chip-U1']
    assert [f['name'] for f in files] == ['pi_rover.py', 'chip.c', 'chip.json']
    assert files[0]['content'] == robot_rover_design()['code']['source']
    assert project['embeddedVision']['robot_code'] == robot_rover_design()['code']
    assert project['embeddedVision']['robot_code_group'] == 'group-chip-U1'
    files[0]['content'] = '# user edited code\n'
    assert validate_rover_circuit(import_rover_project(project))['allowed']


def test_incomplete_rover_can_still_include_code_in_remaining_chip_group():
    circuit = default_rover_circuit()
    circuit['components'] = [p for p in circuit['components'] if p['id'] != 'U1']
    circuit['connections'] = [w for w in circuit['connections'] if not (w['from'].startswith('U1.') or w['to'].startswith('U1.'))]
    project = export_rover_project(circuit)
    assert 'group-chip-U1' not in project['fileGroups']
    assert project['fileGroups']['group-chip-HAT1'][0]['name'] == 'pi_rover.py'
    assert project['embeddedVision']['robot_code_group'] == 'group-chip-HAT1'
    assert not validate_rover_circuit(import_rover_project(project))['allowed']


@pytest.mark.parametrize('mutate', [
    lambda p: p['boards'].append({'id': 'U2', 'boardKind': 'arduino-uno'}),
    lambda p: p['components'].append({'id': 'R1', 'metadataId': 'resistor', 'properties': {}}),
    lambda p: p['components'][0]['properties'].update(chipJson='{"pins":["invented"]}'),
    lambda p: p['components'][0]['properties'].update(wasmBase64='abc'),
    lambda p: p['components'][0]['properties'].update(rotation=90),
    lambda p: p['wires'][0]['start'].update(pinName='GPIO2'),
    lambda p: p['wires'][0]['start'].update(componentId='chassis'),
])
def test_unsupported_changes_are_not_silently_discarded(mutate):
    project = export_rover_project(default_rover_circuit())
    mutate(project)
    with pytest.raises(ValueError):
        import_rover_project(project)


def test_removed_part_is_saved_as_incomplete_draft_and_motion_blocked():
    project = export_rover_project(default_rover_circuit())
    project['components'] = [p for p in project['components'] if p['id'] != 'MOTOR_L']
    project['wires'] = [w for w in project['wires'] if all(
        w[k]['componentId'] != 'MOTOR_L' for k in ('start', 'end'))]
    circuit = import_rover_project(project)
    assert validate_rover_circuit(circuit)['missing_components'] == ['MOTOR_L']
