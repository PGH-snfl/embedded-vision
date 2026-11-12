import {apiPrefix,csrfHeaders,scopedUrl,workspaceId,resolveTask} from './saas.js';
import {createRoverCircuitStorage} from './rover-circuit-storage.js?v=rover-editor-1';
import {createRoverStorage} from './rover-storage.js?v=rover-edit-3';
import {renderRoverSimulator} from './rover-simulator.js?v=object-lock-1';
import {renderRobotGuide} from './robot-guide.js?v=photo-prototypes-1';

// The URL carries only identifiers and the saved revision, never user code.
export function parseMotionQuery(search){
 const params=new URLSearchParams(search),names=['project','plan','function_version','revision'];
 if(names.some(k=>params.getAll(k).length!==1)||[...params.keys()].some(k=>!names.includes(k)))throw new Error('운동 화면 주소를 확인하세요. 편집기에서 다시 열어 주세요.');
 const project=params.get('project'),plan=params.get('plan'),version=params.get('function_version'),raw=params.get('revision');
 if(!/^[a-f0-9]{32}$/.test(project)||!/^[a-f0-9]{32}$/.test(plan)||!/^[a-f0-9]{64}$/.test(version)||!/^(0|[1-9][0-9]{0,15})$/.test(raw))throw new Error('운동 화면 주소를 확인하세요. 편집기에서 다시 열어 주세요.');
 const revision=Number(raw);
 if(!Number.isSafeInteger(revision))throw new Error('회로 저장 버전이 올바르지 않습니다.');
 return {project,plan,version,revision};
}

export function createMotionSession({api,project,plan,version,revision,prefix=apiPrefix}){
 const endpoint=`${prefix}/projects/${project}/inventory/${plan}`;
 const circuit=createRoverCircuitStorage(api,endpoint,version);
 const structure=createRoverStorage(api,endpoint,version);
 async function check(){
  if(!circuit.isLoaded()||circuit.revision()!==revision)throw new Error('회로가 변경되었습니다. 편집기에서 운동 미리보기를 다시 실행하세요.');
  const result=await circuit.validate();
  if(result.revision!==revision||!result.allowed)throw new Error((result.errors||[]).join(' ')||'회로 연결을 다시 확인하세요.');
  return result;
 }
 async function load(){
  const [proposal]=await Promise.all([api(endpoint+'/proposals'),circuit.load()]);
  if(proposal.inventory_plan!==plan||proposal.function_version!==version||!proposal.robot_design)throw new Error('선택한 로봇 기능이 변경되었습니다. 편집기에서 다시 열어 주세요.');
  await check();
  await structure.load();
  return {proposal,structure:structure.snapshot(),endpoint};
 }
 return {load,check,saveStructure:(value,status)=>structure.update(value,status)};
}

async function requestApi(url,options={}){
 const response=await resolveTask(await fetch(scopedUrl(url),{...options,credentials:'same-origin',headers:{...csrfHeaders(),...options.headers}}));
 if(!response.ok){const body=await response.json().catch(()=>({detail:'서버 응답을 확인할 수 없습니다.'}));throw new Error(typeof body.detail==='string'?body.detail:'서버 응답을 확인할 수 없습니다.');}
 return response.json();
}
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

async function start(){
 const status=document.querySelector('#motion-page-status'),host=document.querySelector('#motion-simulator');
 const link=document.querySelector('#analysis-link');link.href=workspaceId?`/w/${workspaceId}/`:'/';
 try{
  const params=parseMotionQuery(location.search),session=createMotionSession({api:requestApi,...params});
  const {proposal,structure,endpoint}=await session.load();
  const dispose=renderRoverSimulator(host,{design:proposal.robot_design,esc,initialStructure:structure,
   onStructureChange:(value,setStatus)=>session.saveStructure(value,setStatus),
   validateMotion:async()=>{try{await session.check();return {allowed:true};}catch(e){return {allowed:false,message:e.message};}}});
  renderRobotGuide(document.querySelector('#motion-guide'),{data:proposal,endpoint,esc});
  status.textContent='저장된 회로를 확인했습니다. 주행 명령마다 다시 확인합니다.';
  if(dispose)window.addEventListener('pagehide',dispose,{once:true});
 }catch(e){status.textContent='운동 화면을 열지 못했습니다: '+(e.message||'다시 시도하세요.');status.classList.add('motion-error');}
}
if(typeof document!=='undefined')void start();
