"""Functional choices become an actual MCU circuit, not a pinless explanation."""
import json
from copy import deepcopy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.api import create_app
from backend.design.enclosure_analysis import enclosure_workbench
from backend.design.functional_build import validate_build,build_workbench
from backend.design.hypotheses import validate_hypotheses
from backend.design.inventory import inventory_plan
from backend.design.recipes import new_graph
from backend.design.component_completion import SystemReasoning
from test_auto_analysis import upload,wait_job
from test_auto_prototype import candidate
from test_components_first_pipeline import OrderedProvider,reasoning
from test_enclosure_analysis import inputs as enclosure_inputs,study


def build_fixture(kind='dimmer'):
    def part(id,model,purpose,location='internal',parameters=None):
        return {'id':id,'model_id':model,'purpose':purpose,'selection_reason':'기능에 필요한 실행 모델과 연결을 선정',
            'observed_part_ids':[],'module_refs':['housing.control'] if model=='arduino-uno' else [],
            'enclosure_id':'housing','location':location,'parameters':parameters or []}
    def wire(a,b):return {'source':a,'target':b,'purpose':'기능 실행을 위한 연결'}
    parts=[part('U1','arduino-uno','입력 처리와 출력 제어'),part('S1','potentiometer','다이얼 입력','panel')]
    wires=[wire('U1.5V','S1.VCC'),wire('U1.GND','S1.GND'),wire('S1.SIG','U1.A0')]
    if kind=='dimmer':
        parts.extend([part('R1','resistor','LED 전류 제한',parameters=[{'name':'value','value':'220'}]),part('D1','led','밝기 출력','panel')])
        wires.extend([wire('U1.5','R1.1'),wire('R1.2','D1.A'),wire('D1.C','U1.GND')])
        code='#include <Arduino.h>\nvoid setup(){pinMode(5,OUTPUT);}\nvoid loop(){analogWrite(5,analogRead(A0)/4);delay(10);}\n'
        behavior='다이얼을 돌린 만큼 LED 밝기를 조절합니다.'
    else:
        parts.extend([part('M1','servo','입력에 따른 회전','external'),part('PS1','dc-power-supply','별도 5V 모터 전원',parameters=[{'name':'voltage','value':5.0}])])
        wires.extend([wire('PS1.+','M1.V+'),wire('PS1.-','U1.GND'),wire('M1.GND','U1.GND'),wire('U1.9','M1.PWM')])
        code='#include <Arduino.h>\nvoid setup(){pinMode(9,OUTPUT);TCCR1A=_BV(COM1A1)|_BV(WGM11);TCCR1B=_BV(WGM13)|_BV(WGM12)|_BV(CS11);ICR1=40000;OCR1A=2000;}\nvoid loop(){OCR1A=2000+analogRead(A0)*2000L/1023;delay(20);}\n'
        behavior='다이얼에 따라 서보 구동 펄스를 1~2ms로 조절합니다.'
    return {'title':'다이얼 제어 · '+kind,'hypothesis_id':'top','behavior':behavior,'parts':parts,'connections':wires,
        'structures':[{'id':'MOUNT1','label':'제어기 고정판','role':'bracket','shape':'box',
            'size_mm':[60.0,4.0,35.0],'position_mm':[0.0,3.0,-180.0],'purpose':'제어 장치를 지지하는 장착판'}],
        'firmware':code,'design_choices':['원본 내부 대신 기능 실행용 부품을 선정','USB 5V 제어 전원 사용'],
        'acceptance_tests':['다이얼을 양끝으로 돌려 출력 변화를 확인'],'not_implemented':[]}


def build_inputs(kind='dimmer'):
    observed,_,_=enclosure_inputs()
    output=build_fixture(kind)
    raw=reasoning();raw['function_hypotheses']=[candidate('다이얼 입력에 따른 출력 제어','다이얼 회전',output['behavior'],part='pot')]
    raw['enclosure_analysis']=study();raw['functional_build']=output
    hs=validate_hypotheses(raw['function_hypotheses'],observed,{'image'})
    return observed,raw,hs


@pytest.mark.parametrize('kind',['dimmer','servo'])
def test_explicit_parts_values_pins_code_and_mounts_complete_the_function(kind):
    observed,raw,hs=build_inputs(kind);before=observed.model_dump_json()
    selected=validate_build(raw['functional_build'],observed,hs,study())
    p=build_workbench(selected,{'source_graph_sha256':'a'*64},study())
    assert observed.model_dump_json()==before
    assert len(p['boards'])==1 and len(p['wires'])>=6
    assert p['fileGroups']['group-U1'][0]['content']==raw['functional_build']['firmware']
    design=p['embeddedVision']['implementation_design']
    assert design['status']=='DESIGN_SELECTED' and len(design['parts'])==4
    assert all(x['quantity']==1 and x['status']=='DESIGN_SELECTED' for x in design['parts'])
    assert not any(c['properties'].get('evInternalHypothesis') for c in p['components'])
    shell=next(c for c in p['components'] if c['properties'].get('evEnclosure'))
    assert shell['properties']['dimensionsStatus']=='DESIGN_SELECTED'
    assert any(c['properties'].get('evDesignedStructure') for c in p['components'])
    assert p['boards'][0]['properties']['evAssembly']['host']['id']==shell['id']
    panel=next(c for c in p['components'] if c['id']=='S1')
    assert panel['properties']['evAssembly']['pose']['position'][1]>shell['properties']['height']
    if kind=='dimmer':
        assert next(c for c in p['components'] if c['id']=='R1')['properties']['value']=='220'
    else:assert next(c for c in p['components'] if c['id']=='PS1')['properties']['voltage']==5


@pytest.mark.parametrize('edit',['pin','model','unwired','value','property','function','enclosure','module','collision'])
def test_invalid_implementation_does_not_become_a_ready_circuit(edit):
    observed,raw,hs=build_inputs();b=raw['functional_build']
    if edit=='pin':b['connections'][0]['target']='S1.INVENTED'
    if edit=='model':b['parts'][1]['model_id']='imaginary-component'
    if edit=='unwired':b['connections']=[w for w in b['connections'] if not any(s.startswith('D1.') for s in [w['source'],w['target']])]
    if edit=='value':b['parts'][2]['parameters'][0]['value']='UNKNOWN'
    if edit=='property':b['parts'][2]['parameters'][0]['name']='__proto__'
    if edit=='function':b['hypothesis_id']='invented'
    if edit=='enclosure':b['parts'][0]['enclosure_id']='invented'
    if edit=='module':b['parts'][0]['module_refs']=['housing.invented']
    if edit=='collision':b['structures'][0]['id']='build-case-housing'
    with pytest.raises(ValueError):validate_build(b,observed,hs,study())


def test_schema_keeps_all_selected_choices_required_and_two_model_calls():
    observed,raw,_=build_inputs();provider=OrderedProvider(observed,raw)
    plan=inventory_plan(new_graph('a'*32,'arduino_lcd')[0],[('image',Path('unused'))],provider)
    assert [task for task,_ in provider.calls]==['component_inventory','system_reasoning']
    assert provider.calls[1][1]['implementation_catalog']['servo']['pins']==['GND','V+','PWM']
    assert plan['functional_build']==raw['functional_build']
    assert plan['component_datasheet']['functional_build']==raw['functional_build']
    schema=SystemReasoning.model_json_schema()
    for node in [schema,*schema['$defs'].values()]:
        if node.get('type')=='object':assert set(node['required'])==set(node['properties'])


def test_electrical_ratings_are_selected_specs_without_becoming_unsupported_runtime_controls():
    observed,raw,hs=build_inputs();raw['functional_build']['parts'][2]['parameters'].append({'name':'powerRatingW','value':0.25})
    b=validate_build(raw['functional_build'],observed,hs,study());p=build_workbench(b,{},study())
    resistor=next(c for c in p['components'] if c['id']=='R1')
    assert resistor['properties']['evSelectedDesign']['parameters']['powerRatingW']==0.25
    assert 'powerRatingW' not in resistor['properties']


def test_automatic_unsupported_goal_becomes_native_runnable_circuit(tmp_path,monkeypatch):
    monkeypatch.setenv('EMBEDDED_VISION_AUTO_ANALYSIS','1')
    monkeypatch.setattr('backend.planner.jobs.status',lambda:{'configured':True})
    observed,raw,_=build_inputs();app=create_app(tmp_path)
    app.state.auto_analysis.provider_factory=lambda:OrderedProvider(observed,raw)
    with TestClient(app) as c:
        source=upload(c)['graph'];pid=source['project_id'];job=wait_job(c,pid)
        assert job['status']=='done';base=f"/api/projects/{pid}/inventory/{job['plan_id']}"
        offered=c.get(base+'/proposals').json()
        assert offered['selected_hypothesis_id']=='top' and offered['selection_origin']=='automatic'
        assert offered['function']['kind']=='unsupported' and offered['functional_design']['status']=='DESIGN_SELECTED'
        response=c.get(base+'/functional-workbench',params={'function_version':offered['function_version']})
        assert response.status_code==200,response.text
        assert 'analogRead(A0)' in response.json()['fileGroups']['group-U1'][0]['content']
        assert c.get(base+'/enclosure-study').json()['implementation']['status']=='DESIGN_SELECTED'
        sheet=c.get(base+'/datasheet').json()
        assert sheet['implementation_design']['status']=='DESIGN_SELECTED'
        assert c.get('/api/projects/'+pid).json()['graph']==source
        assert c.get(base+'/functional-workbench?function_version='+'0'*64).status_code==409
        c.post(base+'/function',json={'expected_revision':source['revision'],'kind':'unknown','description':'다른 기능을 검토합니다.'})
        assert c.get(base+'/functional-workbench').status_code==422
