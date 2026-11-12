import * as THREE from '../../../editor/vendor/velxio/frontend/node_modules/three/build/three.module.js';
import {mechanicalDetails} from '../../../editor/vendor/velxio/frontend/src/components/circuitiny/mechanicalDetails.ts';
import {photoGeometryMesh} from '../../../editor/vendor/velxio/frontend/src/components/circuitiny/photoGeometry.ts';
import {completeMechanicalScene,COMPLETION_VERSION} from '../../../editor/vendor/velxio/frontend/src/components/circuitiny/mechanicalCompletion.ts';
export function mechanicalRole(o){return o.id.startsWith('photo-')?o.id.split('-')[1]:o.id.startsWith('design-wheel-')?'wheel':o.id.startsWith('design-support-')||o.id==='design-caster-stem'?'support':o.id.startsWith('design-frame-')?'frame':o.id.startsWith('design-mount-')?'mount':o.id.startsWith('design-caster-')?'caster':'other';}
export function completeMotionStructure(structure){
 if(structure.objects.some(o=>!!o.photoGeometry))return structure;
 if(structure.completion_version===COMPLETION_VERSION)return structure;
 const nodes=structure.objects.map(o=>({...o,role:mechanicalRole(o),position:o.position.map(n=>n*1000),size:o.size.map(n=>n*1000),designed:o.id.startsWith('design-')}));
 const additions=completeMechanicalScene(nodes,'two_wheel_rover').map(o=>({id:o.id,label:o.label,shape:o.shape,position:o.position.map(n=>n/1000),size:o.size.map(n=>n/1000),rotation:o.rotation,color:o.color}));
 return {...structure,completion_version:COMPLETION_VERSION,objects:[...structure.objects,...additions]};
}
export function mechanicalMesh(o,ghost=false){
 if(o.photoGeometry){const mesh=photoGeometryMesh(o.photoGeometry,o.color,ghost);mesh.scale.set(...o.size);mesh.position.set(...o.position);mesh.rotation.set(...o.rotation);mesh.traverse(p=>{p.userData.structureId=o.id;if(p.material?.color)p.userData.baseColor='#'+p.material.color.getHexString();});return mesh;}
 const group=new THREE.Group();
 const pieces=mechanicalDetails(o.id,mechanicalRole(o))||[{shape:o.shape,size:[1,1,1],position:[0,0,0]}];
 for(const p of pieces){
  const geometry=p.shape==='sphere'?new THREE.SphereGeometry(.5,28,20):p.shape==='torus'?new THREE.TorusGeometry(p.radius,p.tube,12,56):p.shape==='cylinder'?new THREE.CylinderGeometry(p.radius??.5,p.radius??.5,p.size?.[1]??1,p.segments??40):new THREE.BoxGeometry(...(p.size||[1,1,1]));
  const material=new THREE.MeshStandardMaterial({color:p.color||o.color,roughness:.65,metalness:p.metal??.12,transparent:ghost,opacity:ghost?.18:1,depthWrite:!ghost});
  const mesh=new THREE.Mesh(geometry,material);mesh.userData.structureId=o.id;mesh.userData.baseColor=p.color||null;
  mesh.position.set(...p.position);if(p.rotation)mesh.rotation.set(...p.rotation);if(p.scale)mesh.scale.set(...p.scale);group.add(mesh);
 }
 group.scale.set(...o.size);group.position.set(...o.position);group.rotation.set(...o.rotation);group.userData.structureId=o.id;return group;
}
