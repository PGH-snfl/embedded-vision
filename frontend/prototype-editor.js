import {apiPrefix,csrfHeaders,scopedUrl,resolveTask,workspaceId} from './saas.js';
import {workbenchUrl} from './workbench.js?v=photo-autorun-1';
import {renderRoverSimulator} from './rover-simulator.js?v=object-lock-1';
import {renderRobotGuide} from './robot-guide.js?v=photo-prototypes-1';

const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function api(url){
 const response=await resolveTask(await fetch(scopedUrl(url),{credentials:'same-origin',headers:csrfHeaders()}));
 if(!response.ok){const body=await response.json().catch(()=>({}));throw new Error(body.detail||'서버 응답을 확인하세요.');}
 return response.json();
}
async function start(){
 const q=new URLSearchParams(location.search),project=q.get('project'),plan=q.get('plan'),version=q.get('function_version');
 if(!/^[a-f0-9]{32}$/.test(project||'')||!/^[a-f0-9]{32}$/.test(plan||'')||!/^[a-f0-9]{64}$/.test(version||''))throw Error('프로젝트 주소를 확인하세요.');
 const data=await api(`${apiPrefix}/projects/${project}/inventory/${plan}/prototype?`+new URLSearchParams({function_version:version}));
 const design=data.design,projectData=data.workbench;
 document.querySelector('#analysis-link').href=workspaceId?`/w/${workspaceId}/`:'/';
 document.querySelector('#title').textContent=design.title||design.name||'새 회로 설계';
 document.querySelector('#summary').textContent=design.summary||design.behavior||'';
 document.querySelector('#notice').textContent=design.simulation_notice||design.simulator?.notice||'새로 구성한 시제품이며 사진의 원래 배선과 실물 동작은 확인되지 않았습니다.';
 const parts=design.components||design.parts||Object.values(design.specifications||{});
 const lines=design.connections||[];
 const physical=design.physical_design;
 if(data.kind==='watering'&&physical?.status==='REFERENCE_DESIGN'){
  const link=document.createElement('a');link.href=scopedUrl('/watering-circuit.svg');link.target='_blank';link.rel='noopener';link.textContent='실물 참조 회로도';link.className='prototype-diagram-link';document.querySelector('.prototype-tabs').appendChild(link);
 }
 document.querySelector('#design-details').innerHTML=`<div><h3>새 회로 부품</h3><ul>${parts.map(p=>`<li>${esc(typeof p==='string'?p:p.name||p.label||p.id)}</li>`).join('')}</ul></div><div><h3>연결</h3><ul>${lines.map(c=>`<li>${esc(typeof c==='string'?c:`${c.from} → ${c.to}`)}</li>`).join('')}</ul></div>${physical?`<div><h3>제작 부품과 조립 가이드</h3><ul>${(physical.parts||[]).map(p=>`<li>${esc(typeof p==='string'?p:`${p.id} · ${p.name} — ${p.note||''}`)}</li>`).join('')}</ul>${(physical.steps||[]).map((s,i)=>`<p><strong>${i+1}. ${esc(s.title)}</strong><br>${esc(s.description)}</p>`).join('')}<p>${esc(physical.note||'')}</p></div>`:''}`;
 const frame=document.createElement('iframe');frame.title='회로와 코드 편집기';frame.allow='clipboard-write';frame.onload=()=>{document.querySelector('#status').textContent=q.get('autorun')==='1'?'자동 실행 상태와 결과를 편집기에서 확인하세요.':'회로·코드를 확인하고 ▶ 실행을 눌러 보세요.';};
 const editorUrl=new URL(workbenchUrl(projectData),location.href);
 if(q.get('autorun')==='1')editorUrl.searchParams.set('autorun','1');
 frame.src=editorUrl.href;document.querySelector('#editor-frame').appendChild(frame);
 if(data.kind==='obstacle_rover'){
  document.querySelector('#robot-guide-panel').hidden=false;
  renderRobotGuide(document.querySelector('#robot-guide'),{data:{robot_design:design,function_version:version},esc});
  const editor=document.querySelector('#editor-tab'),motion=document.querySelector('#motion-tab'),editorPanel=document.querySelector('#editor-panel'),motionPanel=document.querySelector('#motion-panel');
  let dispose=null;motion.hidden=false;
  motion.onclick=()=>{editorPanel.hidden=true;motionPanel.hidden=false;editor.setAttribute('aria-pressed','false');motion.setAttribute('aria-pressed','true');if(!dispose)dispose=renderRoverSimulator(document.querySelector('#motion-host'),{design,esc})||null;};
  editor.onclick=()=>{document.querySelector('#motion-host [data-rover-action="stop"]')?.click();motionPanel.hidden=true;editorPanel.hidden=false;motion.setAttribute('aria-pressed','false');editor.setAttribute('aria-pressed','true');};
  window.addEventListener('pagehide',()=>dispose?.(),{once:true});
 }
}
start().catch(e=>{document.querySelector('#status').textContent='편집기를 열지 못했습니다: '+(e.message||'다시 시도하세요.');});
