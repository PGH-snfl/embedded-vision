"""Real error handling with mocked HTTP; never contact OpenAI."""
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.application import create_app
from backend.planner.errors import ProviderFailure, http_failure
from backend.planner.provider import ResponsesProvider, SPECIALIST
from test_auto_analysis import graph, wait_job
from test_analysis_model_selection import photo


def mock_http(monkeypatch, handler):
    original = httpx.Client
    calls = []
    def record(request):
        calls.append(json.loads(request.content))
        return handler(request)
    monkeypatch.setattr('backend.planner.provider.api_key', lambda: 'unit-test-only')
    monkeypatch.setattr('backend.planner.jobs.status', lambda: {'configured': True})
    monkeypatch.setattr('backend.planner.provider.httpx.Client',
                        lambda **kw: original(transport=httpx.MockTransport(record)))
    return calls


@pytest.mark.parametrize('status,code,category', [
    (400, 'unsupported_parameter', 'unsupported_setting'),
    (400, 'invalid_json_schema', 'invalid_schema'),
    (401, 'invalid_api_key', 'authentication'),
    (403, 'permission_denied', 'permission'),
    (404, 'model_not_found', 'not_found'),
    (429, 'insufficient_quota', 'quota'),
    (429, 'rate_limit_exceeded', 'rate_limit'),
    (503, 'server_error', 'provider_server'),
])
def test_http_errors_have_safe_metadata_and_no_retry(monkeypatch, status, code, category):
    secret = 'sk-proj-private-value user-photo-and-source-code'
    calls = mock_http(monkeypatch, lambda req: httpx.Response(status,
        headers={'x-request-id': 'req_unit123'}, json={'error': {
            'code': code, 'param': 'tools[0].environment', 'message': secret}}))
    with pytest.raises(ProviderFailure) as caught:
        ResponsesProvider().infer(SPECIALIST, graph(), 'private-prompt', 'component_inventory', [])
    error = caught.value
    assert len(calls) == 1
    assert error.diagnostic == dict(category=category, model=SPECIALIST,
        task='component_inventory', http_calls=1, http_status=status,
        code=code, param='tools[0].environment', request_id='req_unit123')
    assert secret not in str(error) + json.dumps(error.diagnostic)


@pytest.mark.parametrize('body', [None, [], {'error': []}, {'error': {
    'code': 'sk-proj-credential', 'param': 'sk-proj-credential',
    'message': 'sk-proj-credential'}}])
def test_malformed_errors_do_not_leak_values(body):
    error = http_failure(httpx.Response(400, json=body,
        headers={'x-request-id': 'sk-proj-credential'}), model=SPECIALIST,
        task='component_inventory', http_calls=1)
    assert 'sk-proj-credential' not in str(error) + json.dumps(error.diagnostic)


def test_timeout_is_separate_and_not_retried(monkeypatch):
    def timeout(request):
        raise httpx.ReadTimeout('private-content', request=request)
    calls = mock_http(monkeypatch, timeout)
    with pytest.raises(ProviderFailure) as caught:
        ResponsesProvider().infer(SPECIALIST, graph(), '', 'component_inventory', [])
    assert caught.value.diagnostic['category'] == 'timeout' and len(calls) == 1
    assert 'private-content' not in str(caught.value)


def test_real_shell_output_limit_mismatch_has_a_specific_safe_explanation():
    error=http_failure(httpx.Response(400,json={'error':{'param':'input','message':
        'The max_output_length in shell_call_output 12000 and shell_call 2000 do not match.'}}),
        model=SPECIALIST,task='component_inventory',http_calls=3)
    assert error.diagnostic['category']=='tool_output_limit_mismatch'
    assert '출력 길이 설정' in str(error)


def test_no_credits_is_not_a_temporary_rate_limit_even_with_no_error_code():
    error=http_failure(httpx.Response(429,json={'error':{'code':None,'message':
        'You have no credits remaining. Add credits to continue using the API.'}}),
        model=SPECIALIST,task='component_review',http_calls=1)
    assert error.diagnostic['category']=='quota'
    assert '크레딧이 부족' in str(error)


def test_incomplete_token_limit_is_not_an_http_error(monkeypatch):
    mock_http(monkeypatch, lambda req: httpx.Response(200, json={
        'status': 'incomplete', 'incomplete_details': {'reason': 'max_output_tokens'}}))
    with pytest.raises(ProviderFailure) as caught:
        ResponsesProvider().infer(SPECIALIST, graph(), '', 'component_inventory', [])
    assert caught.value.diagnostic['reason'] == 'max_output_tokens'
    assert '토큰 한도' in str(caught.value)


def test_first_failed_inspection_checkpoints_stage_and_attempted_call(tmp_path, monkeypatch):
    monkeypatch.setenv('EMBEDDED_VISION_AUTO_ANALYSIS', '1')
    calls = mock_http(monkeypatch, lambda req: httpx.Response(400, json={
        'error': {'code': 'unsupported_parameter', 'param': 'parallel_tool_calls',
                  'message': 'Unsupported parameter; private image bytes'}}))
    app = create_app(tmp_path)
    with TestClient(app) as client:
        response = client.post('/api/projects', files=photo(), data={'analysis_model': SPECIALIST})
        pid = response.json()['graph']['project_id']
        job = wait_job(client, pid)
        assert job['status'] == 'error' and job['failed_stage'] == 'components'
        assert job['error']['param'] == 'parallel_tool_calls'
        assert job['component_inspection']['skill']['http_calls'] == 1
        assert len(calls) == 1 and job['plan_id'] is None
        assert (tmp_path/(pid+'.png')).is_file()
        assert 'private image' not in json.dumps(job)
