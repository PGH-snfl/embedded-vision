import json
import shutil

from backend.design.simulator_catalog import FRONTEND, load_simulator_catalog


def test_catalog_includes_registered_picker_items_and_runtime_additions():
    catalog = load_simulator_catalog()
    items = {item['id']: item for item in catalog['entries']}
    metadata = json.loads((FRONTEND/'public/components-metadata.json').read_text())['components']
    assert {item['id'] for item in metadata} <= items.keys()
    assert len(items) == len(catalog['entries'])
    assert items['arduino-uno']['placement'] == 'board'
    assert items['raspberry-pi-5']['placement'] == 'board'
    assert items['instr-voltmeter']['placement'] == 'registered'
    assert items['custom-chip']['placement'] == 'registered'
    assert items['nano-rp2040-connect']['placement'] == 'board_artwork_only'
    assert items['esp32-devkit-v1']['placement'] == 'board_artwork_only'
    assert items['junction']['placement'] == 'wire_gesture'
    assert items['lcd1602']['korean_name'].startswith('문자 LCD')
    assert not any({'pinCount', 'voltage', 'pins', 'simulation_supported'} & item.keys() for item in items.values())
    assert '보증하지 않습니다' in catalog['notice']


def test_catalog_reads_updated_metadata_and_korean_names(tmp_path):
    for relative in ('public/components-metadata.json', 'src/data/componentKorean.json',
                     'src/services/ComponentRegistry.ts', 'src/components/ComponentPickerModal.tsx', 'src/types/board.ts'):
        target = tmp_path/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(FRONTEND/relative, target)
    path = tmp_path/'public/components-metadata.json'
    metadata = json.loads(path.read_text())
    metadata['components'].append({'id':'new-sensor', 'name':'New Sensor', 'category':'sensors', 'tags':['new']})
    path.write_text(json.dumps(metadata), encoding='utf-8')
    translation = tmp_path/'src/data/componentKorean.json'
    labels = json.loads(translation.read_text())
    labels['new-sensor'] = {'name':'새 센서', 'description':'설명'}
    translation.write_text(json.dumps(labels), encoding='utf-8')
    items = {item['id']:item for item in load_simulator_catalog(tmp_path)['entries']}
    assert items['new-sensor']['korean_name'] == '새 센서'
    assert items['new-sensor']['tags'] == ['new']


def test_missing_catalog_is_not_silently_treated_as_complete(tmp_path):
    catalog = load_simulator_catalog(tmp_path)
    assert catalog['status'] == 'unavailable'
    assert catalog['entries'] == []
    assert '불러오지 못했습니다' in catalog['notice']
