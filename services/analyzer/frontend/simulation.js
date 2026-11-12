// All curves come from server-side libngspice vectors; no invented fallback data.
export function renderSimulation(host,{result=null,onRun,esc,proposal=false}){
  const v=result?.validation,m=v?.metrics,mode=result?.analysis||'transient';
  function waveform(){
    const raw=result?.vectors;if(!raw)return '';
    const xs=raw[mode==='dc'?'v-sweep':'time'],input=raw.vcc_5v,output=raw.tp_divider;
    if(!Array.isArray(xs)||!Array.isArray(input)||!Array.isArray(output))return '<p>이 회로의 파형은 고급 파형 화면에서 확인하세요.</p>';
    const xmax=Math.max(...xs),ymax=Math.max(5,...input,...output),W=760,H=250;
    const points=ys=>ys.map((y,i)=>`${60+xs[i]/(xmax||1)*660},${210-y/ymax*170}`).join(' ');
    return `<svg viewBox="0 0 ${W} ${H}" class="simulation-wave" role="img" aria-label="ngspice 실제 계산: 공급 전압과 A0 전압"><rect width="760" height="250" rx="10" fill="#142c2c"/><g fill="#dbece3" font-size="13"><text x="20" y="38">${ymax.toFixed(1)} V</text><text x="28" y="214">0</text><text x="62" y="235">0</text><text x="555" y="235">${mode==='dc'?xmax.toFixed(1)+' V 공급 전압':(xmax*1000).toFixed(1)+' ms 시간'}</text><text x="90" y="25" fill="#75d5b5">CH1 · VCC_5V</text><text x="320" y="25" fill="#f4c76e">CH2 · TP_DIVIDER (A0)</text></g><path d="M60 40 V210 H720" fill="none" stroke="#7c9a90"/><polyline points="${points(input)}" fill="none" stroke="#75d5b5" stroke-width="2.5"/><polyline points="${points(output)}" fill="none" stroke="#f4c76e" stroke-width="2.5"/></svg>`;
  }
  host.innerHTML=`<section class="simulation-card"><div class="panel-heading"><h3>회로 동작 확인 · ngspice</h3><span class="tag">${v?esc(v.status)+' · 모델 계산':result?'계산 완료':'계산 전'}</span></div><div class="assistant-body">
    <p>${proposal?'새 설계 사양을 시험합니다. 사진 속 실물의 동작 검증과는 별개입니다.':'현재 회로 그래프의 전압·전류를 계산합니다.'}</p>
    <label>시험 방식 <select data-sim-mode><option value="transient" ${mode==='transient'?'selected':''}>시간 응답 · 전원을 올릴 때</option><option value="dc" ${mode==='dc'?'selected':''}>DC 스윕 · 공급 전압 0→5V</option></select></label>
    <button type="button" class="primary" data-sim-run>시뮬레이션 실행</button><p data-sim-error role="status"></p>
    ${m?`<div class="simulation-metrics"><div><small>A0 전압</small><strong>${m.a0_voltage_v.toFixed(3)} V</strong></div><div><small>저항 전류</small><strong>${m.resistor_current_ma.toFixed(3)} mA</strong></div><div><small>저항 한 개의 소비 전력</small><strong>${m.r1_power_mw.toFixed(3)} mW</strong></div></div>`:''}
    ${waveform()}
    ${result?`<p>${esc(result.note)}</p><p><b>이 패널은 전압·전류 계산입니다. MCU 검증은 임베디드 실행 결과를 확인하세요. 실물은 미검증입니다.</b></p>${v?`<p>${esc(v.meaning)}</p><details class="compact-details"><summary>계산 검증 ${v.checks.filter(c=>c.passed).length}/${v.checks.length} · 가정·한계</summary><ul>${v.checks.map(c=>`<li>${c.passed?'PASS':'FAIL'} · ${esc(c.name)}</li>`).join('')}</ul><ul>${v.assumptions.map(a=>`<li>${esc(a)}</li>`).join('')}</ul><p>이상적인 ADC 예상값 ${m.ideal_adc_count_estimate}는 전압 비율 계산이며 MCU 실행 결과가 아닙니다.</p></details>`:''}<details class="compact-details"><summary>실제 SPICE 입력·전류 방향</summary><pre>${esc(result.deck)}</pre><p>${esc(result.current_reference)}</p></details>`:''}
    <small><a href="https://ngspice.sourceforge.io/shared.html" target="_blank" rel="noopener noreferrer">오픈소스 ngspice 계산 엔진 ↗</a></small></div></section>`;
  host.querySelector('[data-sim-run]').onclick=async()=>{
    const button=host.querySelector('[data-sim-run]'),error=host.querySelector('[data-sim-error]');
    button.disabled=true;button.textContent='ngspice 계산 중…';error.textContent='';
    try{const next=await onRun(host.querySelector('[data-sim-mode]').value);if(host.isConnected)renderSimulation(host,{result:next,onRun,esc,proposal});}
    catch(e){if(host.isConnected){error.textContent='계산 실패: '+e.message;button.disabled=false;button.textContent='시뮬레이션 다시 실행';}}
  };
}
