import {initDatasheet} from './datasheet.js?v=functional-build-1';
import {apiPrefix} from './saas.js';
import {initEmulator} from './emulator.js?v=breadboard-3d-1';
import {renderSimulation} from './simulation.js?v=breadboard-3d-1';
import {prototypeEditorUrl} from './function-intent.js?v=photo-autorun-3';
// Identify components before reasoning about function or creating a circuit.
export const USER_STEP_IDS=['1','2','3','4'];
// A read-only input/output surface; editing and validation stay in their existing modules.
export function initIO(ctx){
  const {state,api,run,esc}=ctx;
  const datasheet=initDatasheet(ctx);
  const $=s=>document.querySelector(s);
  const layout=$('#analysis-layout'),toggle=$('#analysis-sidebar-toggle');
  function collapseSidebar(collapsed){
    layout.classList.toggle('analysis-sidebar-collapsed',collapsed);
    toggle.setAttribute('aria-expanded',String(!collapsed));
    toggle.setAttribute('aria-label',collapsed?'진행 단계 펼치기':'진행 단계 접기');
  }
  collapseSidebar(window.innerWidth<760);
  toggle.onclick=()=>collapseSidebar(!layout.classList.contains('analysis-sidebar-collapsed'));
  $('#user-steps-nav [data-go-step="1"]').onclick=()=>$('#empty').scrollIntoView({block:'start'});
  let project='',view='schematic',cachedCode=null;
  function render(){
    const g=state.data.graph,p=state.plannerResult?.project===g.project_id?state.plannerResult:null;
    if(project!==`${g.project_id}:${g.revision}`){project=`${g.project_id}:${g.revision}`;view='schematic';cachedCode=null;}
    const design=p?.newDesign?.design,code=p?.newDesign?.firmware||cachedCode;
    const source=design?.source_project||g.project_id,asset=design?'image':state.assetId;
    const photo=!!design||['photo','video'].includes(g.mode),ready=g.links.length>0;
    const selected=state.designProposal?.project===g.project_id&&state.designProposal?.revision===g.revision?state.designProposal:null;
    const proto=selected?.data?.prototype_design,protoUrl=proto?prototypeEditorUrl(`${apiPrefix}/projects/${g.project_id}/inventory/${selected.planId}`,selected.data.function_version):null;
    const newCircuit=g.mode==='reference_design',added=new Set(design?.added_parts?.map(p=>p.reference)||[]);
    const execution=p?.execution,done=execution?.status==='DONE'&&!execution.stale&&!p?.plan?.stale;
    const base=`${apiPrefix}/projects/${g.project_id}`,art=done?`${base}/planner/${p.plan.id}/artifacts`:null;
    const legacy=state.data.integrated.eda;
    const preview=done?`${art}/svg`:legacy?.connectivity==='PASS'?`${base}/artifacts/schematic`:null;
    const firmwareSupported=['esp32_led_button','arduino_lcd','arduino_voltage_divider','arduino_led_output','arduino_led_blink','arduino_led_brightness','arduino_led_button','arduino_light_led'].includes(g.profile)&&!state.data.integrated.readiness.length;
    const parts=p?.plan?.inventory?.parts||g.components.map(c=>({name:(c.label.value||c.id)+(added.has(c.id)?' · 추가 부품':''),quantity:1}));
    $('#io-overview').innerHTML=`<section class="panel io-input"><div class="panel-heading"><div><span class="io-kicker">INPUT</span><h2>${photo?'입력 사진':'입력 · 설계 예제'}</h2></div><div class="input-actions"><label class="button" for="upload">사진 선택</label><label class="button" for="video-upload">영상 선택</label></div></div>
      <div class="io-photo"><img src="${apiPrefix}/projects/${source}/assets/${esc(asset)}" alt="${design?'새 설계에 사용한 원본 사진':'분석할 입력 이미지'}"></div>
      <div class="io-caption">${g.mode==='video'?`<label>영상 프레임 <select id="io-frame">${g.assets.map(a=>`<option value="${esc(a.id)}" ${a.id===state.assetId?'selected':''}>${esc(a.filename)}</option>`).join('')}</select></label>`:photo?'사진의 구성품 목록부터 작성하고 기능·보완 부품·데이터시트 순서로 새 회로를 구성합니다.':'실제 촬영 사진이 아닌 설계 예제입니다.'}</div>
      <details class="input-part-details"><summary>부품 요약 · ${parts.length}종</summary><div class="io-parts"><small>${design?'새 설계에 선택한 부품':photo?'식별한 부품 후보':'예제 부품'}</small>${parts.slice(0,12).map(c=>`<span>${esc(c.name)}${c.quantity>1?' × '+c.quantity:''}</span>`).join('')||'<span>부품 분석 대기</span>'}</div></details></section>
`;
    $('#io-output-host').innerHTML=`<section class="panel io-output"><div class="panel-heading"><div><span class="io-kicker">OUTPUT</span><h2>새 회로와 코드</h2></div><span class="tag">${proto?'시제품 편집기 준비됨':ready?(newCircuit?'새 설계 · 실물 미검증':'관측 초안 · 미검증'):'아직 생성 전'}</span></div>
      <nav class="io-tabs" aria-label="출력 보기">${[['schematic','회로도'],['code','코드'],['guide','연결 목록'],['simulation','회로 계산'],['emulator','임베디드 실행']].map(([key,label])=>`<button data-io-view="${key}" aria-pressed="${view===key}">${label}</button>`).join('')}</nav>
      <div id="io-result" class="io-result"></div><div class="io-actions">
      ${proto?`<a class="button primary" href="${esc(protoUrl)}" target="_blank" rel="noopener noreferrer">회로·시뮬레이터 열기 ↗</a>`:ready?`<button id="io-enlarge">크게 보기</button>${done?`<a class="button" href="${art}/sch">KiCad 회로도 ↓</a>`:legacy?`<a class="button" href="${base}/artifacts/sch">KiCad 회로도 ↓</a>`:''}${firmwareSupported?`<a class="button" href="${base}/firmware?download=true">Arduino 코드 ↓</a>`:''}${p?.plan?.executable&&!execution&&!p.plan.stale?'<button id="io-build" class="primary">KiCad 회로도 생성</button>':''}`:'<button id="io-prepare" class="primary">③ 기능·부품 보완로 돌아가기 ↑</button>'}
      </div></section>`;
    renderSteps(g,p,ready,done,!!proto);
    datasheet.refresh();
    const area=$('#io-result');
    if(proto)area.innerHTML=`<div class="io-empty"><b>선택한 기능의 회로와 코드가 준비됐습니다.</b><p>아래 편집기에서 부품·배선을 확인하고 코드를 실행하세요.</p><small>새 시제품이며 실제 부품과 원본 동작은 별도 확인이 필요합니다.</small></div>`;
    else if(view==='code')area.innerHTML=code?`<pre class="io-code">${esc(code.source)}</pre>`:`<div class="io-empty"><b>${firmwareSupported?'코드를 불러오세요':'새 회로를 만들면 코드가 여기에 표시됩니다.'}</b>${firmwareSupported?'<button id="io-load-code">코드 보기</button>':'<p>현재 지원: Arduino 저항 분압·LCD / ESP32 LED·버튼</p>'}</div>`;
    else if(view==='emulator')area.innerHTML=g.profile==='arduino_voltage_divider'?'<div class="io-emulator"></div>':'<div class="io-empty"><p>현재 가상 MCU 실행은 UNO R3 저항 분압 회로를 지원합니다. ② 새 회로 제안에서도 실행할 수 있습니다.</p></div>';
    else if(view==='simulation')area.innerHTML=g.profile==='arduino_voltage_divider'?'<div class="io-simulator"></div>':'<div class="io-empty"><p>현재 기본 화면의 시뮬레이션은 UNO 저항 분압 회로를 지원합니다. 새 회로 제안 단계에서도 시험할 수 있습니다. RC·ESP32 근사 모델은 고급 파형 도구에서 확인하세요.</p></div>';
    else if(view==='guide')area.innerHTML=ready?`<p class="io-diagram-note">회로의 전기적 연결 목록입니다. 실제 빵판 조립 순서와 구멍 위치는 시뮬레이터의 단계별 조립 가이드에서 확인하세요.</p>${['arduino_voltage_divider','arduino_led_output','arduino_led_blink','arduino_led_brightness','arduino_led_button','arduino_light_led'].includes(g.profile)?'<p class="io-diagram-note">③ 기능·부품 보완에서 그래픽 시뮬레이터를 열고 <b>단계별 조립 가이드</b>를 선택하세요.</p>':''}<ol class="io-guide">${state.data.tutorial.steps.map(s=>`<li><b>${esc(s.from)} → ${esc(s.to)}</b><details class="compact-details"><summary>연결 방법·이유</summary><p>${esc(s.wire_color)} 전선 · ${esc(s.why)}</p></details></li>`).join('')}</ol>`:'<div class="io-empty"><b>새 회로를 만들면 연결 목록이 표시됩니다.</b></div>';
    else area.innerHTML=ready?`<div class="io-diagram schematic">${$('#schematic').innerHTML}</div><p class="io-diagram-note">${newCircuit?'새 회로':'관측 초안'}의 연결 미리보기${done?' · KiCad 파일 생성 완료':''}</p>${preview?`<details class="compact-details"><summary>KiCad 원본 도면 보기</summary><img class="eda-image" src="${preview}" alt="KiCad 출력 회로도"></details>`:''}`:`<div class="io-empty"><span class="io-empty-icon">⌁</span><b>입력 사진이 새 회로로 바뀌는 곳</b><p>구성품 목록 → 기능 추론 → 부품 보완·데이터시트 → 회로·코드 생성</p><small>아직 회로를 생성하지 않았습니다.</small></div>`;
    area.querySelectorAll('[role=button]').forEach(el=>{el.removeAttribute('role');el.removeAttribute('tabindex');});
    area.querySelectorAll('[id]').forEach(el=>{if(el.id!=='io-load-code')el.removeAttribute('id');});
    if(view==='emulator'&&g.profile==='arduino_voltage_divider')initEmulator(area.querySelector('.io-emulator'),{api,endpoint:base+'/emulator',revision:g.revision,esc});
    if(view==='simulation'&&g.profile==='arduino_voltage_divider')renderSimulation(area.querySelector('.io-simulator'),{result:state.data.integrated.simulation,esc,onRun:async analysis=>{const result=await ctx.post('/simulate',{analysis});await ctx.accept(result);return result.integrated.simulation;}});
    document.querySelectorAll('[data-io-view]').forEach(b=>b.onclick=()=>{view=b.dataset.ioView;render();});
    if($('#io-frame'))$('#io-frame').onchange=e=>{state.assetId=e.target.value;ctx.renderVisuals();};
    if($('#io-prepare'))$('#io-prepare').onclick=()=>$('#user-step-3').scrollIntoView({block:'start'});
    if($('#io-build'))$('#io-build').onclick=()=>$('#planner-execute')?.click();
    if($('#io-load-code'))$('#io-load-code').onclick=()=>run(async()=>{const id=g.project_id,revision=g.revision;const value=await api(`${base}/firmware`);if(state.data.graph.project_id===id&&state.data.graph.revision===revision){cachedCode=value;render();}});
    if($('#io-enlarge'))$('#io-enlarge').onclick=()=>{
      $('#output-preview-content').innerHTML=area.innerHTML;
      $('#output-preview-content').querySelectorAll('[id]').forEach(e=>e.removeAttribute('id'));
      $('#output-preview').showModal();
    };
  }
  function renderSteps(g,p,ready,done,prototypeReady=false){
    const inventory=p?.plan?.inventory,designed=g.mode==='reference_design';
    const partsReady=(!!inventory?.parts.length&&!p.plan.stale)||designed;
    const current=ready&&designed||prototypeReady?4:p?.plan?.analysis_complete===true?3:2;
    const statuses=['입력 저장됨',inventory?`${inventory.parts.length}종 후보`:designed?'설계 부품 목록':'구성품 분석 대기',p?.plan?.analysis_complete===false?'기능·보완 부품 분석 중':p?.plan?.component_datasheet?'데이터시트 준비됨':partsReady?'기능 확인·구성':'구성품 확인 후 진행',prototypeReady?'시제품 편집기 준비됨':done?'KiCad 파일 준비됨':designed&&ready?'회로·코드 확인 가능':'생성 전'];
    const names=['사진·영상 입력','구성품 목록','기능·부품 보완','회로·시뮬레이션'];
    $('#user-steps-nav').innerHTML=names.map((name,i)=>`<button type="button" title="${i+1}. ${name}" data-go-step="${i+1}" ${current===i+1?'aria-current="step"':''}><span>${i+1}</span><div><b>${name}</b><small>${esc(statuses[i])}</small></div><i aria-hidden="true">→</i></button>`).join('');
    statuses.forEach((status,i)=>$('#user-step-status-'+USER_STEP_IDS[i]).textContent=status);
    $('#parts-to-design').disabled=!partsReady;
    $('#design-to-output').disabled=!ready&&!prototypeReady;
    document.querySelectorAll('[data-go-step]').forEach(button=>button.onclick=()=>{
      const step=button.dataset.goStep;
      const target=USER_STEP_IDS[Number(step)-1];if(!target)return;
      $('#user-step-'+target).scrollIntoView({block:'start',behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth'});
      document.querySelectorAll('#user-steps-nav [data-go-step]').forEach(b=>{if(b.dataset.goStep===step)b.setAttribute('aria-current','step');else b.removeAttribute('aria-current');});
    });
  }
  $('#close-output-preview').onclick=()=>$('#output-preview').close();
  return {render};
}
