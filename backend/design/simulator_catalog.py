"""Read the simulator picker inventory as identification hints, never as a datasheet.

The bundled simulator owns its catalogue. Read the same metadata, localisations
and static picker/board declarations so additions are reflected without keeping
an independent hard-coded copy in the vision service.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / 'third_party' / 'velxio' / 'frontend'


class SimulatorCatalogError(ValueError):
    """The bundled simulator catalogue could not be read reliably."""


def _single_string(block: str, key: str) -> str:
    match = re.search(r'(?m)^\s*' + re.escape(key) + r"\s*:\s*'([^']*)'", block)
    if not match:
        raise SimulatorCatalogError(f'Cannot find {key} in simulator registration')
    return match.group(1)


def _registered_runtime_parts(source: str) -> list[dict]:
    blocks = re.findall(r'data\.components\.push\(\{(.*?)\n\s{6}\}\);', source, re.S)
    if not blocks or len(blocks) != len(re.findall(r'data\.components\.push\(', source)):
        raise SimulatorCatalogError('Cannot read all runtime component registrations')
    parts = []
    for block in blocks:
        part = {key: _single_string(block, key) for key in ('id', 'name', 'category')}
        tags = re.search(r'\btags:\s*\[([^\]]*)\]', block)
        part['tags'] = re.findall(r"'([^']*)'", tags.group(1)) if tags else []
        parts.append(part)
    return parts


def _board_list(picker: str, board_source: str) -> list[dict]:
    board_block = re.search(r'const ALL_BOARDS:\s*BoardKind\[\]\s*=\s*\[(.*?)\];', picker, re.S)
    label_block = re.search(r'export const BOARD_KIND_LABELS:\s*Record<BoardKind, string>\s*=\s*\{(.*?)\n\};', board_source, re.S)
    if not board_block or not label_block:
        raise SimulatorCatalogError('Cannot find static simulator boards')
    ids = re.findall(r"'([^']+)'", board_block.group(1))
    labels: dict[str, str] = {}
    for quoted, bare, value in re.findall(r"(?m)^\s*(?:'([^']+)'|([\w-]+)):\s*'([^']*)'", label_block.group(1)):
        labels[quoted or bare] = value
    if not ids or len(set(ids)) != len(ids) or any(i not in labels for i in ids):
        raise SimulatorCatalogError('Simulator board list and labels do not match')
    return [{'id':i, 'name':labels[i], 'category':'boards', 'tags':[]} for i in ids]


def _korean_board_name(name: str) -> str:
    # Mirrors the fallback in componentKorean.ts; exact translations win.
    for pattern, replacement in ((r'Arduino Uno', '아두이노 우노'), (r'Arduino Nano', '아두이노 나노'),
                                 (r'Arduino Mega', '아두이노 메가'), (r'Raspberry Pi', '라즈베리파이'),
                                 (r'DevKit', '개발 보드'), (r'board', '보드')):
        name = re.sub(pattern, replacement, name, flags=re.I if pattern != 'DevKit' else 0)
    return name


def load_simulator_catalog(frontend: Path = FRONTEND) -> dict:
    """Return picker entries as names and IDs only; mark an unreadable catalogue unavailable.

    `placement` describes picker behavior, not simulation support. It has one
    of: registered, board, board_artwork_only or wire_gesture.
    """
    try:
        metadata = json.loads((frontend/'public/components-metadata.json').read_text(encoding='utf-8'))['components']
        extra=ROOT/'data/watering-parts.json'
        if extra.exists():metadata+=json.loads(extra.read_text(encoding='utf-8'))
        korean = json.loads((frontend/'src/data/componentKorean.json').read_text(encoding='utf-8'))
        if not isinstance(metadata, list) or not metadata or not isinstance(korean, dict):
            raise SimulatorCatalogError('Incomplete simulator catalogue')
        runtime = _registered_runtime_parts((frontend/'src/services/ComponentRegistry.ts').read_text(encoding='utf-8'))
        boards = _board_list((frontend/'src/components/ComponentPickerModal.tsx').read_text(encoding='utf-8'),
                             (frontend/'src/types/board.ts').read_text(encoding='utf-8'))
        board_ids = {board['id'] for board in boards}
        entries = []
        seen = set()
        for item in [*boards, *metadata, *runtime]:
            id = item['id']
            if id in seen:
                # Registry copies of a board are represented by its board entry.
                if id in board_ids:
                    continue
                raise SimulatorCatalogError(f'Duplicate simulator catalogue ID: {id}')
            seen.add(id)
            kind = ('board' if id in board_ids else
                    'board_artwork_only' if id in {'nano-rp2040-connect', 'esp32-devkit-v1'} else
                    'wire_gesture' if id == 'junction' else 'registered')
            translated = korean.get(id, {}).get('name')
            entries.append({'id':id, 'name':item['name'],
                            'korean_name':translated or (_korean_board_name(item['name']) if id in board_ids else item['name']),
                            'category':item['category'], 'tags':item.get('tags', []), 'placement':kind})
        return {'source':'simulator_picker', 'status':'available', 'entries':entries,
                'notice':'시뮬레이터 목록은 부품 식별 참고 자료입니다. 사진 속 존재, 정확한 모델, 핀·정격, 설계 및 시뮬레이션 지원을 보증하지 않습니다. 보드 외형과 배선 분기점은 직접 배치할 수 없습니다.'}
    except (OSError, json.JSONDecodeError, KeyError, TypeError, SimulatorCatalogError):
        return {'source':'simulator_picker', 'status':'unavailable', 'entries':[],
                'notice':'시뮬레이터 부품 목록을 불러오지 못했습니다. 부품 목록 없이 사진을 분석합니다.'}
