// Native snapshots and motion share the same geometry. Positions use metres in
// motion and CSS pixels in the editor; the photo's scale remains a hypothesis.
export async function loadPhotoWorkbench(api,endpoint,version,onStatus=()=>{}){
 const url=endpoint+'/robot-design/workbench?'+new URLSearchParams({function_version:version});
 let workbench=await api(url);
 if(workbench.project.embeddedVision?.photo_structure!=null)return workbench;
 onStatus('사진에 보이는 차체·바퀴·프레임을 오브젝트로 생성하고 있습니다…');
 try{
  await api(endpoint+'/photo-structure',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({expected_revision:workbench.project.embeddedVision.source_revision})});
  workbench=await api(url);
 }catch(error){
  if(/변경/.test(error.message||''))throw error;
  onStatus('사진 구조물 생성: '+(error.message||'분석을 완료하지 못했습니다.'));
 }
 return workbench;
}

export function editorStructure(project){
 const parts=(project.components||[]).filter(p=>p.metadataId==='ev-structure');
 if(!parts.length&&!project.embeddedVision?.photo_structure_version)return null;
 const first=parts.find(p=>Array.isArray(p.properties?.photoSceneOrigin));
 const origin=first?.properties.photoSceneOrigin||[0,0],mm=25.4/96;
 const objects=parts.map(part=>{
  const p=part.properties||{},width=Number(p.width),height=Number(p.height),depth=Number(p.depth),elevation=Number(p.elevation||0);
  if(![width,height,depth,elevation,part.x,part.y].every(Number.isFinite)||[width,height,depth].some(n=>n<2||n>500))throw Error('구조물 치수를 확인하세요.');
  const rotation=[Number(p.rotationX||0),-Number(p.rotation||0),Number(p.rotationZ||0)].map(n=>n*Math.PI/180);
  if(rotation.some(n=>!Number.isFinite(n)||Math.abs(n)>Math.PI*2))throw Error('구조물 회전을 확인하세요.');
  return {id:part.id,label:String(p.label||'사용자 구조물').slice(0,60),shape:['cylinder','sphere'].includes(p.shape)?p.shape:'box',
   position:[((part.x+6)*mm+width/2-origin[0])/1000,(elevation+height/2)/1000,((part.y+6)*mm+depth/2-origin[1])/1000],
   size:[width,height,depth].map(n=>n/1000),rotation,color:/^#[0-9a-f]{6}$/i.test(p.color)?p.color:'#829aaf',
   ...(p.evPhotoGeometry?{photoGeometry:p.evPhotoGeometry}:{})};
 });
 return {version:1,...(project.embeddedVision?.structure_completion?{completion_version:'whole-structure-v1'}:{}),objects};
}
