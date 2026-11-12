// A matching photo candidate is not evidence that its physical rating or
// package matches the new design. Unassigned parts are new requirements.
export function selectHypothesisPreview(previews, recommendedId){
 const found=previews.findIndex(p=>p.candidate_id===recommendedId);
 return {index:found<0?0:found, isRecommended:found>=0};
}
export function hypothesisPreviewCopy(isRecommended){
 return isRecommended
  ? {heading:'추천 기능 회로 미리보기',description:'추천 기능을 새 배선과 코드로 구성했습니다.'}
  : {heading:'다른 기능의 회로 미리보기',description:'이 회로는 다른 기능의 예시입니다.'};
}
export function wrapHypothesisPreviews(content,isRecommended){
 return isRecommended?`<section class="function-intent">${content}</section>`:
  `<details class="compact-details function-intent" data-other-previews><summary>다른 기능의 회로 미리보기</summary>${content}</details>`;
}
export function designRequirements(proposal, observedParts=[]){
  const parts=new Map(observedParts.map(p=>[p.id,p]));
  return Object.entries(proposal.specifications||{}).map(([reference,spec])=>{
    const observedId=proposal.assignments?.[reference]??null;
    const observed=observedId?parts.get(observedId):null;
    const replacement=(proposal.replacements||[]).find(r=>r.reference===reference);
    const candidates=(replacement?.candidate_ids||[]).map(id=>parts.get(id)?.name||id);
    return {reference,spec,observedId,observed,candidates,reason:replacement?.reason||'',
      basis:observedId?'candidate':replacement?'replacement':'added'};
  });
}

// Proposed connections only: no photo wires or hidden-net claims.
export function designPreview(proposal,esc,observedParts=[]){
  const specs=Object.entries(proposal.specifications), pins={}, positions={};
  for(const [ref] of specs){
    pins[ref]=[...new Set(proposal.connections.flatMap(w=>[w.from,w.to]).filter(t=>t.startsWith(ref+'.')))];
  }
  const height=Math.max(220,...Object.values(pins).map(p=>p.length*25+100)),width=Math.max(640,specs.length*210);
  const nodes=specs.map(([ref,s],i)=>{
    const x=30+i*210,y=50,ps=pins[ref];
    ps.forEach((p,j)=>positions[p]=[x+150,y+40+j*25]);
    return `<g><rect x="${x}" y="${y}" width="150" height="${Math.max(85,ps.length*25+55)}" rx="${ref.startsWith('R')?0:8}" fill="#f3f7f0" stroke="#315c47" stroke-width="2"/><text x="${x+12}" y="${y+22}" font-weight="bold">${esc(ref)} ${esc(s.value||'')}</text>${ps.map((p,j)=>`<text x="${x+10}" y="${y+45+j*25}">${esc(p.slice(ref.length+1))}</text><circle cx="${x+150}" cy="${y+40+j*25}" r="3" fill="#315c47"/>`).join('')}</g>`;
  }).join('');
  const wires=proposal.connections.map((w,i)=>{
    const a=positions[w.from],b=positions[w.to],lane=height+18+i*12;
    return `<path d="M${a[0]},${a[1]} h${8+i*3} V${lane} H${b[0]+8+i*3} V${b[1]} H${b[0]}" fill="none" stroke="${['#2d7664','#416aa3','#8b672a','#845581'][i%4]}" stroke-width="2"><title>${esc(w.from+' → '+w.to)}</title></path>`;
  }).join('');
  const divider=`<svg viewBox="0 0 800 280" role="img" aria-label="UNO 5V에서 R1 10k, A0 측정점, R2 10k, GND로 연결된 새 분압 회로" style="width:100%;font:16px sans-serif">
    <g fill="none" stroke="#315c47" stroke-width="3"><rect x="35" y="55" width="180" height="170" rx="10"/>
    <path d="M215 90 H320 M385 90 H470 V150 H550 M215 150 H470 M615 150 H680 V210 H215"/>
    <rect x="320" y="77" width="65" height="26" fill="#fbf3dd"/><rect x="550" y="137" width="65" height="26" fill="#fbf3dd"/>
    <circle cx="470" cy="150" r="5" fill="#315c47"/><path d="M680 210 v20 m-22 0 h44 m-35 9 h26 m-19 9 h12"/></g>
    <g fill="#254a3a"><text x="55" y="82" font-weight="bold">Arduino UNO R3</text><text x="165" y="115">5V</text><text x="165" y="145">A0</text><text x="160" y="205">GND</text>
    <text x="313" y="58">R1 · 10kΩ</text><text x="545" y="118">R2 · 10kΩ</text><text x="420" y="182">TP_DIVIDER</text><text x="325" y="265">약 2.5V 예상 · 새 설계값 · 실물 미검증</text></g></svg>`;
  const diagram=proposal.recipe==='arduino_voltage_divider'?divider:`<svg viewBox="0 0 ${width} ${height+proposal.connections.length*12+40}" role="img" aria-label="새 회로 연결 제안" style="width:100%;min-width:560px;font:14px sans-serif">${wires}${nodes}</svg>`;
  const requirements=designRequirements(proposal,observedParts);
  const needed=requirements.map(({reference,spec,observedId,observed,candidates,reason,basis})=>{
    const source=basis==='candidate'?`사진 후보: ${esc(observed?.name||observedId)} · 실물 모델과 사양 대조 필요`
      :basis==='replacement'?`새로 준비·대체 검토${candidates.length?' · 사진 후보: '+candidates.map(esc).join(', '):''}`
      :'사진에서 사용 가능한 부품을 확인하지 못해 새로 준비';
    return `<li><b>${esc(reference)} · ${esc(spec.name)}${spec.value?' · '+esc(spec.value):''}</b><br><span>${source}</span>${reason?`<br><small>${esc(reason)}</small>`:''}</li>`;
  }).join('');
  return `<article class="assembly-step design-preview"><div class="preview-heading"><b>기능에 필요한 부품과 연결</b><span class="tag">새 설계 · 실물 미검증</span></div><p>${esc(proposal.behavior)}</p><p class="micro">기능을 구현하기 위한 설계 사양입니다. 사진 후보의 모델·값이 이 사양과 같다는 뜻은 아닙니다.</p><ul aria-label="기능에 필요한 부품">${needed}</ul>${proposal.simulation_notice?`<p class="micro">${esc(proposal.simulation_notice)}</p>`:''}<div class="proposal-schematic">${diagram}</div><p class="micro">부품값은 새 설계 사양입니다.</p>
  <details class="compact-details"><summary>새 배선 ${proposal.connections.length}개 · 연결표</summary><ul>${proposal.connections.map(w=>`<li>${esc(w.from)} → ${esc(w.to)}</li>`).join('')}</ul></details>
  <details class="compact-details"><summary>이 회로에 맞춘 Arduino 코드 보기</summary><p>${esc(proposal.firmware.execution)}</p><pre class="io-code">${esc(proposal.firmware.source)}</pre></details>
  <details class="compact-details"><summary>선정 이유·남은 준비물</summary><p>${esc(proposal.reason)}</p><ul>${proposal.remaining_parts.map(p=>`<li>${esc(p.name)} × ${p.quantity} · ${p.role==='assembly'?'조립 준비물':'회로에 사용하지 않음'} · ${esc(p.reason)}</li>`).join('')||'<li>없음</li>'}</ul></details></article>`;
}
