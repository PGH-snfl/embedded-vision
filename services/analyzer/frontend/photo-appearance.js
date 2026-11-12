import {workbenchUrl} from './workbench.js?v=photo-autorun-1';
export function renderPhotoAppearance(host,{scene,api,endpoint,esc,stale=false}){
 const objects=scene?.objects?.filter(o=>o.geometry)||[];
 if(stale||!objects.length){host.replaceChildren();return;}
 host.innerHTML=`<section class="workbench-launch"><div class="workbench-lead"><div><span class="section-kicker">입력 사진 → 같은 구조의 3D 모형</span><h3>사진 기반 구조 · ${objects.length}개</h3><p>사진의 형태·색상·배치를 편집기와 시뮬레이션에서 함께 사용합니다.</p></div><button type="button" class="primary" data-photo-open>사진 구조 열기 ↗</button></div><details class="compact-details"><summary>형상 구성·추정 범위</summary><p>${esc(scene.summary)}</p><p>${objects.map(o=>esc(o.label)).join(' · ')}</p><p>사진에서 보이는 외형을 입체로 근사합니다. 깊이·뒷면·실제 치수는 설계 가정입니다.</p></details><p data-photo-status role="status"></p></section>`;
 const button=host.querySelector('[data-photo-open]'),status=host.querySelector('[data-photo-status]');
 button.onclick=async()=>{
  const win=window.open('about:blank','_blank');if(win)win.opener=null;
  button.disabled=true;
  try{const project=await api(endpoint+'/photo-workbench');const url=workbenchUrl(project);
   if(win)win.location=url;else{const a=document.createElement('a');a.href=url;a.target='_blank';a.rel='noopener';a.textContent='사진 구조 편집기 열기';status.replaceChildren(a);return;}
   status.textContent='조립 보기로 열었습니다. 분해 보기를 누르면 구조물 사이의 내부 회로와 배선을 확인할 수 있습니다.';
  }catch(e){if(win)win.close();status.textContent=e.message;}finally{button.disabled=false;}
 };
}
