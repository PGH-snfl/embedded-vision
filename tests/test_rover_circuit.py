"""Only topology compatibility is checked; this is not electrical simulation."""
from copy import deepcopy
import pytest
from pydantic import ValidationError
from backend.design.rover_circuit import RoverCircuit,default_rover_circuit,validate_rover_circuit
from backend.design.robot_physical import robot_rover_design


def test_initial_wiring_matches_the_single_reviewed_proposal():
    circuit=default_rover_circuit()
    expected=robot_rover_design()['connections']
    assert len(circuit['components'])==6 and len(circuit['connections'])==8
    assert {(c['from'],c['to']) for c in circuit['connections']}=={(c['from'],c['to']) for c in expected}
    result=validate_rover_circuit(circuit)
    assert result['allowed'] and not result['errors']
    assert '실제 전압' in result['notice']


def test_positions_wire_ids_direction_and_labels_do_not_change_connectivity():
    circuit=default_rover_circuit()
    circuit['components'][0].update(x=500,y=500,label='이름 변경')
    circuit['connections'].reverse()
    for i,wire in enumerate(circuit['connections']):
        wire.update(id=f'wire_{i}',**{'from':wire['to'],'to':wire['from']})
    assert validate_rover_circuit(circuit)['allowed']


def test_missing_or_incorrect_wiring_is_editable_but_cannot_run():
    circuit=default_rover_circuit()
    circuit['connections'].pop()
    assert RoverCircuit.model_validate(circuit)
    result=validate_rover_circuit(circuit)
    assert not result['allowed'] and result['missing_nets']
    # A dangerous cross-connection is representable as a draft, not runnable.
    circuit['connections'].append({'id':'wrong','from':'BAT1.red','to':'HAT1.PWR.negative'})
    assert RoverCircuit.model_validate(circuit)
    result=validate_rover_circuit(circuit)
    assert not result['allowed'] and result['unexpected_nets']


def test_removing_component_with_its_wires_is_a_valid_incomplete_draft():
    circuit=default_rover_circuit()
    circuit['components']=[c for c in circuit['components'] if c['id']!='MOTOR_L']
    circuit['connections']=[w for w in circuit['connections'] if not (w['from'].startswith('MOTOR_L.') or w['to'].startswith('MOTOR_L.'))]
    assert not validate_rover_circuit(circuit)['allowed']
    assert validate_rover_circuit(circuit)['missing_components']==['MOTOR_L']


@pytest.mark.parametrize('change',[
    lambda c:c.update(version=True),
    lambda c:c['components'][0].update(kind='pi_power'),
    lambda c:c['components'].append(deepcopy(c['components'][0])),
    lambda c:c['components'][0].update(x=float('nan')),
    lambda c:c['connections'][0].update(to='HAT1.INVENTED'),
    lambda c:c['connections'].append({'id':'extra','from':'HAT1.GPIO40','to':'U1.GPIO40'}),
    lambda c:c['connections'][0].update(to=c['connections'][0]['from']),
    lambda c:c['components'].pop(),
])
def test_reject_bad_or_unknown_components_and_terminal_references(change):
    circuit=default_rover_circuit();change(circuit)
    with pytest.raises(ValidationError): RoverCircuit.model_validate(circuit)
