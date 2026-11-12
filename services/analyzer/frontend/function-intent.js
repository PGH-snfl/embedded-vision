import {workspaceId} from './saas.js';
export function prototypeEditorUrl(endpoint,version){
 const match=endpoint.match(/\/projects\/([a-f0-9]{32})\/inventory\/([a-f0-9]{32})$/);
 if(!match||!/^[a-f0-9]{64}$/.test(version||''))throw new Error('설계 주소를 확인하세요.');
 const base=workspaceId?`/w/${workspaceId}/prototype-editor.html`:'/prototype-editor.html';
 return base+'?'+new URLSearchParams({project:match[1],plan:match[2],function_version:version});
}
// A text LCD needs an observed or user-supplied message before a runnable
// design can be offered. A still image cannot establish changing behavior.
export function candidateCanSimulate(candidate){
 return ['led_output','led_blink','led_brightness','voltage_readout','button_led','light_led'].includes(candidate?.kind)
  || (candidate?.kind==='lcd_text' && /^[A-Za-z0-9 .,!?_\-]{1,16}$/.test(candidate.display_text||''));
}
export function offeredCandidateCanSimulate(data,candidate){
 if(!candidateCanSimulate(candidate))return false;
 return Boolean(simulatorProposal(data,candidate)?.simulator_supported);
}
// Prefer the candidate's own preview. A previously selected LCD message is
// not evidence that a different candidate's message can run.
export function simulatorProposal(data,candidate){
 if(candidate){
  const preview=(data.hypothesis_previews||[]).find(p=>p.candidate_id===candidate.id);
  if(preview)return preview.proposal;
  if(data.function?.kind!==candidate.kind)return null;
  if(candidate.kind==='lcd_text'&&candidate.display_text!==data.function?.display_text)return null;
 }
 return (data.proposals||[]).find(p=>p.recipe===data.recommended&&p.simulator_supported)||null;
}
function simulationAssumptions(proposal,esc){
 if(!proposal?.simulator_supported||!proposal.simulation_behavior)return '';
 return `<div class="simulation-assumptions"><b>새 시뮬레이션에서 실행할 동작</b><p>${esc(proposal.simulation_behavior)}</p><small>이 동작은 새 설계의 기본값이며 사진 속 원래 동작이 확인된 것은 아닙니다.</small></div>`;
}
// Highest qualitative ranking is supplied by the server; no numerical
// probability or verified original behavior is implied by the ordering.
export function recommendedCandidate(data){
 const candidates=data?.function_hypotheses||[];
 if(!candidates.length)return null;
 if(data.recommended_hypothesis_id!==undefined)
  return candidates.find(c=>c.id===data.recommended_hypothesis_id)||null;
 return [...candidates].sort((a,b)=>(a.plausibility==='medium'?0:1)-(b.plausibility==='medium'?0:1))[0];
}
function processingDescription(kind){
 return ({lcd_text:'제어 보드가 화면에 문자를 보냅니다.',voltage_readout:'제어 보드가 전압을 읽습니다.',
  light_led:'제어 보드가 밝기를 읽고 LED를 제어합니다.',button_led:'제어 보드가 버튼 입력을 읽고 LED를 제어합니다.',
  led_output:'제어 보드가 LED 출력을 제어합니다.',led_blink:'제어 보드가 LED를 반복해서 켜고 끕니다.',
  led_brightness:'제어 보드가 신호를 조절해 LED 밝기를 바꿉니다.'})[kind]||'시스템이 입력을 처리합니다.';
}
export function renderRecommendation(data,esc){
 const candidate=recommendedCandidate(data),intent=data?.function;
 // Older plans can have an inferred function without stored hypotheses.
 const inferred=!candidate&&intent?.status==='INFERRED'&&intent.kind!=='unknown'?intent:null;
 const item=candidate||inferred;if(!item)return '';
 const canSimulate=candidate?offeredCandidateCanSimulate(data,candidate):
  candidateCanSimulate(inferred)&&(data.proposals||[]).some(p=>p.recipe===data.recommended&&p.simulator_supported);
 const prototypeAvailable=Boolean(candidate&&data.prototype_candidates?.[candidate.id]);
 const title=candidate?.title||inferred.summary;
 const button=candidate?`<button type="button" class="primary" data-candidate="${esc(candidate.id)}">${canSimulate||prototypeAvailable?'이 기능으로 시뮬레이션':'이 기능을 설계 목표로 선택'}</button>`:
  canSimulate?'<button type="button" class="primary" data-open-inferred>이 기능 시뮬레이션 보기</button>':'';
 const lcdNeedsText=item.kind==='lcd_text'&&!candidateCanSimulate(item);
 const unavailable=!canSimulate&&!prototypeAvailable?`<p class="recommended-unavailable">${data.robot_design&&candidate?.id===data.robot_design.selected_candidate_id?'선택한 이동 기능의 새 2륜 로봇 설계와 3D 동작 시험을 아래에서 확인하세요.':data.physical_design&&item.kind==='button_led'?'아래 Raspberry Pi 실물 회로와 조립 가이드를 확인하세요.':lcdNeedsText?'LCD 표시 문구 확인이 필요합니다. 현재 16자 이내 영문·숫자·기본 문장부호를 지원합니다.':data.virtual_model?'이 기능의 실제 보드용 회로는 아직 자동 생성할 수 없습니다. 위 가상 기능 모델은 별도로 확인할 수 있습니다.':'이 기능은 현재 바로 실행할 수 없습니다. 다른 기능을 선택하거나 필요한 정보를 확인하세요.'}</p>`:'';
 const details=candidate?`<details class="compact-details"><summary>추정 근거·확인할 사항</summary>${(candidate.evidence||[]).map(e=>`<p>${esc(e.observation)}</p>`).join('')}<ul>${(candidate.assumptions||[]).map(a=>`<li>${esc(a)}</li>`).join('')}</ul><p>${esc(candidate.distinguishing_check||'')}</p></details>`:'';
 const simulation=canSimulate?simulationAssumptions(simulatorProposal(data,candidate),esc):'';
 return `<article class="recommended-function" aria-label="가장 가능성이 높은 기능"><div class="recommended-heading"><div><span class="recommended-kicker">가장 가능성이 높은 기능</span><h4>${esc(title)}</h4></div><span class="tag">추정 · 실물 동작 미확인</span></div>
 <p>${esc(candidate?.rationale||'사진에서 관측한 기능을 바탕으로 추정했습니다.')}</p>
 <div class="recommended-flow" aria-label="예상 기능 흐름"><div><small>1 · 입력</small><p>${esc(item.input_behavior||'입력 조건 확인 필요')}</p></div><span aria-hidden="true">→</span><div><small>2 · 처리</small><p>${esc(processingDescription(item.kind))}</p></div><span aria-hidden="true">→</span><div><small>3 · 출력</small><p>${esc(item.output_behavior||'출력 동작 확인 필요')}</p></div></div>
 <p class="recommended-note">사진·영상에 근거한 후보 중 정성적으로 선택했습니다. 수치 확률이나 원본 동작의 확인 결과는 아닙니다.</p>${details}${simulation}${unavailable}${button}</article>`;
}
// The parent replaces #function-intent after a successful selection. Send
// status to the live element so popup-blocked guidance remains visible.
export function setCandidateStatus(host,message,doc=document){
 const activeHost=host.isConnected?host:doc.querySelector('#function-intent');
 const status=activeHost?.querySelector('[data-candidate-status]');
 if(status)status.textContent=message;
}
export function renderFunctionIntent(host,{data,api,endpoint,revision,esc,onChange}){
 const intent=data?.function;
 if(!intent){host.innerHTML='<p>기능 요구사항을 확인하고 있습니다…</p>';return;}
 const known=intent.status!=='UNKNOWN';
 const candidates=data.function_hypotheses||[];
 const recommendation=recommendedCandidate(data),otherCandidates=candidates.filter(c=>c.id!==recommendation?.id);
 const candidateHtml=otherCandidates.length?`<details class="compact-details function-candidates"><summary>다른 기능 후보 ${otherCandidates.length}가지</summary><div class="candidate-heading"><small>${data.hypothesis_source==='multimodal_model'?'사진·영상 모델 추론':'저장된 부품 관측에서 추론'}</small></div>${otherCandidates.map((c,i)=>`<article class="function-candidate"><div class="preview-heading"><b>${i+1}. ${esc(c.title)}</b><span class="tag">추정 · ${c.plausibility==='medium'?'중간':'낮음'}</span></div><p>${esc(c.rationale)}</p><p class="candidate-output">예상 동작: ${esc(c.output_behavior)}</p><details class="compact-details"><summary>근거·가정·구분 방법</summary>${c.evidence.map(e=>`<p>${esc(e.asset_id)} · ${esc(e.observation)}</p>`).join('')}<ul>${c.assumptions.map(a=>`<li>${esc(a)}</li>`).join('')}</ul><p><b>구분 방법</b> ${esc(c.distinguishing_check)}</p><p>추정 강도는 후보 간 정성적 비교이며 정확도·확률이 아닙니다.</p></details>${offeredCandidateCanSimulate(data,c)?simulationAssumptions(simulatorProposal(data,c),esc):''}<button type="button" data-candidate="${esc(c.id)}">${offeredCandidateCanSimulate(data,c)?'이 목표로 설계 → 시뮬레이터':'이 기능을 설계 목표로 선택'}</button></article>`).join('')}</details>`:'';
 host.innerHTML=`<section class="function-intent"><div class="preview-heading"><h3>재현할 기능</h3><span class="tag">${intent.status==='USER_DEFINED'?'사용자 지정':intent.status==='UNKNOWN'?(candidates.length?'기능 후보 추론':'기능 확인 필요'):'관측 기반 추론'}</span></div><p>${!known&&candidates.length?'부품과 관측된 출력을 바탕으로 기능을 추정했습니다.':esc(intent.summary)}</p>${renderRecommendation(data,esc)}${candidateHtml}<p role="status" data-candidate-status></p>
 ${known?`<div class="function-io"><div><small>입력·조건</small><p>${esc(intent.input_behavior)}</p></div><span>→</span><div><small>출력·반응</small><p>${esc(intent.output_behavior)}</p></div></div>`:''}
 ${(data.robot_design||data.prototype_design?[]:(known||!candidates.length?data.function_blockers||[]:[])).map(s=>`<p class="function-blocker">${data.physical_design?'기존 Arduino 회로 자동 생성: ':''}${esc(s)}</p>`).join('')}
 <details class="compact-details"><summary>관측 근거·성공 조건</summary>${intent.evidence.map(e=>`<p>${esc(e.asset_id)} · ${esc(e.observation)}</p>`).join('')||'<p>이전 부품 분석에는 동작 관측이 없습니다. 기능을 직접 지정하거나 사진·영상의 기능 분석을 다시 실행하세요.</p>'}<ul>${intent.acceptance_criteria.map(c=>`<li>${esc(c)}</li>`).join('')}</ul><ul>${intent.unknowns.map(c=>`<li>${esc(c)}</li>`).join('')}</ul><p>배선은 새로 설계하며 원래 프로그램을 복원하지 않습니다. 실제 같은 동작을 하는지는 이후 시험으로 확인해야 합니다.</p></details>
 <details class="compact-details" ${(!known&&!candidates.length)||(intent.kind==='lcd_text'&&!intent.display_text)?'open':''}><summary>원하는 기능 확인·변경</summary><form data-function-form><label>동작 종류<select name="kind" required><option value="unknown">동작을 선택하세요</option>${data.function_options.map(o=>`<option value="${o.kind}" ${intent.kind===o.kind?'selected':''}>${esc(o.label)}</option>`).join('')}<option value="unsupported" ${intent.kind==='unsupported'?'selected':''}>그 밖의 동작 · 추가 설계 필요</option></select></label><label>어떤 조건에서 무엇이 동작해야 하나요?<textarea name="description" required minlength="5" maxlength="1200" placeholder="예: 전원을 켜면 LCD에 Javalab.org를 표시한다">${intent.status==='USER_DEFINED'||known?esc(intent.summary):''}</textarea></label><label data-display-text ${intent.kind!=='lcd_text'?'hidden':''}>LCD 표시 문구<input name="display_text" maxlength="16" pattern="[A-Za-z0-9 .,!?_\\-]+" value="${esc(intent.display_text||'')}" placeholder="Javalab.org"></label><button type="submit" class="primary">이 기능으로 회로 구성</button><p role="status" data-function-status></p></form></details></section>`;
 host.querySelectorAll('[data-candidate]').forEach(button=>button.onclick=async()=>{
  button.disabled=true;
  try{
   const next=await api(endpoint+'/function-candidate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({expected_revision:revision,candidate_id:button.dataset.candidate})});
   onChange(next);
   const ready=next.prototype_design||next.robot_design||(next.proposals||[]).some(p=>p.recipe===next.recommended&&p.simulator_supported);
   setCandidateStatus(host,ready?'선택한 기능의 회로와 시뮬레이터를 위에서 준비합니다.':'목표를 선택했습니다. 회로 구성 상태를 확인하세요.');
   if(ready)document.querySelector('#auto-simulation')?.scrollIntoView({block:'start'});
  }catch(e){setCandidateStatus(host,e.message);button.disabled=false;}
 });
 const inferredButton=host.querySelector('[data-open-inferred]');
 if(inferredButton)inferredButton.onclick=()=>document.querySelector('#auto-simulation')?.scrollIntoView({block:'start'});
 const form=host.querySelector('form'),kind=form.elements.kind,display=form.elements.display_text;
 const update=()=>{host.querySelector('[data-display-text]').hidden=kind.value!=='lcd_text';display.required=kind.value==='lcd_text';};update();kind.onchange=update;
 form.onsubmit=async e=>{e.preventDefault();const button=form.querySelector('button');button.disabled=true;
  try{const next=await api(endpoint+'/function',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({expected_revision:revision,kind:kind.value,description:form.elements.description.value,display_text:kind.value==='lcd_text'?display.value:null})});onChange(next);const ready=next.prototype_design||next.robot_design||(next.proposals||[]).some(p=>p.recipe===next.recommended&&p.simulator_supported);setCandidateStatus(host,ready?'선택한 기능의 회로와 시뮬레이터를 위에서 준비합니다.':'선택한 기능의 회로 구성 상태를 확인하세요.');if(ready)document.querySelector('#auto-simulation')?.scrollIntoView({block:'start'});}
  catch(e){host.querySelector('[data-function-status]').textContent=e.message;button.disabled=false;}
 };
}
