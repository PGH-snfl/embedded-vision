import {apiPrefix,scopedUrl,resolveTask,csrfHeaders,workspaceId} from './saas.js';
import {workbenchUrl} from './workbench.js?v=photo-autorun-1';
async function open(){
 document.querySelector('#return').href=workspaceId?`/w/${workspaceId}/`:'/';
 const q=new URLSearchParams(location.search),project=q.get('project'),plan=q.get('plan');
 if(!/^[a-f0-9]{32}$/.test(project||'')||!/^[a-f0-9]{32}$/.test(plan||''))throw Error('프로젝트 주소를 확인하세요.');
 const response=await resolveTask(await fetch(scopedUrl(`${apiPrefix}/projects/${project}/inventory/${plan}/photo-workbench`),{credentials:'same-origin',headers:csrfHeaders()}));
 if(!response.ok){const data=await response.json().catch(()=>({}));throw Error(data.detail||'사진 구조를 불러오지 못했습니다.');}
 location.replace(workbenchUrl(await response.json()));
}
open().catch(e=>{document.querySelector('#status').textContent=e.message;});
