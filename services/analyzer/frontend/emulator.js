// Replay shows recorded simavr UART/ADC events; it does not synthesize firmware results.
export function initEmulator(host,{api,endpoint,revision,esc}){
  let result=null,timer=null,disposed=false,generation=0;
  function stop(){if(timer){clearInterval(timer);timer=null;}}
  function paint(error=''){
    if(!host.isConnected){disposed=true;stop();return;}
    const samples=result?.samples||[];
    host.innerHTML=`<section class="simulation-card embedded-emulator"><div class="panel-heading"><h3>임베디드 시스템 시뮬레이터</h3><span class="tag">${result?esc(result.status)+' · MCU 실행':'UNO R3 · simavr'}</span></div><div class="assistant-body">
      <p>현재 Arduino 코드를 컴파일하고 가상 ATmega328P에서 실행합니다. 입력 핀을 읽은 결과가 시리얼 창으로 나옵니다.</p>
      <label>시험 <select data-emulator-scenario><option value="circuit" ${result?.scenario!=='input_steps'?'selected':''}>현재 회로 · ngspice A0 전압</option><option value="input_steps" ${result?.scenario==='input_steps'?'selected':''}>ADC 입력 시험 · 1.25→2.5→3.75V</option></select></label>
      <button class="primary" type="button" data-emulator-run>가상 보드에서 코드 실행</button><p data-emulator-error role="status">${esc(error)}</p>
      <div class="emulator-flow"><span>${result?.scenario==='input_steps'?'시험 전압<br><b>가상 입력</b>':'회로 전압<br><b>ngspice</b>'}</span><span>→</span><span>A0 입력<br><b>ADC0</b></span><span>→</span><span>Arduino 코드<br><b>16 MHz MCU</b></span><span>→</span><span>출력<br><b>UART 시리얼</b></span></div>
      ${result?`<div class="emulator-gates"><span>컴파일 ${result.compiled?'완료':'실패'}</span><span>MCU 실행 ${result.firmware_executed?'완료':'실패'}</span><span>검사 ${result.checks.filter(c=>c.passed).length}/${result.checks.length}</span><span>실물 미검증</span></div>
      <p>${esc(result.input_source)}</p><div class="emulator-panels"><div class="virtual-uno"><b>Arduino UNO R3</b><span>ATmega328P · 16 MHz</span><div class="virtual-pin">A0 <strong data-pin-value>—</strong></div><div class="virtual-pin">ADC <strong data-adc-value>—</strong></div><small>5V · GND 공통 / 가상 보드</small></div><div class="serial-monitor"><b>시리얼 모니터 · UART 실행 로그</b><pre data-serial-log></pre></div></div>
      <div class="emulator-playback"><button type="button" data-emulator-play>실행 기록 재생 ▶</button><label>가상 시간 <input type="range" data-emulator-position min="0" max="${Math.max(0,samples.length-1)}" value="${Math.max(0,samples.length-1)}"></label><strong data-emulator-time></strong></div>
      <details class="compact-details"><summary>실행 검사·모델 범위</summary><ul>${result.checks.map(c=>`<li>${c.passed?'PASS':'FAIL'} · ${esc(c.name)}</li>`).join('')}</ul><p>${esc(result.coupling)}</p><ul>${result.limitations.map(s=>`<li>${esc(s)}</li>`).join('')}</ul><p>펌웨어 해시: <code>${esc(result.firmware_sha256)}</code></p><p>가상 실행 ${result.execution?.ms||0} ms · ${result.execution?.cycles||0} CPU cycles</p></details>`:'<p>버튼을 누르면 컴파일 → 회로 계산 → 가상 MCU 실행 → 시리얼 결과 검사를 진행합니다.</p>'}
      <small>실제 보드에 업로드하거나 전원을 연결하지 않습니다. <a href="https://github.com/buserror/simavr" target="_blank" rel="noopener noreferrer">simavr 오픈소스 ↗</a></small></div></section>`;
    const selectSample=index=>{
      const sample=samples[index];if(!sample)return;
      host.querySelector('[data-pin-value]').textContent=(sample.input_mv/1000).toFixed(3)+' V';
      host.querySelector('[data-adc-value]').textContent=sample.raw;
      host.querySelector('[data-serial-log]').textContent='raw,ratio,estimated_voltage_V\n'+samples.slice(0,index+1).map(s=>s.text).join('\n');
      host.querySelector('[data-emulator-time]').textContent=sample.time_ms.toFixed(1)+' ms';
      host.querySelector('[data-emulator-position]').value=index;
    };
    if(samples.length){
      selectSample(samples.length-1);
      host.querySelector('[data-emulator-position]').oninput=e=>{stop();host.querySelector('[data-emulator-play]').textContent='실행 기록 재생 ▶';selectSample(Number(e.target.value));};
      host.querySelector('[data-emulator-play]').onclick=()=>{
        const button=host.querySelector('[data-emulator-play]');if(timer){stop();button.textContent='실행 기록 재생 ▶';return;}
        let index=0;selectSample(index);button.textContent='재생 중지';
        timer=setInterval(()=>{if(!host.isConnected){stop();return;}index++;if(index>=samples.length){stop();button.textContent='다시 재생 ▶';return;}selectSample(index);},200);
      };
    }
    host.querySelector('[data-emulator-run]').onclick=async()=>{
      stop();const scenario=host.querySelector('[data-emulator-scenario]').value;generation++;result=null;paint();host.querySelector('[data-emulator-scenario]').value=scenario;
      host.querySelector('[data-emulator-run]').disabled=true;host.querySelector('[data-emulator-run]').textContent='컴파일·가상 보드 실행 중…';
      try{result=await api(endpoint,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({expected_revision:revision,scenario})});paint();}
      catch(e){paint('실행 실패: '+e.message);}
    };
  }
  paint();api(endpoint).then(r=>{if(generation===0&&!disposed&&host.isConnected&&r.result){result=r.result;paint();}}).catch(e=>{if(generation===0&&host.isConnected)paint('이전 실행을 불러오지 못했습니다: '+e.message);});
}
