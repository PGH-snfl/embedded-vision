import {apiPrefix} from './saas.js';
import {workbenchUrl} from './workbench.js?v=photo-autorun-1';
const host=document.querySelector('#boards'),status=document.querySelector('#status');
const escape=value=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
try{
 const response=await fetch(apiPrefix+'/board-profiles');if(!response.ok)throw Error('보드 정보를 읽지 못했습니다.');
 const {profiles}=await response.json();
 host.innerHTML=Object.entries(profiles).map(([id,p])=>`<article><h2>${escape(p.component.name)}</h2><p>${escape(p.language)} · ${p.runtime.availability==='local'?'로컬 실행 지원':'전용 실행 서비스 필요'}</p><p>${escape(p.selection)}</p><button data-board="${escape(id)}">회로·코드·시뮬레이터 열기 ↗</button><details><summary>실행 조건</summary><p>${escape(p.runtime.notice)}</p><p>코드 파일: ${escape(p.entry_file)}</p><small>실행 결과는 편집기의 조작·동작 검사에서 확인합니다.</small></details></article>`).join('');
 host.addEventListener('click',async event=>{
  const button=event.target.closest('button[data-board]');if(!button)return;
  const win=window.open('about:blank','_blank');if(win)win.opener=null;
  try{
   const response=await fetch(apiPrefix+'/board-profiles/'+encodeURIComponent(button.dataset.board)+'/example');if(!response.ok)throw Error('예제를 읽지 못했습니다.');
   const project=await response.json(),url=new URL(workbenchUrl(project));
   if(profiles[button.dataset.board].runtime.availability==='local')url.searchParams.set('autorun','1');
   if(win)win.location=url.href;else{const a=document.createElement('a');a.href=url.href;a.target='_blank';a.rel='noopener';a.textContent='편집기 열기';status.replaceChildren(a);return;}
   status.textContent=profiles[button.dataset.board].runtime.notice;
  }catch(error){if(win)win.close();status.textContent=error.message;}
 });
}catch(error){status.textContent=error.message;}
