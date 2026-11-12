// Queue changes in order and reject stale tabs rather than overwriting them.
export function createRoverStorage(api,endpoint,functionVersion){
 let revision=0,loaded=false,draft=null,dirty=false,saving=false,error='',status=()=>{};
 const url=endpoint+'/robot-design/structure';
 async function load(){
  const saved=await api(url+'?function_version='+encodeURIComponent(functionVersion));
  revision=saved.revision;draft=saved.structure;loaded=true;return draft;
 }
 async function flush(){
  if(saving||!loaded||!dirty||error)return;
  saving=true;
  try{
   while(dirty){
    const sent=draft;dirty=false;status('구조 저장 중…');
    const result=await api(url,{method:'PUT',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({function_version:functionVersion,expected_revision:revision,structure:sent})});
    revision=result.revision;
   }
   status('구조 저장됨');
  }catch(e){dirty=true;error=e.message||'서버 저장 실패';status('저장 실패: '+error+' 변경 사항을 확인한 뒤 새로고침하세요.');}
  finally{saving=false;}
 }
 function update(value,setStatus){draft=value;dirty=true;if(setStatus)status=setStatus;if(error){status('저장 실패: '+error+' 변경 사항을 확인한 뒤 새로고침하세요.');return;}status('구조 저장 중…');void flush();}
 function snapshot(){return draft;}
 function isLoaded(){return loaded;}
 return {load,update,snapshot,isLoaded};
}
