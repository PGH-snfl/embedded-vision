// Persist each committed drawing in order and verify the saved version before motion.
export function createRoverCircuitStorage(api,endpoint,functionVersion){
 const url=endpoint+'/robot-design/circuit';
 let revision=0,draft=null,loaded=false,dirty=false,pending=null,error='',generation=0,status=()=>{};
 async function load(){const data=await api(url+'?function_version='+encodeURIComponent(functionVersion));revision=data.revision;draft=data.circuit;loaded=true;return draft;}
 async function flush(){
  if(error)throw new Error(error);
  if(pending)return pending;
  pending=(async()=>{
   try{
    while(dirty){
     const sent=draft;dirty=false;status('회로 저장 중…');
     const data=await api(url,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({function_version:functionVersion,expected_revision:revision,circuit:sent})});
     revision=data.revision;
    }
    status('회로 저장됨');
   }catch(e){dirty=true;error=e.message||'회로 저장 실패';status('저장 실패: '+error);throw e;}
  })();
  try{return await pending;}finally{pending=null;}
 }
 function update(graph,setStatus){if(!loaded)return;draft=graph;dirty=true;generation++;if(setStatus)status=setStatus;if(error){status('저장 실패: '+error+' 새로고침 후 확인하세요.');return;}status('회로 저장 중…');void flush().catch(()=>{});}
 async function validate(){
  if(!loaded)throw new Error('회로를 불러오지 못했습니다.');
  await flush();
  const checkedGeneration=generation,checkedRevision=revision;
  const result=await api(url+'/validate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({function_version:functionVersion,expected_revision:checkedRevision})});
  if(checkedGeneration!==generation)throw new Error('검사 중 회로가 변경되었습니다. 다시 확인하세요.');
  return result;
 }
 async function commitEditor(project){
  if(!loaded)throw new Error('회로를 불러오지 못했습니다.');
  await flush();
  const data=await api(endpoint+'/robot-design/workbench/commit',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({function_version:functionVersion,expected_revision:revision,project})});
  revision=data.revision;draft=data.circuit;generation++;
  return {validation:data.validation,revision:data.revision};
 }
 return {load,update,validate,commitEditor,revision:()=>revision,snapshot:()=>draft,isLoaded:()=>loaded};
}
