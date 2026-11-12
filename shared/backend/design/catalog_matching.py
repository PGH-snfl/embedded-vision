"""Match model observations to *possible* simulator entries, never as evidence."""
import re

# Words common to whole categories do not establish identity on their own.
_STOP = {'module', 'sensor', 'board', 'arduino', 'part', 'component',
         '모듈', '센서', '보드', '부품', '아두이노', '개발', '시스템', '후보',
         '소형', '대형', '중형', '일반', '계열', '미니', '작은', '큰'}


def _aliases(value):
    text = str(value).casefold()
    for original, replacement in (('브레드보드', '빵판'), ('브레드 보드', '빵판'),
                                  ('우노', 'uno'), ('나노', 'nano'), ('메가', 'mega')):
        text = text.replace(original, replacement)
    return text


def _normal(value):
    return re.sub(r'[^a-z0-9가-힣]+', '', _aliases(value))


def _tokens(value):
    return {t for t in re.findall(r'[a-z0-9]+|[가-힣]+', _aliases(value))
            if len(t) >= 2 and t not in _STOP and not re.fullmatch(r'\d+(?:k|m|ohm|v|ma|uf|nf|pf)?', t)}


def _score(part, entry):
    # Markings and model candidates can be incomplete; matching never verifies them.
    observations = [part.name, *part.model_candidates, *part.markings]
    labels = [entry['id'], entry['name'], entry['korean_name']]
    best = 0
    for observation in observations:
        a = _normal(observation)
        if len(a) < 2:
            continue
        for label in labels:
            b = _normal(label)
            if a == b:
                best = max(best, 100)
            elif len(a) >= 4 and (a in b or b in a) and len(b) >= 4:
                best = max(best, 80)
            else:
                common = _tokens(observation) & _tokens(label)
                # Common family terms alone are not sufficient to claim a model.
                if common:
                    model_tokens = {t for t in common if re.search(r'[a-z]', t) and re.search(r'\d', t)}
                    best = max(best, 75 if model_tokens else 40 + min(20, 5 * len(common)))
    # An explicitly named model in the observation outranks alternatives the
    # model listed merely as candidates. This remains a name match, not proof.
    primary = _tokens(part.name)
    identifiers = {t for t in primary if t in {'uno', 'nano', 'mega', 'pico'}
                   or (re.search(r'[a-z]', t) and re.search(r'\d', t))}
    label_tokens = set().union(*(_tokens(label) for label in labels))
    if identifiers & label_tokens:
        best += 100
    # Size is a tie-breaker only after a meaningful component-name match.
    if best and any(word in _aliases(part.name) for word in ('소형', '미니', 'mini')):
        if any(word in _aliases(' '.join(labels)) for word in ('소형', '미니', 'mini')):
            best += 10
    return best


def match_inventory(inventory, catalog):
    """Return ranked, explicitly tentative matches; leave absent matches empty."""
    matches = []
    for part in inventory.parts:
        ranked = sorted(((score, item) for item in catalog['entries']
                         if (score := _score(part, item)) > 0),
                        key=lambda pair: (-pair[0], pair[1]['id']))
        # A distinctive model match outranks broad generic words such as '온도'.
        if ranked and ranked[0][0] >= 75:
            ranked = [pair for pair in ranked if pair[0] >= 75]
        ranked = ranked[:5]
        matches.append({
            'part_id': part.id,
            'candidates': [{'id': item['id'], 'name': item['korean_name'],
                            'availability': ('available' if item['placement'] in {'registered','board'} else
                                             'unavailable' if item['placement'] in {'board_artwork_only','wire_gesture'}
                                             else 'unknown'),
                            'placement': item['placement']} for _, item in ranked],
            'note': ('목록 이름을 비교한 참고 후보입니다. 사진 속 모델이나 핀·정격이 확인된 것은 아닙니다.'
                     if ranked else '목록에서 일치하는 이름을 찾지 못했습니다. 목록에 없거나 이름이 다를 수 있습니다.'),
        })
    return {'status': 'ready', 'source': catalog['source'], 'entry_count': len(catalog['entries']),
            'notice': catalog['notice'], 'matches': matches}
