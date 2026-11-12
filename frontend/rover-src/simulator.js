import * as THREE from '../../third_party/velxio/frontend/node_modules/three/build/three.module.js';
import {OrbitControls} from '../../third_party/velxio/frontend/node_modules/three/examples/jsm/controls/OrbitControls.js';
import {stepRover,roverPoseToWorld,ROVER_WHEEL_LAYOUT,ROVER_ASSUMPTIONS,ROVER_COMMANDS} from './kinematics.js';
import {defaultStructure,validStructure,cloneStructure,MAX_OBJECTS} from './structure.js';
import {createManualController,MANUAL_COMMANDS,manualLabel} from './manual-control.js';
import {createObstacleController} from './obstacle-control.js';
import {canDragComponent} from '../../third_party/velxio/frontend/src/components/circuitiny/objectMovement.ts';
import {validAssemblyVisual} from './assembly-visual.js';
import {mechanicalMesh,mechanicalRole,completeMotionStructure} from './mechanical-shape.js';

const NAMES={forward:'전진',backward:'후진',left:'좌회전',right:'우회전',stop:'정지'};

// Keep the motor command behind an optional asynchronous circuit check.
// Stop always takes effect immediately, even while a request is in flight.
export function createMotionGuard({validateMotion,onCommand,onState}) {
 let generation=0,pending=false,disposed=false;
 const notify=(busy,message)=>{if(!disposed)onState(busy,message);};
 async function request(next){
  if(disposed)return;
  if(next==='stop'){
   generation++;pending=false;onCommand('stop');notify(false,'');return;
  }
  if(pending)return;
  if(typeof validateMotion!=='function'){onCommand(next);return;}
  const ticket=++generation;pending=true;onCommand('stop');notify(true,'회로 연결을 확인하고 있습니다…');
  try{
   const answer=await validateMotion(next);
   if(disposed||ticket!==generation)return;
   const allowed=answer===true||answer?.allowed===true;
   if(allowed){onCommand(next);notify(false,'');}
   else{onCommand('stop');notify(false,typeof answer?.message==='string'?answer.message:'회로 연결을 확인한 뒤 다시 실행하세요.');}
  }catch(error){
   if(!disposed&&ticket===generation){onCommand('stop');notify(false,'회로 검증에 실패했습니다: '+(error?.message||'다시 확인하세요.'));}
  }finally{
   if(ticket===generation)pending=false;
  }
 }
 function dispose(){disposed=true;generation++;pending=false;}
 return {request,dispose};
}

// This view evaluates a deliberately simplified, deterministic motion model.
// It does not run the generated Pi code or simulate motors/electricity.
export function renderRoverSimulator(host,{design,esc,initialStructure=null,onStructureChange,validateMotion,assemblyVisual,structureComplete=false}={}) {
 if(!host)return;
 if(host.__roverDispose)host.__roverDispose();
 const photoMode=design?.photo_structure!=null;
 host.innerHTML=`<section class="rover-sim"><div class="preview-heading"><h3>이동 로봇 3D 동작 시험</h3><span class="tag">가상 운동 모델</span></div>
 <p>${photoMode?'사진 구조와 반대편·하부를 보완한 전체 설계입니다. design으로 시작하는 오브젝트는 설계 보완이며 원본 형상과 실제 치수는 미확인입니다. 노란 화살표가 가정한 앞쪽입니다.':'선택한 로봇의 차체와 좌우 바퀴를 3D로 확인하고 조작하세요. 노란 화살표와 작은 보조 바퀴 쪽이 앞입니다. 좌우는 로봇의 앞쪽을 기준으로 합니다.'}</p>
 <p class="rover-disclaimer">모터 출력 비율을 가상의 바퀴 속도로 바꾼 예상 움직임입니다. 코드·라즈베리파이·회로·모터 또는 실제 물리 작동을 실행하거나 검증하지 않습니다.</p>
 <div class="rover-sim-layout"><div class="rover-viewport" data-rover-viewport tabindex="0" aria-label="마우스로 회전하고 방향키로 조작할 수 있는 가상 로봇 3D 화면"></div><div class="rover-controls">
 <section class="rover-manual"><h4>직접 조작</h4><p>방향키 또는 W A S D를 누르는 동안 움직입니다. 버튼도 길게 누를 수 있습니다.</p><div class="rover-pad" aria-label="직접 조작 방향 버튼"><button type="button" data-rover-hold="forward" aria-label="전진: 누르는 동안 이동">▲ 전진</button><button type="button" data-rover-hold="left" aria-label="좌회전: 누르는 동안 이동">◀ 좌회전</button><button type="button" data-rover-hold="right" aria-label="우회전: 누르는 동안 이동">우회전 ▶</button><button type="button" data-rover-hold="backward" aria-label="후진: 누르는 동안 이동">▼ 후진</button></div></section>
 ${design?.simulation_kind==='obstacle_rover'?`<section class="rover-manual" data-obstacle-controls><h4>장애물 회피</h4><p>가상 센서 거리를 조절하고 자동 주행을 시작하세요. 앞의 표식은 입력한 거리를 나타냅니다. 20 cm 이하면 후진 후 좌회전합니다.</p><label>장애물 거리: <span data-obstacle-value>50</span> cm <input data-obstacle-distance type="range" min="2" max="100" value="50" step="1"></label><label><input data-obstacle-fail type="checkbox"> 센서 응답 없음</label><button type="button" data-obstacle-start>자동 주행 시작</button><button type="button" data-obstacle-stop>자동 주행 정지</button><p data-obstacle-state role="status">정지</p></section>`:''}
 <div class="rover-actions" aria-label="로봇 주행 명령"><button type="button" data-rover-action="forward">전진 1초</button><button type="button" data-rover-action="left">좌회전 1초</button><button type="button" data-rover-action="right">우회전 1초</button><button type="button" data-rover-action="backward">후진 1초</button><button type="button" data-rover-action="stop">정지</button><button type="button" data-rover-reset>위치 초기화</button></div>
 <p class="rover-state" data-rover-state aria-live="polite">정지 · 왼쪽 0% / 오른쪽 0%</p><p data-motion-status role="status"></p><p class="rover-location" data-rover-location>위치 X 0.00 m · Y 0.00 m · 방향 0°</p>
 <button type="button" data-rover-top>위에서 보기</button><button type="button" data-rover-back>반대쪽 보기</button><button type="button" data-rover-orbit>회전 잠금</button>
 <section class="rover-edit"><h4>3D 구조 편집</h4><p>구조물은 기본으로 고정됩니다. 클릭해 선택한 뒤 이동 활성화를 켜고 드래그하세요. 상자나 원기둥을 추가할 수 있습니다. 이동은 바닥 방향이며 높이는 숫자로 조절합니다. 구조물을 드래그하면 주행이 정지합니다.</p>
 <div class="rover-add"><button type="button" data-add-shape="box">＋ 상자</button><button type="button" data-add-shape="cylinder">＋ 원기둥</button></div>
 <label>선택한 구조물<select data-object-select><option value="">구조물을 선택하세요</option></select></label>
 <div data-object-fields hidden><button type="button" data-object-move aria-pressed="false">이동 활성화</button><label>이름<input data-object-label maxlength="60"></label><div class="rover-object-grid"><label>X 위치(m)<input data-object-position="0" type="number" min="-2" max="2" step="0.005"></label><label>높이(m)<input data-object-position="1" type="number" min="-2" max="2" step="0.005"></label><label>Z 위치(m)<input data-object-position="2" type="number" min="-2" max="2" step="0.005"></label><label>가로(m)<input data-object-size="0" type="number" min="0.002" max="1" step="0.005"></label><label>높이 크기(m)<input data-object-size="1" type="number" min="0.002" max="1" step="0.005"></label><label>세로(m)<input data-object-size="2" type="number" min="0.002" max="1" step="0.005"></label></div><div class="rover-object-grid"><label>X 회전(°)<input data-object-rotation="0" type="number" min="-360" max="360" step="1"></label><label>Y 회전(°)<input data-object-rotation="1" type="number" min="-360" max="360" step="1"></label><label>Z 회전(°)<input data-object-rotation="2" type="number" min="-360" max="360" step="1"></label></div><label>색상<input data-object-color type="color"></label><button type="button" data-object-delete>선택한 구조물 삭제</button></div>
 <p class="micro">구조는 로봇에 붙어 함께 움직입니다. 편집은 시각 모델에만 적용되며 바퀴 간격·속도·전기 회로 또는 실물 설계를 바꾸지 않습니다. ${photoMode?'사진에서 생성한 바퀴도 개별 편집할 수 있습니다.':'기본 바퀴와 지지 바퀴는 고정되어 있습니다.'}</p><p data-structure-status role="status"></p></section>
 <details class="compact-details"><summary>모델 가정</summary><p>바퀴 간격 0.14 m, 출력 100%에서 바퀴 속도 0.20 m/s로 가정합니다. 실제 바퀴 속도·차체 치수·전원·미끄러짐·하중은 측정하지 않았습니다. 버튼 명령은 1초 후 정지합니다.</p></details>
 </div></div><p class="micro">${photoMode?'사진의 보이는 형태를 단순화한 추정 모델입니다. 표시 기준 길이 220 mm는 가정이며 제작 치수가 아닙니다.':'3D 모양과 크기는 보기 위한 예시입니다. 사진에서 관찰한 실물이나 제작 도면이 아닙니다.'}</p></section>`;
 const viewport=host.querySelector('[data-rover-viewport]'), stateNode=host.querySelector('[data-rover-state]'), locationNode=host.querySelector('[data-rover-location]');
 let renderer;
 try {renderer=new THREE.WebGLRenderer({antialias:true});}
 catch(e){viewport.textContent='이 브라우저에서 3D 그래픽을 사용할 수 없습니다. WebGL 지원을 확인하세요.';host.querySelectorAll('button').forEach(b=>b.disabled=true);return;}
 renderer.setPixelRatio(Math.min(window.devicePixelRatio||1,2));renderer.setClearColor(0xf3f7f4);viewport.appendChild(renderer.domElement);
 const scene=new THREE.Scene();
 const camera=new THREE.PerspectiveCamera(42,1,0.01,100);camera.position.set(.65,.58,.72);
 const controls=new OrbitControls(camera,renderer.domElement);controls.target.set(0,.04,0);controls.enableDamping=false;controls.mouseButtons={LEFT:THREE.MOUSE.PAN,MIDDLE:THREE.MOUSE.DOLLY,RIGHT:THREE.MOUSE.ROTATE};controls.minDistance=.25;controls.maxDistance=4;controls.maxPolarAngle=Math.PI-.02;controls.update();
 scene.add(new THREE.HemisphereLight(0xffffff,0x698276,2.1));
 const sun=new THREE.DirectionalLight(0xffffff,2.2);sun.position.set(2,4,3);scene.add(sun);
 const grid=new THREE.GridHelper(8,80,0x99b7a4,0xd8e5dd);grid.position.y=-.002;scene.add(grid);
 const robot=new THREE.Group();scene.add(robot);
 if(assemblyVisual){
  if(!validAssemblyVisual(assemblyVisual)){viewport.textContent='조립 그래픽의 형식을 확인하지 못했습니다. 회로 편집기에서 다시 실행하세요.';host.querySelectorAll('button').forEach(b=>b.disabled=true);renderer.dispose();return;}
  try{robot.add(new THREE.ObjectLoader().parse(assemblyVisual));}
  catch{controls.dispose();renderer.dispose();renderer.forceContextLoss();throw Error('조립 그래픽을 읽지 못했습니다. 회로 편집기에서 다시 실행하세요.');}
 }
 function material(color){return new THREE.MeshStandardMaterial({color,roughness:.68,metalness:.12});}
 const black=material(0x1a2425),silver=material(0xbac4bf),blue=material(0x286690);
 const fallbackStructure=()=>photoMode?{version:1,objects:[]}:defaultStructure();
 let structure=initialStructure===null?fallbackStructure():validStructure(initialStructure)?cloneStructure(initialStructure):fallbackStructure();
 if(photoMode&&!structureComplete)structure=completeMotionStructure(structure);
 const statusNode=host.querySelector('[data-structure-status]');
 if(initialStructure!==null&&!validStructure(initialStructure))statusNode.textContent='저장된 구조를 읽지 못해 기본 구조를 표시합니다. 편집 전 저장 상태를 확인하세요.';
 const selectable=new Map(),objectSelect=host.querySelector('[data-object-select]'),fields=host.querySelector('[data-object-fields]');let selectedId=null,moveTarget=null;
 const setSaveStatus=text=>{if(statusNode.isConnected)statusNode.textContent=String(text||'');};
 function notifyStructure(){if(typeof onStructureChange==='function')onStructureChange(cloneStructure(structure),setSaveStatus);else setSaveStatus('이 화면에서만 편집 중입니다.');}
 function addMesh(o){const ghost=!!assemblyVisual&&['housing','chassis','platform','frame'].includes(mechanicalRole(o));const mesh=mechanicalMesh(o,ghost);robot.add(mesh);selectable.set(o.id,mesh);}
 function rebuildSelect(){objectSelect.textContent='';const first=document.createElement('option');first.value='';first.textContent='구조물을 선택하세요';objectSelect.appendChild(first);for(const o of structure.objects){const option=document.createElement('option');option.value=o.id;option.textContent=o.label+(o.id.startsWith('design-')?' · 설계 보완':'');objectSelect.appendChild(option);}objectSelect.value=selectedId||'';}
 function showSelection(){const button=host.querySelector('[data-object-move]');button.textContent=moveTarget===selectedId&&selectedId?'이동 완료':'이동 활성화';button.setAttribute('aria-pressed',String(!!selectedId&&moveTarget===selectedId));host.querySelectorAll('[data-object-position]').forEach(field=>field.disabled=!selectedId||moveTarget!==selectedId);const o=structure.objects.find(x=>x.id===selectedId);fields.hidden=!o;for(const [id,mesh] of selectable)mesh.traverse(part=>{if(part.material)part.material.emissive.setHex(id===selectedId?0x26471d:0);});rebuildSelect();if(!o)return;host.querySelector('[data-object-label]').value=o.label;host.querySelector('[data-object-color]').value=o.color;for(const e of host.querySelectorAll('[data-object-position]'))e.value=o.position[Number(e.dataset.objectPosition)];for(const e of host.querySelectorAll('[data-object-size]'))e.value=o.size[Number(e.dataset.objectSize)];for(const e of host.querySelectorAll('[data-object-rotation]'))e.value=Number((o.rotation[Number(e.dataset.objectRotation)]*180/Math.PI).toFixed(6));}
 function selectObject(id){const next=selectable.has(id)?id:null;if(next!==selectedId)moveTarget=null;selectedId=next;showSelection();}
 for(const o of structure.objects)addMesh(o);showSelection();
 const wheelGroups={};
 for(const {side,z} of photoMode?[]:ROVER_WHEEL_LAYOUT){
  const wheel=new THREE.Group();wheel.position.set(-.055,.034,z);robot.add(wheel);wheelGroups[side]=wheel;
  const tyre=new THREE.Mesh(new THREE.CylinderGeometry(.034,.034,.018,24),black);tyre.rotation.x=Math.PI/2;wheel.add(tyre);
  const hub=new THREE.Mesh(new THREE.CylinderGeometry(.016,.016,.019,18),silver);hub.rotation.x=Math.PI/2;wheel.add(hub);
  const spoke=new THREE.Mesh(new THREE.BoxGeometry(.025,.003,.020),blue);wheel.add(spoke);
 }
 if(!photoMode){const caster=new THREE.Mesh(new THREE.SphereGeometry(.012,12,10),black);caster.position.set(.095,.012,0);robot.add(caster);}
 // The arrow is attached to the body, so the nose remains visible when the
 // camera or robot turns. It is only a visual orientation marker.
 const arrowColor=material(0xf2ba42);
 const arrowShaft=new THREE.Mesh(new THREE.BoxGeometry(.07,.003,.006),arrowColor);arrowShaft.position.set(.025,.154,0);robot.add(arrowShaft);
 const arrowHead=new THREE.Mesh(new THREE.ConeGeometry(.012,.035,3),arrowColor);arrowHead.rotation.z=-Math.PI/2;arrowHead.position.set(.077,.154,0);robot.add(arrowHead);
 if(assemblyVisual){const box=new THREE.Box3().setFromObject(robot),center=box.getCenter(new THREE.Vector3()),span=box.getSize(new THREE.Vector3()).length();controls.target.copy(center);camera.position.copy(center).add(new THREE.Vector3(.55,.75,1).normalize().multiplyScalar(Math.max(.35,span*1.65)));controls.update();}
 let obstacleMarker=null,obstacleMaterial=null;
 if(design?.simulation_kind==='obstacle_rover'){
  for(const z of [-.028,.028]){const sensor=new THREE.Mesh(new THREE.CylinderGeometry(.012,.012,.016,16),silver);sensor.rotation.z=Math.PI/2;sensor.position.set(.125,.11,z);robot.add(sensor);}
  obstacleMaterial=material(0xe4925b);obstacleMarker=new THREE.Mesh(new THREE.BoxGeometry(.025,.10,.20),obstacleMaterial);obstacleMarker.position.y=.05;scene.add(obstacleMarker);
 }
 const pathMaterial=new THREE.LineBasicMaterial({color:0x388465});let pathGeometry=new THREE.BufferGeometry();let path=new THREE.Line(pathGeometry,pathMaterial);scene.add(path);
 let pose={x:0,y:0,heading:0},points=[new THREE.Vector3(0,.002,0)],command='stop',left=0,right=0,start=0,last=0,locked=false,disposed=false,frame=0,drag=null;
 function fit(){const w=Math.max(280,viewport.clientWidth||500),h=Math.max(280,viewport.clientHeight||330);renderer.setSize(w,h,false);camera.aspect=w/h;camera.updateProjectionMatrix();}
 const observer=new ResizeObserver(fit);observer.observe(viewport);fit();
 function setCommand(next){command=next;const isAuto=next.startsWith('auto:'),isManual=next.startsWith('manual:'),name=isAuto?next.slice(5):isManual?next.slice(7):next;[left,right]=isAuto?(name==='left'?[-.5,.5]:MANUAL_COMMANDS[name]):isManual?MANUAL_COMMANDS[name]:ROVER_COMMANDS[name];start=performance.now();last=start;stateNode.textContent=`${isManual||isAuto?manualLabel(name):NAMES[name]} · 왼쪽 ${Math.round(left*100)}% / 오른쪽 ${Math.round(right*100)}%${name==='stop'?'':(isManual||isAuto)?' · 조작 중':' · 1초 후 정지'}`;}
 const actionButtons=[...host.querySelectorAll('[data-rover-action]')],motionStatus=host.querySelector('[data-motion-status]');
 const motionGuard=createMotionGuard({validateMotion,onCommand:setCommand,onState:(busy,message)=>{
  actionButtons.forEach(btn=>{btn.disabled=busy&&btn.dataset.roverAction!=='stop';});
  motionStatus.textContent=message;
 }});
 const obstacleController=createObstacleController();let obstacleRunning=false,obstacleCommand=null,obstacleEpoch=0,obstacleTimer=null;
 const autoState=host.querySelector('[data-obstacle-state]');
 function stopObstacle(){obstacleEpoch++;clearTimeout(obstacleTimer);obstacleTimer=null;obstacleRunning=false;obstacleCommand=null;obstacleController.reset();if(autoState)autoState.textContent='정지';}
 const manual=createManualController({host,validateMotion,enabled:()=>!drag,stop:()=>{stopObstacle();void motionGuard.request('stop');},run:name=>{stopObstacle();setCommand('manual:'+name);},onStatus:message=>{motionStatus.textContent=message;}});
 if(autoState){
  const distance=host.querySelector('[data-obstacle-distance]');
  distance.oninput=()=>{host.querySelector('[data-obstacle-value]').textContent=distance.value;};
  host.querySelector('[data-obstacle-start]').onclick=async()=>{
   manual.releaseAll();stopObstacle();setCommand('stop');const ticket=obstacleEpoch;
   async function check(){
    try{const result=typeof validateMotion==='function'?await validateMotion('forward'):true;
     if(ticket!==obstacleEpoch||disposed)return;
     if(result!==true&&result?.allowed!==true){stopObstacle();setCommand('stop');autoState.textContent=result?.message||'회로 연결을 확인하세요.';return;}
     if(!obstacleRunning){obstacleController.reset();obstacleRunning=true;autoState.textContent='자동 주행 중';}
     obstacleTimer=setTimeout(check,1000);
    }catch(e){if(ticket!==obstacleEpoch||disposed)return;stopObstacle();setCommand('stop');autoState.textContent='회로 확인 실패: '+(e?.message||'다시 시도하세요.');}
   }
   await check();
  };
  host.querySelector('[data-obstacle-stop]').onclick=()=>{stopObstacle();setCommand('stop');};
 }

 actionButtons.forEach(btn=>btn.addEventListener('click',()=>{stopObstacle();manual.releaseAll();if(drag&&btn.dataset.roverAction!=='stop')return;void motionGuard.request(btn.dataset.roverAction);}));
 host.querySelector('[data-rover-reset]').onclick=()=>{stopObstacle();setCommand('stop');manual.releaseAll();pose={x:0,y:0,heading:0};points=[new THREE.Vector3(0,.002,0)];path.geometry.dispose();path.geometry=new THREE.BufferGeometry().setFromPoints(points);};
 host.querySelector('[data-rover-top]').onclick=()=>{const target=controls.target;camera.position.set(target.x,target.y+1.3,target.z+.001);controls.update();};
 host.querySelector('[data-rover-back]').onclick=()=>{const t=controls.target;camera.position.set(t.x-(camera.position.x-t.x),camera.position.y,t.z-(camera.position.z-t.z));controls.update();};
 host.querySelector('[data-rover-orbit]').onclick=e=>{locked=!locked;controls.enabled=!locked;e.currentTarget.textContent=locked?'회전 잠금 해제':'회전 잠금';};
 objectSelect.onchange=()=>selectObject(objectSelect.value);
 host.querySelector('[data-object-move]').onclick=()=>{moveTarget=moveTarget===selectedId?null:selectedId;showSelection();};
 host.querySelectorAll('[data-add-shape]').forEach(button=>button.onclick=()=>{
  if(structure.objects.length>=MAX_OBJECTS){setSaveStatus(`구조물은 최대 ${MAX_OBJECTS}개입니다.`);return;}
  let id;do{id='object_'+Math.random().toString(36).slice(2,12);}while(selectable.has(id));
  const shape=button.dataset.addShape;const o={id,shape,label:shape==='box'?'새 상자':'새 원기둥',position:[0,.18,0],size:[.05,.05,.05],rotation:[0,0,0],color:shape==='box'?'#7aa8bf':'#c5a46f'};
  structure.objects.push(o);addMesh(o);selectObject(id);notifyStructure();
 });
 host.querySelector('[data-object-delete]').onclick=()=>{const mesh=selectable.get(selectedId);if(!mesh)return;robot.remove(mesh);mesh.traverse(part=>{part.geometry?.dispose();part.material?.dispose();});selectable.delete(selectedId);structure.objects=structure.objects.filter(o=>o.id!==selectedId);selectedId=null;moveTarget=null;showSelection();notifyStructure();};
 host.querySelector('[data-object-label]').onchange=e=>{const o=structure.objects.find(x=>x.id===selectedId),value=e.target.value.trim();if(!o)return;if(!value||value.length>60){showSelection();setSaveStatus('이름을 1~60자로 입력하세요.');return;}o.label=value;showSelection();notifyStructure();};
 host.querySelector('[data-object-color]').onchange=e=>{const o=structure.objects.find(x=>x.id===selectedId);if(!o)return;o.color=e.target.value;selectable.get(o.id).traverse(part=>{if(part.material&&!part.userData.baseColor)part.material.color.set(o.color);});notifyStructure();};
 for(const field of host.querySelectorAll('[data-object-position],[data-object-size]'))field.onchange=e=>{const o=structure.objects.find(x=>x.id===selectedId),f=e.target;if(!o)return;const property=f.hasAttribute('data-object-position')?'position':'size';if(property==='position'&&moveTarget!==selectedId){showSelection();return;}const idx=Number(property==='position'?f.dataset.objectPosition:f.dataset.objectSize),value=Number(f.value),min=property==='position'?-2:.002,max=property==='position'?2:1;if(f.value===''||!Number.isFinite(value)||value<min||value>max){showSelection();setSaveStatus(`값은 ${min}~${max} m 범위여야 합니다.`);return;}o[property][idx]=value;const mesh=selectable.get(o.id);mesh[property==='position'?'position':'scale'].set(...o[property]);notifyStructure();};
 for(const field of host.querySelectorAll('[data-object-rotation]'))field.onchange=e=>{const o=structure.objects.find(x=>x.id===selectedId),f=e.target;if(!o)return;const degrees=Number(f.value),idx=Number(f.dataset.objectRotation);if(f.value===''||!Number.isFinite(degrees)||degrees<-360||degrees>360){showSelection();setSaveStatus('회전은 -360~360° 범위여야 합니다.');return;}o.rotation[idx]=degrees*Math.PI/180;selectable.get(o.id).rotation.set(...o.rotation);notifyStructure();};
 const raycaster=new THREE.Raycaster(),pointer=new THREE.Vector2(),plane=new THREE.Plane(),point=new THREE.Vector3(),offset=new THREE.Vector3();
 function ray(event){const rect=renderer.domElement.getBoundingClientRect();pointer.set((event.clientX-rect.left)/rect.width*2-1,-(event.clientY-rect.top)/rect.height*2+1);raycaster.setFromCamera(pointer,camera);}
 function pointerDown(event){if(event.button!==0||!selectable.size)return;ray(event);const hit=raycaster.intersectObjects([...selectable.values()],true)[0];if(!hit){selectObject(null);return;}
  const id=hit.object.userData.structureId,canMove=canDragComponent({selected:selectedId===id,armed:moveTarget===id,simulating:false,wireMode:false});selectObject(id);if(!canMove)return;
  event.preventDefault();manual.releaseAll();robot.updateMatrixWorld(true);const world=selectable.get(selectedId).getWorldPosition(new THREE.Vector3());plane.setFromNormalAndCoplanarPoint(new THREE.Vector3(0,1,0),world);if(!raycaster.ray.intersectPlane(plane,point))return;offset.copy(world).sub(point);drag={id:selectedId,pointerId:event.pointerId,changed:false};controls.enabled=false;renderer.domElement.setPointerCapture(event.pointerId);
 }
 function pointerMove(event){if(!drag||event.pointerId!==drag.pointerId)return;ray(event);if(!raycaster.ray.intersectPlane(plane,point))return;const local=robot.worldToLocal(point.add(offset).clone());const o=structure.objects.find(x=>x.id===drag.id);if(!o)return;o.position[0]=Math.max(-2,Math.min(2,local.x));o.position[2]=Math.max(-2,Math.min(2,local.z));selectable.get(o.id).position.set(...o.position);drag.changed=true;showSelection();}
 function pointerEnd(event){if(!drag||event.pointerId!==drag.pointerId)return;const changed=drag.changed;drag=null;controls.enabled=!locked;if(renderer.domElement.hasPointerCapture(event.pointerId))renderer.domElement.releasePointerCapture(event.pointerId);if(changed)notifyStructure();}
 function finishMovement(event){if(event.key!=='Escape')return;if(drag)pointerEnd({pointerId:drag.pointerId});moveTarget=null;showSelection();}
 window.addEventListener('keydown',finishMovement);
 renderer.domElement.addEventListener('pointerdown',pointerDown);renderer.domElement.addEventListener('pointermove',pointerMove);renderer.domElement.addEventListener('pointerup',pointerEnd);renderer.domElement.addEventListener('pointercancel',pointerEnd);
 function draw(ts){
  if(disposed)return;
  if(!host.isConnected){dispose();return;}
  if(obstacleRunning){
   const distance=host.querySelector('[data-obstacle-fail]').checked?null:Number(host.querySelector('[data-obstacle-distance]').value);
   const next=obstacleController.step(distance,ts);
   if(next!==obstacleCommand){obstacleCommand=next;setCommand(next==='stop'?'stop':'auto:'+next);autoState.textContent=next==='stop'?'센서 응답 없음 · 정지':({forward:'전진 중',backward:'장애물 감지 · 후진 중',left:'장애물 회피 · 좌회전 중'})[next];}
  }
  if(command!=='stop'){
   const end=(command.startsWith('manual:')||command.startsWith('auto:'))?ts:Math.min(ts,start+ROVER_ASSUMPTIONS.durationSeconds*1000),dt=Math.max(0,Math.min(2,(end-last)/1000));last=end;
   if(dt>0){
    pose=stepRover(pose,left,right,dt);if(wheelGroups.left)wheelGroups.left.rotation.z-=left*ROVER_ASSUMPTIONS.maxWheelSpeedMps*dt/.034;if(wheelGroups.right)wheelGroups.right.rotation.z-=right*ROVER_ASSUMPTIONS.maxWheelSpeedMps*dt/.034;
    if(photoMode)for(const o of structure.objects.filter(o=>mechanicalRole(o)==='wheel')){const wheel=selectable.get(o.id);if(wheel)wheel.rotateY(-(o.position[2]<0?left:right)*ROVER_ASSUMPTIONS.maxWheelSpeedMps*dt/Math.max(.005,o.size[0]/2));}
    const world=roverPoseToWorld(pose);points.push(new THREE.Vector3(world.x,.002,world.z));if(points.length>2000)points.shift();path.geometry.dispose();path.geometry=new THREE.BufferGeometry().setFromPoints(points);
   }
   if(!command.startsWith('manual:')&&!command.startsWith('auto:')&&ts>=start+ROVER_ASSUMPTIONS.durationSeconds*1000)setCommand('stop');
  }
  const world=roverPoseToWorld(pose);robot.position.set(world.x,0,world.z);robot.rotation.y=world.rotationY;
  if(obstacleMarker){const distance=Number(host.querySelector('[data-obstacle-distance]').value)/100;obstacleMarker.visible=!host.querySelector('[data-obstacle-fail]').checked;obstacleMarker.position.set(world.x+(distance+.125)*Math.cos(pose.heading),.05,world.z-(distance+.125)*Math.sin(pose.heading));obstacleMarker.rotation.y=pose.heading;}
  locationNode.textContent=`위치 X ${pose.x.toFixed(2)} m · Y ${pose.y.toFixed(2)} m · 방향 ${(pose.heading*180/Math.PI).toFixed(0)}°`;
  controls.update();renderer.render(scene,camera);frame=requestAnimationFrame(draw);
 }
 function dispose(){if(disposed)return;window.removeEventListener('keydown',finishMovement);stopObstacle();manual.dispose();disposed=true;motionGuard.dispose();cancelAnimationFrame(frame);observer.disconnect();renderer.domElement.removeEventListener('pointerdown',pointerDown);renderer.domElement.removeEventListener('pointermove',pointerMove);renderer.domElement.removeEventListener('pointerup',pointerEnd);renderer.domElement.removeEventListener('pointercancel',pointerEnd);controls.dispose();const materials=new Set(),textures=new Set();scene.traverse(obj=>{if(obj.geometry)obj.geometry.dispose();for(const m of Array.isArray(obj.material)?obj.material:obj.material?[obj.material]:[])materials.add(m);});for(const m of materials){for(const value of Object.values(m))if(value?.isTexture)textures.add(value);m.dispose();}textures.forEach(t=>t.dispose());for(const m of [black,silver,blue,arrowColor,pathMaterial,obstacleMaterial])if(m&&!materials.has(m))m.dispose();renderer.dispose();renderer.forceContextLoss();}
 host.__roverDispose=dispose;frame=requestAnimationFrame(draw);
 return dispose;
}
