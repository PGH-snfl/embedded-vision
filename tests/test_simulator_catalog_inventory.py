from pathlib import Path

from backend.design.catalog_matching import match_inventory
from backend.design.inventory import inventory_plan
from backend.design.models import Inventory, ObservedPart
from backend.design.recipes import new_graph
from backend.design.simulator_catalog import load_simulator_catalog


def part(name, kind='board', status='INFERRED'):
    return ObservedPart(id='P1', kind=kind, name=name, model_candidates=[], quantity=1,
        status=status, markings=[], regions=[{'asset_id':'image','x0':0,'y0':0,'x1':.5,'y1':.5}],
        evidence='visible candidate', checks_needed=['모델 확인'])


def inventory(p):
    return Inventory(summary='candidate', parts=[p], suggested_function='', unknowns=[])


def test_candidate_matches_are_tentative_and_keep_availability_distinct():
    catalog=load_simulator_catalog()
    source=inventory(part('Arduino Uno'))
    before=source.model_dump(mode='json')
    result=match_inventory(source,catalog)
    assert result['status']=='ready'
    assert result['matches'][0]['candidates'][0]['id']=='arduino-uno'
    assert result['matches'][0]['candidates'][0]['availability']=='available'
    assert '확인된 것은 아닙니다' in result['matches'][0]['note']
    assert source.model_dump(mode='json')==before
    result=match_inventory(inventory(part('nano-rp2040-connect')),catalog)
    assert next(c for c in result['matches'][0]['candidates'] if c['id']=='nano-rp2040-connect')['availability']=='unavailable'


def test_no_match_does_not_force_a_simulator_part_or_match_a_value():
    catalog=load_simulator_catalog()
    for p in [part('MY-UNKNOWN-XYZ-9876'), part('10k 후보', 'potentiometer', 'UNKNOWN')]:
        result=match_inventory(inventory(p),catalog)
        assert result['matches'][0]['candidates']==[]
        assert '찾지 못했습니다' in result['matches'][0]['note']


class CaptureProvider:
    def infer(self, model, context, prompt, task, assets):
        if task=='component_inventory':
            self.context=context
            self.prompt=prompt
        return inventory(part('Arduino Uno')), {'model':'test'}


def test_model_receives_catalog_but_keeps_observation_and_status():
    graph,_=new_graph('b'*32,'arduino_lcd')
    provider=CaptureProvider()
    result=inventory_plan(graph,[('image',Path('unused'))],provider)
    entries=provider.context['simulator_catalog']['entries']
    assert entries
    assert all(entry['placement'] not in {'board','board_artwork_only'} for entry in entries)
    assert not any(entry['id']=='arduino-uno' for entry in entries)
    assert 'board_profiles' not in provider.context
    assert 'board_workflow' not in provider.context['workflow']
    assert '관측 근거가 아니며' in provider.prompt
    assert result['inventory']['parts'][0]['status']=='INFERRED'
    assert result['inventory']['parts'][0]['name']=='Arduino Uno'
    assert result['simulator_catalog']['status']=='ready'


def test_catalog_unavailable_does_not_block_photo_analysis(monkeypatch):
    graph,_=new_graph('b'*32,'arduino_lcd')
    monkeypatch.setattr('backend.design.inventory.load_simulator_catalog', lambda: {
        'source':'simulator_picker','status':'unavailable','entries':[],'notice':'목록을 불러오지 못했습니다.'})
    provider=CaptureProvider()
    result=inventory_plan(graph,[('image',Path('unused'))],provider)
    assert result['simulator_catalog']['status']=='unavailable'
    assert result['simulator_catalog']['matches']==[]
    assert provider.context['simulator_catalog']['entries']==[]
    assert result['inventory']['parts'][0]['name']=='Arduino Uno'


def test_model_name_wins_over_unrelated_generic_temperature_parts():
    catalog=load_simulator_catalog()
    result=match_inventory(inventory(part('온도 센서 DHT22', 'sensor')),catalog)
    ids=[entry['id'] for entry in result['matches'][0]['candidates']]
    assert ids[0]=='dht22'
    assert 'bmp280' not in ids and 'ntc-temperature-sensor' not in ids


def test_korean_generic_candidates_keep_unknown_and_are_not_verified():
    candidate=part('가변저항', 'potentiometer', 'UNKNOWN')
    source=inventory(candidate)
    result=match_inventory(source,load_simulator_catalog())
    ids=[entry['id'] for entry in result['matches'][0]['candidates']]
    assert 'potentiometer' in ids and 'slide-potentiometer' in ids
    assert 'resistor-10k' not in ids
    assert source.parts[0].status=='UNKNOWN'
    assert '확인된 것은 아닙니다' in result['matches'][0]['note']


def test_specific_uno_name_outranks_unrelated_model_candidates():
    board=part('Arduino UNO 계열 개발 보드')
    board.model_candidates=['Arduino Mega', 'Arduino Nano', 'Arduino Nano ESP32']
    candidates=match_inventory(inventory(board),load_simulator_catalog())['matches'][0]['candidates']
    assert candidates[0]['id']=='arduino-uno'


def test_korean_breadboard_alias_does_not_match_small_sound_sensor():
    candidates=match_inventory(inventory(part('소형 브레드보드', 'breadboard')),load_simulator_catalog())['matches'][0]['candidates']
    ids=[candidate['id'] for candidate in candidates]
    assert ids[0] == 'breadboard-mini'
    assert 'small-sound-sensor' not in ids
