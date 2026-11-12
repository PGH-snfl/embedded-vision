import {selectedAnalysisModel} from './analysis-model.js?v=analysis-model-1';
import {markAutoLaunch} from './auto-navigation.js?v=photo-auto-nav-2';
import {apiPrefix} from './saas.js';
import {initIO} from './io.js?v=functional-build-1';
import {initPlanner} from './planner.js?v=analysis-errors-1';
import {initPinReview} from './pinreview.js?v=breadboard-3d-1';
import {initCamera} from './camera.js?v=analysis-model-1';
import {initSingleView} from './singleview.js?v=breadboard-3d-1';
import {initWorkflow} from './workflow.js?v=components-first-2';
export function initIntegrated(ctx) {
  const {state,api,run,accept,post,select,renderVisuals,message,esc}=ctx;
  const $=s=>document.querySelector(s);
  const io=initIO(ctx);
  const planner=initPlanner(ctx);
  const camera=initCamera({...ctx,refreshAnalysis:planner.refresh});
  const pinReview=initPinReview(ctx);
  const occlusion=initSingleView(ctx);
  let tab='review',channels=['',''],sample=0,timer=null,firmwareData=null,codeProject='',agentReply='';
  let stage='input',stageProject='';
  const workflow=initWorkflow({...ctx,navigate});
  function navigate(next,subtab){
    if(timer){clearInterval(timer);timer=null;}
    stage=next;tab=subtab||(stage==='outputs'?'build':'review');
    state.pendingPinReview=null;state.pendingAnchor=null;
    $('#technical-details').open=true;renderVisuals();$('#workflow-overview').scrollIntoView({block:'start'});
  }
  const project=()=>state.data.graph;
  const endpoint=path=>`${apiPrefix}/projects/${project().project_id}${path}`;
  const badge=value=>`<span class="result-badge ${value==='PASS'?'pass':value==='FAIL'?'fail':''}">${esc(value)}</span>`;
  function wireEvents(){
    $('#open-planner').onclick=()=>$('#user-step-2').scrollIntoView({block:'start'});
    $('#reference-esp').onclick=()=>run(()=>newReference('esp32_led_button'));
    $('#reference-rc').onclick=()=>run(()=>newReference('rc_filter'));
    $('#video-upload').onchange=()=>run(async()=>{const f=$('#video-upload').files[0];if(!f)return;const body=new FormData();body.append('video',f);body.append('analysis_model',selectedAnalysisModel());message('영상에서 선명한 주요 프레임을 추출합니다…');state.assetId='image';const uploaded=await api('/api/projects/video',{method:'POST',body});const autoReady=markAutoLaunch(uploaded.graph.project_id);await accept(uploaded);message(autoReady?'주요 프레임에서 구성품을 먼저 식별하고 기능·보완 부품을 분석합니다.':'영상은 저장했습니다. 브라우저 세션 저장이 불가능해 자동 이동할 수 없습니다. 분석 후 회로·시뮬레이터 열기 버튼을 눌러 주세요.');$('#video-upload').value='';await planner.refresh();$('#user-step-2').scrollIntoView({block:'start'});});
  }
  async function newReference(profile){
    message('새 설계 예제를 만들고 회로도·PCB 검사와 파형 계산을 실행합니다…');state.assetId='image';state.selected=null;tab='build';
    await accept(await api('/api/projects/reference',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({profile})}));
    stage='outputs';tab='build';renderVisuals();
    await fullPipeline();
  }
  async function fullPipeline(){
    const blockers=state.data.integrated.readiness;
    if(blockers.length){message('먼저 확인할 항목: '+blockers.slice(0,6).join(' / '),true);return;}
    message('KiCad 회로도 → 연결 대조 → ERC → PCB 배선 → DRC 실행 중…');
    await accept(await post('/build',{}));
    message('ngspice 파형을 계산합니다…');
    await accept(await post('/simulate',{analysis:'transient'}));
    message(`통합 실행 완료: 연결 ${state.data.integrated.eda.connectivity} · ERC ${state.data.integrated.eda.erc} · DRC ${state.data.integrated.eda.drc}. 실물 검증은 별도입니다.`);
  }
  function render(){
    if(!state.data)return;
    const g=project(),integrated=state.data.integrated;
    if(stageProject!==g.project_id){stageProject=g.project_id;stage='input';tab='review';}
    $('#integration-tools').innerHTML=`<div class="workflow-tools"><select id="asset-select" aria-label="검토할 사진 또는 프레임">${g.assets.map((a,i)=>`<option value="${esc(a.id)}" ${a.id===state.assetId?'selected':''}>${i+1}. ${esc(a.filename)}</option>`).join('')}</select><select id="anchor-terminal" aria-label="사진에 표시할 핀">${g.components.filter(c=>c.asset_id===state.assetId).flatMap(c=>c.terminals.map(t=>`<option value="${esc(t.id)}">${esc(c.id)} · ${esc(t.name.value||t.id)}</option>`)).join('')}</select><button id="anchor-mark">핀 위치 지정</button><button id="analyze-image">◎ OCR·부품 후보 분석</button><label class="pcb-analysis"><input id="pcb-analysis" type="checkbox"> PCB 표면 분석</label><button id="full-pipeline" class="primary">설계 전체 실행 →</button></div><nav class="workspace-tabs">${[['review','연결 검토'],['build','회로도·PCB'],['scope','파형·전류'],['code','코드·조립'],['catalog','부품·근거']].map(([key,name])=>`<button data-worktab="${key}" class="${tab===key?'active':''}">${name}</button>`).join('')}</nav>`;
    $('#asset-select').onchange=()=>{state.assetId=$('#asset-select').value;state.selected=null;renderVisuals();};
    $('#anchor-mark').onclick=()=>{const terminal=$('#anchor-terminal').value;if(!terminal){message('먼저 부품과 단자 라벨을 지정하세요.',true);return;}state.pendingAnchor=terminal;tab='review';render();message(terminal+' 핀의 실제 위치를 이미지에서 클릭하세요.');};
    $('#analyze-image').onclick=()=>run(async()=>{const pcb=$('#pcb-analysis').checked;message('로컬 OCR 모델이 글자와 부품 표식 후보를 분석합니다…');await accept(await post('/analyze',{asset_id:state.assetId,pcb}));message(`OCR 분석 완료: ${state.data.integrated.analysis.ocr.length}개 문자 영역. 자동 연결은 확정하지 않았습니다.`);});
    $('#full-pipeline').onclick=()=>run(fullPipeline);
    document.querySelectorAll('[data-worktab]').forEach(b=>b.onclick=()=>navigate(b.dataset.worktab==='catalog'?'validation':b.dataset.worktab==='review'?'wiring':'outputs',b.dataset.worktab));
    $('#review-workspace').hidden=tab!=='review';$('#review-workspace').classList.toggle('tab-hidden',tab!=='review');
    const area=$('#integration-workspace');area.innerHTML='';
    if(tab==='build')renderBuild(area,integrated);
    else if(tab==='scope')renderScope(area,integrated);
    else if(tab==='code')renderCode(area,integrated);
    else if(tab==='catalog')renderCatalog(area,integrated);
    else if(integrated.analysis)renderAnalysis(area,integrated.analysis);
    renderAssistant();camera.render();pinReview.render();occlusion.render();
    $('.notice span').textContent=state.data.tutorial.notice;
    document.querySelectorAll('.version').forEach(e=>e.textContent='CIRCUIT PLANNER · 0.4');
    workflow.render(stage);io.render();
  }
  function renderBuild(area,i){
    if(['arduino_lcd','arduino_voltage_divider'].includes(project().profile)){
      area.innerHTML='<section class="panel"><div class="result-body"><h2>새 Arduino 회로도 · KiCad MCP</h2><p>아래 계획에서 MCP로 회로도 생성 → 연결 대조 → ERC를 실행하세요. PCB는 아직 지원하지 않습니다. UNO 분압 회로의 SPICE 계산은 ④ 시뮬레이션에서 실행할 수 있습니다. LCD 문자 표시는 원본 분석의 기능 목표에서 그래픽 시뮬레이터를 열어 실행할 수 있습니다.</p><button id="lcd-mcp-results">새 회로·코드·검사 결과 보기 ↓</button></div></section>';
      $('#lcd-mcp-results').onclick=()=>$('#assistant-panel').scrollIntoView({block:'start'});return;
    }
    const e=i.eda;
    area.innerHTML=`<div class="integration-grid"><section class="panel"><div class="panel-heading"><h2>KiCad 편집 가능 회로도</h2><button id="build-now">${e?'현재 버전 다시 검사':'회로도·PCB 생성'}</button></div><div class="result-body">${e?`<div class="gate-pills">연결 대조 ${badge(e.connectivity)} ERC ${badge(e.erc)}</div><img class="eda-image" src="${endpoint('/artifacts/schematic')}" alt="KiCad가 내보낸 실제 회로도"><div class="download-row"><a class="button" href="${endpoint('/artifacts/sch')}">회로도 파일 ↓</a><a class="button" href="${endpoint('/artifacts/erc')}">ERC 보고서 ↓</a></div>`:`<p>확인한 그래프에서 회로도를 만들고 KiCad가 다시 읽은 연결과 원래 그래프를 대조합니다.</p><ul>${i.readiness.slice(0,12).map(x=>`<li>${esc(x)}</li>`).join('')||'<li>생성 조건을 만족합니다.</li>'}</ul>`}</div></section><section class="panel"><div class="panel-heading"><h2>PCB 배치·배선</h2>${badge(e?.drc||'NOT_RUN')}</div><div class="result-body">${e?.pcb==='GENERATED'?`<div class="pcb-view"><img class="eda-image" src="${endpoint('/artifacts/pcb')}" alt="실제 KiCad PCB 레이어 출력"></div><div class="download-row"><a class="button primary" href="${endpoint('/artifacts/zip')}">KiCad 프로젝트 ZIP ↓</a><a class="button" href="${endpoint('/artifacts/board')}">PCB 파일 ↓</a><a class="button" href="${endpoint('/artifacts/drc')}">DRC 보고서 ↓</a></div>`:'<p>회로도 연결 대조와 ERC를 통과하면 PCB를 생성합니다.</p>'}<p class="engineering-note">${esc(e?.note||'지원하는 카탈로그 부품으로 구성된 예제를 먼저 검증하세요.')}</p>${e?.drc_violations?.length?`<ul class="errors">${e.drc_violations.slice(0,10).map(v=>`<li>${esc(v.description)}</li>`).join('')}</ul>`:''}</div></section></div>`;
    $('#build-now').onclick=()=>run(async()=>{message('회로도와 PCB 생성·검사 중…');await accept(await post('/build',{}));message('생성과 검사 결과를 업데이트했습니다.');});
  }
  function renderAnalysis(area,a){
    area.innerHTML=`<section class="panel analysis-panel"><div class="panel-heading"><h2>자동 분석 결과 · ${esc(a.engine)}</h2><span class="tag">분석 r${a.revision}</span></div><div class="result-body"><div class="ocr-tags">${a.ocr.map(r=>`<span>${esc(r.text)} <small>문자 점수 ${r.score.toFixed(2)}</small></span>`).join('')||'<p>읽을 수 있는 표식을 찾지 못했습니다.</p>'}</div><p>부품 후보 ${a.component_proposals_added}개 추가 · 추정 연결 후보 ${a.proposed_links?.length||0}개 · 자동 확정 연결 ${a.electrical_nets_inferred}개 · PCB 내층 ${a.inner_layers}</p>${a.trace_candidates.length?`<p>표면 직선 후보 ${a.trace_candidates.length}개. 부품 테두리나 인쇄선일 수 있어 전기적 net에 넣지 않았습니다.</p>`:''}<p class="engineering-note">${a.limitations.map(esc).join(' ')}</p></div></section>`;
  }
  function vector(sim,name){const v=sim.vectors[name.toLowerCase()];return Array.isArray(v)?v:v?.real?.map((x,i)=>Math.hypot(x,v.imag[i]));}
  function renderScope(area,i){
    const sim=i.simulation,g=project();
    if(sim){if(!sim.nodes.includes(channels[0]))channels[0]=sim.nodes[0];if(!sim.nodes.includes(channels[1]))channels[1]=sim.nodes[1]||sim.nodes[0];}
    area.innerHTML=`<div class="integration-grid"><section class="panel scope-panel"><div class="panel-heading"><h2>오실로스코프 · 실제 ngspice 결과</h2><span class="tag">${sim?esc(sim.analysis):'NOT_RUN'}</span></div><div class="scope-toolbar"><label>분석<select id="analysis-type">${['transient','ac','dc'].map(a=>`<option ${a===sim?.analysis?'selected':''}>${a}</option>`).join('')}</select></label><button id="simulate-now" class="primary">계산 실행</button>${sim?[0,1].map((ch)=>`<label>CH${ch+1}<select id="channel-${ch}">${sim.nodes.map(n=>`<option ${channels[ch]===n?'selected':''}>${n}</option>`).join('')}</select></label>`).join(''):''}</div><div id="waveform">${sim?'':'<p class="empty-schematic">시뮬레이션을 실행하면 두 Test Point의 파형이 표시됩니다.</p>'}</div><div class="result-body"><div id="scope-readout"></div>${sim?`<div class="current-controls"><button id="play-current">전류 재생 ▶</button><input id="sample-position" aria-label="파형 시점" type="range" min="0" max="${Math.max(0,(vector(sim,channels[0])?.length||1)-1)}" value="0"><strong id="current-readout"></strong></div><p class="engineering-note">${esc(sim.note)}</p><small>${esc(sim.current_reference)}</small><details><summary>실제 SPICE 입력 보기</summary><pre>${esc(sim.deck)}</pre></details>`:''}</div></section><section class="panel"><div class="panel-heading"><h2>값 변경·Test Point</h2><span class="micro">GRAPH → SPICE → WAVEFORM</span></div><div class="result-body"><form id="parameters-form">${g.components.filter(c=>['resistor','capacitor'].includes(c.kind)).map(c=>`<label>${esc(c.id)}<input name="${esc(c.id)}" value="${esc(c.value.value||'')}" required></label>`).join('')}<label>주파수 (Hz)<input name="frequency" type="number" min="0.1" max="1000000" step="any" value="${g.parameters.frequency||1000}" required></label><label>진폭 (V)<input name="amplitude" type="number" min="0.001" max="3.3" step="any" value="${g.parameters.amplitude||1}" required></label><button class="primary" type="submit">그래프 변경·파형 다시 계산</button></form><div class="testpoints">${i.test_points.map(n=>`<button data-tp="${esc(n.name)}">${esc(n.name)}</button>`).join('')}</div><p class="engineering-note">Test Point는 측정할 전기적 노드 이름입니다. PCB·KiCad·SPICE가 같은 이름을 사용합니다. 추가 프로브용 패드는 아직 배치하지 않습니다.</p><div id="current-schematic"></div></div></section></div>`;
    $('#simulate-now').onclick=()=>run(async()=>{message('ngspice 해석 중…');await accept(await post('/simulate',{analysis:$('#analysis-type').value}));message('실제 계산 결과를 업데이트했습니다.');});
    if(g.profile==='arduino_voltage_divider'){area.querySelectorAll('#parameters-form input,#parameters-form button').forEach(el=>el.disabled=true);area.querySelector('#parameters-form').insertAdjacentHTML('beforebegin','<p>UNO 분압의 5V·10kΩ 사양은 고정입니다. 임의 값 변경은 아직 지원하지 않습니다.</p>');[...$('#analysis-type').options].find(o=>o.value==='ac')?.remove();}
    $('#parameters-form').onsubmit=e=>{e.preventDefault();run(async()=>{const f=new FormData(e.target),values={};g.components.filter(c=>['resistor','capacitor'].includes(c.kind)).forEach(c=>values[c.id]=f.get(c.id));await accept(await post('/parameters',{values,frequency:Number(f.get('frequency')),amplitude:Number(f.get('amplitude'))}));message('새 버전의 그래프와 파형을 저장했습니다. KiCad 결과는 재생성해야 합니다.');});};
    if(sim){drawWaveform(sim);[0,1].forEach(ch=>$(`#channel-${ch}`).onchange=()=>{channels[ch]=$(`#channel-${ch}`).value;drawWaveform(sim);});$('#sample-position').oninput=()=>{sample=Number($('#sample-position').value);updateSample(sim);};$('#play-current').onclick=()=>{if(timer){clearInterval(timer);timer=null;$('#play-current').textContent='전류 재생 ▶';}else{timer=setInterval(()=>{if(!$('#sample-position')){clearInterval(timer);timer=null;return;}sample=(sample+3)%vector(sim,channels[0]).length;$('#sample-position').value=sample;updateSample(sim);},60);$('#play-current').textContent='일시 정지 Ⅱ';}};$('#current-schematic').innerHTML=$('#schematic').innerHTML;updateSample(sim);}
    document.querySelectorAll('[data-tp]').forEach(button=>button.onclick=()=>{if(!sim||!sim.nodes.includes(button.dataset.tp)){message('이 노드는 현재 해석의 파형 채널에 포함되지 않습니다.');return;}channels[1]=button.dataset.tp;$('#channel-1').value=channels[1];drawWaveform(sim);});
  }
  function drawWaveform(sim){
    const xs=sim.vectors.time||sim.vectors.frequency||sim.vectors['v-sweep'];if(!xs)return;
    const ys=channels.map(c=>vector(sim,c)),all=ys.flat().filter(Number.isFinite),lo=Math.min(0,...all),hi=Math.max(.1,...all),range=hi-lo||1;
    const W=800,H=300,left=55,right=775,top=25,bottom=255;
    const transform=x=>sim.analysis==='ac'?Math.log10(Math.max(x,1e-20)):x;
    const xmin=transform(xs[0]),xmax=transform(xs.at(-1));
    let svg=`<svg viewBox="0 0 ${W} ${H}" aria-label="ngspice 두 채널 파형"><rect width="800" height="300" fill="#142d2b"/>`;
    for(let j=0;j<=5;j++){const y=top+(bottom-top)*j/5;svg+=`<path d="M${left} ${y}H${right}" stroke="#2a4741"/><text x="8" y="${y+4}" fill="#9fb8ab" font-size="11">${(hi-range*j/5).toFixed(2)} V</text>`;}
    for(let j=0;j<=5;j++){const x=left+(right-left)*j/5;const v=xs[0]+(xs.at(-1)-xs[0])*j/5;const label=sim.analysis==='ac'?`${Math.pow(10,xmin+(xmax-xmin)*j/5).toPrecision(2)} Hz`:sim.analysis==='dc'?`${v.toFixed(2)} V`:`${(v*1000).toPrecision(3)} ms`;svg+=`<path d="M${x} ${top}V${bottom}" stroke="#2a4741"/><text x="${x}" y="282" fill="#9fb8ab" font-size="10" text-anchor="middle">${label}</text>`;}
    ys.forEach((values,ch)=>{const path=values.map((v,index)=>`${index?'L':'M'}${(left+(transform(xs[index])-xmin)/(xmax-xmin||1)*(right-left)).toFixed(2)} ${(top+(hi-v)/range*(bottom-top)).toFixed(2)}`).join(' ');svg+=`<path d="${path}" fill="none" stroke="${ch?'#79baf1':'#d5e69a'}" stroke-width="2"/>`;});
    svg+='</svg>';$('#waveform').innerHTML=svg;$('#scope-readout').textContent=`CH1 ${channels[0]} · CH2 ${channels[1]} · ${xs.length} samples · r${sim.revision}`;
  }
  function updateSample(sim){
    const key=sim.vectors['vsupply#branch']?'vsupply#branch':sim.vectors['vdrive#branch']?'vdrive#branch':'vinput#branch',v=vector(sim,key);const current=v?-v[Math.min(sample,v.length-1)]:0;if(sim.analysis==='ac'){$('#current-readout').textContent=`AC 전류 진폭 ${Math.abs(current*1000).toFixed(3)} mA · 순간 방향 표시 안 함`;document.querySelectorAll('#current-schematic .current-flow').forEach(e=>e.classList.remove('current-flow'));return;}
    $('#current-readout').textContent=`기준 방향 전류 ${(current*1000).toFixed(3)} mA`;
    document.querySelectorAll('#current-schematic [data-link="W1"], #current-schematic [data-link="W2"]').forEach(el=>{el.classList.toggle('current-flow',Math.abs(current)>1e-9);el.classList.toggle('reverse-current',current<0);el.classList.toggle('high-current',Math.abs(current)>.001);});
  }
  function renderCode(area,i){
    const g=project();area.innerHTML=`<div class="integration-grid"><section class="panel"><div class="panel-heading"><h2>Arduino 코드·GPIO 명령</h2><button id="load-code">코드 생성</button></div><div class="result-body"><div id="firmware-code">${firmwareData&&codeProject===`${g.project_id}:${g.revision}`?codeHTML(firmwareData):'<p>검토한 ESP32 LED/버튼 또는 Arduino 저항 분압·LCD 새 회로에서 코드를 생성합니다. 실제 보드용 컴파일·업로드는 별도입니다.</p>'}</div><div class="behavior-demo" ${g.profile==='esp32_led_button'?'':'hidden'}><strong>명령 동작 설명</strong><button id="button-model">버튼 누르기</button><span id="led-model" class="led-indicator"></span><span id="behavior-text">버튼 OPEN → GPIO18 HIGH → LED OFF</span><small>논리 동작 설명 모델 · MCU 실행 결과 아님</small></div></div></section><section class="panel"><div class="panel-heading"><h2>단계별 조립 가이드</h2><span class="tag">실물 대조 필요</span></div><div class="result-body"><p>${esc(state.data.tutorial.notice)}</p><div class="assembly-step"><b>준비</b> ${g.profile==='arduino_light_led'?'USB 전원을 분리하고 조도 센서의 VCC/GND/AO 라벨, 5V 호환, LED 극성을 확인하세요.':g.profile==='arduino_voltage_divider'?'USB 전원을 분리하고 UNO R3의 5V/GND/A0 라벨과 10kΩ 저항 두 개를 확인하세요.':g.profile==='arduino_lcd'?'USB/전원을 분리하고 UNO·LCD의 5V 정격, 핀 라벨, 가변저항의 실제 와이퍼 접점을 확인하세요.':g.profile==='rc_filter'?'신호 발생기와 전원을 분리하고 R1·C1 값, 커넥터 핀, 공통 GND를 확인하세요.':'USB/전원을 분리하세요. 부품 모델, LED 극성, 버튼 내부 공통 접점, 브레드보드 전원 레일의 끊김을 확인하세요.'}</div>${state.data.tutorial.steps.map((s,index)=>`<button class="assembly-step" data-guide="${esc(s.link_id)}"><b>STEP ${index+1} · ${esc(s.from)} → ${esc(s.to)}</b><span>추천 전선: ${esc(s.wire_color)} / 실제 핀: ${esc(s.physical_from||'?')} → ${esc(s.physical_to||'?')}</span><span>${esc(s.why)}</span><small>${esc(s.caution)}</small></button>`).join('')}<div class="assembly-step"><b>전원 전 확인</b> ${g.profile==='arduino_voltage_divider'?'5V-GND 단락 여부를 확인하고 USB 전원 한 곳만 사용하세요. 외부 전원은 연결하지 않습니다. 시리얼 모니터 속도는 115200입니다.':g.profile==='arduino_lcd'?'5V-GND 단락과 LCD 백라이트 극성·정격을 확인하세요. 검증 후 UNO USB 전원 한 곳을 연결하고 대비를 조절합니다.':g.profile==='arduino_light_led'?'5V-GND 단락 여부와 조도 센서의 5V·GND·AO 라벨, LED 극성을 확인하세요. 실물에서는 시리얼 값으로 출력 방향과 임계값을 조정합니다.':g.profile==='arduino_led_button'?'5V-GND 단락 여부와 LED 극성, 버튼의 접점 쌍을 확인하세요. USB 전원을 연결하고 버튼을 누르면 LED가 켜지는지 확인합니다.':g.profile==='rc_filter'?'회로와 실물을 대조하고 신호 발생기 GND를 TP_GND에 연결하세요. 입력 진폭과 부품 정격을 확인한 뒤 TP_INPUT·TP_FILTER_OUT을 측정합니다.':'실제 연결과 회로도를 대조하고 3V3-GND 단락 여부를 확인하세요. ESP32는 USB 한 곳에서 전원을 공급하고 버튼/LED 동작을 확인합니다.'}</div></div></section></div>`;
    $('#load-code').onclick=()=>run(async()=>{firmwareData=await api(endpoint('/firmware'));codeProject=`${g.project_id}:${g.revision}`;$('#firmware-code').innerHTML=codeHTML(firmwareData);});
    let pressed=false;$('#button-model').onclick=()=>{pressed=!pressed;$('#led-model').classList.toggle('on',pressed);$('#button-model').textContent=pressed?'버튼 놓기':'버튼 누르기';$('#behavior-text').textContent=pressed?'버튼 CLOSED → GPIO18 LOW → 30ms 확인 → GPIO23 HIGH → LED ON':'버튼 OPEN → GPIO18 HIGH → GPIO23 LOW → LED OFF';};
    document.querySelectorAll('[data-guide]').forEach(b=>b.onclick=()=>{stage='validation';tab='review';select('link',b.dataset.guide);message('선택한 단계의 배선을 회로에서 강조했습니다.');});
  }
  function codeHTML(code){return `<a class="button" href="${endpoint('/firmware?download=true')}">Arduino .ino ↓</a><p class="engineering-note">${esc(code.execution)} · 보드 컴파일 ${code.compiled?'완료':'미실행'}</p><div class="command-map">${code.commands.map(c=>`<p><code>${esc(c.function)}</code> → <b>${esc(c.terminal)}</b><br>${esc(c.meaning)}</p>`).join('')}</div><pre class="code-block">${esc(code.source)}</pre>`;}
  function renderCatalog(area,i){
    area.innerHTML=`<section class="panel"><div class="panel-heading"><h2>부품 목록·데이터시트·핀 매핑</h2><span class="micro">관측 정보와 제조사 정보를 대조하세요</span></div><div class="result-body"><div class="bom-table"><table><thead><tr><th>부품</th><th>라벨·값</th><th>상태</th><th>카탈로그·근거</th></tr></thead><tbody>${i.bom.map(c=>`<tr><td>${esc(c.id)}</td><td>${esc(c.label||'?')}<br><b>${esc(c.value||'')}</b></td><td>${esc(c.status)}</td><td>${c.catalog?`<a href="${esc(c.catalog.source)}" target="_blank" rel="noreferrer">제조사/라이브러리 원문 ↗</a><p>${esc(c.catalog.note)}</p>`:'부품 식별과 카탈로그 지정 필요'}<button data-catalog="${esc(c.id)}">카탈로그 확인</button></td></tr>`).join('')}</tbody></table></div><div id="catalog-form"></div></div></section>`;
    document.querySelectorAll('[data-catalog]').forEach(button=>button.onclick=()=>{const c=project().components.find(c=>c.id===button.dataset.catalog);$('#catalog-form').innerHTML=`<form id="assign-catalog"><h3>${esc(c.id)} 실물 모델 확인</h3><select name="catalog">${Object.entries(i.catalog).filter(([k,v])=>v.kind===c.kind).map(([k,v])=>`<option value="${esc(k)}">${esc(v.name)}</option>`).join('')}</select><label>실제 부품을 확인한 근거<input name="note" required minlength="5" placeholder="예: 보드 앞뒷면의 DevKitC V4 표기를 확인함"></label><button class="primary">확인·핀 매핑 저장</button><small>모양이 비슷하다는 이유만으로 모델을 확정하지 마세요. 단자 라벨도 일치해야 합니다.</small></form>`;$('#assign-catalog').onsubmit=e=>{e.preventDefault();run(async()=>{const f=new FormData(e.target);await accept(await post(`/components/${c.id}/catalog`,{catalog_id:f.get('catalog'),note:f.get('note')}));message('사용자 확인 근거와 카탈로그 핀 매핑을 기록했습니다.');});};});
  }
  function renderAssistant(){planner.render();}
  async function handleAnchor(position){const terminal_id=state.pendingAnchor;state.pendingAnchor=null;await run(async()=>{await accept(await post('/anchor',{terminal_id,position}));message('사진의 핀 위치를 저장했습니다. 두 끝점 위치를 지정한 뒤 OCR·부품 후보 분석을 실행하세요.');});}
  wireEvents();return {render,handleAnchor,analyzeCamera:camera.start,automaticPhoto:planner.refresh,pinOverlay:pinReview.overlay,handlePinPoint:pinReview.handlePoint,chooseText:pinReview.chooseText,chooseSegment:pinReview.chooseSegment};
}
