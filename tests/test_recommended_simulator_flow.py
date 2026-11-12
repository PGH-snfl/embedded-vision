"""Photo-analysis recommendation through simulator export, using isolated test data."""
import json

from fastapi.testclient import TestClient

from backend.api import create_app
from backend.design.hypotheses import infer_candidates
from test_function_hypotheses import led_inventory
from test_parts_first import setup


def seed_analysis(client, app, root, *, unsupported_first=False):
    original, url, _ = setup(client, app, root)
    project = original['project_id']
    plan_path = next((root / 'planner' / project).glob('*.json'))
    plan = json.loads(plan_path.read_text())
    inventory = led_inventory()
    candidates = [h.model_dump(mode='json') for h in infer_candidates(inventory)]
    if unsupported_first:
        # A supported alternative must not replace a more plausible unsupported
        # function solely because it happens to have a simulation recipe.
        unsupported = dict(candidates[0], id='robot_behavior', kind='unsupported',
                           title='자동 주차 기능 추정', plausibility='medium')
        candidates = [dict(candidates[0], plausibility='low'), unsupported]
    plan.update(inventory=inventory.model_dump(mode='json'),
                function_hypotheses=candidates, hypothesis_source='multimodal_model')
    plan_path.write_text(json.dumps(plan, ensure_ascii=False))
    for path in (root / 'function_targets' / project).glob('*.json'):
        path.unlink()
    return original, url.removesuffix('/design')


def test_top_led_candidate_to_simulator_export_preserves_photo(tmp_path):
    app = create_app(tmp_path)
    with TestClient(app) as client:
        original, endpoint = seed_analysis(client, app, tmp_path)
        response = client.get(endpoint + '/proposals')
        assert response.status_code == 200
        options = response.json()
        assert options['recommended_hypothesis_id'] == 'led_output'
        assert any(p['candidate_id'] == 'led_output' and p['proposal']['simulator_supported']
                   for p in options['hypothesis_previews'])
        selected = client.post(endpoint + '/function-candidate', json={
            'expected_revision': original['revision'], 'candidate_id': 'led_output'})
        assert selected.status_code == 200, selected.text
        proposal = selected.json()
        assert proposal['recommended'] == 'arduino_led_output'
        result = client.get(endpoint + '/workbench', params={
            'recipe': proposal['recommended'], 'function_version': proposal['function_version']})
        assert result.status_code == 200, result.text
        project = result.json()
        assert project['embeddedVision']['basis'] == 'proposed_design_only'
        assert not project['embeddedVision']['physical_verified']
        assert project['embeddedVision']['recipe'] == 'arduino_led_output'
        assert project['boards'][0]['boardKind'] == 'arduino-uno'
        assert {'breadboard', 'led', 'resistor'} <= {c['metadataId'] for c in project['components']}
        assert project['wires'] and project['fileGroups']['group-U1'][0]['content']
        assert client.get('/api/projects/' + original['project_id']).json()['graph'] == original


def test_unsupported_top_candidate_is_not_replaced_by_simulatable_alternative(tmp_path):
    app = create_app(tmp_path)
    with TestClient(app) as client:
        original, endpoint = seed_analysis(client, app, tmp_path, unsupported_first=True)
        options = client.get(endpoint + '/proposals').json()
        assert options['recommended_hypothesis_id'] == 'robot_behavior'
        previews = options['hypothesis_previews']
        assert not any(p['candidate_id'] == 'robot_behavior' for p in previews)
        assert any(p['candidate_id'] == 'led_output' and p['proposal']['simulator_supported'] for p in previews)
        selected = client.post(endpoint + '/function-candidate', json={
            'expected_revision': original['revision'], 'candidate_id': 'robot_behavior'})
        assert selected.status_code == 200, selected.text
        assert selected.json()['function']['kind'] == 'unsupported'
        assert not selected.json()['proposals']
        assert client.get(endpoint + '/workbench', params={'recipe': 'arduino_led_output'}).status_code == 422
        alternative = client.post(endpoint + '/function-candidate', json={
            'expected_revision': original['revision'], 'candidate_id': 'led_output'})
        assert alternative.status_code == 200, alternative.text
        assert alternative.json()['recommended'] == 'arduino_led_output'


def browser_fixture(root, unsupported_first=False):
    """Create a disposable, synthetic model result for a manual browser check."""
    from backend.design.inventory import POLICY_VERSION
    from backend.planner.service import digest

    if (root / 'projects.sqlite3').exists():
        raise ValueError('Use an empty, disposable fixture directory.')
    app = create_app(root)
    with TestClient(app) as client:
        original, endpoint = seed_analysis(client, app, root, unsupported_first=unsupported_first)
        graph = app.state.store.get(original['project_id'])
        job = {'id': 'f' * 32, 'project_id': graph.project_id, 'revision': graph.revision,
               'graph_sha256': digest(graph), 'policy': POLICY_VERSION,
               'status': 'done', 'message': '브라우저 검증용 가상 분석 결과입니다.',
               'plan_id': endpoint.rsplit('/', 1)[-1]}
        directory = root / 'auto_jobs'
        directory.mkdir(exist_ok=True)
        (directory / (graph.project_id + '.json')).write_text(json.dumps(job, ensure_ascii=False))
    return original['project_id']


if __name__ == '__main__':
    import argparse
    from pathlib import Path

    parser = argparse.ArgumentParser(description='Generate a disposable browser-test project')
    parser.add_argument('root', type=Path)
    parser.add_argument('--unsupported-first', action='store_true')
    args = parser.parse_args()
    print(browser_fixture(args.root, args.unsupported_first))
