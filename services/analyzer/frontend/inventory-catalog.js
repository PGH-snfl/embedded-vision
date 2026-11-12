// A simulator catalog match is a suggestion, never an observation of the
// photographed part or a guarantee that the simulator models its behavior.
export function catalogReference(catalog, partId) {
  if (!catalog || catalog.status === 'unavailable' || !Array.isArray(catalog.matches)) return null;
  const match = catalog.matches.find(item => item?.part_id === partId);
  if (!match) return {candidates: [], note: ''};
  return {
    candidates: Array.isArray(match.candidates) ? match.candidates : [],
    note: typeof match.note === 'string' ? match.note : '',
  };
}

export function catalogStatusMessage(catalog) {
  if (!catalog) return '이전 분석 결과에는 시뮬레이터 목록 참조가 없습니다. 다시 분석하면 목록을 참고합니다.';
  if (catalog.status === 'unavailable' || !Array.isArray(catalog.matches)) return '시뮬레이터 부품 목록을 불러오지 못해 이번 분석에는 참고하지 못했습니다.';
  return '시뮬레이터 부품 목록을 참고했습니다. 목록 후보와 사진 속 부품이 같은지는 확인이 필요합니다.';
}

export function renderCatalogReference(catalog, partId, esc) {
  const match = catalogReference(catalog, partId);
  if (!match) return '';
  const availability = value => value === 'unavailable' ? '추가 불가' :
    value === 'available' ? '목록에서 배치 가능 · 동작 확인 필요' : '지원 여부 미확인';
  const candidates = match.candidates.map(candidate =>
    `<li>${esc(candidate.name || candidate.id || '이름 미확인')} · ${availability(candidate.availability)}</li>`
  ).join('');
  return `<div class="catalog-reference"><p><b>시뮬레이터 목록 후보</b> · 사진 속 부품과의 일치 미확인</p>${candidates ? `<ul>${candidates}</ul>` : '<p>일치하는 후보를 확인하지 못했습니다.</p>'}${match.note ? `<p>${esc(match.note)}</p>` : ''}</div>`;
}
