// Assembly guide for the reviewed Raspberry Pi 2WD rover design. Text, parts,
// and the wiring list are derived from the server's single design record.
function safeLink(url){try{const u=new URL(url);return ['http:','https:'].includes(u.protocol)?u.href:'';}catch(_){return '';}}

// The drawing is intentionally specific to this HAT and connection set.
// Never show a plausible-looking but stale picture after a recipe change.
export function matchesRobotWiring(d){
 const pairs=[['U1.GPIO40','HAT1.GPIO40'],['U1.USB_C','PS1.USB_C'],
  ['MOTOR_L.black','HAT1.M1.left'],['MOTOR_L.red','HAT1.M1.right'],
  ['MOTOR_R.black','HAT1.M2.left'],['MOTOR_R.red','HAT1.M2.right'],
  ['BAT1.red','HAT1.PWR.positive'],['BAT1.black','HAT1.PWR.negative']];
 if(d?.id!=='raspberry_pi_2wd_robot'||d.connections?.length!==pairs.length||d.board?.model!=='Raspberry Pi 4 Model B')return false;
 const models={HAT1:'Adafruit DC & Stepper Motor HAT #2348',MOTOR_L:'#2939에 포함된 #2941',MOTOR_R:'#2939에 포함된 #2941',BAT1:'별도 5V 정전압 DC 전원, 3A 이상, 차단 스위치'};
 if(!Object.entries(models).every(([id,model])=>d.parts?.some(p=>p.id===id&&p.model===model)))return false;
 return pairs.every(([a,b])=>d.connections.some(c=>(c.from===a&&c.to===b)||(c.from===b&&c.to===a)));
}
export function robotWiringDiagram(d,highlight,esc){
 if(d?.id==='uno_obstacle_rover'){
  const lines=(d.connections||[]).filter(c=>!highlight.length||highlight.some(id=>c.id===id||c.from.startsWith(id+'.')||c.to.startsWith(id+'.')));
  if(!lines.length)return '<p>이 단계의 배선을 연결표에서 확인하세요.</p>';
  const rows=lines.map((c,i)=>{const y=30+i*30,color=c.color==='red'?'#c52f2f':c.color==='black'?'#263238':'#159957';return `<text x="12" y="${y+4}" font-size="12">${esc(c.from)}</text><path d="M185 ${y} H470" stroke="${color}" stroke-width="3"/><circle cx="185" cy="${y}" r="4" fill="${color}"/><circle cx="470" cy="${y}" r="4" fill="${color}"/><text x="485" y="${y+4}" font-size="12">${esc(c.to)}</text>`;}).join('');
  return `<svg viewBox="0 0 670 ${Math.max(100,lines.length*30+50)}" class="rover-wiring" role="img" aria-label="선택 단계의 로봇 부품 핀과 배선">${rows}</svg>`;
 }
 if(!matchesRobotWiring(d))return '<p class="rover-warning">서버의 연결 정보가 그림과 달라 그래픽을 숨겼습니다. 아래 배선표를 확인하세요.</p>';
 const on=(...ids)=>!highlight.length||ids.some(id=>highlight.includes(id));
 const dim=(...ids)=>on(...ids)?'':'rover-dim';
 const wireId=(a,b)=>d.connections.find(c=>(c.from===a&&c.to===b)||(c.from===b&&c.to===a))?.id;
 const cls=(a,b,...parts)=>dim(wireId(a,b),...parts);
 return `<svg viewBox="0 0 920 490" class="rover-wiring" role="img" aria-label="Raspberry Pi와 모터 HAT를 40핀으로 결합하고, M1과 M2에 각각 두 모터, PWR에 모터 전원을 연결한 배선 그림">
 <rect x="25" y="34" width="205" height="122" rx="12" fill="#dfefe4" stroke="#427f5b"/><text x="127" y="66" text-anchor="middle" font-size="16" font-weight="700">Raspberry Pi 4B</text><text x="127" y="92" text-anchor="middle" font-size="12">40핀 헤더 · USB-C 전원</text><text x="127" y="116" text-anchor="middle" font-size="11">전원: Pi용 5V 전원 장치</text>
 <path class="${cls('U1.GPIO40','HAT1.GPIO40','U1','HAT1')}" d="M128 156V211" stroke="#537762" stroke-width="12"/><text x="143" y="181" font-size="11">40핀 직접 결합</text><text x="143" y="196" font-size="10">SDA · SCL · 공통 GND</text>
 <rect x="260" y="31" width="174" height="72" rx="10" fill="#eef2fa" stroke="#99a5c3"/><text x="347" y="58" text-anchor="middle" font-size="13" font-weight="700">Pi 전용 전원</text><text x="347" y="80" text-anchor="middle" font-size="11">5.1V · USB-C</text><path class="${cls('U1.USB_C','PS1.USB_C','PS1')}" d="M260 71H230" stroke="#495b75" stroke-width="5"/>
 <rect x="25" y="211" width="430" height="238" rx="12" fill="#e6f0ff" stroke="#6284b5"/><text x="240" y="241" text-anchor="middle" font-size="16" font-weight="700">Adafruit 모터 HAT #2348</text><text x="240" y="262" text-anchor="middle" font-size="11">Pi 40핀에 장착 · M1 / M2 중간 GND는 비움</text>
 <text x="72" y="295" font-size="12" font-weight="700">M1 · 왼쪽 모터</text><text x="72" y="323" font-size="11">왼쪽 나사: 검정</text><text x="72" y="348" font-size="11">오른쪽 나사: 빨강</text>
 <text x="251" y="295" font-size="12" font-weight="700">M2 · 오른쪽 모터</text><text x="251" y="323" font-size="11">왼쪽 나사: 검정</text><text x="251" y="348" font-size="11">오른쪽 나사: 빨강</text>
 <text x="72" y="399" font-size="12" font-weight="700">PWR · 모터 전원</text><text x="72" y="421" font-size="11">+ 빨강 / − 검정</text>
 <path class="${cls('MOTOR_L.black','HAT1.M1.left','MOTOR_L')}" d="M154 319H485C507 319 512 130 545 130" fill="none" stroke="#303b42" stroke-width="4"/><path class="${cls('MOTOR_L.red','HAT1.M1.right','MOTOR_L')}" d="M165 344H495C520 344 527 152 545 152" fill="none" stroke="#d74c42" stroke-width="4"/>
 <path class="${cls('MOTOR_R.black','HAT1.M2.left','MOTOR_R')}" d="M335 319H515C536 319 530 252 545 252" fill="none" stroke="#303b42" stroke-width="4"/><path class="${cls('MOTOR_R.red','HAT1.M2.right','MOTOR_R')}" d="M350 344H528C542 344 532 274 545 274" fill="none" stroke="#d74c42" stroke-width="4"/>
 <path class="${cls('BAT1.red','HAT1.PWR.positive','BAT1')}" d="M150 417H545" stroke="#d74c42" stroke-width="4"/><path class="${cls('BAT1.black','HAT1.PWR.negative','BAT1')}" d="M150 432H545" stroke="#303b42" stroke-width="4"/>
 <rect x="545" y="101" width="275" height="78" rx="10" fill="#f5f4ef" stroke="#aab2a7"/><circle cx="580" cy="140" r="22" fill="#4c5a5d"/><text x="681" y="133" text-anchor="middle" font-size="14" font-weight="700">왼쪽 DC 기어드 모터</text><text x="681" y="153" text-anchor="middle" font-size="11">검정 ↔ M1 왼쪽 · 빨강 ↔ 오른쪽</text>
 <rect x="545" y="222" width="275" height="78" rx="10" fill="#f5f4ef" stroke="#aab2a7"/><circle cx="580" cy="261" r="22" fill="#4c5a5d"/><text x="681" y="254" text-anchor="middle" font-size="14" font-weight="700">오른쪽 DC 기어드 모터</text><text x="681" y="274" text-anchor="middle" font-size="11">검정 ↔ M2 왼쪽 · 빨강 ↔ 오른쪽</text>
 <rect x="545" y="387" width="275" height="68" rx="10" fill="#fff6de" stroke="#c9a85b"/><text x="682" y="413" text-anchor="middle" font-size="14" font-weight="700">모터용 독립 5V 전원</text><text x="682" y="433" text-anchor="middle" font-size="11">HAT PWR +/−에 연결</text>
 <text x="26" y="477" font-size="11">개략 연결도입니다. 실제 단자 위치·방향과 극성은 제조사 사진으로 확인하고 전원을 분리해 연결하세요.</text>
 </svg>`;
}

export function robotGuideHTML(data,endpoint,esc,stale=false){
 const d=data?.robot_design;if(!d)return '';
 const parts=(d.parts||[]).map(p=>`<article class="rover-part"><b>${esc(p.name)} · ${esc(p.quantity)}개</b><span>${esc(p.model||'규격 확인 필요')}</span><small>${esc(p.note||'')}</small>${p.photo_comparison_notice?`<small>${esc(p.photo_comparison_notice)}</small>`:''}${p.photo_candidates?.length?`<small>사진 후보: ${p.photo_candidates.map(c=>esc(c.name)).join(' / ')}</small>`:''}</article>`).join('');
 const sources=(d.sources||[]).map(s=>{const url=safeLink(s.url);return url?`<li><a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(s.title)} ↗</a></li>`:'';}).join('');
 const code=d.code||{};
 return `<section class="rover-guide"><div class="preview-heading"><h3>${esc(d.title)}</h3><span class="tag">새 설계 · 실물 시험 전</span></div>
 <p class="rover-goal">${esc(d.behavior)}</p>
 <p class="rover-notice">사진 속 동작을 복원한 것이 아닌 새 프로토타입입니다. 실물 조립·구동은 아직 시험하지 않았습니다.</p>
 ${d.structure?.dimensions_status?`<p class="rover-notice">3D 구조: ${esc(d.structure.dimensions_status)}</p>`:''}
 ${(d.warnings||[]).map(x=>`<p class="rover-warning">${esc(x)}</p>`).join('')}
 <h4>준비할 부품</h4><div class="rover-parts">${parts}</div>
 <div class="rover-instruction"><div class="rover-diagram" data-rover-diagram></div><div class="rover-step"><small data-rover-count></small><h4 data-rover-title></h4><p data-rover-description></p><div><button type="button" data-rover-prev>이전</button> <button type="button" data-rover-next>다음 단계</button></div></div></div>
 <details class="compact-details"><summary>전체 배선과 부품 자료</summary><ul>${(d.connections||[]).map(c=>`<li>${esc(c.description)}</li>`).join('')}</ul><ul>${sources}</ul></details>
 <details class="compact-details"><summary>기본 ${d.id==='uno_obstacle_rover'?'Arduino':'Raspberry Pi'} 코드와 실행 방법</summary><p>아래는 기본 코드입니다. 편집한 코드는 회로 편집기의 코드 복사 버튼을 사용하세요.</p><p>${esc(code.dependencies||'')}</p><p>${esc(code.install||'')}</p><pre class="rover-code">${esc(code.source||'')}</pre><p>실행: <code>${esc(code.run||'')}</code></p><p>${esc(code.commands||'')}</p></details>
 ${d.id==='uno_obstacle_rover'?`<a class="rover-download" href="data:text/plain;charset=utf-8,${encodeURIComponent(code.source||'')}" download="${esc(code.filename||'sketch.ino')}">기본 Arduino 로봇 코드 다운로드</a>`:!stale&&endpoint?`<a class="rover-download" href="${esc(endpoint)}/robot-design/python?function_version=${encodeURIComponent(data.function_version||'')}" download="${esc(code.filename||'rover.py')}">기본 Raspberry Pi 로봇 코드 다운로드</a>`:''}
 </section>`;
}

export function renderRobotGuide(host,{data,endpoint,esc,stale=false}){
 host.innerHTML=robotGuideHTML(data,endpoint,esc,stale);
 const d=data?.robot_design;if(!d)return;
 const steps=d.steps||[];let index=0;
 const draw=()=>{
  const s=steps[index]||{};
  host.querySelector('[data-rover-count]').textContent=steps.length?`STEP ${index+1} / ${steps.length}`:'단계 안내 없음';
  host.querySelector('[data-rover-title]').textContent=s.title||'';
  host.querySelector('[data-rover-description]').textContent=s.description||'';
  host.querySelector('[data-rover-prev]').disabled=index===0;
  host.querySelector('[data-rover-next]').disabled=index>=steps.length-1;
  host.querySelector('[data-rover-diagram]').innerHTML=robotWiringDiagram(d,s.highlight||[],esc);
 };
 host.querySelector('[data-rover-prev]').onclick=()=>{index=Math.max(0,index-1);draw();};
 host.querySelector('[data-rover-next]').onclick=()=>{index=Math.min(steps.length-1,index+1);draw();};draw();
}
