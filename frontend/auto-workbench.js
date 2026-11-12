import {workbenchUrl} from './workbench.js?v=photo-autorun-1';
import {workspaceId} from './saas.js';
import {consumeAutoLaunch,autoLaunchStorageFailed} from './auto-navigation.js?v=photo-auto-nav-2';

export function autoTarget(data){
 if(!data?.function_version||data.analysis_complete===false)return null;
 if(data.selected_hypothesis_id&&data.functional_design?.hypothesis_id===data.selected_hypothesis_id)return {kind:'functional'};
 if(data.prototype_design)return {kind:'prototype'};
 if(data.robot_design)return {kind:'robot'};
 const item=(data.proposals||[]).find(p=>p.recipe===data.recommended&&p.simulator_supported);
 return item?{kind:'recipe',recipe:item.recipe}:null;
}
export function withAutorun(url,base){
 const value=new URL(url,base);value.searchParams.set('autorun','1');return value.href;
}
export function createAutoWorkbench({host,api,navigate=url=>window.location.assign(url)}){
 let key='',generation=0;
 function clear(){
  if(key){generation++;key='';host.replaceChildren();}
  host.hidden=true;
 }
 async function update({data,project,plan,revision,stale,endpoint}){
  const target=!stale&&autoTarget(data);
  if(!target){clear();return;}
  const nextKey=[project,plan,revision,data.function_version,target.kind,target.recipe||''].join(':');
  if(nextKey===key)return;
  key=nextKey;const ticket=++generation;
  host.hidden=false;
  const robotNotice=target.kind==='robot'?'이 이동 로봇은 회로와 코드를 보여주고 운동 미리보기에서 수동 조작합니다. 가상 운동은 이 코드를 실행한 결과가 아닙니다.':'사진의 기능을 추정해 만든 새 회로입니다. 코드와 배선을 확인하고 입력값을 바꿔 보세요.';
  host.innerHTML=`<div class="panel-heading"><h2>회로·시뮬레이션</h2><span class="tag">${data.selection_origin==='automatic'?'자동 추정 · 새 설계':'선택한 새 설계'}</span></div><div class="auto-workbench-body"><p>${robotNotice}</p><p data-auto-workbench-status role="status">시뮬레이터를 준비하고 있습니다…</p><p><a class="button primary" data-auto-workbench-open hidden>회로·시뮬레이터 열기 →</a></p></div>`;
  const status=host.querySelector('[data-auto-workbench-status]'),link=host.querySelector('[data-auto-workbench-open]');
  try{
   let url;
   if(target.kind==='functional'){
    const project=await api(endpoint+'/functional-workbench?'+new URLSearchParams({function_version:data.function_version}));
    if(ticket!==generation)return;url=workbenchUrl(project);
   }else if(target.kind==='prototype'){
    const result=await api(endpoint+'/prototype?'+new URLSearchParams({function_version:data.function_version}));
    if(ticket!==generation)return;
    url=workbenchUrl(result.workbench);
   }else if(target.kind==='robot'){
    if(!/^[a-f0-9]{32}$/.test(project)||!/^[a-f0-9]{32}$/.test(plan)||!/^[a-f0-9]{64}$/.test(data.function_version))throw Error('로봇 설계 주소를 확인하세요.');
    // Confirm the existing robot workbench can be prepared before navigating.
    const prepared=await api(endpoint+'/robot-design/workbench?'+new URLSearchParams({function_version:data.function_version}));
    if(ticket!==generation)return;
    if(!prepared?.project)throw Error('로봇 회로를 준비하지 못했습니다.');
    const base=workspaceId?`/w/${workspaceId}/rover-editor.html`:'/rover-editor.html';
    url=base+'?'+new URLSearchParams({project,plan,function_version:data.function_version});
   }else{
    const result=await api(endpoint+'/workbench?'+new URLSearchParams({recipe:target.recipe,function_version:data.function_version}));
    if(ticket!==generation)return;
    url=workbenchUrl(result);
   }
   if(ticket!==generation)return;
   url=target.kind==='robot'?new URL(url,location.href).href:withAutorun(url,location.href);
   link.href=url;link.hidden=false;
   status.textContent=autoLaunchStorageFailed(project)?'브라우저 세션 저장이 불가능해 자동 이동할 수 없습니다. 아래 버튼으로 시뮬레이터를 직접 여세요.':'회로가 준비되었습니다. 아래 버튼으로 시뮬레이터를 열 수 있습니다.';
   if(data.selection_origin==='automatic'&&consumeAutoLaunch(project)){
    status.textContent='완성된 회로의 시뮬레이터로 이동합니다…';
    try{navigate(url);}catch{status.textContent='자동 이동하지 못했습니다. 아래 버튼으로 직접 여세요.';}
   }
  }catch(error){
   if(ticket===generation){
    link.remove();status.textContent='회로를 준비하지 못했습니다: '+(error.message||'다시 확인하세요.');
    const retry=document.createElement('button');retry.type='button';retry.textContent='시뮬레이터 다시 준비';
    retry.onclick=()=>{key='';void update({data,project,plan,revision,stale,endpoint});};
    status.after(retry);
   }
  }
 }
 return {update,clear};
}
