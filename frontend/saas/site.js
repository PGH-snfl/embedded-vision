const status=document.querySelector('#status');
const csrf=()=>decodeURIComponent(document.cookie.split('; ').find(c=>c.startsWith('ev_csrf='))?.slice(8)||'');
async function request(url,body){
 const response=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json','X-EV-CSRF':csrf()},body:JSON.stringify(body||{})});
 const data=await response.json();if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'입력을 확인하세요.');return data;
}
const login=document.querySelector('#login');
if(login)login.onsubmit=async event=>{event.preventDefault();const button=login.querySelector('button');button.disabled=true;status.textContent='로그인 중…';try{const f=new FormData(login);await request('/api/saas/login',{email:f.get('email'),password:f.get('password')});location.assign('/workspaces');}catch(e){status.textContent=e.message;}finally{button.disabled=false;}};
const list=document.querySelector('#workspace-list');
if(list){
 const response=await fetch('/api/saas/me');if(response.status===401)location.assign('/login');
 else if(response.ok){const me=await response.json();for(const w of me.workspaces){const a=document.createElement('a');a.className='workspace-card';a.href='/w/'+w.id+'/';const name=document.createElement('strong');name.textContent=w.name;const role=document.createElement('span');role.textContent=({owner:'소유자',editor:'편집자',viewer:'조회자'})[w.role]||w.role;a.append(name,role);list.append(a);}}
 document.querySelector('#logout').onclick=async()=>{try{await request('/api/saas/logout');location.assign('/login');}catch(e){status.textContent=e.message;}};
 document.querySelector('#workspace').onsubmit=async event=>{event.preventDefault();try{const data=await request('/api/saas/workspaces',{name:new FormData(event.target).get('name')});location.assign('/w/'+data.id+'/');}catch(e){status.textContent=e.message;}};
}
