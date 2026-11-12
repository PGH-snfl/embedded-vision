import json

from backend.design.watering_prototype import RECIPE, SOURCE, watering_proposal, watering_workbench
from backend.emulator.toolchain import command, compile_firmware
from backend.workbench.breadboard import projected_nets


def test_watering_project_contains_sensor_mosfet_separate_supply_and_real_pump_load():
    p = watering_proposal()
    project = watering_workbench({'source_project':'test'})
    assert p['recipe'] == project['embeddedVision']['recipe'] == RECIPE
    assert p['simulator_supported'] and not p['hardware_verified']
    assert not project['embeddedVision']['physical_verified']
    assert 'MOSFET' in p['name'] and '펌프' in p['simulation_notice']
    assert p['physical_design']['status'] == 'REFERENCE_DESIGN'
    assert {'soil-moisture-sen0193','mosfet-irlz44n','dc-water-pump','dc-power-supply','diode-1n5822'} <= {c['metadataId'] for c in project['components']}
    environment=[c for c in project['components'] if c['metadataId']=='ev-structure']
    assert {c['properties']['environmentKind'] for c in environment} == {'planter','reservoir','hose'}
    assert all(c['properties']['visualOnly'] for c in environment)
    assert not {c['id'] for c in environment}&{w[e]['componentId'] for w in project['wires'] for e in ('start','end')}
    assert project['embeddedVision']['environment_design_version']==2
    assert project['embeddedVision']['watering_circuit_version']==2
    assert next(c for c in project['components'] if c['id']=='S1')['properties']['value']==560
    assert len(project['wires'])==26
    assert project['fileGroups']['group-U1'][0]['content'] == SOURCE
    nets = projected_nets(project['wires'])
    assert frozenset({'U1.A0','S1.SIG'}) in nets
    assert frozenset({'U1.5','R1.1','RG1.1'}) in nets
    assert any({'D1.C','U1.GND','S1.GND','Q1.S','PS1.-'}<=net for net in nets)
    assert any({'PS1.+','M1.+','D2.C','C1.+'}<=net for net in nets)
    assert any({'M1.-','Q1.D','D2.A'}<=net for net in nets)
    assert not any({'PS1.+','U1.5V'}<=net for net in nets)
    assert not any(w.get('bb') and w['start']['componentId'] in {'M1','Q1','PS1'} for w in project['wires'])
    # Keep power terminals away from the breadboard's automatic seating region.
    assert all(c['y']<75 for c in project['components'] if c['id'] in {'M1','Q1','PS1','D2','C1','C2'})


def test_environment_manifest_and_web_preset_are_identical():
    from backend.design.environment_objects import PRESET, environment_components
    from pathlib import Path
    frontend=Path(__file__).resolve().parents[1]/'third_party/velxio/frontend/src/components/circuitiny/environmentPresets.json'
    assert json.loads(PRESET.read_text())==json.loads(frontend.read_text())
    parts=environment_components()
    assert next(c for c in parts if c['id']=='M1')['properties']['waterSystem']['controlPin']==5
    parts[0]['properties']['width']=1
    assert environment_components()[0]['properties']['width']==80


def test_compiled_uno_executes_input_steps_and_reports_actual_output(tmp_path):
    build = compile_firmware(SOURCE,tmp_path)
    output = command([build['runner'],build['elf'],2500,'input_steps'],timeout=30)
    events = [json.loads(line) for line in output.splitlines() if line.startswith('{')]
    uart = ''.join(chr(e['byte']) for e in events if e['event']=='uart')
    readings = []
    for line in uart.splitlines():
        if line.startswith('soil_adc='):
            parts = line.split(',')
            readings.append((int(parts[0].split('=')[1]), int(parts[1].split('=')[1])))
    assert any(raw < 360 and command == 0 for raw, command in readings)
    assert any(500 <= raw <= 625 and command == 1 for raw, command in readings)
    assert any(raw > 625 and command == 0 for raw, command in readings)
    assert not events[-1]['crashed']
