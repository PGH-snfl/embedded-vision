"""The simulated recipe must not be mislabeled as the original photo behavior."""
import json

from fastapi.testclient import TestClient

from backend.api import create_app
from backend.design.hypotheses import as_design_target, infer_candidates
from backend.design.function import simulation_behavior
from test_light_recipe import light_inventory
from test_parts_first import setup


def ambiguous_light_candidate():
    candidate = next(h for h in infer_candidates(light_inventory()) if h.kind == 'light_led')
    return candidate.model_copy(update={
        'title': '주변 밝기에 따른 LED 제어',
        'output_behavior': '빛에 따라 LED 점등 또는 밝기가 변할 수 있지만 방향은 미상입니다.',
    })


def test_ambiguous_original_output_and_simulator_default_are_separate():
    candidate = ambiguous_light_candidate()
    target = as_design_target(candidate)
    assert candidate.output_behavior in target.unknowns[-1]
    assert '미상' not in simulation_behavior(target)
    assert '512보다 크면 LED를 켜고' in simulation_behavior(target)
    assert target.output_behavior != candidate.output_behavior


def test_light_candidate_preview_and_export_report_executed_behavior(tmp_path):
    app = create_app(tmp_path)
    with TestClient(app) as client:
        original, url, _ = setup(client, app, tmp_path)
        endpoint = url.removesuffix('/design')
        plan_path = next((tmp_path / 'planner' / original['project_id']).glob('*.json'))
        plan = json.loads(plan_path.read_text())
        candidate = ambiguous_light_candidate()
        plan.update(inventory=light_inventory().model_dump(mode='json'),
                    function_hypotheses=[candidate.model_dump(mode='json')])
        plan_path.write_text(json.dumps(plan, ensure_ascii=False))
        for target in (tmp_path / 'function_targets' / original['project_id']).glob('*.json'):
            target.unlink()

        options = client.get(endpoint + '/proposals').json()
        preview = options['hypothesis_previews'][0]['proposal']
        assert preview['inferred_behavior'] == candidate.output_behavior
        assert '512보다 크면 LED를 켜고' in preview['simulation_behavior']
        assert preview['behavior'] == preview['simulation_behavior']
        assert 'reading > DARK_THRESHOLD' in preview['firmware']['source']

        response = client.post(endpoint + '/function-candidate', json={
            'expected_revision': original['revision'], 'candidate_id': candidate.id})
        assert response.status_code == 200, response.text
        selected = response.json()
        proposal = selected['proposals'][0]
        assert proposal['simulation_behavior'] == preview['simulation_behavior']
        assert any(candidate.output_behavior in item for item in selected['function']['unknowns'])
        exported = client.get(endpoint + '/workbench', params={
            'recipe': proposal['recipe'], 'function_version': selected['function_version']})
        assert exported.status_code == 200, exported.text
        assert exported.json()['embeddedVision']['simulation_behavior'] == proposal['simulation_behavior']
        assert 'DARK_THRESHOLD = 512' in exported.json()['fileGroups']['group-U1'][0]['content']


def test_lcd_candidate_distinguishes_fixed_text_from_possible_changing_status():
    from test_parts_first import inventory

    candidate = next(h for h in infer_candidates(inventory()) if h.kind == 'lcd_text')
    candidate = candidate.model_copy(update={'display_text': 'Hello'})
    target = as_design_target(candidate)
    assert candidate.output_behavior in target.unknowns[-1]
    assert '고정 표시' in simulation_behavior(target)
    assert 'Hello' in simulation_behavior(target)


def test_inferred_intent_does_not_mislabel_generated_light_behavior():
    from backend.design.function import constrain
    from backend.design.proposals import propose

    observed = as_design_target(ambiguous_light_candidate()).model_copy(update={
        'status': 'INFERRED',
        'output_behavior': '주변 밝기 변화에 반응하는지는 아직 불확실합니다.',
    })
    result = constrain(propose(light_inventory(), function_kind='light_led'), observed)
    proposal = result['proposals'][0]
    assert proposal['function']['output_behavior'] == observed.output_behavior
    assert proposal['behavior'] == proposal['simulation_behavior']
    assert '512보다 크면 LED를 켜고' in proposal['behavior']
