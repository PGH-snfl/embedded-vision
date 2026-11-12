// Keyboard and held buttons control only the virtual differential-drive model.
export const MANUAL_COMMANDS=Object.freeze({
 forward:[.5,.5],backward:[-.5,-.5],left:[0,.5],right:[.5,0],
 'forward-left':[.2,.5],'forward-right':[.5,.2],
 'backward-left':[-.5,-.2],'backward-right':[-.2,-.5]
});
const keyMap={KeyW:'forward',ArrowUp:'forward',KeyS:'backward',ArrowDown:'backward',KeyA:'left',ArrowLeft:'left',KeyD:'right',ArrowRight:'right'};
const labels={forward:'전진',backward:'후진',left:'좌회전',right:'우회전','forward-left':'전진하며 좌회전','forward-right':'전진하며 우회전','backward-left':'후진하며 좌회전','backward-right':'후진하며 우회전'};
export function manualLabel(name){return labels[name]||'정지';}
export function manualDirection(values){
 const s=new Set(values),vertical=(s.has('forward')?1:0)-(s.has('backward')?1:0),horizontal=(s.has('right')?1:0)-(s.has('left')?1:0);
 if(vertical&&horizontal)return (vertical>0?'forward':'backward')+(horizontal>0?'-right':'-left');
 return vertical?(vertical>0?'forward':'backward'):horizontal?(horizontal>0?'right':'left'):null;
}
export function createManualController({host,doc= document,win=window,validateMotion,stop,run,onStatus=()=>{},enabled=()=>true,recheckMs=1000,timeoutMs=3000}){
 const held=new Map(),buttons=[...host.querySelectorAll('[data-rover-hold]')];let generation=0,timer=null,deadline=null,disposed=false;
 const clear=()=>{clearTimeout(timer);clearTimeout(deadline);timer=deadline=null;};
 const updateButtons=()=>{for(const button of buttons)button.dataset.active=[...held.values()].includes(button.dataset.roverHold)?'true':'false';};
 const current=()=>manualDirection(held.values());
 const blocked=target=>!!target?.closest?.('input,textarea,select,[contenteditable]:not([contenteditable="false"]),[role="textbox"],dialog,[role="dialog"]');
 function releaseAll(message=''){
  generation++;clear();held.clear();updateButtons();stop();onStatus(message);
 }
 function fail(ticket,message){if(disposed||ticket!==generation)return;releaseAll(message);}
 function verify(name,ticket,initial){
  if(disposed||ticket!==generation||current()!==name)return;
  deadline=setTimeout(()=>fail(ticket,'회로 연결 확인 시간이 초과되어 정지했습니다.'),timeoutMs);
  Promise.resolve().then(()=>typeof validateMotion==='function'?validateMotion(name):true).then(result=>{
   if(disposed||ticket!==generation||current()!==name)return;
   clearTimeout(deadline);deadline=null;
   if(result!==true&&result?.allowed!==true){fail(ticket,result?.message||'회로 연결을 확인한 뒤 다시 조작하세요.');return;}
   if(initial){run(name);onStatus('');}
   timer=setTimeout(()=>verify(name,ticket,false),recheckMs);
  }).catch(error=>fail(ticket,'회로 검증에 실패해 정지했습니다: '+(error?.message||'다시 확인하세요.')));
 }
 function changed(){
  generation++;const ticket=generation;clear();updateButtons();stop();
  const name=current();if(!name){onStatus('');return;}
  onStatus('회로 연결을 확인하고 있습니다…');verify(name,ticket,true);
 }
 function keydown(e){
  const direction=keyMap[e.code]||((e.code==='Space'||e.code==='Enter')?e.target?.dataset?.roverHold:null);if(!direction||e.repeat||e.altKey||e.ctrlKey||e.metaKey||blocked(e.target)||doc.hidden||host.closest('[hidden]')||!enabled())return;
  if(e.target!==doc.body&&e.target!==doc.documentElement&&!host.contains(e.target))return;
  if(held.has('key:'+e.code))return;e.preventDefault();held.set('key:'+e.code,direction);changed();
 }
 function keyup(e){const id='key:'+e.code;if(!held.has(id))return;e.preventDefault();held.delete(id);changed();}
 // Focusing an input cancels held manual keys, but must not stop an
 // independent automatic drive when no manual key or button is held.
 function onFocus(e){if(held.size&&(blocked(e.target)||(!host.contains(e.target)&&e.target!==doc.body)))releaseAll();}
 function onVisibility(){if(doc.hidden)releaseAll();}
 function onBlur(){releaseAll();}
 const pointerDown=e=>{if(e.button!==0||held.has('pointer:'+e.pointerId)||!enabled())return;e.preventDefault();try{e.currentTarget.setPointerCapture(e.pointerId);}catch{}held.set('pointer:'+e.pointerId,e.currentTarget.dataset.roverHold);changed();};
 const pointerUp=e=>{const id='pointer:'+e.pointerId;if(!held.has(id))return;held.delete(id);changed();};
 for(const button of buttons){button.addEventListener('pointerdown',pointerDown);button.addEventListener('pointerup',pointerUp);button.addEventListener('pointercancel',pointerUp);button.addEventListener('lostpointercapture',pointerUp);}
 doc.addEventListener('keydown',keydown);doc.addEventListener('keyup',keyup);doc.addEventListener('visibilitychange',onVisibility);doc.addEventListener('focusin',onFocus);win.addEventListener('blur',onBlur);
 function dispose(){if(disposed)return;releaseAll();disposed=true;doc.removeEventListener('keydown',keydown);doc.removeEventListener('keyup',keyup);doc.removeEventListener('visibilitychange',onVisibility);doc.removeEventListener('focusin',onFocus);win.removeEventListener('blur',onBlur);for(const button of buttons){button.removeEventListener('pointerdown',pointerDown);button.removeEventListener('pointerup',pointerUp);button.removeEventListener('pointercancel',pointerUp);button.removeEventListener('lostpointercapture',pointerUp);}}
 return {releaseAll,dispose};
}
