import {apiPrefix,csrfHeaders,scopedUrl,resolveTask} from './saas.js';
import {mountRobotWorkbench} from './robot-workbench.js?v=loading-1';
import {createRoverCircuitStorage} from './rover-circuit-storage.js?v=rover-editor-1';
import {createRoverStorage} from './rover-storage.js?v=rover-edit-3';
import {renderRobotGuide} from './robot-guide.js?v=photo-prototypes-1';
import {loadPhotoWorkbench,editorStructure} from './photo-structure.js?v=loading-1';

const host=document.querySelector('#editor-host');
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function api(url,options={}){
 const response=await resolveTask(await fetch(scopedUrl(url),{...options,credentials:'same-origin',headers:{...csrfHeaders(),...options.headers}}));
 if(!response.ok){const err=await response.json().catch(()=>({detail:'서버 응답을 확인할 수 없습니다.'}));throw new Error(typeof err.detail==='string'?err.detail:'요청을 확인할 수 없습니다.');}
 return response.json();
}
async function start(){
 const q=new URLSearchParams(location.search),project=q.get('project'),plan=q.get('plan'),version=q.get('function_version');
 if(!/^[a-f0-9]{32}$/.test(project||'')||!/^[a-f0-9]{32}$/.test(plan||'')||!/^[a-f0-9]{64}$/.test(version||''))throw new Error('프로젝트 주소가 올바르지 않습니다. 분석 화면에서 다시 열어 주세요.');
 const endpoint=`${apiPrefix}/projects/${project}/inventory/${plan}`;
 const store=createRoverCircuitStorage(api,endpoint,version);
 const structure=createRoverStorage(api,endpoint,version);
 const panel=document.querySelector('#motion-panel'),simHost=document.querySelector('#motion-simulator');
 let disposeMotion=null;
 document.querySelector('#return-editor').onclick=()=>{
  if(disposeMotion){disposeMotion();disposeMotion=null;}
  panel.hidden=true;host.hidden=false;
 };
 window.addEventListener('pagehide',()=>{if(disposeMotion)disposeMotion();},{once:true});
 await store.load();
 const workbench=await loadPhotoWorkbench(api,endpoint,version,message=>{host.textContent=message;});
 if(workbench.revision!==store.revision())throw new Error('다른 화면에서 회로가 변경되었습니다. 새로고침해 주세요.');
 mountRobotWorkbench(host,{project:workbench.project,
  onTranslate:(source,target,project)=>api(endpoint+'/robot-design/translate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({function_version:version,source,target,project})}),
  onMotion:async(payload,notifySaved,assemblyVisual)=>{
   if(payload?.embeddedVision?.circuit_revision!==store.revision())throw new Error('회로 버전이 변경되었습니다. 새로고침 후 다시 확인하세요.');
   const currentStructure=editorStructure(payload);
   const {validation,revision}=await store.commitEditor(payload);
   notifySaved(revision);
   if(!validation.allowed)throw new Error((validation.errors||[]).join(' ')||'회로 연결을 확인하세요.');
   const checked=await store.validate();
   if(!checked.allowed)throw new Error((checked.errors||[]).join(' ')||'회로 연결을 확인하세요.');
   const proposal=await api(endpoint+'/proposals');
   if(proposal.inventory_plan!==plan||proposal.function_version!==version||!proposal.robot_design)throw new Error('선택한 로봇 기능이 변경되었습니다. 다시 열어 주세요.');
   if(!structure.isLoaded())await structure.load();
   const {renderRoverSimulator}=await import('./rover-simulator.js?v=object-lock-1');
   // The connection or selected function may have changed while loading.
   if(store.revision()!==revision)throw new Error('회로가 변경되었습니다. 다시 실행하세요.');
   const latest=await store.validate();
   if(!latest.allowed)throw new Error((latest.errors||[]).join(' ')||'회로 연결을 확인하세요.');
   if(disposeMotion){disposeMotion();disposeMotion=null;}
   disposeMotion=renderRoverSimulator(simHost,{design:proposal.robot_design,esc,initialStructure:currentStructure??structure.snapshot(),assemblyVisual,structureComplete:!!payload.embeddedVision?.structure_completion,
    onStructureChange:(value,setStatus)=>structure.update(value,setStatus),
    validateMotion:async()=>{try{if(store.revision()!==revision)throw new Error('회로가 변경되었습니다. 다시 실행하세요.');const result=await store.validate();if(!result.allowed)throw new Error((result.errors||[]).join(' ')||'회로 연결을 확인하세요.');return {allowed:true};}catch(e){return {allowed:false,message:e.message};}}})||null;
   renderRobotGuide(document.querySelector('#motion-guide'),{data:proposal,endpoint,esc});
   host.hidden=true;panel.hidden=false;panel.scrollTop=0;
   simHost.querySelector('[data-rover-viewport]')?.focus({preventScroll:true});
  }});
}
start().catch(error=>{host.textContent='편집기를 열지 못했습니다: '+(error.message||'프로젝트를 확인하세요.');});
