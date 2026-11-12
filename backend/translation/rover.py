"""Translate the reviewed MotorKit rover example without executing user code.

The AST comparison allows comments, formatting and constant command values;
other program changes are rejected rather than silently lost. The generated
I2C writes model MotorKit's PCA9685 channels and braking behavior, not motors.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import math
from pathlib import Path
from string import Template

from ..design.robot_physical import CODE

COMMANDS = ('forward', 'backward', 'left', 'right', 'stop')
MAX_SOURCE_LENGTH = 50_000


class UnsupportedTranslation(ValueError):
    """Source semantics or destination cannot be translated reliably."""


def _extract(source: str) -> dict[str, tuple[float, float]]:
    if not isinstance(source, str) or not source or len(source) > MAX_SOURCE_LENGTH:
        raise UnsupportedTranslation('Python 코드는 1~50,000자여야 합니다.')
    try:
        tree = ast.parse(source)
        expected = ast.parse(CODE)
        def command_node(t):
            found = [n for n in t.body if isinstance(n, ast.Assign) and len(n.targets) == 1
                     and isinstance(n.targets[0], ast.Name) and n.targets[0].id == 'COMMANDS']
            if len(found) != 1:
                raise UnsupportedTranslation('기본 명령 목록을 확인할 수 없습니다.')
            return found[0]
        node = command_node(tree)
        # Reject duplicate keys before literal_eval can silently collapse them.
        if not isinstance(node.value, ast.Dict) or len(node.value.keys) != len(COMMANDS):
            raise UnsupportedTranslation('명령 목록에는 기본 명령 5개가 필요합니다.')
        raw = ast.literal_eval(node.value)
        if not isinstance(raw, dict) or set(raw) != set(COMMANDS):
            raise UnsupportedTranslation('명령 이름은 기본 전진·후진·회전·정지 5개만 지원합니다.')
        values = {}
        for key in COMMANDS:
            pair = raw[key]
            if not isinstance(pair, (tuple, list)) or len(pair) != 2:
                raise UnsupportedTranslation('각 명령은 좌우 모터 출력 2개가 필요합니다.')
            if any(type(x) not in (int, float) or not math.isfinite(x) or not -1 <= x <= 1 for x in pair):
                raise UnsupportedTranslation('모터 출력은 -1부터 1까지의 숫자여야 합니다.')
            values[key] = (float(pair[0]), float(pair[1]))
        if values['stop'] != (0.0, 0.0):
            raise UnsupportedTranslation('정지 명령은 양쪽 출력 0이어야 합니다.')
        # Replace only the allowed expression, then compare the entire AST.
        normalized = copy.deepcopy(tree)
        command_node(normalized).value = ast.Constant(value=None)
        command_node(expected).value = ast.Constant(value=None)
        if ast.dump(normalized, include_attributes=False) != ast.dump(expected, include_attributes=False):
            raise UnsupportedTranslation('명령 값 외에 코드 동작이 변경되어 자동 변환할 수 없습니다.')
        return values
    except UnsupportedTranslation:
        raise
    except (SyntaxError, ValueError, TypeError, RecursionError, MemoryError, OverflowError) as exc:
        raise UnsupportedTranslation('코드 문법 또는 명령 값을 분석할 수 없습니다.') from exc


def translate_rover_code(source: str, target: str) -> dict:
    values = _extract(source)
    if target not in ('raspberry_pi_c', 'arduino_cpp'):
        raise UnsupportedTranslation('지원하지 않는 변환 대상입니다.')
    rows = ',\n'.join('    {"%s", %.17g, %.17g}' % (k, *values[k]) for k in COMMANDS)
    name = 'pi_rover.c' if target == 'raspberry_pi_c' else 'arduino_rover.ino'
    template = Path(__file__).with_name('pi_rover.c.in' if target == 'raspberry_pi_c' else 'arduino_rover.ino.in').read_text(encoding='utf-8')
    code = Template(template).substitute(command_rows=rows)
    details = [
        '기본 Raspberry Pi MotorKit 예제에서 명령별 좌우 출력값만 바꾼 코드에 한해 변환합니다. 임의의 다른 프로그램은 지원하지 않습니다.',
        '두 모터의 출력 방향·속도와 정지 시 제동을 기준으로 재구성했습니다. PWM 해상도와 타이밍은 반올림되어 완전히 같지 않습니다.',
        '변환된 소스는 실물 시험 전입니다. 모터 방향·전원·배선을 확인하고 바퀴를 띄워 짧게 시험하세요.',
        'I²C 오류나 전원 장애 시 소프트웨어 정지는 보장되지 않습니다. 별도의 모터 전원 차단 스위치가 필요합니다.',
    ]
    if target == 'raspberry_pi_c':
        details += ['Raspberry Pi 4B + Adafruit Motor HAT #2348, 기본 I²C 버스 /dev/i2c-1 및 주소 0x60 기준입니다. I²C 활성화와 접근 권한이 필요합니다.',
                    '컴파일: cc -std=c11 -Wall -Wextra -o pi_rover pi_rover.c -lm  ·  실행: ./pi_rover forward --seconds 1']
    else:
        details += ['Arduino Uno + Adafruit Motor Shield V2를 따로 준비하고 모터 전원을 포함해 다시 배선해야 합니다. Raspberry Pi HAT를 그대로 끼우는 설계가 아닙니다.',
                    '업로드 후 시리얼 모니터 115200 baud에서 forward, backward, left, right, stop 뒤에 선택적으로 초(0~2)를 입력합니다. 예: forward 1',
                    '명령 실행 중에는 시리얼 입력을 처리하지 않아 stop 명령은 최대 2초 늦게 적용됩니다. 즉시 정지는 별도 전원 차단 스위치를 사용하세요.',
                    '원본 Raspberry Pi는 터미널 명령행 인자, Arduino는 시리얼 명령을 사용합니다. 무선·자율 주행 기능은 추가되지 않습니다.']
    return {'code': code, 'filename': name,
            'notice': '지원된 2륜 로봇 코드 변환 · 실물 동작 미검증', 'details': details,
            'source_sha256': hashlib.sha256(source.encode('utf-8')).hexdigest()}
