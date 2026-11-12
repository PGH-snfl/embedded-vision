// Editable connection diagram for the reviewed Raspberry Pi rover. This is a
// wiring representation of the 40-pin HAT, not an internal HAT schematic.
const PARTS = Object.freeze({
 U1:{kind:'pi4',label:'Raspberry Pi 4B',width:190,height:100,pins:[['GPIO40','40핀 헤더',190,30],['USB_C','USB-C',0,70]]},
 HAT1:{kind:'motor_hat',label:'모터 HAT #2348',width:210,height:210,pins:[['GPIO40','40핀 헤더',0,30],['M1.left','M1 검정',210,30],['M1.right','M1 빨강',210,55],['M2.left','M2 검정',210,95],['M2.right','M2 빨강',210,120],['PWR.positive','전원 +',210,165],['PWR.negative','전원 −',210,190]]},
 MOTOR_L:{kind:'motor_left',label:'왼쪽 DC 모터',width:160,height:86,pins:[['black','검정',0,30],['red','빨강',0,58]]},
 MOTOR_R:{kind:'motor_right',label:'오른쪽 DC 모터',width:160,height:86,pins:[['black','검정',0,30],['red','빨강',0,58]]},
 BAT1:{kind:'motor_power',label:'모터 전원 5V',width:160,height:86,pins:[['red','+',0,30],['black','−',0,58]]},
 PS1:{kind:'pi_power',label:'Pi 전원 5.1V',width:160,height:86,pins:[['USB_C','USB-C',160,30]]}
});
const FALLBACK={U1:[120,150],HAT1:[430,150],MOTOR_L:[720,80],MOTOR_R:[720,260],BAT1:[720,480],PS1:[120,420]};
const svgNS='http://www.w3.org/2000/svg';
const copy=x=>JSON.parse(JSON.stringify(x));
const portKey=(id,pin)=>`${id}.${pin}`;
const sameEdge=(a,b)=>a.from===b.from&&a.to===b.to||a.from===b.to&&a.to===b.from;
const edgeId=()=>`W_${Math.random().toString(36).slice(2,11)}`;
export function robotCircuitPins(){return Object.fromEntries(Object.entries(PARTS).map(([id,p])=>[id,p.pins.map(([name])=>portKey(id,name))]));}
export function robotCircuitPositions(graph){
 const positions={};for(const c of graph.components){const spec=PARTS[c.id];if(!spec||spec.kind!==c.kind)continue;for(const [name,,dx,dy] of spec.pins)positions[portKey(c.id,name)]={x:c.x+dx,y:c.y+dy};}return positions;
}
export function robotCircuitConnect(graph,from,to,id){
 const pins=robotCircuitPositions(graph);if(!pins[from]||!pins[to]||from===to)throw Error('서로 다른 유효한 단자를 선택하세요.');
 if(graph.connections.some(w=>sameEdge(w,{from,to})))throw Error('이미 연결된 단자입니다.');
 if(graph.connections.length>=24)throw Error('배선은 최대 24개입니다.');
 if(!id){do{id=edgeId();}while(graph.connections.some(w=>w.id===id));}
 if(graph.connections.some(w=>w.id===id))throw Error('배선 ID가 중복되었습니다.');
 return {...graph,components:copy(graph.components),connections:[...copy(graph.connections),{id,from,to}]};
}
export function robotCircuitReconnect(graph,id,end,to){
 const pins=robotCircuitPositions(graph);if(!pins[to]||!['from','to'].includes(end))throw Error('유효한 단자에 놓아 주세요.');
 const connections=copy(graph.connections),edge=connections.find(w=>w.id===id);if(!edge)throw Error('배선을 찾을 수 없습니다.');
 edge[end]=to;if(edge.from===edge.to||connections.some(w=>w.id!==id&&sameEdge(w,edge)))throw Error('같은 단자이거나 이미 연결된 배선입니다.');
 return {...graph,components:copy(graph.components),connections};
}
export function robotCircuitRemovePart(graph,id){return {...graph,components:graph.components.filter(c=>c.id!==id).map(copy),connections:graph.connections.filter(w=>!w.from.startsWith(id+'.')&&!w.to.startsWith(id+'.')).map(copy)};}
export function robotCircuitAddPart(graph,id){
 const spec=PARTS[id];if(!spec||graph.components.some(c=>c.id===id))throw Error('이 부품은 이미 있거나 지원되지 않습니다.');
 const [x,y]=FALLBACK[id];return {...graph,components:[...copy(graph.components),{id,kind:spec.kind,label:spec.label,x,y}],connections:copy(graph.connections)};
}

function wireColor(edge){const t=`${edge.from} ${edge.to}`;if(/PWR\.positive|BAT1\.red|M\d\.right|\.red/.test(t))return '#d45447';if(/PWR\.negative|BAT1\.black|M\d\.left|\.black/.test(t))return '#334b56';return '#548c7c';}
function pathBetween(a,b){const delta=Math.max(45,Math.abs(b.x-a.x)*.42);return `M${a.x} ${a.y} C${a.x+delta} ${a.y} ${b.x-delta} ${b.y} ${b.x} ${b.y}`;}
function makeSvg(name,attrs){const el=document.createElementNS(svgNS,name);for(const [k,v] of Object.entries(attrs))el.setAttribute(k,String(v));return el;}

/**
 * `onChange(graph, setStatus)` is called once per completed edit.
 * `onSimulate(graph, setStatus)` may validate before opening the 3D view.
 * `getGraph()` returns a copy of the current editor state.
 */
export function renderRobotCircuit(host,{initialGraph,onChange,onSimulate,esc=x=>String(x)}={}){
 if(!host||!initialGraph)return null;
 let graph=copy(initialGraph),selectedPart=null,selectedWire=null,pendingPort=null,drag=null;
 host.innerHTML=`<section class="robot-circuit-editor"><div class="preview-heading"><h3>① 로봇 회로 편집</h3><span class="tag">새 설계 · 실물 미검증</span></div><p>부품을 끌어 이동하고 단자 두 개를 차례로 클릭해 배선을 연결하세요. 배선의 끝 원을 바로 끌어 다른 단자로 옮길 수도 있습니다.</p><p class="robot-circuit-warning">그림은 Pi와 HAT를 하나의 40핀 결합으로 표현한 연결도입니다. HAT 내부 회로는 표시하지 않습니다. 배선을 변경하면 아래의 고정 조립 가이드·실물 코드와 달라질 수 있으며, 실제 전기·펌웨어 동작은 검증되지 않습니다.</p><div class="robot-circuit-actions"><label>부품 추가 <select data-robot-add-part><option value="">부품 선택</option></select></label><button type="button" data-robot-add>부품 추가</button><button type="button" data-robot-delete disabled>선택 삭제</button><button type="button" data-robot-cancel hidden>배선 선택 취소</button></div><div class="robot-circuit-viewport"><svg viewBox="0 0 1000 680" role="group" aria-label="편집 가능한 라즈베리파이와 모터 HAT 배선도" data-robot-svg></svg></div><p class="robot-circuit-help" data-robot-hint>연결할 단자를 선택하세요.</p><p role="status" data-robot-status></p><button type="button" class="primary" data-robot-simulate>회로 확인 후 ② 3D 운동 시뮬레이션 →</button></section>`;
 const svg=host.querySelector('[data-robot-svg]'),status=host.querySelector('[data-robot-status]'),hint=host.querySelector('[data-robot-hint]'),select=host.querySelector('[data-robot-add-part]'),remove=host.querySelector('[data-robot-delete]'),cancel=host.querySelector('[data-robot-cancel]');
 const setStatus=t=>{if(status.isConnected)status.textContent=String(t||'');};
 const emit=()=>{if(onChange)onChange(copy(graph),setStatus);};
 function say(t){hint.textContent=t;}
 function toPoint(e){const p=svg.createSVGPoint();p.x=e.clientX;p.y=e.clientY;const m=svg.getScreenCTM();return m?p.matrixTransform(m.inverse()):{x:0,y:0};}
 function refreshLines(){const ports=robotCircuitPositions(graph);svg.querySelectorAll('[data-wire-path]').forEach(path=>{const edge=graph.connections.find(x=>x.id===path.dataset.wirePath);if(edge&&ports[edge.from]&&ports[edge.to])path.setAttribute('d',pathBetween(ports[edge.from],ports[edge.to]));});svg.querySelectorAll('[data-wire-handle]').forEach(handle=>{const edge=graph.connections.find(x=>x.id===handle.dataset.wireHandle);const p=edge&&ports[edge[handle.dataset.end]];if(p){handle.setAttribute('cx',p.x);handle.setAttribute('cy',p.y);}});}
 function changePort(port){
  if(!pendingPort){pendingPort=port;cancel.hidden=false;say(`${port} 선택됨 · 연결할 다른 단자를 클릭하세요.`);draw();return;}
  try{graph=robotCircuitConnect(graph,pendingPort,port);pendingPort=null;cancel.hidden=true;selectedWire=graph.connections[graph.connections.length-1].id;selectedPart=null;say('새 배선을 추가했습니다.');emit();draw();}catch(e){say(e.message);}
 }
 function draw(){
  svg.replaceChildren();const ports=robotCircuitPositions(graph);
  const available=Object.keys(PARTS).filter(id=>!graph.components.some(c=>c.id===id));select.innerHTML='<option value="">부품 선택</option>'+available.map(id=>`<option value="${esc(id)}">${esc(PARTS[id].label)}</option>`).join('');
  remove.disabled=!selectedPart&&!selectedWire;cancel.hidden=!pendingPort;
  for(const edge of graph.connections){const a=ports[edge.from],b=ports[edge.to];if(!a||!b)continue;
   const hit=makeSvg('path',{d:pathBetween(a,b),fill:'none',stroke:'transparent','stroke-width':18,'data-wire-hit':edge.id,tabindex:0,role:'button','aria-label':`배선 ${edge.from} → ${edge.to}`});
   const line=makeSvg('path',{d:pathBetween(a,b),fill:'none',stroke:wireColor(edge),'stroke-width':edge.id===selectedWire?5:3,'data-wire-path':edge.id,'pointer-events':'none'});
   const selectWire=()=>{selectedWire=edge.id;selectedPart=null;pendingPort=null;say('배선 양 끝의 원을 끌어 단자를 옮기거나 선택 삭제를 누르세요.');draw();};
   hit.addEventListener('click',e=>{e.stopPropagation();selectWire();});hit.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();selectWire();}});svg.append(hit,line);
  }
  for(const c of graph.components){const p=PARTS[c.id];if(!p||p.kind!==c.kind)continue;
   const group=makeSvg('g',{transform:`translate(${c.x},${c.y})`,'data-part':c.id,tabindex:0,role:'button','aria-label':`${c.label} 이동 또는 선택`});
   group.append(makeSvg('rect',{width:p.width,height:p.height,rx:11,fill:c.id==='HAT1'?'#e5efff':'#eef6ee',stroke:c.id===selectedPart?'#387a50':'#8ca39c','stroke-width':c.id===selectedPart?3:1.5}));
   const title=makeSvg('text',{x:p.width/2,y:24,'text-anchor':'middle','font-size':13,'font-weight':700});title.textContent=c.label;group.append(title);
   if(c.kind==='motor_left'||c.kind==='motor_right'){
    group.append(makeSvg('circle',{cx:105,cy:57,r:16,fill:'#fff',stroke:'#496e5c','stroke-width':1.5}));
    const symbol=makeSvg('text',{x:105,y:62,'text-anchor':'middle','font-size':14,'font-weight':700});symbol.textContent='M';group.append(symbol);
   }
   for(const [name,label,dx,dy] of p.pins){const side=dx===0?'start':'end';const t=makeSvg('text',{x:dx===0?12:p.width-12,y:dy+4,'text-anchor':side,'font-size':11});t.textContent=label;group.append(t);
    const pin=makeSvg('circle',{cx:dx,cy:dy,r:7,fill:pendingPort===portKey(c.id,name)?'#f3a23b':'#fff',stroke:'#476e5a','stroke-width':2,'data-port':portKey(c.id,name),tabindex:0,role:'button','aria-label':`${c.label} ${label} 단자`});
    pin.addEventListener('pointerdown',e=>e.stopPropagation());pin.addEventListener('click',e=>{e.stopPropagation();changePort(portKey(c.id,name));});pin.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();changePort(portKey(c.id,name));}});group.append(pin);
   }
   group.addEventListener('pointerdown',e=>{if(e.button!==0)return;e.preventDefault();e.stopPropagation();const p0=toPoint(e);selectedPart=c.id;selectedWire=null;pendingPort=null;cancel.hidden=true;drag={kind:'part',id:c.id,pointerId:e.pointerId,offsetX:p0.x-c.x,offsetY:p0.y-c.y,changed:false};svg.setPointerCapture(e.pointerId);draw();});group.addEventListener('keydown',e=>{if(e.target!==group)return;if(e.key==='Enter'||e.key===' '){e.preventDefault();selectedPart=c.id;selectedWire=null;pendingPort=null;say('부품을 선택했습니다. 선택 삭제를 누르면 연결된 선도 삭제됩니다.');draw();}});svg.append(group);
  }
  // All ends are directly draggable. Clicking (without dragging) still starts
  // or completes a new connection at the underlying terminal. If several
  // wires share a terminal, selecting a wire brings its handles to the front.
  const edges=[...graph.connections].sort((a,b)=>(a.id===selectedWire?1:0)-(b.id===selectedWire?1:0));
  for(const edge of edges)for(const end of ['from','to']){const p=ports[edge[end]];if(!p)continue;const h=makeSvg('circle',{cx:p.x,cy:p.y,r:8,fill:pendingPort===edge[end]?'#f3a23b':'#f5f8ee',stroke:edge.id===selectedWire?'#cf8b2f':'#658a75','stroke-width':edge.id===selectedWire?3:2,'data-wire-handle':edge.id,'data-end':end,tabindex:0,role:'button','aria-label':`배선 끝 ${edge[end]}: 끌어 이동 또는 클릭해 연결`});
   h.addEventListener('pointerdown',e=>{if(e.button!==0)return;e.preventDefault();e.stopPropagation();const pt=toPoint(e);drag={kind:'wire',id:edge.id,end,pointerId:e.pointerId,startX:pt.x,startY:pt.y,moved:false};svg.setPointerCapture(e.pointerId);});
   h.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();changePort(edge[end]);}});svg.append(h);}
 }
 svg.addEventListener('pointermove',e=>{
  if(!drag||drag.pointerId!==e.pointerId)return;const p=toPoint(e);
  if(drag.kind==='part'){const c=graph.components.find(x=>x.id===drag.id);if(!c)return;const spec=PARTS[c.id];const nx=Math.round(Math.max(20,Math.min(980-spec.width,p.x-drag.offsetX))),ny=Math.round(Math.max(20,Math.min(680-spec.height,p.y-drag.offsetY)));if(nx!==c.x||ny!==c.y){c.x=nx;c.y=ny;drag.changed=true;const group=svg.querySelector(`[data-part="${c.id}"]`);if(group)group.setAttribute('transform',`translate(${c.x},${c.y})`);refreshLines();}}
  else{if(Math.hypot(p.x-drag.startX,p.y-drag.startY)>4)drag.moved=true;const handle=svg.querySelector(`[data-wire-handle="${drag.id}"][data-end="${drag.end}"]`);if(handle&&drag.moved){handle.setAttribute('cx',p.x);handle.setAttribute('cy',p.y);}}
 });
 svg.addEventListener('pointerup',e=>{
  if(!drag||drag.pointerId!==e.pointerId)return;const current=drag;drag=null;if(svg.hasPointerCapture(e.pointerId))svg.releasePointerCapture(e.pointerId);
  if(current.kind==='part'){if(current.changed){say('부품 위치를 변경했습니다.');emit();}draw();return;}
  const edge=graph.connections.find(w=>w.id===current.id);
  if(!current.moved){if(edge)changePort(edge[current.end]);return;}
  selectedWire=current.id;selectedPart=null;pendingPort=null;
  const pt=toPoint(e),ports=robotCircuitPositions(graph),nearest=Object.entries(ports).map(([key,p])=>({key,d:Math.hypot(p.x-pt.x,p.y-pt.y)})).sort((a,b)=>a.d-b.d)[0];
  if(!nearest||nearest.d>24){say('다른 단자 근처에 배선 끝을 놓아 주세요.');draw();return;}
  try{graph=robotCircuitReconnect(graph,current.id,current.end,nearest.key);say('배선 끝을 옮겼습니다.');emit();}catch(err){say(err.message);}draw();
 });
 svg.addEventListener('pointercancel',e=>{if(drag?.pointerId===e.pointerId){drag=null;draw();}});
 host.querySelector('[data-robot-add]').onclick=()=>{if(!select.value){say('추가할 부품을 먼저 선택하세요.');return;}try{graph=robotCircuitAddPart(graph,select.value);selectedPart=select.value;selectedWire=null;say('부품을 추가했습니다. 단자를 연결하세요.');emit();draw();}catch(e){say(e.message);}};
 remove.onclick=()=>{if(selectedWire){graph={...graph,connections:graph.connections.filter(x=>x.id!==selectedWire)};selectedWire=null;}else if(selectedPart){graph=robotCircuitRemovePart(graph,selectedPart);selectedPart=null;}pendingPort=null;say('선택한 항목을 삭제했습니다.');emit();draw();};
 cancel.onclick=()=>{pendingPort=null;say('배선 선택을 취소했습니다.');draw();};
 const simulate=host.querySelector('[data-robot-simulate]');
 simulate.onclick=async()=>{if(!onSimulate||simulate.disabled)return;simulate.disabled=true;try{await onSimulate(copy(graph),setStatus);}catch(e){setStatus(e?.message||'회로를 확인하지 못했습니다.');}finally{if(simulate.isConnected)simulate.disabled=false;}};
 draw();return {getGraph:()=>copy(graph),setStatus};
}
