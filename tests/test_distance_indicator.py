import subprocess
from pathlib import Path

from backend.design.distance_indicator import distance_design, DISTANCE_CONNECTIONS
from backend.emulator.toolchain import ROOT, compile_firmware
from backend.workbench.breadboard import projected_nets


def test_complete_distance_workbench_has_consistent_nets_and_code():
    design = distance_design()
    project = design['workbench']
    components = {c['id']: c for c in project['components']}
    assert components['S1']['metadataId'] == 'hc-sr04'
    assert components['LCD1']['metadataId'] == 'lcd1602'
    assert components['D1']['metadataId'] == 'led'
    assert project['fileGroups']['group-U1'][0]['content'] == design['code']['source']
    expected = [{'start': {'componentId': a.split('.')[0], 'pinName': a.split('.')[1]},
                 'end': {'componentId': b.split('.')[0], 'pinName': b.split('.')[1]}}
                for a, b in DISTANCE_CONNECTIONS]
    assert projected_nets(project['wires']) == projected_nets(expected)
    assert '사진의 배선' in design['assumptions'][0]


def test_compiled_uno_code_reads_echo_and_drives_near_indicator(tmp_path):
    built = compile_firmware(distance_design()['code']['source'], tmp_path / 'build')
    harness = Path(__file__).with_name('distance_sensor_harness.c')
    executable = tmp_path / 'distance-harness'
    lib = ROOT / 'lib/x86_64-linux-gnu'
    subprocess.run(['cc', '-O2', '-I' + str(ROOT / 'include/simavr'), str(harness),
                    '-L' + str(lib), '-Wl,-rpath,' + str(lib), '-lsimavr', '-o', str(executable)],
                   check=True, capture_output=True, text=True)
    def run(distance):
        return subprocess.run([str(executable), str(built['elf']), str(distance)], check=True,
                              capture_output=True, text=True, timeout=15).stdout
    near, far, missing = run(10), run(34), run(0)
    assert 'Distance: 10 cm' in near and 'LED=1' in near
    assert 'Distance: 34 cm' in far and 'LED=0' in far
    assert 'No echo' in missing and 'LED=0' in missing
