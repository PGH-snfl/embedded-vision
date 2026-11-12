// URL-bound workspace identity. Switching another tab cannot change this tab's tenant.
export const workspaceId = /^\/w\/([a-f0-9]{32})(?:\/|$)/.exec(location.pathname)?.[1] || null;
export const apiPrefix = workspaceId ? `/api/w/${workspaceId}` : '/api';
export const projectStorageKey = workspaceId ? `ev-project:${workspaceId}` : 'ev-project';
export const csrfHeaders = () => ({'X-EV-CSRF': decodeURIComponent(document.cookie.split('; ').find(c=>c.startsWith('ev_csrf='))?.slice(8)||'')});
export function scopedUrl(url) {
  return workspaceId && url.startsWith('/api/') && !url.startsWith('/api/w/') && !url.startsWith('/api/saas/')
    ? apiPrefix+url.slice(4) : url;
}

export async function resolveTask(response) {
  if(response.status!==202)return response;
  const queued=await response.clone().json();
  if(!queued.status_url)return response;
  const started=Date.now();
  while(Date.now()-started<20*60*1000){
    window.dispatchEvent(new CustomEvent('ev-server-job',{detail:'서버에서 작업을 처리하고 있습니다…'}));
    await new Promise(r=>setTimeout(r,800));
    const poll=await fetch(queued.status_url,{credentials:'same-origin'});
    if(!poll.ok)return poll;
    const job=await poll.json();
    if(['done','failed','interrupted'].includes(job.status)){
      window.dispatchEvent(new CustomEvent('ev-server-job',{detail:job.status==='done'?'서버 작업 완료':'서버 작업 중단'}));
      const result=job.result;
      return new Response(JSON.stringify(result?.data||result||{detail:'작업이 중단되었습니다. 자동 재실행하지 않습니다.'}),{
        status:result?.status_code||(job.status==='done'?200:503),headers:{'Content-Type':'application/json'}});
    }
  }
  throw new Error('처리 시간이 길어졌습니다. 작업은 자동 재제출하지 않습니다. 잠시 후 결과를 확인하세요.');
}

export async function initSaas(){
  if(!workspaceId)return;
  const response=await fetch('/api/saas/me');
  if(response.status===401){location.assign('/login');return;}
  if(!response.ok)throw new Error('로그인 상태를 확인할 수 없습니다.');
  const me=await response.json(),workspace=me.workspaces.find(w=>w.id===workspaceId);
  document.querySelectorAll('#empty p').forEach(p=>p.childNodes.forEach(n=>{if(n.nodeType===Node.TEXT_NODE)n.textContent=n.textContent.replace('사진은 이 컴퓨터에 저장됩니다.','사진은 작업공간의 서버에 저장됩니다.');}));
  const bar=document.createElement('div');bar.className='saas-workspace-bar';
  const label=document.createElement('strong');label.textContent=workspace?.name||'작업공간';
  const back=document.createElement('a');back.href='/workspaces';back.textContent='작업공간 전환';
  const status=document.createElement('span');status.setAttribute('role','status');status.textContent=me.email;
  bar.append(label);if(me.auth_enabled!==false)bar.append(back);bar.append(status);document.body.prepend(bar);
  window.addEventListener('ev-server-job',event=>{status.textContent=event.detail;});
}
