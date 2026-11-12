"""Observed inventory must precede reasoning and never absorb inferred additions."""
import json
import threading
from copy import deepcopy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.api import create_app
from backend.design.component_completion import SystemReasoning, inventory_digest
from backend.design.function import unknown_function
from backend.design.inventory import inventory_plan
from backend.design.models import Inventory
from backend.design.recipes import new_graph
from test_auto_analysis import upload, wait_job
from test_auto_prototype import candidate
from test_parts_first import inventory


def reasoning():
    h=candidate('문자 표시 시스템','전원 켜기','LCD에 Ready 표시',kind='lcd_text',part='lcd')
    h['display_text']='Ready'
    return {'function':unknown_function().model_dump(mode='json'), 'function_hypotheses':[h],
        'required_parts':[{'id':'ADD_R1','name':'LCD 백라이트 전류 제한 저항','kind':'resistor',
            'quantity':1,'model_candidates':['resistor_axial'],'status':'INFERRED','photo_presence':'UNKNOWN',
            'reason_type':'missing_for_function','purpose':'백라이트 전류 제한',
            'reason':'LCD는 보이지만 백라이트 저항은 확인되지 않아 새 설계에 보완합니다.',
            'basis_part_ids':['lcd'],'hypothesis_ids':['top'],
            'checks_needed':['LCD 백라이트 전압·전류에 맞는 값과 정격 확인']}],
        'system_model':None,'virtual_model':None,'photo_structure':None}


class OrderedProvider:
    def __init__(self, observed=None, result=None):
        self.observed=observed if observed is not None else inventory()
        self.result=result if result is not None else reasoning()
        self.calls=[]
    def infer(self,model,context,prompt,task,assets):
        self.calls.append((task,deepcopy(context)))
        if task=='component_inventory':
            assert 'observed_inventory' not in context
            return self.observed.model_copy(deep=True), {'model':model}
        assert task=='system_reasoning'
        expected=self.observed.model_copy(update={'suggested_function':''})
        assert context['observed_inventory']==expected.model_dump(mode='json')
        assert context['observed_inventory_sha256']==inventory_digest(expected)
        if isinstance(self.result,Exception):raise self.result
        return deepcopy(self.result), {'model':model}


def test_inventory_checkpoint_precedes_function_and_seals_the_observed_list():
    graph,_=new_graph('a'*32,'arduino_lcd');provider=OrderedProvider();snapshots=[]
    def checkpoint(plan):
        assert len(provider.calls)==1
        assert plan['analysis_complete'] is False
        assert plan['function_hypotheses']==[] and plan['required_parts']==[]
        snapshots.append(plan)
    result=inventory_plan(graph,[('image',Path('unused'))],provider,on_inventory=checkpoint)
    assert [task for task,_ in provider.calls]==['component_inventory','system_reasoning']
    assert result['inventory']==snapshots[0]['inventory']
    assert result['id']==snapshots[0]['id'] and result['analysis_complete']
    sheet=result['component_datasheet']
    assert sheet['observed_inventory_sha256']==result['observed_inventory_sha256']
    assert [p['id'] for p in sheet['observed_parts']]==['board','lcd','pot']
    assert sheet['inferred_parts'][0]['id']=='ADD_R1'
    assert sheet['inferred_parts'][0]['photo_presence']=='UNKNOWN'
    assert result['analysis_stages']==['components','function','completion','datasheet']


@pytest.mark.parametrize('edit',[
    {'basis_part_ids':['invented']}, {'hypothesis_ids':['invented']},
    {'status':'CONFIRMED'}, {'photo_presence':'CONFIRMED'}, {'id':'lcd'}])
def test_completion_cannot_invent_observations_or_claim_confirmation(edit):
    raw=reasoning();raw['required_parts'][0].update(edit)
    graph,_=new_graph('a'*32,'arduino_lcd')
    with pytest.raises(ValueError):
        inventory_plan(graph,[('image',Path('unused'))],OrderedProvider(result=raw))


def test_unrecognized_image_does_not_generate_an_ungrounded_system():
    graph,_=new_graph('a'*32,'arduino_lcd')
    provider=OrderedProvider(Inventory(summary='식별 불가',parts=[],suggested_function='',unknowns=['구성품 미확인']))
    result=inventory_plan(graph,[('image',Path('unused'))],provider)
    assert len(provider.calls)==1 and result['function']['status']=='UNKNOWN'
    assert result['required_parts']==[] and result['component_datasheet']['observed_parts']==[]


def test_strict_reasoning_schema_does_not_allow_replacing_inventory():
    schema=SystemReasoning.model_json_schema()
    assert 'parts' not in schema['properties'] and 'required_parts' in schema['properties']
    for node in [schema,*schema['$defs'].values()]:
        if node.get('type')=='object':
            assert node['additionalProperties'] is False
            assert set(node['required'])==set(node['properties'])


def test_components_are_visible_during_reasoning_and_missing_board_can_be_added(tmp_path,monkeypatch):
    monkeypatch.setenv('EMBEDDED_VISION_AUTO_ANALYSIS','1')
    monkeypatch.setattr('backend.planner.jobs.status',lambda:{'configured':True})
    observed=inventory();observed.parts=[p for p in observed.parts if p.id!='board']
    entered=threading.Event();release=threading.Event()
    class Slow(OrderedProvider):
        def infer(self,model,context,prompt,task,assets):
            if task=='system_reasoning':entered.set();assert release.wait(5)
            return super().infer(model,context,prompt,task,assets)
    provider=Slow(observed);app=create_app(tmp_path);app.state.auto_analysis.provider_factory=lambda:provider
    with TestClient(app) as client:
        source=upload(client)['graph'];pid=source['project_id']
        try:
            assert entered.wait(2)
            job=client.get(f'/api/projects/{pid}/auto-analysis').json()['job']
            base=f"/api/projects/{pid}/inventory/{job['plan_id']}"
            partial=client.get(f"/api/projects/{pid}/planner/{job['plan_id']}").json()['plan']
            assert partial['analysis_complete'] is False
            assert [p['id'] for p in partial['inventory']['parts']]==['lcd','pot']
            pending=client.get(base+'/proposals').json()
            assert pending['recommended'] is None and pending['function_hypotheses']==[]
            assert client.post(base+'/function',json={'expected_revision':1,'kind':'lcd_text',
                'description':'Ready 표시','display_text':'Ready'}).status_code==409
        finally:release.set()
        finished=wait_job(client,pid);assert finished['status']=='done'
        assert finished['plan_id']==job['plan_id']
        response=client.get(base+'/datasheet?download=true');assert response.status_code==200
        sheet=response.json();assert sheet['analysis_complete'] and not sheet['hardware_verified']
        assert 'attachment' in response.headers['content-disposition']
        proposal=client.get(base+'/proposals').json()
        assert proposal['selection_origin']=='automatic' and proposal['recommended']=='arduino_lcd'
        selected=next(p for p in proposal['proposals'] if p['recipe']=='arduino_lcd')
        assert selected['assignments']['U1'] is None and 'U1' in selected['added_parts']
        result=client.get(base+'/workbench',params={'recipe':'arduino_lcd','function_version':proposal['function_version']})
        assert result.status_code==200,result.text
        workbench=result.json()
        assert 'lcd.print("Ready")' in workbench['fileGroups']['group-U1'][0]['content']
        assert workbench['embeddedVision']['component_datasheet']==proposal['component_datasheet']
        assert client.get('/api/projects/'+pid).json()['graph']==source
        path=tmp_path/'planner'/pid/(job['plan_id']+'.json');saved=json.loads(path.read_text())
        saved['inventory']['parts'][0]['name']='changed';path.write_text(json.dumps(saved))
        assert client.get(base+'/proposals').status_code==409


def test_reasoning_failure_preserves_checkpoint(tmp_path,monkeypatch):
    monkeypatch.setenv('EMBEDDED_VISION_AUTO_ANALYSIS','1')
    monkeypatch.setattr('backend.planner.jobs.status',lambda:{'configured':True})
    app=create_app(tmp_path);app.state.auto_analysis.provider_factory=lambda:OrderedProvider(result=RuntimeError('기능 분석 실패'))
    with TestClient(app) as client:
        pid=upload(client)['graph']['project_id'];job=wait_job(client,pid)
        assert job['status']=='error' and job['plan_id']
        plan=client.get(f"/api/projects/{pid}/planner/{job['plan_id']}").json()['plan']
        assert len(plan['inventory']['parts'])==3 and plan['analysis_complete'] is False
        assert plan['required_parts']==[] and not plan['executable']
