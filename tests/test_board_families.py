"""Model names must not conflate a Linux Pi, Pico, and Arduino-class boards."""
import pytest

from backend.design.models import Inventory, ObservedPart
from backend.design.proposals import compatible, family, propose
from backend.design.recipes import recipe_info


def part(name, kind='board', *, status='INFERRED', candidates=None, pid='part'):
    return ObservedPart(id=pid, kind=kind, name=name, model_candidates=candidates or [],
        quantity=1, status=status, markings=[],
        regions=[{'asset_id':'image','x0':0,'y0':0,'x1':.5,'y1':.5}],
        evidence='모델 후보', checks_needed=['실물 모델 확인'])


@pytest.mark.parametrize(('name','expected'), [
    ('Raspberry Pi 4 Model B', 'raspberry_pi'),
    ('Raspberry Pi 5', 'raspberry_pi'),
    ('Raspberry Pi Zero 2 W', 'raspberry_pi'),
    ('Raspberry Pi Pico', 'pico'),
    ('Raspberry Pi Pico W RP2040', 'pico'),
    ('Raspberry-Pi-Pico 2 RP2350', 'pico'),
    ('RP2040 development board', None),
    ('Raspberry', None),
    ('Arduino UNO R3', 'uno'),
    ('ESP32 DevKit', 'esp32'),
])
def test_board_family(name,expected):
    assert family(part(name))==expected


def test_conflicting_candidates_and_unknown_are_not_resolved_arbitrarily():
    assert family(part('Raspberry Pi 4',candidates=['Raspberry Pi Pico'])) is None
    assert family(part('Raspberry Pi 4',status='UNKNOWN')) is None


@pytest.mark.parametrize('name',['Raspberry Pi 4','Raspberry Pi Pico','RP2040 board','unknown board'])
def test_unsupported_boards_never_assigned_as_uno_or_esp32(name):
    observed=part(name,pid='board')
    for recipe in ['arduino_led_button','esp32_led_button']:
        assert not compatible(observed,recipe,recipe_info()[recipe]['slots']['U1'])
    inventory=Inventory(summary='사진 후보',parts=[observed,part('LED','led',pid='led'),
        part('push button','button',pid='button')],suggested_function='',unknowns=[])
    result=propose(inventory,function_kind='button_led')
    for proposal in result['proposals']:
        assert proposal['assignments']['U1']!='board'
        if proposal['recipe']=='arduino_led_button':
            # UNO may be explicitly offered as a new replacement, not as an
            # identification of the photographed incompatible board.
            assert proposal['assignments']['U1'] is None
            assert 'U1' in proposal['added_parts']
