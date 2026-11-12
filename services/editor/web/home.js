const status=document.querySelector('#status');
async function openEditor(project){
 if(project.format!=='velxio-project'||!Array.isArray(project.boards)||!Array.isArray(project.components)||!Array.isArray(project.wires))throw Error('Velxio 프로젝트(.vlx) 파일을 선택하세요.');
 const response=await fetch('/api/editor/projects',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(project)});
 if(!response.ok)throw Error('프로젝트를 편집기 저장소에 준비하지 못했습니다.');
 const prepared=await response.json();
 if(!/^\/editor\?/.test(prepared.editor_url))throw Error('편집기 주소를 확인하세요.');
 location.assign(prepared.editor_url);
}
async function example(model){
 status.textContent='편집기를 준비하고 있습니다…';
 try{const response=await fetch('/api/editor/examples/'+encodeURIComponent(model));if(!response.ok)throw Error('예제를 불러오지 못했습니다.');await openEditor(await response.json());}
 catch(error){status.textContent=error.message;}
}
document.querySelector('#new-project').onclick=()=>example('arduino-uno');
document.querySelector('#project-file').onchange=async event=>{
 const file=event.target.files[0];if(!file)return;
 try{if(file.size>20*1024*1024)throw Error('프로젝트 파일은 20MB 이하로 선택하세요.');await openEditor(JSON.parse(await file.text()));}
 catch(error){status.textContent=error.message||'프로젝트 파일을 읽지 못했습니다.';}
 finally{event.target.value='';}
};
try{
 const response=await fetch('/api/editor/examples');if(!response.ok)throw Error('보드 예제를 읽지 못했습니다.');
 for(const item of await response.json()){
  const button=document.createElement('button'),name=document.createElement('strong'),note=document.createElement('small');
  name.textContent=item.name;note.textContent=item.runtime==='local'?'로컬 시뮬레이션 지원':'설계·편집 예제 · 전용 실행 환경 필요';button.append(name,note);button.onclick=()=>example(item.id);document.querySelector('#examples').append(button);
 }
}catch(error){status.textContent=error.message;}
