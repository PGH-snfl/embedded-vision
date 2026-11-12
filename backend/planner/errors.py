"""Persist diagnostic metadata, never provider bodies, prompts or credentials."""
import re


class ProviderFailure(RuntimeError):
    def __init__(self, message, *, category, model, task, http_calls, **details):
        super().__init__(message)
        self.diagnostic = dict(category=category, model=model, task=task,
                               http_calls=http_calls, **details)


def http_failure(response, *, model, task, http_calls):
    try:
        body = response.json()
        error = body.get('error', {}) if isinstance(body, dict) else {}
        if not isinstance(error, dict):
            error = {}
    except ValueError:
        error = {}
    # Do not copy error.message: it can echo user input or a credential.
    codes = {'invalid_api_key', 'insufficient_quota', 'rate_limit_exceeded',
             'model_not_found', 'invalid_request_error', 'unsupported_parameter',
             'unsupported_value', 'invalid_value', 'invalid_json_schema',
             'context_length_exceeded', 'permission_denied', 'server_error'}
    code = error.get('code')
    code = code if isinstance(code, str) and code in codes else None
    param = error.get('param')
    if not (isinstance(param, str) and len(param) <= 160
            and re.fullmatch(r'(?:model|tools|text|input|reasoning|include|parallel_tool_calls|max_output_tokens|store|tool_choice)(?:[.\[\]A-Za-z0-9_]+)?', param)):
        param = None
    message = error.get('message', '')
    message = message.lower() if isinstance(message, str) else ''
    status = response.status_code
    if status == 401:
        category, hint = 'authentication', 'API 키 인증에 실패했습니다.'
    elif status == 403:
        category, hint = 'permission', '모델 또는 기능 접근 권한이 없습니다.'
    elif status == 429:
        no_credits=any(s in message for s in ['no credits remaining','insufficient credits','credit balance is depleted'])
        quota=code=='insufficient_quota' or no_credits or 'exceeded your current quota' in message
        category, hint = ('quota', 'OpenAI API 크레딧이 부족합니다. 결제 설정에서 잔액을 확인하세요.') if quota else ('rate_limit', 'API 요청 한도에 도달했습니다.')
    elif status == 400:
        category, hint = 'invalid_request', '요청 형식·설정이 거절됐습니다.'
        if 'max_output_length' in message and 'shell_call_output' in message and 'do not match' in message:
            category, hint = 'tool_output_limit_mismatch', '도구 요청과 응답의 출력 길이 설정이 일치하지 않습니다.'
        elif code == 'invalid_json_schema' or ('schema' in message and 'invalid' in message):
            category, hint = 'invalid_schema', '응답 JSON 형식 정의가 거절됐습니다.'
        elif code in {'unsupported_parameter', 'unsupported_value'} or any(s in message for s in ['not supported', 'unsupported', 'unknown parameter']):
            category, hint = 'unsupported_setting', '지원하지 않는 요청 설정입니다.'
    elif status == 404:
        category, hint = 'not_found', '모델 또는 API 경로를 확인하세요.'
    elif status >= 500:
        category, hint = 'provider_server', 'OpenAI 서버 오류입니다.'
    else:
        category, hint = 'http_error', 'API 요청이 거절됐습니다.'
    request_id = response.headers.get('x-request-id', '')
    request_id = request_id if re.fullmatch(r'req_[A-Za-z0-9_-]{1,100}', request_id) else None
    suffix = (' 항목: ' + param + '.') if param else ''
    if code:
        suffix += ' 코드: ' + code + '.'
    return ProviderFailure(f'OpenAI API HTTP {status}. {hint}{suffix}',
                           category=category, model=model, task=task,
                           http_calls=http_calls, http_status=status,
                           code=code, param=param, request_id=request_id)
