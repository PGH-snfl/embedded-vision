import {apiPrefix} from './saas.js';
const stages=[['input','입력 확인'],['recognition','부품·문자'],['wiring','새 회로 구성'],['validation','회로 검증'],['outputs','결과물']];

export function initWorkflow(ctx){
  const {state,esc,navigate}=ctx;
  const $=s=>document.querySelector(s);
  function render(stage){
    const {graph:g,integrated:i}=state.data,asset=g.assets.find(a=>a.id===state.assetId)||g.assets[0];
    const photo=['photo','video'].includes(g.mode),parts=g.components.filter(c=>c.asset_id===asset.id);
    const pins=parts.flatMap(c=>c.terminals),positioned=pins.filter(t=>t.image_position).length;
    const texts=(g.text_observations||[]).filter(t=>t.asset_id===asset.id);
    const hypotheses=(g.wire_hypotheses||[]).filter(h=>h.asset_id===asset.id);
    const confirmed=g.links.filter(l=>l.connection.status==='CONFIRMED').length;
    const inferred=g.links.filter(l=>l.connection.status==='INFERRED').length;
    const unknown=g.links.filter(l=>l.connection.status==='UNKNOWN').length;
    const planner=state.plannerResult?.project===g.project_id?state.plannerResult:null,inventory=planner?.plan?.inventory;
    const blockers=i.readiness,eda=planner?.execution||i.eda,simulation=i.simulation;
    const stateNames=[photo?'입력 저장됨':'설계 예제',inventory?`${inventory.parts.length}종 부품 후보`:parts.length?`${parts.length}개 ${photo?'후보':'부품'}`:'부품 목록 대기',
      photo?'기능 추정 후 새 설계':`${g.links.length}개 설계 연결`,
      blockers.length?`${blockers.length}항목 확인 필요`:'생성 조건 충족',eda||simulation?'생성 결과 있음':'생성 전'];
    const index=stages.findIndex(s=>s[0]===stage),name=stages[index][1];
    const content={
      input:{title:'분석할 입력을 먼저 확인하세요',description:'파일과 프로젝트 종류를 확인한 뒤 다음 단계로 이동합니다. 단계 이동만으로 분석이나 설계를 실행하지 않습니다.',
        input:photo?`${asset.filename} · ${asset.width} × ${asset.height}`:'명시된 설계 예제 · 사진 복원 결과 아님',
        process:g.mode==='video'?'영상에서 주요 프레임을 추출하고 선택한 프레임을 표시합니다.':photo?'사진을 저장하고 분석에 사용할 좌표를 준비합니다.':'미리 정의한 부품과 연결을 불러옵니다.',
        output:`${g.assets.length}개 ${g.mode==='video'?'프레임':'이미지'} · 현재 ${asset.id} · 수정 버전 r${g.revision}`},
      recognition:{title:'부품 이름과 실제 핀을 구분해 확인하세요',description:'AI 후보와 읽은 문자를 대조합니다. 문자 위치와 전선이 꽂힌 접점은 다르므로, 실제 핀 위치를 따로 검토합니다.',
        input:'선택한 입력 이미지',process:photo?'부품 탐색 → 확대 재검토 → OCR(사진 속 문자 읽기) → 사용자 확인':'설계 정의와 지원 부품 카탈로그를 대조합니다.',
        output:`부품 ${parts.length}개 · 문자 영역 ${texts.length}개 · 위치를 지정한 핀 ${positioned}개`},
      wiring:{title:photo?'추정 기능으로 새 회로를 구성하세요':'설계 예제의 핀 연결을 확인하세요',description:photo?'추정 기능으로 새 설계를 살펴보고 필요한 부품을 사진의 후보와 비교하세요. 원본 배선은 재현할 필요가 없습니다.':'예제에 명시된 부품 사이의 연결입니다. 사진에서 배선을 추정한 결과가 아닙니다.',
        input:photo?`사진의 선 조각 + 위치를 지정한 핀 ${positioned}개`:`설계 정의의 연결 ${g.links.length}개`,process:photo?'구성품 목록 → 기능 추론 → 부품 보완·데이터시트 → 새 연결·코드 생성':'설계에 명시한 핀과 부품 사이의 연결을 대조합니다.',
        output:`${photo?'경로 가설 '+hypotheses.length+'개 · ':''}전체 회로 연결: 추론 ${inferred} / 미확인 ${unknown} / 확정 ${confirmed}`},
      validation:{title:'회로 데이터의 빈칸과 검증 상태를 확인하세요',description:'Circuit Graph는 부품·핀·연결·근거를 함께 저장한 공통 회로 데이터입니다. 이 데이터를 확인한 뒤 결과물을 생성합니다.',
        input:`전체 회로: 부품 ${g.components.length}개 · 연결 ${g.links.length}개`,process:'부품 모델·값 → 데이터시트 핀 대응 → 연결 확인 → 생성 조건 검사',
        output:blockers.length?`미해결 ${blockers.length}항목 · 결과 생성 대기`:'생성 조건 충족 · 실물 작동 확인은 별도'},
      outputs:{title:'생성된 파일과 실제 계산 결과를 확인하세요',description:'확인한 회로 데이터에서 회로도·PCB·파형·코드를 생성합니다. 아직 생성하지 않은 결과는 미생성으로 표시합니다.',
        input:`현재 회로 데이터 r${g.revision}`,process:'KiCad 회로도 → 연결 대조·ERC → PCB·DRC / 지원 회로의 SPICE 계산',
        output:`회로도 ${eda?'생성됨':'미생성'} · PCB ${eda?.pcb==='GENERATED'?'생성됨':'미생성'} · 파형 ${simulation?'계산됨':'미계산'}`}
    }[stage];
    $('#workflow-overview').innerHTML=`<nav class="stage-nav" aria-label="부품 확인과 새 설계 단계">${stages.map(([key,label],n)=>`<button type="button" data-stage="${key}" ${key===stage?'aria-current="step"':''}><span class="stage-number">${String(n+1).padStart(2,'0')}</span><span><b>${label}</b><small>${esc(stateNames[n])}</small></span><span class="stage-chevron" aria-hidden="true">›</span></button>`).join('')}</nav>
      <section class="stage-summary" aria-labelledby="stage-title"><div class="stage-heading"><div><span class="eyebrow">STEP ${index+1} / 5 · ${esc(name)}</span><h2 id="stage-title">${content.title}</h2><p>${content.description}</p></div><span class="stage-context">${photo?'실제 입력 검토':'설계 예제'}<br>r${g.revision} · ${esc(asset.id)}</span></div><div class="stage-io">${[['입력',content.input],['처리',content.process],['출력',content.output]].map(([label,text],n)=>`<article><span class="io-label">${label}</span><p>${esc(text)}</p>${n<2?'<span class="io-arrow" aria-hidden="true">→</span>':''}</article>`).join('')}</div>
      <div class="stage-actions"><span>단계 상태는 현재 데이터 기준입니다. 후보 생성은 연결 검증 완료를 뜻하지 않습니다.</span><div><button id="stage-back" ${index===0?'disabled':''}>← 이전</button><button id="stage-next" class="primary" ${index===4?'disabled':''}>${index===4?'마지막 단계':stages[index+1][1]+' 확인 →'}</button></div></div></section>`;
    $('#workflow-overview').querySelectorAll('[data-stage]').forEach(b=>b.onclick=()=>navigate(b.dataset.stage));
    $('#stage-back').onclick=()=>navigate(stages[index-1][0]);
    $('#stage-next').onclick=()=>navigate(stages[index+1][0]);
    $('#flow-input-summary').innerHTML=`<div class="panel-heading"><h2>이번 입력에서 확인할 것</h2><span class="tag">입력 1건 기준</span></div><div class="flow-body"><dl><dt>프로젝트</dt><dd>${esc(g.title)}</dd><dt>선택한 이미지</dt><dd>${esc(asset.filename)}</dd><dt>분석 결과</dt><dd>${inventory?inventory.parts.length+'종 자동 식별 후보':parts.length+'개 지정 부품'} · ${texts.length}개 문자 영역</dd><dt>중간 결과</dt><dd>${photo?'구성품 목록 → 기능 추론 → 보완·데이터시트 → 새 회로':g.links.length+'개 새 연결'}</dd><dt>최종 결과</dt><dd>${eda?'생성 기록 있음':'아직 생성하지 않음'}</dd></dl><p class="flow-note">${photo?'기능 후보를 바탕으로 회로를 제안하고 필요한 부품과 사진을 비교합니다. 기존 배선 관측 데이터는 보존됩니다.':'이 프로젝트는 새 설계 예제입니다. 사진에서 회로를 복원한 결과가 아닙니다.'}</p><button data-flow-open="recognition">부품·문자 확인 시작 →</button></div>`;
    $('#flow-validation').innerHTML=`<div class="validation-layout"><section class="panel"><div class="panel-heading"><h2>다음 단계로 넘기기 전</h2><span class="tag">${blockers.length?'확인 필요':'생성 가능'}</span></div><div class="flow-body">${blockers.length?`<ul class="blocker-list">${blockers.map(b=>`<li>${esc(b)}</li>`).join('')}</ul>`:'<p>지원 카탈로그·핀 매핑·연결의 생성 조건을 충족했습니다. 실제 검사는 결과물 단계에서 실행합니다.</p>'}<div class="flow-links"><button data-flow-open="recognition">부품·핀 확인</button><button data-flow-open="wiring">배선 가설 검토</button><button id="flow-catalog">데이터시트·카탈로그 확인</button></div></div></section><section class="panel"><div class="panel-heading"><h2>검증 상태 읽기</h2></div><div class="flow-body"><dl><dt>부품·핀·연결</dt><dd>${blockers.length?'검토 필요':'생성 조건 충족'}</dd><dt>회로 연결 대조</dt><dd>${esc(eda?.connectivity||'NOT_RUN · 미실행')}</dd><dt>ERC · 회로 규칙</dt><dd>${esc(eda?.erc||'NOT_RUN · 미실행')}</dd><dt>DRC · PCB 규칙</dt><dd>${esc(eda?.drc||'NOT_RUN · 미실행')}</dd><dt>실물 작동</dt><dd>미검증</dd></dl><p class="flow-note">확정 = 근거로 확인한 정보 · 추론 = 가능한 후보 · 미확인 = 판단 근거 부족. 순위 점수는 정답 확률이 아닙니다.</p></div></section></div>`;
    $('#flow-results').innerHTML=`<div class="output-cards">${[
      ['회로 데이터','항상 확인 가능','부품·핀·연결·관측 근거를 담은 JSON 파일','graph'],
      ['회로도·PCB',eda?`ERC ${eda.erc} · DRC ${eda.drc}`:'미생성','KiCad에서 편집할 파일과 설계 검사 결과','build'],
      ['파형·측정 지점',simulation?'계산 결과 있음':'미계산','지원 회로의 전압·전류를 실제 계산한 결과','scope'],
      ['코드·조립 설명',['esp32_led_button','arduino_lcd','arduino_voltage_divider','arduino_led_output','arduino_led_blink','arduino_led_brightness','arduino_led_button','arduino_light_led'].includes(g.profile)?'코드 생성 지원':'가이드 확인','연결 순서와 이유. 펌웨어·실물 작동은 별도 검증','code']
    ].map(([title,status,description,target])=>`<article><span class="tag">${esc(status)}</span><h3>${title}</h3><p>${description}</p>${target==='graph'?`<a class="button" href="${apiPrefix}/projects/${g.project_id}/export" download>회로 데이터 내려받기</a>`:`<button data-output-tab="${target}">열기 →</button>`}</article>`).join('')}</div>${blockers.length?`<div class="flow-blocked">새 결과를 생성하려면 ${blockers.length}개 확인 항목을 해결해야 합니다. <button data-flow-open="validation">확인 항목 보기</button></div>`:''}`;
    document.querySelectorAll('[data-flow-open]').forEach(b=>b.onclick=()=>navigate(b.dataset.flowOpen));
    $('#flow-catalog').onclick=()=>navigate('validation','catalog');
    document.querySelectorAll('[data-output-tab]').forEach(b=>b.onclick=()=>navigate('outputs',b.dataset.outputTab));
    $('#workspace').dataset.stage=stage;
    $('#review-workspace').hidden=stage==='outputs';$('#review-workspace').classList.toggle('tab-hidden',stage==='outputs');
    $('#full-pipeline').disabled=blockers.length>0||['arduino_lcd','arduino_voltage_divider','arduino_led_output','arduino_led_blink','arduino_led_brightness','arduino_led_button','arduino_light_led'].includes(g.profile);
    if($('#build-now'))$('#build-now').disabled=blockers.length>0||['arduino_lcd','arduino_voltage_divider','arduino_led_output','arduino_led_blink','arduino_led_brightness','arduino_led_button','arduino_light_led'].includes(g.profile);
    if($('#simulate-now'))$('#simulate-now').disabled=blockers.length>0||g.profile==='arduino_lcd';
    if($('#load-code'))$('#load-code').disabled=blockers.length>0||!['esp32_led_button','arduino_lcd','arduino_voltage_divider','arduino_led_output','arduino_led_blink','arduino_led_brightness','arduino_led_button','arduino_light_led'].includes(g.profile);
  }
  return {render};
}
