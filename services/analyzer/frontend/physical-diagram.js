// A fixed breadboard layout for the single reviewed Pi button-to-LED design.
// The circuit's endpoints must agree with the server's recipe before displaying it.
const h = (x,y) => `<circle cx="${x}" cy="${y}" r="3.1" fill="#46565a"/>`;
const colX = [450,468,486,504,522,560,578,596,614,632];
const rowY = row => 75 + (row-1)*17;
export function piBreadboardDiagram(active=[], ids={}) {
 let holes='';
 for(let row=1;row<=18;row++)for(const x of colX)holes+=h(x,rowY(row));
 let pins='';
 for(let row=0;row<20;row++)for(let side=0;side<2;side++){
  const n=row*2+side+1,x=92+side*23,y=58+row*16;
  pins+=`<circle cx="${x}" cy="${y}" r="4.2" fill="${n===1?'#c94345':n===11?'#f08b32':n===13?'#4076cc':n===6?'#3e4449':'#cbd5d4'}"/>`;
 }
 const cls = name => active.length && !active.includes(ids[name]) && !active.includes('U1') ? 'pi-dim' : '';
 return `<svg class="pi-breadboard" viewBox="0 0 850 460" role="img" aria-label="Raspberry Pi 헤더와 빵판을 연결하는 그림. 핀 11에서 저항과 LED를 거쳐 핀 6으로, 핀 13과 버튼 신호, 핀 1의 3.3V와 버튼 전원, 핀 6과 공통 접지를 연결합니다.">
 <rect x="13" y="20" width="310" height="368" rx="16" fill="#e3f2e8" stroke="#a1c5ad"/>
 <text x="26" y="43" font-weight="700" font-size="14">Raspberry Pi 40핀 헤더 · 위에서 보기</text>
 <text x="26" y="64" font-size="10">① · ② 시작</text><text x="150" y="80" font-size="10">↑ microSD 쪽</text><text x="150" y="360" font-size="10">↓ USB · 이더넷 단자 쪽</text><rect x="80" y="48" width="47" height="325" rx="5" fill="#294134"/>${pins}
 <text x="136" y="62" font-size="11">1번 3V3 · 2번</text><text x="136" y="94" font-size="11" fill="#34474b">6번 GND</text>
 <text x="136" y="142" font-size="11" fill="#a25310">11번 GPIO17</text><text x="136" y="158" font-size="11" fill="#2457a6">13번 GPIO27</text>
 <text x="26" y="380" font-size="10">핀 번호는 GPIO 번호와 다릅니다.</text>
 <rect x="390" y="20" width="290" height="405" rx="12" fill="#f9faf7" stroke="#b6c8bf"/>
 <text x="405" y="43" font-size="14" font-weight="700">브레드보드 · 1–18행 확대</text>
 <rect x="537" y="56" width="12" height="324" rx="6" fill="#e1e8e1"/>
 ${colX.map((x,i)=>`<text x="${x}" y="61" text-anchor="middle" font-size="10">${'ABCDEFGHIJ'[i]}</text>`).join('')}
 ${Array.from({length:18},(_,i)=>`<text x="423" y="${rowY(i+1)+3}" text-anchor="end" font-size="10">${i+1}</text>`).join('')}${holes}
 <path class="${cls('gpio17')}" d="M92 138 C40 150, 35 18, 345 20 C390 20, 390 75, 450 75" fill="none" stroke="#e98a2f" stroke-width="4"/>
 <path class="${cls('ground')}" d="M115 90 C265 20, 328 77, 362 111 C390 140, 410 160, 468 160" fill="none" stroke="#333d43" stroke-width="4"/>
 <path class="${cls('gpio27')}" d="M92 154 C55 175, 53 392, 348 397 C405 397, 405 296, 468 296" fill="none" stroke="#457bc5" stroke-width="4"/>
 <path class="${cls('power')}" d="M92 58 C35 28, 20 417, 350 430 C425 434, 414 364, 468 364" fill="none" stroke="#c94345" stroke-width="4"/>
 <path class="${cls('button_ground')}" d="M468 330 C382 336, 372 189, 486 160" fill="none" stroke="#77767e" stroke-width="4"/>
 <g class="${cls('resistor')}"><path d="M468 75 L468 98 M468 120 L468 143" stroke="#5e5852" stroke-width="3"/><rect x="462" y="98" width="12" height="22" rx="4" fill="#dcbf8b" stroke="#846d4d"/><path d="M462 103h12 M462 108h12 M462 113h12" stroke="#82512e" stroke-width="2"/></g>
 <g class="${cls('led')}"><path d="M450 143 L441 146 L441 157 L450 160" stroke="#666" fill="none" stroke-width="2"/><circle cx="438" cy="151.5" r="6" fill="#ed5959" stroke="#a72c2c"/><text x="641" y="142" font-size="10" fill="#9d3131">LED + A5</text><text x="641" y="159" font-size="10" fill="#9d3131">LED − A6</text></g>
 <g class="${cls('button')}"><path d="M450 296 C510 276, 675 267, 727 300" stroke="#929e98" stroke-width="3" fill="none"/><path d="M450 330 C530 318, 678 316, 727 319" stroke="#303b40" stroke-width="3" fill="none"/><path d="M450 364 C540 368, 680 360, 727 338" stroke="#c94345" stroke-width="3" fill="none"/><rect x="727" y="286" width="94" height="70" rx="8" fill="#355648"/><circle cx="774" cy="316" r="17" fill="#e8eae4" stroke="#24342b"/><text x="774" y="350" fill="#fff" text-anchor="middle" font-size="10">버튼 모듈</text></g>
 <text x="405" y="402" font-size="10">같은 번호의 A–E와 F–J는 각각 연결됩니다.</text>
 <text x="405" y="417" font-size="10">버튼: 흰색 A14 · 검정 A16 · 빨강 A18</text>
 </svg>`;
}
