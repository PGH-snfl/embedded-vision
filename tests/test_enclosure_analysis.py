"""Deterministic contracts only; these fixtures do not measure photo inference accuracy."""
import json
from copy import deepcopy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.api import create_app
from backend.design.enclosure_analysis import EnclosureAnalysis, enclosure_workbench, validate_enclosure_analysis
from backend.design.inventory import inventory_plan
from backend.design.models import Inventory
from backend.design.recipes import new_graph
from backend.design.hypotheses import validate_hypotheses
from test_auto_analysis import upload
from test_components_first_pipeline import OrderedProvider, reasoning
from test_parts_first import inventory


def study():
    def module(id, parent, name, role, candidates):
        return dict(id=id,parent_id=parent,name=name,role=role,candidate_parts=candidates,
            required_part_ids=[],purpose=name+' 기능',rationale='외부 표시 기능을 구현하기 위한 후보',
            confidence='medium',status='INFERRED',photo_presence='UNKNOWN',alternatives=['다른 통합 모듈 가능'])
    return dict(summary='예시 외장 내부의 기능 기반 가설',enclosures=[dict(id='housing',name='예시 제어기 외장',
        observed_part_ids=['case','lcd'],structure_object_id=None,hypothesis_ids=['top'],
        rationale='외장과 외부 LCD를 근거로 내부 제어 및 전원부를 가정합니다.',
        modules=[module('control',None,'제어부','controller',['MCU 모듈 예시']),
            module('mcu','control','마이크로컨트롤러','controller',['ATmega 계열 예시']),
            module('supply',None,'전원부','power',['DC 전압 변환 모듈 예시']),
            module('cap','supply','평활 커패시터','passive',['커패시터 · 값 미확인'])],
        assumptions=['외장 내부에 제어 회로가 있다고 가정'],unknowns=['실제 IC 모델·배선·치수'])],
        limitations=['불투명 외장 안의 실물 구성은 관측되지 않았습니다.'])


def inputs():
    observed=inventory()
    case=observed.parts[0].model_copy(update={'id':'case','kind':'other','name':'외장'})
    observed.parts.append(case)
    result=reasoning();result['enclosure_analysis']=study()
    hypotheses=validate_hypotheses(result['function_hypotheses'],observed,{'image'})
    return observed,result,hypotheses


def test_internal_hypotheses_do_not_become_observed_parts_or_add_calls():
    graph,_=new_graph('a'*32,'arduino_lcd');observed,result,_=inputs()
    provider=OrderedProvider(observed,result)
    plan=inventory_plan(graph,[('image',Path('unused'))],provider)
    assert [task for task,_ in provider.calls]==['component_inventory','system_reasoning']
    assert not plan['routing']['specialist_called']
    assert [p['id'] for p in plan['inventory']['parts']]==['board','lcd','pot','case']
    assert plan['enclosure_analysis']==study()
    assert plan['component_datasheet']['enclosure_analysis']==study()
    assert len(plan['required_parts'])==1
    assert all(m['status']=='INFERRED' and m['photo_presence']=='UNKNOWN'
        for case in study()['enclosures'] for m in case['modules'])


@pytest.mark.parametrize('mutation', ['parent','cycle','duplicate','deep','confirmed','presence','observed','function','required','structure'])
def test_rejects_invalid_trees_claims_and_references(mutation):
    observed,result,hypotheses=inputs();raw=deepcopy(study());case=raw['enclosures'][0];nodes=case['modules']
    if mutation=='parent':nodes[0]['parent_id']='missing'
    if mutation=='cycle':nodes[0]['parent_id']='mcu'
    if mutation=='duplicate':nodes[1]['id']='control'
    if mutation=='deep':
        nodes.extend([{**nodes[0],'id':'n3','parent_id':'mcu'},
            {**nodes[0],'id':'n4','parent_id':'n3'},{**nodes[0],'id':'n5','parent_id':'n4'}])
    if mutation=='confirmed':nodes[0]['status']='CONFIRMED'
    if mutation=='presence':nodes[0]['photo_presence']='CONFIRMED'
    if mutation=='observed':case['observed_part_ids']=['unseen']
    if mutation=='function':case['hypothesis_ids']=['invented']
    if mutation=='required':nodes[0]['required_part_ids']=['invented']
    if mutation=='structure':case['structure_object_id']='invented'
    with pytest.raises(ValueError):
        validate_enclosure_analysis(raw,observed,hypotheses,result['required_parts'],None)


def test_bad_references_discard_study_without_changing_the_observed_checkpoint():
    graph,_=new_graph('a'*32,'arduino_lcd');observed,result,_=inputs()
    result['enclosure_analysis']['enclosures'][0]['observed_part_ids']=['missing']
    plan=inventory_plan(graph,[('image',Path('unused'))],OrderedProvider(observed,result))
    assert plan['analysis_complete'] and plan['enclosure_analysis'] is None
    assert len(plan['inventory']['parts'])==4 and plan['required_parts']
    assert any('내부 분해' in w for w in plan['system_model_warnings'])


def test_inspection_project_is_pinless_illustrative_and_keeps_hypotheses():
    analysis=study();original=deepcopy(analysis)
    project=enclosure_workbench(analysis,{'source_project':'a'*32,'source_graph_sha256':'b'*64})
    assert analysis==original
    assert project['boards']==project['wires']==[] and project['fileGroups']=={}
    assert len(project['components'])==5
    assert all(p['metadataId']=='ev-structure' and 'pins' not in p for p in project['components'])
    assert all(p['properties']['dimensionsStatus']=='UNKNOWN' for p in project['components'])
    for p in project['components'][1:]:
        props=p['properties'];assert props['evInternalHypothesis']['photo_presence']=='UNKNOWN'
        assert props['width']>0 and props['depth']>0 and 0<=props['elevation']<90
    assert project['embeddedVision']['recipe']=='enclosure_hypothesis_view'
    assert not project['embeddedVision']['physical_verified']
    assert EnclosureAnalysis.model_validate(analysis)


def test_inspection_endpoint_does_not_need_goal_selection_or_modify_source(tmp_path,monkeypatch):
    monkeypatch.setenv('EMBEDDED_VISION_AUTO_ANALYSIS','0')
    app=create_app(tmp_path)
    with TestClient(app) as client:
        source=upload(client)['graph'];pid=source['project_id'];observed,result,_=inputs()
        plan=inventory_plan(app.state.store.get(pid),[('image',Path('unused'))],OrderedProvider(observed,result))
        folder=tmp_path/'planner'/pid;folder.mkdir(exist_ok=True)
        path=folder/(plan['id']+'.json');path.write_text(json.dumps(plan))
        base=f"/api/projects/{pid}/inventory/{plan['id']}"
        assert client.get(base+'/proposals').json()['enclosure_analysis']==study()
        response=client.get(base+'/enclosure-study');assert response.status_code==200,response.text
        data=response.json();assert data['available'] and data['analysis']==study()
        assert data['workbench']['embeddedVision']['inventory_plan']==plan['id']
        assert client.get('/api/projects/'+pid).json()['graph']==source
        assert json.loads(path.read_text())==plan
        plan['enclosure_analysis']['enclosures'][0]['modules'][0]['parent_id']='missing'
        path.write_text(json.dumps(plan));assert client.get(base+'/enclosure-study').status_code==422
        del plan['enclosure_analysis'];path.write_text(json.dumps(plan))
        legacy=client.get(base+'/enclosure-study').json()
        assert legacy['available'] and legacy['implementation']['status']=='DESIGN_SELECTED'
        assert legacy['workbench']['boards'] and legacy['workbench']['wires']
        plan['enclosure_analysis']=study();plan['inventory']['parts'][0]['name']='changed'
        path.write_text(json.dumps(plan));assert client.get(base+'/enclosure-study').status_code==409
        plan['graph_sha256']='stale';path.write_text(json.dumps(plan))
        assert client.get(base+'/enclosure-study').status_code==409
