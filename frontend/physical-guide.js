import {piBreadboardDiagram} from './physical-diagram.js?v=pi-hardware-3';

// The reviewed drawing is tied to a specific physical layout. Refuse to draw
// it if the server data changes rather than silently showing incorrect wiring.
export function matchesReviewedLayout(design) {
 if(design?.id!=='raspberry_pi_4b_button_led')return false;
 const pairs=[['U1.P11','A1'],['U1.P6','B6'],['U1.P13','B14'],['B16','C6'],['U1.P1','B18']];
 const expected={R1:{'1':'B1','2':'B5'},D1:{A:'A5',K:'A6'},SW1:{signal_white:'A14',gnd_black:'A16',power_red:'A18'}};
 const models={R1:'1 kΩ, 허용오차 5% 이내, 0.25 W 이상, 축형',D1:'Kingbright WP7113ID',SW1:'Adafruit STEMMA Wired Tactile Push-Button #4431'};
 const pins=[['3V3',1,null],['GND',6,null],['GPIO17',11,17],['GPIO27',13,27]];
 if(design.board?.model!=='Raspberry Pi 4 Model B (40핀 헤더)'||design.board?.gpio_voltage!=='3.3 V'||design.board?.pins?.length!==pins.length||!pins.every(([name,physical,bcm])=>design.board.pins.some(p=>p.name===name&&p.physical===physical&&p.bcm===bcm)))return false;
 if(design.breadboard?.rows<18||design.breadboard?.columns!=='ABCDEFGHIJ'||JSON.stringify(design.breadboard?.groups)!==JSON.stringify(['A-E','F-J']))return false;
 if(design.connections?.length!==pairs.length || !pairs.every(([a,b])=>design.connections.some(c=>c.from===a&&c.to===b)))return false;
 return Object.entries(expected).every(([id,holes])=>{
  const part=design.parts?.find(p=>p.id===id);return part&&part.model===models[id]&&part.holes?.length===Object.keys(holes).length&&Object.entries(holes).every(([terminal,hole])=>part.holes?.some(h=>h.terminal===terminal&&h.hole===hole));
 });
}
function safeLink(url){try{const u=new URL(url);return ['http:','https:'].includes(u.protocol)?u.href:'';}catch(_){return '';}}
export function physicalGuideHTML(data,endpoint,esc,stale=false){
 const d=data?.physical_design;
 if(!d)return `<p class="pi-placeholder">실물 배선 안내는 현재 버튼을 누르는 동안 LED가 켜지는 기능을 직접 선택한 경우에 제공됩니다. 다른 기능은 해당 실물 회로를 추가로 설계해야 합니다.</p>`;
 const parts=(d.parts||[]).map(p=>`<div class="pi-part"><b>${esc(p.name)} · ${esc(p.quantity)}개</b><span>${esc(p.model)}</span><small>${esc(p.note)}</small><small>${esc(p.photo_comparison_notice||'사진과의 호환성을 확인하세요.')}${(p.photo_candidates||[]).length?`<br>사진 후보: ${p.photo_candidates.map(c=>esc(c.name)).join(' / ')}`:''}</small></div>`).join('');
 const steps=d.steps||[];
 const code=d.code||{};
 const sources=(d.sources||[]).map(s=>{const href=safeLink(s.url);return href?`<li><a href="${esc(href)}" target="_blank" rel="noopener noreferrer">${esc(s.title)} ↗</a></li>`:'';}).join('');
 return `<section class="physical-guide"><div class="preview-heading"><h3>실제 부품으로 만들기 · ${esc(d.title)}</h3><span class="tag">새 설계 · 실물 시험 전</span></div>
 <p>${esc(d.behavior)}</p><p class="pi-notice">Pi 4B를 위에서 볼 때 microSD 쪽 끝이 1·2번, USB·이더넷 쪽 끝이 높은 번호입니다. Raspberry Pi OS 터미널의 <code>pinout</code> 명령으로도 확인하세요.</p><p class="pi-notice">사진의 원본 배선을 복원한 결과가 아닙니다. 선택한 기능을 위한 별도의 회로이며 Raspberry Pi 4B에서 실물 동작은 아직 시험하지 않았습니다.</p>
 ${(d.warnings||[]).map(w=>`<p class="pi-warning">${esc(w)}</p>`).join('')}
 <h4>준비할 부품</h4><div class="pi-parts">${parts}</div>
 <div class="pi-layout"><div class="pi-diagram-wrap" data-pi-diagram></div><div class="pi-step-panel"><span class="pi-step-counter" data-pi-counter></span><h4 data-pi-title></h4><p data-pi-description></p><div class="pi-step-controls"><button type="button" data-pi-prev>이전</button><button type="button" data-pi-next>다음 단계</button></div></div></div>
 <details class="compact-details"><summary>전체 배선표 및 자료</summary><ul class="pi-list">${(d.connections||[]).map(c=>`<li>${esc(c.description)}</li>`).join('')}</ul><p>${esc(d.breadboard?.holes_note||'')}</p><ul class="pi-list">${sources}</ul></details>
 <details class="compact-details"><summary>실제 보드 Python 코드와 실행 방법</summary><p>${esc(code.dependencies||'')}</p><p>패키지가 없으면 Raspberry Pi OS 터미널에서 설치: <code>${esc(code.install||'')}</code></p><p>다운로드한 파일을 Raspberry Pi에 복사한 뒤 해당 폴더에서 실행하세요.</p><pre class="pi-code">${esc(code.source||'')}</pre><p>실행: <code>${esc(code.run||'')}</code> · 종료: Ctrl+C</p></details>
 <div class="pi-guide-links">${!stale&&endpoint?`<a href="${esc(endpoint)}/physical-design/python?function_version=${encodeURIComponent(data.function_version||'')}" download="${esc(code.filename||'pi_button_led.py')}">실제 Raspberry Pi용 Python 코드 다운로드</a>`:''}<small>이 코드는 Raspberry Pi의 실제 GPIO 핀을 제어합니다. 안내된 부품과 배선만 사용하고 전원을 끈 상태에서 조립하세요.</small></div></section>`;
}
export function renderPhysicalGuide(host,{data,endpoint,esc,stale=false}){
 host.innerHTML=physicalGuideHTML(data,endpoint,esc,stale);
 const d=data?.physical_design;if(!d)return;
 const steps=d.steps||[], diagram=host.querySelector('[data-pi-diagram]');
 const available=matchesReviewedLayout(d);
 const ids={gpio17:'W1',ground:'W2',gpio27:'W3',button_ground:'W4',power:'W5',resistor:'R1',led:'D1',button:'SW1'};
 // The recipe IDs are checked too, so step highlights cannot be misleading.
 const wires=[['W1','U1.P11','A1'],['W2','U1.P6','B6'],['W3','U1.P13','B14'],['W4','B16','C6'],['W5','U1.P1','B18']];
 const diagramValid=available&&wires.every(([id,from,to])=>d.connections.some(c=>c.id===id&&c.from===from&&c.to===to));
 let index=0;
 const draw=()=>{
  const s=steps[index];
  host.querySelector('[data-pi-counter]').textContent=steps.length?`STEP ${index+1} / ${steps.length}`:'단계 안내 없음';
  host.querySelector('[data-pi-title]').textContent=s?.title||'조립 단계를 확인할 수 없습니다.';
  host.querySelector('[data-pi-description]').textContent=s?.description||'';
  host.querySelector('[data-pi-prev]').disabled=index===0;
  host.querySelector('[data-pi-next]').disabled=index>=steps.length-1;
  diagram.innerHTML=diagramValid?piBreadboardDiagram(s?.highlight||[],ids):'<p class="pi-warning">서버의 부품·구멍 정보와 그림이 일치하지 않아 그림을 표시하지 않습니다. 배선표를 확인하세요.</p>';
 };
 host.querySelector('[data-pi-prev]').onclick=()=>{index=Math.max(0,index-1);draw();};
 host.querySelector('[data-pi-next]').onclick=()=>{index=Math.min(steps.length-1,index+1);draw();};draw();
}
