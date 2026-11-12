"""Board switching ports the edited source and circuit together, never the photo again."""
from copy import deepcopy
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.application import create_app
from backend.design.board_profiles import board_example,profile_for
from backend.translation.system import convert_system,source_context,local_plan,ConversionNeedsAI,ConversionPlan,FirmwarePlan,button_source

BOARDS=['arduino-uno','raspberry-pi-pico','esp32','raspberry-pi-4']


def firmware_plan(plan):
    return {'firmware':plan['build']['firmware'],'used_gpio_pins':['GP15','GP14'],
            'acceptance_tests':plan['build']['acceptance_tests'],'limitations':[], 'unsupported_requirements':[]}



@pytest.mark.parametrize(('source','target'),[(a,b) for a in BOARDS for b in BOARDS if a!=b])
def test_switches_all_different_board_pairs_with_matching_code_wires_and_runtime(source,target):
    original=board_example(source);before=deepcopy(original)
    original['boards'][0]['compiledProgram']='stale'
    original['boards'][0]['properties']['evSimulationVerification']={'report':{'status':'pass'}}
    before=deepcopy(original);result=convert_system(original,target)
    assert original==before and result['method']=='verified_local_template' and result['provider_calls']==0
    converted=result['workbench'];board=converted['boards'][0]
    assert board['boardKind']==target and 'compiledProgram' not in board
    assert 'evSimulationVerification' not in board['properties']
    assert converted['fileGroups'][board['activeFileGroupId']][0]['name']==profile_for(target)['entry_file']
    assert converted['fileGroups']!=original['fileGroups']
    assert {p['id'] for p in converted['components']}=={p['id'] for p in original['components']}
    for a,b in zip(original['components'],converted['components']):
        assert (a['id'],a['x'],a['y'])==(b['id'],b['x'],b['y'])
        if 'evAssembly' in a['properties']:assert a['properties']['evAssembly']==b['properties']['evAssembly']
    assert result['validation']['behavior']=='not_verified'
    assert board['properties']['evBoardRuntime']['io_test_status']=='not_run'
    assert converted['embeddedVision']['translation_instance']
    assert converted['embeddedVision']['implementation_design']['structures']==original['embeddedVision']['implementation_design']['structures']
    assert {m['source'] for m in result['pin_mapping']}==set(source_context(original)['board_pins'])
    assert all(e['pinName'] in profile_for(target)['component']['pins'] for w in converted['wires'] for e in [w['start'],w['end']] if e['componentId']==board['id'])
    roundtrip=convert_system(converted,source)
    assert roundtrip['workbench']['boards'][0]['boardKind']==source
    assert roundtrip['workbench']['embeddedVision']['translation_instance']!=converted['embeddedVision']['translation_instance']


def test_uuid_component_ids_and_user_modified_values_are_preserved():
    source=board_example('arduino-uno');old=source['components'][1]['id'];new='1b9a-component'
    source['components'][1]['id']=new
    for w in source['wires']:
        for end in [w['start'],w['end']]:
            if end['componentId']==old:end['componentId']=new
    resistor=next(p for p in source['components'] if p['metadataId']=='resistor');resistor['properties']['value']='470'
    r=convert_system(source,'raspberry-pi-pico')['workbench']
    assert new in {p['id'] for p in r['components']}
    assert next(p for p in r['components'] if p['metadataId']=='resistor')['properties']['value']=='470'


@pytest.mark.parametrize('edit',['code','file','short'])
def test_modified_behavior_or_topology_does_not_silently_use_a_button_example(edit):
    source=board_example('arduino-uno')
    if edit=='code':source['fileGroups']['group-U1'][0]['content']=source['fileGroups']['group-U1'][0]['content'].replace('!digitalRead(2)','digitalRead(2)')
    if edit=='file':source['fileGroups']['group-U1'].append({'name':'helper.cpp','content':'int extra(){return 1;}'})
    if edit=='short':source['wires'].append({'id':'short','start':{'componentId':'U1','pinName':'5'},'end':{'componentId':'U1','pinName':'GND'}})
    with pytest.raises(ValueError if edit=='short' else ConversionNeedsAI):convert_system(source,'raspberry-pi-pico')


def test_ai_uses_current_code_once_and_never_reads_images_or_copies_cached_code():
    source=board_example('arduino-uno');plan=local_plan(source,source_context(source),'raspberry-pi-pico')
    source['fileGroups']['group-U1'][0]['content']+='\nvoid customBehavior(){}\n'
    class Planner:
        calls=[]
        def infer(self,model,context,prompt,task,assets):
            self.calls.append((model,task))
            assert task=='system_code_conversion' and assets==[]
            assert 'customBehavior' in context['source_project']['files'][0]['content']
            assert 'embeddedVision' not in context['source_project']
            assert context['target_board']=='raspberry-pi-pico'
            return firmware_plan(plan),{'model':model,'usage':None}
    provider=Planner();result=convert_system(source,'raspberry-pi-pico',allow_ai=True,provider=provider)
    assert len(provider.calls)==1 and result['method']=='circuit_rules_ai_code' and result['provider_calls']==1


@pytest.mark.parametrize('failure',['hardware','pin','literal_pin','missing_function','syntax'])
def test_invalid_ai_code_is_rejected_before_a_target_project_is_created(failure):
    source=board_example('arduino-uno');plan=firmware_plan(local_plan(source,source_context(source),'raspberry-pi-pico'))
    if failure=='hardware':plan['connections']=[]
    if failure=='pin':plan['used_gpio_pins']=['GP99']
    if failure=='literal_pin':plan['firmware']=plan['firmware'].replace('Pin(15,','Pin(22,')
    if failure=='missing_function':plan['unsupported_requirements']=['버튼 입력']
    if failure=='syntax':plan['firmware']='from machine import Pin\nwhile True print(1)\n'
    class Planner:
        def infer(self,*args):return plan,{}
    before=deepcopy(source)
    with pytest.raises(ValueError):convert_system(source,'raspberry-pi-pico',allow_ai=True,provider=Planner())
    assert source==before


def test_api_and_strict_provider_schema(tmp_path):
    schema=FirmwarePlan.model_json_schema()
    for node in [schema,*schema.get('$defs',{}).values()]:
        if node.get('type')=='object':assert set(node['required'])==set(node['properties'])
    with TestClient(create_app(tmp_path)) as client:
        p=board_example('arduino-uno');result=client.post('/api/system-conversions/preview',json={'project':p,'target':'raspberry-pi-pico'})
        assert result.status_code==200 and result.json()['method']=='verified_local_template'
        assert client.post('/api/system-conversions/preview',json={'project':p,'target':'arduino-uno'}).status_code==422
        p['fileGroups']['group-U1'][0]['content']+='\nvoid extra(){}\n'
        response=client.post('/api/system-conversions/preview',json={'project':p,'target':'raspberry-pi-pico'})
        assert response.status_code==409 and response.json()['detail']['code']=='ai_required'
        assert client.post('/api/system-conversions/preview',json={'project':p,'target':'raspberry-pi-pico'},headers={'origin':'https://unrelated.example'}).status_code==403


def test_saas_conversion_uses_its_worker_and_cannot_be_read_from_another_workspace(tmp_path):
    from backend.saas.app import create_saas_app
    from backend.saas.settings import Settings
    from backend.saas.worker import Worker
    origin='http://127.0.0.1:8770';settings=Settings(tmp_path/'saas',origin=origin,development=True,auth_enabled=False)
    with TestClient(create_saas_app(settings),base_url=origin) as client:
        wid=client.get('/api/saas/me').json()['default_workspace']
        response=client.post(f'/api/w/{wid}/system-conversions/preview',headers={'origin':origin,'Idempotency-Key':'test-conversion'},
            json={'project':board_example('arduino-uno'),'target':'raspberry-pi-pico'})
        assert response.status_code==202
        worker=Worker(settings)
        try:assert worker.run_once()
        finally:worker.close()
        status=client.get(response.json()['status_url']).json()
        assert status['status']=='done'
        assert status['result']['data']['workbench']['boards'][0]['boardKind']=='raspberry-pi-pico'
        assert status['result']['data']['provider_calls']==0
        assert client.get(response.json()['status_url'].replace(wid,'a'*32)).status_code==404


def test_provider_uses_the_conversion_schema_without_network_or_image_upload(monkeypatch):
    import httpx
    import backend.planner.provider as mod
    source=board_example('arduino-uno');plan=firmware_plan(local_plan(source,source_context(source),'raspberry-pi-pico'));calls=[]
    def handler(request):
        payload=json.loads(request.content);calls.append(payload)
        assert payload['store'] is False and payload['text']['format']['strict'] is True
        assert set(payload['text']['format']['schema']['properties'])==set(FirmwarePlan.model_fields)
        assert all(c['type']=='input_text' for c in payload['input'][0]['content'])
        return httpx.Response(200,json={'id':'test','status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':json.dumps(plan)}]}],'usage':{}})
    client=httpx.Client
    monkeypatch.setattr(mod,'api_key',lambda:'unit-test-only')
    monkeypatch.setattr(mod.httpx,'Client',lambda **kwargs:client(transport=httpx.MockTransport(handler)))
    result,_=mod.ResponsesProvider().infer(mod.PRIMARY,{},'전환','system_code_conversion',[])
    assert result.used_gpio_pins==['GP15','GP14'] and len(calls)==1


def test_water_environment_is_preserved_once_and_its_controller_pin_follows_conversion():
    source=json.loads(Path('third_party/velxio/frontend/src/__tests__/fixtures/functional-watering-live.json').read_text())['project']
    captured={}
    class Planner:
        def infer(self,model,payload,prompt,task,assets):
            captured.update(payload)
            bindings=payload['portable_model']['bindings'];pins=[b['target_pin'] for b in bindings]
            pump=next(b['target_number'] for b in bindings if b['source_pin']=='9')
            sensor=next(b['target_number'] for b in bindings if b['source_pin']=='A0')
            return {'firmware':f'from machine import Pin, ADC\nfrom time import sleep_ms\npump = Pin({pump}, Pin.OUT)\nsensor = ADC(Pin({sensor}))\nwhile True:\n    pump.value(sensor.read() > 2000)\n    sleep_ms(10)\n',
                    'used_gpio_pins':pins,'acceptance_tests':['환경 객체 보존 검사'],'limitations':['실행 동등성 미검증'], 'unsupported_requirements':[]},{}
    response=convert_system(source,'esp32',allow_ai=True,provider=Planner());result=response['workbench']
    assert {p['id'] for p in source['components']}<={p['id'] for p in result['components']}
    pump=next(p for p in result['components'] if p['metadataId']=='dc-water-pump')
    mapped=next(b['target_number'] for b in captured['portable_model']['bindings'] if b['source_pin']=='9')
    assert pump['properties']['waterSystem']['controlPin']==mapped
    assert sum(p.get('properties',{}).get('environmentKind')=='planter' for p in result['components'])==1


def test_size_limit_is_checked_before_any_model_request():
    p=board_example('arduino-uno');sample=next(x for x in p['components'] if x['metadataId']=='led')
    p['components'].extend({**deepcopy(sample),'id':'EXTRA'+str(i)} for i in range(13))
    class NeverCalled:
        def infer(self,*args):raise AssertionError('No paid call for an oversized project')
    with pytest.raises(ValueError,match='15개'):convert_system(p,'raspberry-pi-pico',allow_ai=True,provider=NeverCalled())


def test_malformed_workspace_payload_returns_validation_error(tmp_path):
    p=board_example('arduino-uno');p['fileGroups']=[]
    with TestClient(create_app(tmp_path)) as client:
        assert client.post('/api/system-conversions/preview',json={'project':p,'target':'raspberry-pi-pico'}).status_code==422
