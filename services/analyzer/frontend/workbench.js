import {fullBreadboardProject} from './workbench-layout.js?v=1';
import {workspaceId} from './saas.js';
export function workbenchUrl(data){
 data=fullBreadboardProject(data);
 // The simulator may be served on a separate port. Carry the analysis
 // origin so its return link opens the same project workspace.
 data={...data,embeddedVision:{...data.embeddedVision,analysis_origin:location.origin}};
 const bytes=new TextEncoder().encode(JSON.stringify(data));
 const encoded=btoa(Array.from(bytes,b=>String.fromCharCode(b)).join(''));
 const editor=workspaceId?location.origin+'/w/'+workspaceId+'/editor':`http://127.0.0.1:${globalThis.EMBEDDED_VISION_EDITOR_PORT||8768}/editor`;
 return editor+'?embedded=1&view=photo-autorun-1#project='+encodeURIComponent(encoded);
}
export async function openGoalWorkbench({api,endpoint,data,win}){
 const selected=data.proposals.find(p=>p.recipe===data.recommended&&p.simulator_supported);
 if(!selected){if(win)win.close();return false;}
 const payload=await api(endpoint+'/workbench?'+new URLSearchParams({recipe:selected.recipe,function_version:data.function_version}));
 if(win){win.location=workbenchUrl(payload);return true;}
 return false;
}
export function initWorkbench(host,{api,endpoint,recipe='arduino_voltage_divider',functionVersion}){
  host.innerHTML=`<section class="workbench-launch"><div class="workbench-lead"><div><span class="section-kicker">INTERACTIVE</span><h3>그래픽 시뮬레이터</h3><p>빵판에 꽂힌 부품과 배선을 3D로 확인하고 코드를 실행하세요.</p></div><button type="button" class="primary" data-open>Velxio 편집기 열기 ↗</button></div><details class="compact-details"><summary>사용법·지원 범위·파일 저장</summary><p>회로 열기 → 3D에서 부품·배선 편집 → 코드 편집 → ▶ 실행 → 보드 출력 확인</p><p>현재 자동 가져오기는 UNO 분압·LED 점등·깜빡임·밝기 조절·버튼 제어·조도 센서와 16×2 병렬 LCD 문자 표시를 지원합니다. LCD의 전원·대비·백라이트는 실제 전기적 동작을 완전히 검증하지 않습니다. 변경 내용은 브라우저에 임시 저장되며 SaaS에서는 작업공간에 저장할 수 있습니다. 원본 분석·KiCad에는 자동 반영되지 않습니다.</p><button type="button" data-download>편집 프로젝트(.vlx) 저장</button></details><p role="status" data-status></p></section>`;
  const status=host.querySelector('[data-status]');
  const payload=()=>api(endpoint+'/workbench?'+new URLSearchParams({recipe,...(functionVersion?{function_version:functionVersion}:{})}));
  host.querySelector('[data-open]').onclick=async()=>{
    // Reserve the tab during the user gesture; popup blockers otherwise drop async opens.
    const win=window.open('about:blank','_blank');if(win)win.opener=null;
    try{
      const data=await payload();
      const url=workbenchUrl(data);
      if(win)win.location=url;else{const a=document.createElement('a');a.href=url;a.target='_blank';a.rel='noopener';a.textContent='편집기 열기';status.replaceChildren(a);return;}
      status.textContent=workspaceId?'작업공간의 편집기를 새 탭에서 열었습니다.':'새 탭에서 편집기를 열었습니다. 접속이 안 되면 bash run_workbench.sh를 실행하세요.';
    }catch(e){if(win)win.close();status.textContent=e.message;}
  };
  host.querySelector('[data-download]').onclick=async()=>{
    try{const data=fullBreadboardProject(await payload()),url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='embedded-uno.vlx';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
    catch(e){status.textContent=e.message;}
  };
}
