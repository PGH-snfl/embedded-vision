// Coordinates and sizes are visualization-only metres, local to the rover.
export const MAX_OBJECTS=50;
const defaults=[
 ['chassis_lower','하부 차체',[0,.062,0],[.22,.012,.12],'#c84943'],
 ['chassis_upper','상부 차체',[-.015,.116,0],[.17,.008,.10],'#c84943'],
 ['board','보드',[-.025,.076,0],[.075,.009,.055],'#17724c'],
 ['driver','구동 보드',[-.025,.096,0],[.055,.028,.045],'#286690'],
 ['battery','배터리',[.052,.131,0],[.08,.023,.045],'#1a2425'],
 ['support_1','지지대 1',[-.077,.09,-.045],[.006,.046,.006],'#bac4bf'],
 ['support_2','지지대 2',[-.077,.09,.045],[.006,.046,.006],'#bac4bf'],
 ['support_3','지지대 3',[.065,.09,-.045],[.006,.046,.006],'#bac4bf'],
 ['support_4','지지대 4',[.065,.09,.045],[.006,.046,.006],'#bac4bf'],
];
export function defaultStructure(){return {version:1,objects:defaults.map(([id,label,position,size,color])=>({id,shape:'box',label,position:[...position],size:[...size],rotation:[0,0,0],color}))};}
export function validStructure(value){
 if(!value||typeof value!=='object'||Array.isArray(value)||value.version!==1||!Array.isArray(value.objects)||value.objects.length>MAX_OBJECTS||Object.keys(value).some(k=>!['version','objects','completion_version'].includes(k))||(value.completion_version!=null&&value.completion_version!=='whole-structure-v1'))return false;
 const seen=new Set();
 for(const o of value.objects){
  if(!o||typeof o!=='object'||Array.isArray(o)||Object.keys(o).some(k=>!['id','shape','label','position','size','rotation','color','photoGeometry'].includes(k)))return false;
  if(typeof o.id!=='string'||!/^[A-Za-z][A-Za-z0-9_-]{0,63}$/.test(o.id)||seen.has(o.id))return false;
  seen.add(o.id);
  if(!['box','cylinder','sphere'].includes(o.shape)||typeof o.label!=='string'||!o.label.trim()||o.label.length>60||typeof o.color!=='string'||!/^#[0-9a-fA-F]{6}$/.test(o.color))return false;
  if(!Array.isArray(o.position)||o.position.length!==3||!o.position.every(n=>typeof n==='number'&&Number.isFinite(n)&&n>=-2&&n<=2))return false;
  if(!Array.isArray(o.size)||o.size.length!==3||!o.size.every(n=>typeof n==='number'&&Number.isFinite(n)&&n>=.002&&n<=1))return false;
  if(o.rotation!==undefined&&(!Array.isArray(o.rotation)||o.rotation.length!==3||!o.rotation.every(n=>typeof n==='number'&&Number.isFinite(n)&&n>=-2*Math.PI&&n<=2*Math.PI)))return false;
 }
 return true;
}
export function cloneStructure(value){return {version:1,...(value.completion_version?{completion_version:value.completion_version}:{}),objects:value.objects.map(o=>({...o,position:[...o.position],size:[...o.size],rotation:o.rotation?[...o.rotation]:[0,0,0]}))};}
