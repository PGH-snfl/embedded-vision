"""One versioned contract for every image/video input, never a success report."""
from shared.paths import PROJECT_ROOT
from copy import deepcopy
from functools import lru_cache
import hashlib
import json
from pathlib import Path

WORKFLOW_FILE = PROJECT_ROOT / 'data/workflows/photo-system-v1.json'
STAGE_ORDER = ('input', 'components', 'function', 'completion', 'datasheet', 'circuit',
               'structure', 'assembly', 'editor', 'simulation', 'verification')

@lru_cache(maxsize=1)
def _definition():
    data = json.loads(WORKFLOW_FILE.read_text())
    if tuple(s['id'] for s in data['stages']) != STAGE_ORDER:
        raise ValueError('공통 워크플로우의 단계 순서가 올바르지 않습니다.')
    if data['input_modes'] != ['photo', 'video'] or data['default_destination'] != 'interactive_simulator':
        raise ValueError('공통 입력과 시뮬레이션 목표를 확인하세요.')
    from .design.board_profiles import board_profiles
    data['board_workflow'] = board_profiles()
    raw = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    return {**data, 'sha256': hashlib.sha256(raw).hexdigest()}

def workflow_definition():
    return deepcopy(_definition())

def workflow_stamp():
    data = _definition()
    return {k: deepcopy(data[k]) for k in ('id', 'version', 'sha256', 'default_destination', 'viewer', 'board_workflow')} | {
        'stage_order': list(STAGE_ORDER), 'kind': 'processing_contract',
        'notice': '공통 처리 규칙입니다. 모든 단계의 완료나 실행 성공을 뜻하지 않습니다.'}

def workflow_prompt():
    data = _definition()
    stages = '\n'.join(f'{i}. {s["title"]}: {s["instruction"]}' for i, s in enumerate(data['stages'], 1))
    return '공통 워크플로우 v' + str(data['version']) + '\n' + stages + '\n규칙:\n' + '\n'.join(data['rules'])

def attach_workflow(project):
    return {**project, 'embeddedVision': {**project.get('embeddedVision', {}), 'workflow': workflow_stamp()}}
