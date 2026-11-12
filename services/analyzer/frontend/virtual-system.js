// A functional model is a set of assumptions about behavior, not a circuit,
// processor emulator, recovered firmware, or evidence of physical operation.
const boardNames={arduino:'Arduino',raspberry_pi:'Raspberry Pi'};
const recommendationNames={...boardNames,esp32:'ESP32',pico:'Raspberry Pi Pico'};
const statusNames={CONFIRMED:'확인',INFERRED:'추정',UNKNOWN:'미확인'};

function list(items,esc){
 return (items||[]).map(x=>`<li>${esc(x)}</li>`).join('');
}
function blocks(items,esc){
 return (items||[]).map(x=>`<div class="virtual-block"><b>${esc(x.name)}</b><span>${esc(x.description)}</span><small>${esc(statusNames[x.status]||'미확인')}</small></div>`).join('')||'<div class="virtual-block virtual-empty">확인 필요</div>';
}
function controls(inputs,esc){
 return (inputs||[]).map((input,i)=>{
  const label=esc(input.label||input.id),unit=input.unit?` <small>${esc(input.unit)}</small>`:'';
  if(input.type==='boolean')return `<label class="virtual-input virtual-checkbox"><input data-virtual-input="${i}" type="checkbox" ${input.default===true?'checked':''}> <span>${label}${unit}</span></label>`;
  if(input.type==='number')return `<label class="virtual-input"><span>${label}${unit}</span><input data-virtual-input="${i}" type="number" step="any" ${Number.isFinite(input.min)?`min="${input.min}"`:''} ${Number.isFinite(input.max)?`max="${input.max}"`:''} value="${Number.isFinite(input.default)?input.default:''}" required></label>`;
  return `<p>지원하지 않는 입력: ${label}</p>`;
 }).join('');
}
function printable(value){return value===null||value===undefined?'미확인':typeof value==='boolean'?(value?'켜짐':'꺼짐'):String(value);}
export function virtualResultHTML(result,model,esc){
 const sources=result.output_sources||{};
 const outputs=(model?.outputs||[]).map(o=>{
  const source=sources[o.id]||{},suffix=source.source==='assumed_default'?'가정한 기본값':source.source==='rule'?'추정 규칙 결과':'미지원·미확인';
  const value=result.outputs?.[o.id];
  return `<div class="virtual-output"><span>${esc(o.label||o.id)}</span><strong>${esc(printable(value))}${value!=null&&o.unit?' '+esc(o.unit):''}</strong><small>${esc(suffix)}</small></div>`;
 }).join('');
 const status={ready:'계산 완료',partial:'일부만 계산',unsupported:'계산 불가'}[result.status]||'확인 필요';
 return `<div class="virtual-results"><div class="preview-heading"><b>가상 동작 결과</b><span class="tag">${esc(status)}</span></div><div class="virtual-output-grid">${outputs||'<p>계산할 출력이 없습니다.</p>'}</div>${result.notice?`<p class="micro">${esc(result.notice)}</p>`:''}<details class="compact-details"><summary>가정 및 지원하지 않는 항목</summary><ul>${list(result.assumptions,esc)}${list(result.unsupported_requirements,esc)}${(result.unsupported_outputs||[]).map(x=>`<li>${esc(x)} 출력은 계산하지 않았습니다.</li>`).join('')}</ul></details></div>`;
}
export function virtualSystemHTML(data,esc,stale=false,endpoint=''){
 if(!data)return '';
 const system=data?.system_model,model=data?.virtual_model;
 if(!system&&!model)return `<section class="virtual-system"><div class="preview-heading"><h3>시스템 기능 분석</h3><span class="tag">분석 필요</span></div><p>전체 시스템의 기능과 가상 동작 모델을 확인하지 못했습니다. 사진·영상 분석을 다시 실행해 보세요.</p>${(data.system_model_warnings||[]).map(x=>`<p class="micro">${esc(x)}</p>`).join('')}</section>`;
 const recommendation=system?.board_recommendation;
 const recommendedName=recommendationNames[recommendation?.family]||'확인 필요';
 const board=model?.target_board in boardNames?model.target_board:(recommendation?.family in boardNames?recommendation.family:'arduino');
 const assumptions=[...(system?.assumptions||[]),...(system?.unknowns||[])];
 const collapse=Object.keys(data.prototype_candidates||{}).length>0;
 return `<section class="virtual-system"><div class="preview-heading"><h3>시스템 기능 분석</h3><span class="tag">추정 · 원본 동작 미확인</span></div>
 <p>${esc(system?.summary||'입력과 출력의 관계를 확인합니다.')}</p>
 <div class="virtual-flow" aria-label="추정한 입력 처리 출력 흐름"><div><small>1 · 입력</small>${blocks(system?.inputs,esc)}</div><span class="virtual-arrow" aria-hidden="true">→</span><div><small>2 · 처리</small>${blocks(system?.logic,esc)}</div><span class="virtual-arrow" aria-hidden="true">→</span><div><small>3 · 출력</small>${blocks(system?.outputs,esc)}</div></div>
 <p class="virtual-recommend"><b>추천 보드: ${esc(recommendedName)}</b> · ${esc(recommendation?.reason||'필요한 처리와 입출력을 확인해야 합니다.')} <small>${esc(statusNames[recommendation?.status]||'미확인')}</small></p>
 <details class="compact-details"><summary>가정과 추가 확인 사항</summary><ul>${list(assumptions,esc)||'<li>제시된 추가 사항 없음</li>'}</ul></details>
 ${collapse?'<details class="compact-details"><summary>간단한 기능 논리 계산</summary>':''}<div class="virtual-simulator"><div class="preview-heading"><h4>가상 기능 시뮬레이션</h4><span class="tag">가정 기반 논리 계산</span></div>
 <p>입력값을 바꿔 위 시스템 분석에서 추정한 규칙의 출력을 확인합니다. 아래 회로 목표 선택과 별개로 동작합니다. 보드를 바꿔도 같은 규칙을 계산하며, 실제 회로·보드 코드 실행이나 원본 기능의 검증은 아닙니다.</p>
 ${!model?'<p class="function-blocker">현재 이 시스템의 가상 동작 규칙이 없어 실행할 수 없습니다.</p>':`<form data-virtual-form><label class="virtual-board">목표 보드<select name="target_board"><option value="arduino" ${board==='arduino'?'selected':''}>Arduino</option><option value="raspberry_pi" ${board==='raspberry_pi'?'selected':''}>Raspberry Pi · Linux 보드</option></select></label><div class="virtual-input-grid">${controls(model.inputs,esc)||'<p>조작 가능한 입력이 없습니다.</p>'}</div><button type="submit" class="primary" ${stale?'disabled':''}>가상 동작 확인</button><p role="status" data-virtual-status></p></form><div data-virtual-results></div>${!stale&&endpoint?`<div class="virtual-code"><a href="${esc(endpoint)}/virtual-simulation/python?target_board=raspberry_pi" download="virtual_system.py">Raspberry Pi용 가상 입출력 Python 코드 다운로드</a><small>표준 Python에서 가상 입출력만 처리합니다. GPIO 핀이나 실제 장치를 제어하지 않습니다.</small></div>`:''}`}</div>${collapse?'</details>':''}</section>`;
}
export function renderVirtualSystem(host,{data,api,endpoint,esc,stale=false}){
 host.innerHTML=virtualSystemHTML(data,esc,stale,endpoint);
 const form=host.querySelector('[data-virtual-form]');if(!form)return;
 const model=data.virtual_model;
 const clearResult=()=>{host.querySelector('[data-virtual-results]').innerHTML='';};
 form.addEventListener('input',clearResult);
 form.addEventListener('change',clearResult);
 form.onsubmit=async event=>{
  event.preventDefault();if(!form.reportValidity())return;
  const inputs={};
  for(const [i,input] of (model.inputs||[]).entries()){
   const element=form.querySelector(`[data-virtual-input="${i}"]`);
   if(!element)continue;
   inputs[input.id]=input.type==='boolean'?element.checked:Number(element.value);
  }
  const button=form.querySelector('button'),status=form.querySelector('[data-virtual-status]');
  const fields=Array.from(form.querySelectorAll('input,select'));
  const targetBoard=form.elements.target_board.value;
  button.disabled=true;fields.forEach(field=>field.disabled=true);clearResult();status.textContent='가상 동작을 계산하고 있습니다…';
  try{
   const result=await api(endpoint+'/virtual-simulation',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({target_board:targetBoard,inputs})});
   if(!host.isConnected)return;
   host.querySelector('[data-virtual-results]').innerHTML=virtualResultHTML(result,model,esc);
   status.textContent='';
  }catch(error){if(host.isConnected)status.textContent=error.message||'가상 동작 계산에 실패했습니다.';}
  finally{if(host.isConnected){button.disabled=stale;fields.forEach(field=>field.disabled=false);}}
 };
}
