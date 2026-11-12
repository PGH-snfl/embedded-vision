const STATUS={CONFIRMED:'확정',INFERRED:'추정',UNKNOWN:'미확인'};
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export function safeSource(value){try{const u=new URL(value);return ['https:','http:'].includes(u.protocol)?u.href:null;}catch{return null;}}
const norm=v=>String(v||'').toLowerCase().replace(/[^a-z0-9가-힣]/g,'');
const aliases={arduino_uno_r3_interface:['Arduino UNO R3','UNO R3','Arduino Uno Rev3'],esp32_devkitc_v4:['ESP32 DevKitC V4'],wp7113id:['WP7113ID'],b3f1000:['B3F-1000']};
const SOURCE_LABELS={manufacturer_datasheet:'제조사 원본 데이터시트',manufacturer_guide:'제조사 사용 안내',manufacturer_pinout:'제조사 핀 배치 자료',manufacturer_tutorial:'제조사 예제 설명',footprint_library:'KiCad 풋프린트 참고자료',simulation_reference:'시뮬레이터 참고자료'};
export function buildDatasheet(graph,plan,catalog={},designData=null,selection={}){
 const inventory=plan?.inventory?.parts?.length?plan.inventory:null,stale=!!inventory&&(plan.stale||plan.revision!==graph.revision);
 const rows=inventory?.parts||graph.components.map(c=>({id:c.id,kind:c.kind,name:c.label.value||c.id,quantity:1,status:c.label.status,model_candidates:c.label.candidates||[],markings:[],regions:[{asset_id:c.asset_id}],evidence:c.label.reason,checks_needed:[],component:c}));
 const parts=rows.map(p=>{
  const component=p.component;
  const names=new Set([p.name,...p.model_candidates,...p.markings].map(norm).filter(Boolean));
  const refs=Object.entries(catalog).filter(([id,c])=>c.kind===p.kind&&(id===component?.catalog_id||[c.name,...(aliases[id]||[])].some(n=>names.has(norm(n))))).map(([id,c])=>({id,name:c.name,url:safeSource(c.source),note:c.note||'',voltage:c.voltage||null,pins:c.pins||{},kind:SOURCE_LABELS[c.source_type]||'출처 유형 미확인 참고자료',basis:id===component?.catalog_id?'사용자가 지정한 카탈로그 · 실물과 다시 대조 필요':'모델 후보와 일치 · 실물 모델 미확인'}));
  return {id:p.id,name:p.name,quantity:p.quantity,status:STATUS[p.status]?p.status:'UNKNOWN',models:[...p.model_candidates],markings:[...p.markings],evidence:p.evidence,checks:[...p.checks_needed],assets:[...new Set(p.regions.map(r=>r.asset_id))],value:component?.value?.value||null,valueStatus:component?.value?.status||'UNKNOWN',pins:component?.terminals?.map(t=>({label:t.name.value||'미확인',mapping:t.pin_mapping.value,status:t.pin_mapping.status}))||[],references:refs,search:'https://www.google.com/search?q='+encodeURIComponent((p.model_candidates[0]||p.name)+' datasheet manufacturer')};
 });
 const selected=designData?.proposals?.find(p=>p.recipe===(selection.recipe||designData.recommended));
 const prototype=designData?.prototype_details;
 const prototypeSpecs=prototype?.specifications||Object.fromEntries((prototype?.components||prototype?.parts||[])
  .filter(p=>p&&typeof p==='object').map(p=>[p.id,{name:p.name||p.id,value:p.value||null,source:p.source||null,note:p.note||'새 시제품에 선정한 부품이며 사진 속 동일 모델·정격은 미확인입니다.'}]));
 const offered=selected?[{title:designData.function?.summary||selected.name,proposal:selected}]
  :prototype?[{title:prototype.title||prototype.name,proposal:{recipe:prototype.recipe||prototype.id,
    behavior:prototype.simulation_behavior||prototype.simulator?.behavior||prototype.behavior||prototype.summary,
    specifications:prototypeSpecs,assignments:prototype.assignments||{},replacements:prototype.replacements||[],
    function:{status:'INFERRED'}}}]
  :(designData?.hypothesis_previews||[]).filter(p=>!selection.candidateId||p.candidate_id===selection.candidateId).map(p=>({title:p.title,proposal:p.proposal}));
 const designs=stale?[]:offered.map(({title,proposal:p})=>({title,recipe:p.recipe,behavior:p.behavior,
  status:p.function?.status||'INFERRED',parts:Object.entries(p.specifications||{}).map(([ref,s])=>{
   const observed=inventory?.parts?.find(part=>part.id===p.assignments?.[ref]);
   const replacement=(p.replacements||[]).find(r=>r.reference===ref);
   const related=(replacement?.candidate_ids||[]).map(id=>inventory?.parts?.find(part=>part.id===id)).filter(Boolean);
   const catalogEntry=Object.values(catalog).find(c=>c.name===s.name&&c.source===s.source);
   return {ref,name:s.name,value:s.value||null,note:s.note||'',source:safeSource(s.source),
    sourceKind:SOURCE_LABELS[catalogEntry?.source_type]||'참고자료',
    observed:observed?{id:observed.id,name:observed.name,status:observed.status}:null,
    related:related.map(part=>({id:part.id,name:part.name,status:part.status})),
    replacementReason:replacement?.reason||''};
  })}));
 const chosen=selection.candidateId||designData?.selected_hypothesis_id;
 const inferredParts=stale?[]:(plan?.component_datasheet?.inferred_parts||plan?.required_parts||[])
  .filter(p=>!chosen||!p.hypothesis_ids?.length||p.hypothesis_ids.includes(chosen))
  .map(p=>({...p,origin:'inferred_addition',status:'INFERRED',photo_presence:'UNKNOWN',
    references:(p.references||[]).map(ref=>({...ref,url:safeSource(ref.url)}))}));
 return {project:graph.project_id,title:graph.title,revision:graph.revision,analysis:inventory?'사진·영상 부품 분석':['reference_design','synthetic_demo'].includes(graph.mode)?'새 설계·예제 사양 · 실물 식별 결과 아님':'회로 그래프에 기록된 부품',planId:plan?.id||null,stale,createdAt:new Date().toISOString(),summary:inventory?.summary||'현재 프로젝트의 부품 정보를 정리했습니다.',unknowns:inventory?.unknowns||[],parts,designs,inferredParts,
  photoInventory:!!inventory,analysisComplete:plan?.analysis_complete!==false,systemHypotheses:stale?[]:plan?.component_datasheet?.function_hypotheses||plan?.function_hypotheses||[],
  enclosureAnalysis:stale?null:plan?.component_datasheet?.enclosure_analysis||plan?.enclosure_analysis||null,
  implementationDesign:stale?null:designData&&'functional_design' in designData?designData.functional_design:plan?.component_datasheet?.implementation_design||null};
}
export function completionBody(r){
 const additions=r.inferredParts||[];
 return `<section class="component-completion" aria-label="기능 구현용 보완 부품"><h3>기능 구현에 필요한 보완 부품 · ${additions.length}종</h3><p>아래 부품은 사진에서 확인한 목록에 합치지 않습니다. 기능을 구현하기 위한 추정이며 사진 속 존재 여부는 미확인입니다.</p>${!r.analysisComplete?'<p role="status">구성품 목록은 저장됐으며 기능·보완 부품을 분석하고 있습니다.</p>':''}${additions.map(p=>`<article class="datasheet-part"><h4>${esc(p.name)} × ${p.quantity} <small>추정 보완 · 사진 내 존재 미확인</small></h4><p>${esc(p.purpose)}</p><p>${esc(p.reason)}</p><details class="compact-details"><summary>근거·모델 후보·확인할 사양</summary><p>근거 구성품: ${(p.basis_part_ids||[]).map(esc).join(', ')}</p><p>해당 기능 후보: ${(p.hypothesis_ids||[]).map(esc).join(', ')}</p><p>모델 후보: ${(p.model_candidates||[]).map(esc).join(' / ')||'미정'}</p><ul>${(p.checks_needed||[]).map(c=>`<li>${esc(c)}</li>`).join('')}</ul>${(p.references||[]).filter(s=>s.url).map(s=>`<a target="_blank" rel="noopener noreferrer" href="${esc(s.url)}">${esc(SOURCE_LABELS[s.source_type]||'참고자료')} · ${esc(s.name)}</a>`).join('')}<p>값·정격·물리 핀은 자료와 실물을 대조하기 전까지 미확인입니다.</p></details></article>`).join('')}</section>`;
}
export function datasheetBody(r){
 const d=r.implementationDesign;
 const selected=d?`<section class="datasheet-design"><h2>기능 구현 설계 · 부품 선정 완료</h2><p>${esc(d.behavior)}</p>${d.runtime?`<p>선정 보드: ${esc(d.runtime.board_kind)} · 코드: ${esc(d.runtime.language)} · 파일: ${esc(d.runtime.entry_file)}</p><p>${esc(d.runtime.notice)}</p>`:""}<ul>${d.parts.map(p=>`<li><strong>${esc(p.id)} · ${esc(p.name)}</strong> × ${esc(p.quantity)} · ${esc(Object.entries(p.parameters||{}).map(([k,v])=>`${k}=${v}`).join(', '))}<p>${esc(p.purpose)} · ${esc(p.selection_reason)}</p></li>`).join('')}</ul><details><summary>선정 구조·배선·실행 코드</summary>${(d.structures||[]).map(s=>`<p>${esc(s.label)} · ${esc(s.size_mm?.join(' × '))} mm · ${esc(s.purpose)}</p>`).join('')}<ul>${d.connections.map(w=>`<li>${esc(w.source)} → ${esc(w.target)}</li>`).join('')}</ul><pre>${esc(d.firmware?.source||'')}</pre></details></section>`:'';
 return selected+observedDatasheetBody(r);
}
function observedDatasheetBody(r){
 const observed=r.parts.map((p,i)=>`<article class="datasheet-part"><h3>${i+1}. ${esc(p.name)} <small>× ${p.quantity} · ${esc(STATUS[p.status])}</small></h3><dl><dt>모델 후보</dt><dd>${p.models.map(esc).join(' / ')||'미확인'}</dd><dt>읽힌 표식</dt><dd>${p.markings.map(esc).join(' / ')||'미확인'}</dd><dt>값·정격</dt><dd>${p.value?esc(p.value)+' · '+esc(STATUS[p.valueStatus]):'미확인 · 사진만으로 확정하지 않음'}</dd><dt>기록된 핀 매핑</dt><dd>${p.pins.some(t=>t.mapping&&t.status==='CONFIRMED')?p.pins.filter(t=>t.mapping&&t.status==='CONFIRMED').map(t=>esc(t.label)+' → '+esc(t.mapping)).join(', ')+' · 실물 핀과 대조 필요':'미확인 · 원본 자료와 실물 핀을 대조하세요'}</dd></dl><details class="compact-details"><summary>인식 근거·확인할 사항</summary><p>${esc(p.evidence)}</p><ul>${p.checks.map(c=>`<li>${esc(c)}</li>`).join('')||'<li>실물 모델·전원 전압·핀 라벨을 확인하세요.</li>'}</ul><small>${esc(p.id)} · 입력 ${p.assets.map(esc).join(', ')}</small></details><div class="datasheet-sources">${p.references.map(c=>`<details class="compact-details"><summary>${esc(c.name)} · ${esc(c.kind)}</summary><p>${esc(c.basis)}</p>${c.url?`<a class="button" target="_blank" rel="noopener noreferrer" href="${esc(c.url)}">${esc(c.kind)} 열기 ↗</a>`:'<p>유효한 원문 링크 없음</p>'}<p>${esc(c.note)}</p>${c.voltage?`<p>해당 참고 모델의 전압 정보: ${esc(c.voltage)}</p>`:''}<p>자료에 기록된 핀 라벨: ${Object.entries(c.pins).map(([a,b])=>esc(a)+' → '+esc(b)).join(', ')||'미등록'}</p><small>이 정보가 사진 속 부품과 같다는 뜻은 아닙니다. 회로도 표시용 포트와 물리 핀 번호를 구분하세요.</small></details>`).join('')||'<p>일치하는 등록 자료가 없습니다. 정확한 모델을 확인한 후 제조사 자료를 찾으세요.</p>'}<a class="datasheet-search" target="_blank" rel="noopener noreferrer" href="${esc(p.search)}">데이터시트 검색 ↗</a></div></article>`).join('');
 const designs=(r.designs||[]).map(d=>`<section class="datasheet-design"><h3>기능에 필요한 새 부품 · ${esc(d.title)}</h3><p>${esc(d.behavior)} · ${d.status==='USER_DEFINED'?'사용자가 선택한 목표':'추정 기능 · 원본 동작 미확인'}</p><p>아래 값은 새 회로의 설계 사양이며 사진 속 부품의 측정 결과가 아닙니다.</p>${d.parts.map(p=>`<article class="datasheet-part"><h4>${esc(p.ref)} · ${esc(p.name)}${p.value?' · '+esc(p.value):''}</h4><p>${p.observed?'사진의 후보: '+esc(p.observed.name)+' · '+esc(STATUS[p.observed.status]||'미확인')+' · 실제 호환성 확인 필요':p.related.length?'새로 준비 · 사진의 후보와 다른 구성':'새로 준비할 부품'}</p>${p.related.length?`<p>비교할 사진 후보: ${p.related.map(x=>esc(x.name)+' · '+esc(STATUS[x.status]||'미확인')).join(', ')}</p>`:''}${p.replacementReason?`<p>${esc(p.replacementReason)}</p>`:''}<p>${esc(p.note)}</p>${p.source?`<a target="_blank" rel="noopener noreferrer" href="${esc(p.source)}">${esc(p.sourceKind)} 열기 ↗</a>`:''}</article>`).join('')}</section>`).join('');
 return `<p class="datasheet-notice">관측·설계 정보를 정리한 시스템 부품 요약 자료입니다. 제조사가 작성한 원본 데이터시트가 아닙니다. 아래의 원문 링크는 종류별로 구분한 참고자료이며 해당 사진 부품과의 일치는 자동 검증되지 않았습니다. 모델 후보의 정격·핀 배치를 실제 부품에 그대로 적용하지 마세요.</p>`+`${r.stale?'<p class="datasheet-warning">이전 버전 분석입니다. 현재 사진·프로젝트와 다시 대조하세요.</p>':''}<p>${esc(r.summary)}</p><p class="datasheet-meta">프로젝트 ${esc(r.project)} · r${r.revision} · ${esc(r.analysis)} · 관측 ${r.parts.length}종 / 추정 보완 ${(r.inferredParts||[]).length}종</p><h2>1. ${r.photoInventory?'사진에서 확인한 구성품':'기록된 구성품'}</h2><div class="datasheet-parts">${observed}</div><h2>2. 구성품으로 추론한 기능</h2>${(r.systemHypotheses||[]).map(h=>`<article><h3>${esc(h.title)} · 추정</h3><p>${esc(h.rationale)}</p><p>${esc(h.input_behavior)} → ${esc(h.output_behavior)}</p></article>`).join('')||'<p>기능 분석 대기 또는 별도 지정한 설계입니다.</p>'}<h2>3. 부족한 부품 보완</h2>${completionBody(r)}<h2>4. 새 회로의 부품 사양</h2>${designs||'<p>기능에 맞는 회로 구성 단계에서 값과 연결을 지정합니다.</p>'}${r.unknowns.length?`<details class="compact-details"><summary>전체 미확인 항목 · ${r.unknowns.length}건</summary><ul>${r.unknowns.map(s=>`<li>${esc(s)}</li>`).join('')}</ul></details>`:''}<p class="datasheet-meta">생성 시각 ${esc(r.createdAt)} · 분석 ID ${esc(r.planId||'없음')} · 미확인 값과 정격은 관측 사실로 생성하지 않았습니다.</p>`;
}
export function datasheetDocument(r){return `<!doctype html><html lang="ko"><meta charset="utf-8"><title>${esc(r.title)} · 부품 데이터시트</title><style>body{font:15px/1.8 system-ui,sans-serif;max-width:1000px;margin:30px auto;padding:20px;color:#244638}article{border:1px solid #ccd9d0;padding:20px;margin:20px 0;border-radius:10px}dt{font-weight:bold}dd{margin:0 0 12px}a{color:#216850}small{color:#63766b}summary{cursor:pointer}details{margin:12px 0}h1{font-size:25px}.datasheet-notice,.datasheet-warning{background:#f6f0df;padding:14px}.datasheet-meta{font-size:12px;color:#63766b}@media print{details{display:block}details>*{display:block!important}article{break-inside:avoid}}</style><body><h1>${esc(r.title)} · 부품 데이터시트</h1>${datasheetBody(r)}</body></html>`;}
export function initDatasheet({state,api}){
 const button=document.querySelector('#open-datasheet'),dialog=document.querySelector('#datasheet-dialog'),body=document.querySelector('#datasheet-content');
 let snapshot=null;
 function refresh(){const g=state.data?.graph,p=state.plannerResult?.project===g?.project_id?state.plannerResult.plan:null;button.disabled=!g||!(p?.inventory?.parts.length||g.components?.length);button.title=button.disabled?'사진 분석으로 부품을 확인한 후 열 수 있습니다.':'부품 후보·정격 확인 항목·원문 링크를 봅니다.';}
 button.onclick=async()=>{
  const g=state.data?.graph;if(!g)return;
  const p=state.plannerResult?.project===g.project_id?state.plannerResult.plan:null;
  const cached=state.designProposal;
  let design=cached?.project===g.project_id&&cached.planId===p?.id&&cached.revision===g.revision?cached.data:null;
  // The report can be opened before the design panel finishes loading.
  if(!design&&p?.inventory&&!p.stale&&p.revision===g.revision&&api){
   button.disabled=true;
   try{design=await api(`/api/projects/${g.project_id}/inventory/${p.id}/proposals`);}catch{/* Observed parts remain available. */}
   finally{button.disabled=false;}
   if(state.data?.graph.project_id!==g.project_id||state.data?.graph.revision!==g.revision)return;
  }
  if(design?.prototype_design&&p&&!p.stale&&p.revision===g.revision&&api){
   button.disabled=true;
   try{const details=await api(`/api/projects/${g.project_id}/inventory/${p.id}/prototype?`+new URLSearchParams({function_version:design.function_version}));design={...design,prototype_details:details.design};}
   catch{/* The observed list and inferred requirements remain available. */}
   finally{button.disabled=false;}
   if(state.data?.graph.project_id!==g.project_id||state.data?.graph.revision!==g.revision)return;
  }
  const selection=cached?.data===design?{candidateId:cached.selectedCandidateId,recipe:cached.selectedRecipe}:{};
  snapshot=buildDatasheet(g,p,state.data.integrated?.catalog,design,selection);
  body.innerHTML=datasheetBody(snapshot);document.querySelector('#datasheet-heading').textContent=`시스템 데이터시트 · 관측 ${snapshot.parts.length}종 / 추정 보완 ${snapshot.inferredParts.length}종`;dialog.showModal();
 };
 document.querySelector('#close-datasheet').onclick=()=>dialog.close();
 document.querySelector('#download-datasheet').onclick=()=>{if(!snapshot)return;const url=URL.createObjectURL(new Blob([datasheetDocument(snapshot)],{type:'text/html;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download='component-datasheet-'+snapshot.project+'-r'+snapshot.revision+'.html';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
 return {refresh};
}
