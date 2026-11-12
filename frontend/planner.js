import {selectedAnalysisModel,analysisModelLabel} from './analysis-model.js?v=analysis-model-1';
import {apiPrefix} from './saas.js';
import {initInventory} from './inventory.js?v=photo-appearance-1';
export const ANALYSIS_PHASES=['queued','sol','components','component_review','coverage','function','completion','datasheet','routing','astra','validation'];
export function initPlanner(ctx){
  const {state,api,post,run,message,esc}=ctx;
  const inventory=initInventory(ctx);
  let newDesign=null;
  let config=null,result=null,projectKey='',loading=false,task='circuit_inference',prompt='',probe='',autoJob=null,pollTimer=null;
  const active=new Set([...ANALYSIS_PHASES,'waiting_credentials']);
  const $=s=>document.querySelector(s);
  const url=()=>`${apiPrefix}/projects/${state.data.graph.project_id}/planner`;
  async function pollAutomatic(){
    if(pollTimer)clearTimeout(pollTimer);
    if(!state.data||!['photo','video'].includes(state.data.graph.mode))return;
    const key=state.data.graph.project_id,base=`${apiPrefix}/projects/${key}`;
    try{
      const r=await api(`${base}/auto-analysis`);
      if(state.data.graph.project_id!==key)return;
      const old=autoJob;autoJob=r.job;
      if(r.configured&&autoJob?.status==='waiting_credentials'&&!autoJob.stale){
        const started=await api(`${base}/auto-analysis`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({expected_revision:state.data.graph.revision,model:autoJob.analysis_model||'gpt-6.1-sol'})});
        if(state.data.graph.project_id!==key)return;
        autoJob=started.job;config=await api('/api/planner/status');
      }
      if(autoJob?.plan_id&&((result?.plan?.id!==autoJob.plan_id&&(!result?.plan||(old?.id===autoJob.id&&old?.plan_id!==autoJob.plan_id)))||
          (result?.plan?.id===autoJob.plan_id&&result.plan.analysis_complete===false&&autoJob.status==='done'))){
        const plan=await api(`${base}/planner/${autoJob.plan_id}`);
        if(state.data.graph.project_id!==key)return;
        result=plan;
      }
      if(JSON.stringify(old)!==JSON.stringify(autoJob)){render();ctx.renderVisuals();}
      if(active.has(autoJob?.status))pollTimer=setTimeout(pollAutomatic,2500);
    }catch(e){if(state.data.graph.project_id===key){message('자동 분석 상태 확인 실패: '+e.message,true);pollTimer=setTimeout(pollAutomatic,5000);}}
  }
  async function refresh(){
    const key=state.data.graph.project_id;loading=true;
    try{
      const [c,r,d]=await Promise.all([api('/api/planner/status'),api(url()),api(`${apiPrefix}/projects/${key}/new-design`),inventory.load()]);
      if(state.data.graph.project_id===key){config=c;result=r;newDesign=d;}
    }catch(e){message(e.message,true);}finally{loading=false;if(state.data.graph.project_id!==key)refresh();else{render();ctx.renderVisuals();pollAutomatic();}}
  }
  function inspectionHTML(){
    const samePlan=!autoJob||autoJob.plan_id===result?.plan?.id;
    const fromJob=autoJob?.component_inspection;
    const report=fromJob||(samePlan?result?.plan?.component_inspection:null);
    if(!report)return '';
    const reviewed=new Set(report.reviewed_ids||[]).size,total=(report.initial_ids||[]).length+(report.added_ids||[]).length;
    const statuses={running:'진행 중',partial:'일부 확인 제한',reviewed_candidates:'검출 후보 검토 완료'};
    const planId=fromJob?autoJob.plan_id:result?.plan?.id;
    const reviews=new Map((report.reviews||[]).map(r=>[r.part_id,r]));
    const dispositions={visible:'확대 검토',unclear:'판독 제한',not_component:'부품 후보 제외'};
    const crops=(report.crops||[]).filter(c=>['component_review','final_inventory_display'].includes(c.purpose));
    return `<details class="compact-details component-inspection"><summary>${report.mode==='final_json'?'자유 분석·최종 JSON':'부품별 확대·재검토'} · ${total?reviewed+'/'+total+' 후보':'중간 메모 작성 중'}</summary><p>${esc(statuses[report.status]||report.status)} · ${esc(report.skill?.name||'')} · 요청 ${Number(report.skill?.http_calls||0)}회</p><p class="micro">${esc(report.notice||'')} ${(report.grouped_ids||[]).length?'묶음 수량은 개별 부품마다 확인한 결과가 아닙니다.':''}</p>${planId?`<div class="inspection-crops">${crops.map(c=>{const review=reviews.get(c.part_ids?.[0]);return `<figure><a href="${url()}/${encodeURIComponent(planId)}/inspection/${encodeURIComponent(c.crop_id)}" target="_blank" rel="noopener"><img loading="lazy" src="${url()}/${encodeURIComponent(planId)}/inspection/${encodeURIComponent(c.crop_id)}" alt="${esc((c.part_ids||[]).join(', '))} 원본 확대"></a><figcaption><strong>${esc((c.part_ids||[]).join(', '))} · ${esc(review?.name||'검토 대기')}</strong><small>${esc((review?.markings||[]).join(' / ')||'읽힌 표식 없음')} · ${esc(dispositions[review?.disposition]||'대기')}</small></figcaption></figure>`;}).join('')}</div>`:'<p class="micro">목록 저장 후 확대 이미지를 확인할 수 있습니다.</p>'}${(report.notes||[]).length?`<details class="compact-details"><summary>중간 분석 메모 · 프로그램 실행에 직접 사용하지 않음</summary>${report.notes.map(n=>`<h4>${esc(({component_notes:'구성품 관찰',component_recheck_notes:'확대·누락 재검토',system_reasoning_notes:'기능·회로 설계'})[n.stage]||n.stage)}</h4><pre>${esc(n.text)}</pre>`).join('')}</details>`:''}${(report.skipped||[]).map(s=>`<p>${esc(s.part_id)} · ${esc(s.reason)}</p>`).join('')}${(report.uninspected_regions||[]).length?`<p>추가 확인이 필요한 영역 ${(report.uninspected_regions||[]).length}개</p>`:''}</details>`;
  }
  function renderAutomatic(){
    const el=$('#auto-analysis-panel');if(!el)return;
    if(!['photo','video'].includes(state.data.graph.mode)){el.hidden=true;return;}
    el.hidden=false;
    const phase=autoJob?.stale&&!ANALYSIS_PHASES.includes(autoJob.status)?'stale':autoJob?.status||'idle';
    const label={queued:'분석 대기',sol:'기본 분석 중',components:'구성품 목록 작성 중',component_review:'부품별 확대 재검토 중',coverage:'누락·중복 대조 중',function:'목록 기반 기능 추론 중',completion:'부족한 부품 보완 중',datasheet:'데이터시트 작성 중',routing:'어려운 구간 선별',astra:'해당 구간 심화 분석 중',validation:'결과 검사 중',done:'자동 분석 완료',waiting_credentials:'API 키 설정 대기',error:'분석 실패',interrupted:'분석 중단',stale:'이전 버전 분석',disabled:'자동 분석 꺼짐',idle:'저장된 사진'}[phase]||phase;
    const usedModel=autoJob?.analysis_model||result?.plan?.analysis_model||'gpt-6.1-sol';
    const modelChanged=usedModel!==selectedAnalysisModel();
    const stages=['components','component_review','coverage','function','completion','datasheet'],stageIndex=['validation','done'].includes(phase)?6:stages.indexOf(phase);
    const pipeline=stages.map((s,i)=>`<span class="auto-step ${i<stageIndex?'complete':i===stageIndex?'current':''}">${i+1}. ${['구성품 목록','부품별 확대','누락·중복 대조','기능 추론','부품 보완','데이터시트'][i]}</span>`).join('');
    const failedStage=autoJob?.error?.task==='final_photo_json'?'최종 JSON 정리':{components:'구성품 목록',component_review:'부품별 확대',coverage:'누락·중복 대조',function:'기능 추론',completion:'부품 보완',datasheet:'데이터시트'}[autoJob?.failed_stage]||autoJob?.failed_stage||'기록 없음';
    const diagnostic=autoJob?.error;
    const failure=autoJob?.status==='error'?`<div class="analysis-failure" role="alert"><p class="errors">${esc(autoJob.message)}</p><details class="compact-details"><summary>실패 원인·단계</summary><p>실패 단계: ${esc(failedStage)}</p>${diagnostic?`<p>${esc(diagnostic.task)} · 요청 ${Number(diagnostic.http_calls||0)}회${diagnostic.param?' · 항목 '+esc(diagnostic.param):''}${diagnostic.request_id?' · 요청 ID '+esc(diagnostic.request_id):''}</p>`:'<p>이전 기록에는 상세 API 원인이 저장되지 않았습니다.</p>'}<p class="micro">자동 재호출하지 않았습니다. 입력 사진과 이전 분석 결과는 보존합니다.</p></details></div>`:'';
    el.innerHTML=`<div class="panel-heading"><h2>사진·영상 부품별 분석</h2><span class="tag neutral" role="status">${esc(label)} · ${esc(analysisModelLabel(autoJob?usedModel:selectedAnalysisModel()))}</span></div><div class="assistant-body">${failure}<details class="compact-details"><summary>분석 단계·처리 방식</summary><div class="auto-pipeline">${pipeline}</div><p>${esc(autoJob?.message||'새 사진은 업로드와 함께 자동 분석합니다. 기존 사진은 아래 버튼으로 시작할 수 있습니다.')}</p><p class="micro">전체 부품 목록을 만든 뒤 원본 영역을 최대 2배 확대해 부품별로 재검토하고, 분할 이미지로 누락·중복을 대조합니다. 검토한 목록으로 기능·회로·코드를 설계합니다. 부품 수에 따라 API 호출·처리 시간이 늘어나며 한도 안에서 진행합니다. 지원하는 동작은 회로·코드·시뮬레이션으로 이어집니다. 원본과 동일한 동작인지는 별도 확인이 필요합니다. 불확실한 모델·정격은 확인 대상으로 남습니다.</p></details>${phase==='waiting_credentials'?'<p>서버에서 <code>bash configure_openai.sh</code>로 새 API 키를 설정하면 이 화면이 자동으로 분석을 재개합니다.</p>':''}${(['idle','error','interrupted','stale'].includes(phase)||(modelChanged&&['done','waiting_credentials'].includes(phase)))?'<button id="auto-start" class="primary">이 사진 '+esc(analysisModelLabel(selectedAnalysisModel()))+'로 '+(phase==='idle'?'분석':'다시 분석')+'</button>':''}${autoJob?.plan_id?'<button id="auto-results">구성품·기능 결과 확인 ↓</button>':''}${inspectionHTML()}</div>`;
    if($('#auto-start'))$('#auto-start').onclick=()=>run(async()=>{const r=await post('/auto-analysis?retry=true',{model:selectedAnalysisModel()});autoJob=r.job;render();pollAutomatic();});
    if($('#auto-results'))$('#auto-results').onclick=()=>run(async()=>{result=await api(`${url()}/${autoJob.plan_id}`);render();$('#user-step-2').scrollIntoView({block:'start'});});
  }
  function render(){
    if(!state.data)return;
    const g=state.data.graph;
    if(projectKey!==g.project_id){if(pollTimer)clearTimeout(pollTimer);projectKey=g.project_id;result=null;autoJob=null;newDesign=null;prompt='';if(!loading)refresh();}
    renderAutomatic();
    const plan=result?.plan,execution=result?.execution;
    state.plannerResult={project:g.project_id,plan,execution,newDesign};
    const stale=plan&&(plan.stale||execution?.stale||plan.revision!==g.revision);
    if(plan?.inventory){inventory.render($('#assistant-panel'),plan,stale);return;}
    inventory.clearAuto();
    $('#parts-stage').innerHTML=g.mode==='reference_design'?`<div class="panel"><div class="assistant-body"><p>${newDesign?.design?'검토한 부품으로 새 회로를 구성했습니다. 원본 부품 검토는 저장한 입력 프로젝트에서 다시 확인할 수 있습니다.':'명시된 설계 예제의 부품 목록입니다. 사진을 분석한 결과가 아닙니다.'}</p><div class="io-parts">${g.components.map(c=>`<span>${esc(c.id)} · ${esc(c.label.value||'미확인')}</span>`).join('')}</div></div></div>`:'<div class="panel"><div class="assistant-body"><p>분석이 끝나면 부품 후보가 여기에 표시됩니다. 기능과 보완 부품은 ③에서 확인하세요.</p></div></div>';

    $('#assistant-panel').innerHTML=`<div class="panel-heading"><h2>${g.mode==='reference_design'?'새 회로 구성 완료':'추정 기능과 새 회로를 확인하세요'}</h2><span class="tag neutral">구성품 → 기능 → 보완 → 데이터시트 → 회로</span></div>
      <div class="assistant-body">
      
      <details class="planner-settings"><summary>고급 설정 · 모델 연결·추가 요청</summary><div class="gate-pills"><span class="result-badge ${config?.configured?'pass':''}">${config?.configured?'API 키 설정됨 · 호출 검증 별도':'모델 연결 대기'}</span><span>${esc(config?.note||'연결 설정 확인 중…')}</span><button id="planner-refresh">상태 새로고침</button><button id="planner-probe">MCP 연결 확인</button></div>
      ${probe?`<p role="status">${esc(probe)}</p>`:''}
      <form id="planner-form"><label>작업 종류 <select id="planner-task"><option value="circuit_inference">사진의 회로 연결 추론</option><option value="explain">부품·동작 설명</option><option value="build_schematic">검증된 그래프로 회로도 계획</option></select></label>
      <label>요청 <input id="planner-prompt" aria-label="모델 분석 요청" maxlength="2000" required placeholder="예: 가려진 배선의 후보와 확인할 근거를 설명해줘" value="${esc(prompt)}"></label>
      <p class="micro">${g.mode==='video'?'영상에서 추출한 주요 프레임 최대 6장을':'현재 선택한 사진 한 장을'} 모델 API로 전송합니다. 상단에서 선택한 모델로 분석합니다. Sol을 선택하면 어려운 회로 구간만 Astra가 최대 1회 추가 검토하며, Astra를 선택하면 전체를 직접 분석합니다.</p>
      <button class="primary" id="planner-submit" ${!config?.configured?'disabled':''}>추가 분석·계획 요청</button></form></details>
      ${plan?`<div class="planner-result"><h3>분석 결과 검토 · r${plan.revision} ${stale?'· 이전 버전':''}</h3><p>${esc(plan.decision.summary)}</p>
      <details class="compact-details"><summary>분석 근거·검증 기록</summary><div class="gate-pills">${plan.attempts.map(a=>`<span class="result-badge">${esc(a.call.model)} · ${a.call.elapsed_seconds??'?'}초</span>`).join('')}<span>${plan.routing.primary==='gpt-6-astra'?'Astra 전체 분석':plan.routing.specialist_called?'Astra 검토 완료':plan.routing.specialist_error?'Astra 호출 실패':'Astra 미호출'}</span></div>
      ${plan.routing.escalation_reasons.length?`<p>Astra 호출 사유: ${plan.routing.escalation_reasons.map(esc).join(' / ')}</p>`:''}
      ${plan.specialist_summary?`<p>심화 검토: ${esc(plan.specialist_summary)}</p>`:''}
      ${plan.routing.no_escalation_reason?`<p class="micro">${esc(plan.routing.no_escalation_reason)}</p>`:''}
      ${plan.routing.specialist_error?`<p class="errors">${esc(plan.routing.specialist_error)}</p>`:''}
      ${plan.decision.findings.map(f=>`<article class="assembly-step"><b>${esc(f.subject)} · ${esc(f.status)}</b><p>${esc(f.hypothesis||'확인할 수 없음')}</p><p>근거: ${esc(f.rationale)}</p><small>이미지 ${f.asset_ids.map(esc).join(', ')||'없음'} · 근거 ID ${f.evidence_ids.map(esc).join(', ')||'없음'}</small><p>확인 방법: ${esc(f.verification_needed)}</p></article>`).join('')}
      ${[...plan.decision.unresolved,...plan.decision.conflicts].length?`<h4>남은 불확실성·충돌</h4><ul>${[...plan.decision.unresolved,...plan.decision.conflicts].map(s=>`<li>${esc(s)}</li>`).join('')}</ul>`:''}
      <details><summary>실행 조건·호출 기록</summary><ul>${plan.blockers.map(s=>`<li>${esc(s)}</li>`).join('')}</ul><pre class="code-block">${esc(JSON.stringify({routing:plan.routing,calls:plan.attempts.map(a=>a.call)},null,2))}</pre></details></details>
      ${newDesign?.design?`<details class="compact-details"><summary>생성한 코드·추가 부품 상세</summary><h3>새 회로에 맞춘 코드</h3><p>원본 프로젝트는 상단 목록에서 다시 열 수 있습니다. 새 설계는 원본과 별도로 저장되어 있습니다.</p><p>${esc(newDesign.design.behavior)}</p><a class="button" href="${apiPrefix}/projects/${g.project_id}/firmware?download=true">Arduino 코드 ↓</a><details><summary>코드 보기 · 컴파일·실물 미검증</summary><pre class="code-block">${esc(newDesign.firmware?.source||'회로가 변경되어 코드를 다시 검토해야 합니다.')}</pre></details><p>추가로 준비할 부품: ${newDesign.design.added_parts.map(p=>esc(p.reference+' · '+p.name+' '+(p.value||''))).join(', ')||'없음'}</p></details>`:''}<details class="compact-details"><summary>회로도 생성 순서</summary>${plan.execution_steps.length?`<ol>${plan.execution_steps.map(s=>`<li>${esc(s)}</li>`).join('')}</ol>`:'<p>검토 전용 계획입니다. 원본 회로에서 미확인 항목을 해결한 뒤 회로도 계획을 생성하세요.</p>'}</details>
      <button id="planner-execute" class="primary" ${!plan.executable||stale||execution?'disabled':''}>검토한 계획을 새 KiCad 프로젝트에서 실행</button>
      <details class="compact-details"><summary>설계 범위·주의 사항</summary><p class="engineering-note">${esc(plan.notice)}</p></details>
      ${execution?`<p>실행 ${esc(execution.status)} · 연결 대조 ${esc(execution.connectivity)} · ERC ${esc(execution.erc)} · PCB/DRC 미실행</p>${execution.error?`<p class="errors">${esc(execution.error)}</p>`:''}<a class="button" href="${url()}/${plan.id}/artifacts/report">실행 기록 ↓</a>${execution.status==='DONE'?`<a class="button" href="${url()}/${plan.id}/artifacts/sch">KiCad 회로도 ↓</a>`:''}`:''}</div>`:
      '<p class="micro">사진을 올리면 자동 분석 결과가 여기에 나타납니다. 상단에서 분석 모델을 고를 수 있습니다. 선택한 모델은 새 입력 또는 직접 시작한 재분석에 적용됩니다.</p>'}
      </div>`;
    $('#planner-task').value=task;
    $('#planner-task').onchange=e=>{task=e.target.value;};
    $('#planner-prompt').oninput=e=>{prompt=e.target.value;};
    $('#planner-refresh').onclick=()=>run(refresh);
    $('#planner-probe').onclick=()=>run(async()=>{probe='KiCad MCP 연결 확인 중…';render();let r;try{r=await api('/api/planner/mcp/probe',{method:'POST'});}catch(e){probe='MCP 연결 실패: '+e.message;render();throw e;}probe=r.tools_ready?'MCP 연결됨 · 회로도 생성·netlist·ERC 도구 있음 · GUI 편집 확인 별도':`MCP 도구 누락: ${r.missing_tools.join(', ')}`;render();});
    $('#planner-form').onsubmit=e=>{e.preventDefault();run(async()=>{message(analysisModelLabel(selectedAnalysisModel())+'가 사진과 회로를 분석합니다…');const asset_ids=g.mode==='video'?g.assets.slice(0,6).map(a=>a.id):[state.assetId];result=await post('/planner',{prompt,task,asset_ids,model:selectedAnalysisModel()});render();message('계획을 생성했습니다. 추정 근거와 남은 확인 항목을 검토하세요.');});};
    if($('#planner-execute'))$('#planner-execute').onclick=()=>run(async()=>{message('별도 프로젝트에서 KiCad MCP 회로도 생성 → 연결 대조 → ERC 실행 중…');result=await post(`/planner/${plan.id}/execute`,{});render();ctx.renderVisuals();if(result.execution.status==='DONE')$('#user-step-4').scrollIntoView({block:'start'});message(result.execution.status==='DONE'?'MCP 회로도 생성과 검증 완료':result.execution.error,result.execution.status!=='DONE');});
  }
  document.addEventListener('ev-analysis-model-change',()=>{if(state.data)renderAutomatic();});
  return {render,refresh};
}
