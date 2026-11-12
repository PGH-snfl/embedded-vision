export function textAdvice(state,textId,componentId,esc){
  const g=state.data.graph;
  const row=state.data.review_assist?.[state.assetId]?.texts.find(t=>t.text_id===textId);
  if(!row)return '<div class="pin-advice">문자 영역을 선택하면 부품별 라벨 분리 후보를 표시합니다.</div>';
  const owner=row.owners.find(o=>o.component_id===componentId);
  const part=g.components.find(c=>c.id===componentId);
  const saved=new Set((part?.terminals||[]).map(t=>String(t.name.value||'').toUpperCase()));
  return `<div class="pin-advice"><strong>문자가 속한 부품 확인</strong><p>${row.ownership_ambiguous?'영역이 겹치거나 소속이 불명확합니다. 사진을 보고 직접 선택하세요.':'가까운 부품 후보입니다. 실제 소속을 확인하세요.'}</p><div class="observation-list">${row.owners.map(o=>`<button type="button" data-text-owner="${esc(o.component_id)}" class="${owner===o?'selected':''}">${esc(o.label)}${o.relation==='near_edge'?' · 경계 근처':''}</button>`).join('')||'해당 문자 가까이에서 찾은 부품이 없습니다. 부품 영역을 확인하세요.'}</div>${owner?`<p>원문에서 분리한 이름 후보 · 클릭 후 실제 핀을 찍으세요.</p><div class="observation-list">${owner.tokens.map((t,i)=>`<button type="button" data-label-token="${i}" ${saved.has(t.label.toUpperCase())?'disabled':''}>${esc(t.label)}${saved.has(t.label.toUpperCase())?' · 저장됨':''}</button>`).join('')||'분리할 수 있는 라벨이 없습니다. 직접 읽고 입력하세요.'}</div>${owner.unparsed.length?`<p>해석하지 않은 원문: ${owner.unparsed.map(t=>esc(t.text)).join(' / ')}</p>`:''}<small>OCR가 빠뜨린 이름은 추가하지 않습니다. 글자 위치를 실제 핀 위치로 사용하지 않습니다.</small>`:'<p>부품을 선택하면 그 종류에 맞는 문자 분리 후보가 표시됩니다.</p>'}</div>`;
}

export function wireAdvice(proposal,esc){
  if(!proposal)return '';
  const labels={READY:'핀 대응 후보 있음',MISSING_PIN:'핀 위치 필요',AMBIGUOUS:'핀 대응 모호',EXISTING:'기존 연결 있음'};
  return `<div class="pin-advice wire-advice"><strong>${labels[proposal.state]}</strong><p>${esc(proposal.reason)}</p>${proposal.matches.map((matches,i)=>`<p>끝점 ${i+1}: ${matches.map(m=>`${esc(m.label)} (${m.distance_px.toFixed(1)}px)`).join(' / ')||'가까운 지정 핀 없음'}</p>`).join('')}${proposal.state==='READY'?'<small>아래 핀 선택은 거리 기반 제안입니다. 실제 접촉을 확인해야 저장할 수 있습니다.</small>':''}${proposal.existing_link_id?'<button type="button" id="existing-proposal-link">기존 연결 검토</button>':''}</div>`;
}
