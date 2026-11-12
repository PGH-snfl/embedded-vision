import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from backend.api import create_app
from backend.design.hypotheses import infer_candidates,validate_hypotheses,candidate_payload
from backend.design.function import FunctionHypothesis
from backend.design.inventory import inventory_plan
from backend.design.recipes import new_graph
from test_parts_first import inventory,setup


def led_inventory():
    inv=inventory()
    inv.parts=[inv.parts[0],inv.parts[1].model_copy(update={'id':'led','kind':'led','name':'외부 LED','evidence':'노란 빛으로 켜진 LED가 보임'}),inv.parts[2].model_copy(update={'id':'r','kind':'resistor','name':'저항','evidence':'저항 몸체가 보임'})]
    return inv


def test_lit_led_has_three_plausible_alternatives_not_confirmed():
    inv=led_inventory();before=inv.model_dump_json();hs=infer_candidates(inv)
    assert [h.id for h in hs]==['led_output','led_blink','led_brightness']
    assert all(h.status=='INFERRED' and h.assumptions and h.distinguishing_check for h in hs)
    assert hs[0].plausibility=='medium' and hs[1].plausibility=='low'
    assert inv.model_dump_json()==before


def test_no_button_is_invented_for_led_only():
    hs=infer_candidates(led_inventory())
    assert not any(h.kind=='button_led' for h in hs)
    assert all(set(h.part_ids)<={'board','led','r'} for h in hs)


def test_bad_part_or_asset_reference_rejected():
    inv=led_inventory();h=infer_candidates(inv)[0].model_dump(mode='json')
    h['part_ids']=['invisible_sensor']
    with pytest.raises(RuntimeError):validate_hypotheses([h],inv,{'image'})
    h=infer_candidates(inv)[0].model_dump(mode='json');h['evidence'][0]['asset_id']='fake'
    with pytest.raises(RuntimeError):validate_hypotheses([h],inv,{'image'})


def test_model_hypotheses_saved_with_provenance():
    inv=led_inventory();hs=infer_candidates(inv)
    class Provider:
        def infer(self,*args):
            from backend.design.function import unknown_function
            return {**inv.model_dump(mode='json'),'function':unknown_function().model_dump(mode='json'),
                    'function_hypotheses':[h.model_dump(mode='json') for h in hs]},{}
    g,_=new_graph('a'*32,'arduino_lcd')
    p=inventory_plan(g,[('image',Path('not-read'))],Provider())
    assert len(p['function_hypotheses'])==3
    assert candidate_payload(p,inv)['hypothesis_source']=='multimodal_model'
    assert candidate_payload({},inv)['hypothesis_source']=='stored_component_observations'


def test_rank_is_qualitative_stable_and_does_not_depend_on_support():
    inv=led_inventory();hs=[h.model_dump(mode='json') for h in infer_candidates(inv)]
    hs[0]['plausibility']='low';hs[1]['plausibility']='medium';hs[1]['kind']='unsupported'
    hs[2]['plausibility']='medium'
    result=candidate_payload({'function_hypotheses':hs,'asset_ids':['image']},inv)
    assert [h['id'] for h in result['function_hypotheses']]==['led_blink','led_brightness','led_output']
    assert result['recommended_hypothesis_id']=='led_blink'
    assert '확률은 아닙니다' in result['hypothesis_note']


def test_inferred_observed_function_is_a_recommendation_with_no_existing_candidates():
    inv=inventory();p={'asset_ids':['image'],'function':{'kind':'lcd_text','status':'INFERRED',
        'summary':'LCD 고정 문자 표시','input_behavior':'전원을 켭니다','output_behavior':'문구가 보입니다',
        'evidence':[{'asset_id':'image','observation':'화면에 Hello 표시'}],
        'unknowns':['문구가 고정인지 미확인'],'acceptance_criteria':[],'display_text':'Hello'}}
    result=candidate_payload(p,inv)
    assert result['recommended_hypothesis_id']=='observed_function'
    h=result['function_hypotheses'][0]
    assert h['kind']=='lcd_text' and h['status']=='INFERRED' and h['display_text']=='Hello'
    assert h['part_ids']==['lcd'] and h['evidence'][0]['asset_id']=='image'


def test_user_defined_function_does_not_replace_observed_recommendation():
    inv=led_inventory();hs=[h.model_dump(mode='json') for h in infer_candidates(inv)]
    p={'asset_ids':['image'],'function_hypotheses':hs,'function':{'kind':'led_blink',
        'status':'USER_DEFINED','summary':'사용자 목표','input_behavior':'','output_behavior':'',
        'evidence':[],'unknowns':[],'acceptance_criteria':[],'display_text':None}}
    assert candidate_payload(p,inv)['recommended_hypothesis_id']=='led_output'


def test_candidate_selection_is_target_not_original_truth(tmp_path):
    app=create_app(tmp_path)
    with TestClient(app) as c:
        original,url,_=setup(c,app,tmp_path)
        path=next((tmp_path/'planner'/original['project_id']).glob('*.json'))
        from test_parts_first import seal_fixture_inventory
        plan=json.loads(path.read_text());plan['inventory']=led_inventory().model_dump(mode='json');plan.pop('function_hypotheses',None);path.write_text(json.dumps(seal_fixture_inventory(plan)))
        # setup() saved an LCD target; the preview exercise starts before any
        # target is selected and must not recreate that file.
        for target in (tmp_path/'function_targets'/original['project_id']).glob('*.json'):target.unlink()
        endpoint=url.removesuffix('/design')
        options=c.get(endpoint+'/proposals').json()
        assert len(options['function_hypotheses'])==3
        assert not options['proposals']  # No automatic conversion to a different function.
        assert options['function']['status']=='UNKNOWN'
        previews=options['hypothesis_previews']
        assert {p['candidate_id'] for p in previews}=={'led_output','led_blink','led_brightness'}
        assert all(p['proposal']['function']['status']=='INFERRED' for p in previews)
        assert all(p['proposal']['connections'] and p['proposal']['firmware']['source'] for p in previews)
        assert not list((tmp_path/'function_targets'/original['project_id']).glob('*.json'))
        response=c.post(endpoint+'/function-candidate',json={'expected_revision':original['revision'],'candidate_id':'led_blink'})
        assert response.status_code==200,response.text
        target=response.json()['function']
        assert target['status']=='USER_DEFINED' and target['kind']=='led_blink'
        assert target['summary']=='일정 간격으로 LED 깜빡이기' and target['unknowns']
        assert response.json()['recommended']=='arduino_led_blink'
        assert response.json()['recommended_hypothesis_id']=='led_output'
        assert {p['candidate_id'] for p in response.json()['hypothesis_previews']}=={'led_output','led_blink','led_brightness'}
        changed=c.post(endpoint+'/function-candidate',json={'expected_revision':original['revision'],'candidate_id':'led_brightness'})
        assert changed.status_code==200 and changed.json()['function']['kind']=='led_brightness'
        assert changed.json()['recommended_hypothesis_id']=='led_output'
        assert c.get('/api/projects/'+original['project_id']).json()['graph']==original
        assert c.post(endpoint+'/function-candidate',json={'expected_revision':999,'candidate_id':'led_blink'}).status_code==409
        assert c.post(endpoint+'/function-candidate',json={'expected_revision':original['revision'],'candidate_id':'invented'}).status_code==422


def test_unsupported_lcd_text_is_retained_as_hypothesis_and_fails_cleanly(tmp_path):
    app=create_app(tmp_path)
    with TestClient(app) as c:
        original,url,_=setup(c,app,tmp_path)
        path=next((tmp_path/'planner'/original['project_id']).glob('*.json'))
        plan=json.loads(path.read_text());inv=inventory()
        h=infer_candidates(inv)[0].model_dump(mode='json');h['display_text']='한글'
        plan['inventory']=inv.model_dump(mode='json');plan['function_hypotheses']=[h];path.write_text(json.dumps(plan))
        endpoint=url.removesuffix('/design')
        result=c.get(endpoint+'/proposals').json()
        assert result['function_hypotheses'][0]['display_text']=='한글'
        assert not result['hypothesis_previews']
        selected=c.post(endpoint+'/function-candidate',json={'expected_revision':original['revision'],'candidate_id':h['id']})
        assert selected.status_code==422 and '16자 이내' in selected.json()['detail']


def test_inferred_lcd_recommendation_can_open_simulator_without_hardware_confirmation(tmp_path):
    app=create_app(tmp_path)
    with TestClient(app) as c:
        original,url,_=setup(c,app,tmp_path)
        path=next((tmp_path/'planner'/original['project_id']).glob('*.json'))
        plan=json.loads(path.read_text());plan['inventory']=inventory().model_dump(mode='json')
        plan['function_hypotheses']=[]
        plan['function']={'kind':'lcd_text','status':'INFERRED','summary':'LCD 문자 표시',
            'input_behavior':'전원이 켜집니다','output_behavior':'LCD에 Hello를 표시합니다',
            'evidence':[{'asset_id':'image','observation':'LCD에 Hello가 표시됨'}],
            'unknowns':['원래 표시가 지속되는지 미확인'],'acceptance_criteria':[],'display_text':'Hello'}
        path.write_text(json.dumps(plan))
        for target in (tmp_path/'function_targets'/original['project_id']).glob('*.json'):target.unlink()
        endpoint=url.removesuffix('/design')
        response=c.get(endpoint+'/proposals');assert response.status_code==200
        data=response.json();assert data['recommended_hypothesis_id']=='observed_function'
        preview=next(p for p in data['hypothesis_previews'] if p['candidate_id']=='observed_function')
        assert preview['proposal']['recipe']=='arduino_lcd' and preview['proposal']['simulator_supported']
        selected=c.post(endpoint+'/function-candidate',json={'expected_revision':original['revision'],'candidate_id':'observed_function'})
        assert selected.status_code==200,selected.text
        choice=selected.json()
        result=c.get(endpoint+'/workbench',params={'recipe':'arduino_lcd','function_version':choice['function_version']})
        assert result.status_code==200,result.text
        assert not result.json()['embeddedVision']['physical_verified']
        assert 'Hello' in result.json()['fileGroups']['group-U1'][0]['content']
