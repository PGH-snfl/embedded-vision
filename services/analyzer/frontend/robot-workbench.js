import {workspaceId} from './saas.js';

// Embed the actual Velxio editor. Only its authenticated frame may submit a
// snapshot; the server still checks and stores every electrical connection.
export function mountRobotWorkbench(host,{project,onMotion,onTranslate,motionTab=false}){
 const bytes=new Uint8Array(24);crypto.getRandomValues(bytes);
 const channel=Array.from(bytes,b=>b.toString(16).padStart(2,'0')).join('');
 const data={...project,embeddedVision:{...project.embeddedVision,analysis_origin:location.origin}};
 const encoded=btoa(Array.from(new TextEncoder().encode(JSON.stringify(data)),b=>String.fromCharCode(b)).join(''));
 const editor=workspaceId?location.origin+'/w/'+workspaceId+'/editor':`http://${location.hostname==='localhost'?'localhost':'127.0.0.1'}:8768/editor`;
 const targetOrigin=new URL(editor).origin;
 const src=editor+'?embedded=1&motion=1&channel='+channel+(motionTab?'&motion_tab=1':'')+'#project='+encodeURIComponent(encoded);
 const obstacle=project.embeddedVision?.recipe==='uno_obstacle_rover';
 host.innerHTML=`<section class="robot-workbench"><div class="preview-heading"><h3>① 기존 Arduino 시스템 편집기</h3><span class="tag">새 설계 · 실물 미검증</span></div><p>부품과 배선을 편집하고 준비된 코드를 확인하세요. <b>운동 미리보기</b>를 누르면 3D 운동 화면으로 이동합니다.</p><p class="robot-workbench-notice">${obstacle?'UNO·초음파 센서·L293D와 배선, 미리 작성된 Arduino 코드를 확인하세요. 모터·전원은 시각 전용입니다.':'Pi·모터 HAT·모터·전원은 연결을 편집하기 위한 시각 부품입니다. GPIO40은 40핀 전체 결합을 뜻합니다.'} 3D 운동은 별도의 가상 모델이며 실제 코드나 전기 동작을 실행하지 않습니다.</p><iframe title="Arduino 시스템 회로 편집기" allow="clipboard-write" referrerpolicy="strict-origin-when-cross-origin"></iframe><p role="status" data-workbench-status>편집기를 불러오는 중입니다. 화면이 보이지 않으면 편집기 서버를 확인하세요.</p><details class="compact-details"><summary>저장과 실행 범위</summary><p>배선과 부품 위치는 운동 미리보기 실행 시 서버에 저장하고 검사합니다. 편집한 코드와 구조물은 편집기 프로젝트에 저장됩니다. 로봇용 코드는 ${obstacle?'Arduino':'Raspberry Pi'}에서 실행하도록 작성된 예제이며 3D 가상 운동에서 실행되지 않습니다. 가상 운동은 검토된 기본 연결만 지원합니다.</p></details></section>`;
 const frame=host.querySelector('iframe'),status=host.querySelector('[data-workbench-status]');
 let busy=false,translating=false,disposed=false,editorReady=false;
 frame.onload=()=>{if(!disposed&&!editorReady)status.textContent='회로와 3D 화면을 준비하고 있습니다…';};
 frame.onerror=()=>{if(!disposed)status.textContent='편집기 프로그램을 불러오지 못했습니다. 편집기 서버 연결을 확인하세요.';};
 const receive=async event=>{
  if(disposed||!host.isConnected||event.source!==frame.contentWindow||event.origin!==targetOrigin||event.data?.channel!==channel)return;
  if(event.data.type==='ev:editor-status'){
   if(!['loading','ready','error'].includes(event.data.phase)||typeof event.data.message!=='string'||event.data.message.length>300)return;
   editorReady=event.data.phase==='ready';status.textContent=event.data.message;return;
  }
  if(event.data.type==='ev:translate-request'){
   const {requestId,source,target,project:translationProject}=event.data;
   if(typeof onTranslate!=='function'||typeof requestId!=='string'||!/^[a-f0-9]{32,128}$/i.test(requestId)||typeof source!=='string'||source.length>50000||!['raspberry_pi_c','arduino_cpp'].includes(target))return;
   if(translating){frame.contentWindow.postMessage({type:'ev:translate-result',channel,requestId,error:'이전 번역을 처리 중입니다. 잠시 후 다시 시도하세요.'},targetOrigin);return;}
   translating=true;
   try{
    if(!translationProject||JSON.stringify(translationProject).length>1000000)throw new Error('현재 회로를 확인할 수 없습니다.');
    const result=await onTranslate(source,target,translationProject);
    if(!disposed&&host.isConnected)frame.contentWindow.postMessage({type:'ev:translate-result',channel,requestId,result},targetOrigin);
   }catch(e){if(!disposed&&host.isConnected)frame.contentWindow.postMessage({type:'ev:translate-result',channel,requestId,error:e.message||'코드를 번역하지 못했습니다.'},targetOrigin);}
   finally{translating=false;}
   return;
  }
  if(event.data?.type!=='ev:motion-request'||busy)return;
  const requestId=event.data.requestId;
  if(motionTab&&(event.data.popup!==true||typeof requestId!=='string'||!/^[a-f0-9]{32,128}$/i.test(requestId)))return;
  try{
   const payload=event.data.payload,serialized=JSON.stringify(payload);
   if(!serialized||serialized.length>1000000)throw new Error('편집 프로젝트가 너무 크거나 올바르지 않습니다.');
   busy=true;frame.inert=true;status.textContent='편집한 회로를 저장하고 연결을 확인하고 있습니다…';
   const visualScene=event.data.visualScene;
   if(visualScene&&JSON.stringify(visualScene).length>12000000)throw new Error('조립 그래픽이 너무 큽니다.');
   const motionUrl=await onMotion(payload,revision=>{
    if(Number.isSafeInteger(revision)&&revision>=0)frame.contentWindow.postMessage({type:'ev:revision-saved',channel,revision},targetOrigin);
   },visualScene);
   if(motionTab&&!disposed&&host.isConnected)frame.contentWindow.postMessage({type:'ev:motion-result',channel,requestId,url:motionUrl},targetOrigin);
   if(!disposed)status.textContent='회로를 저장했습니다.';
  }catch(e){if(!disposed){const error=e.message||'회로를 확인하세요.';status.textContent='운동 미리보기를 열지 못했습니다: '+error;if(motionTab&&host.isConnected)frame.contentWindow.postMessage({type:'ev:motion-result',channel,requestId,error},targetOrigin);}}
  finally{frame.inert=false;busy=false;}
 };
 window.addEventListener('message',receive);frame.src=src;
 return ()=>{disposed=true;window.removeEventListener('message',receive);};
}
