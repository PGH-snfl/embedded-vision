/** Only accept bounded, self-contained procedural scene data from our editor. */
export function validAssemblyVisual(value){
 if(!value||value.metadata?.type!=='Object'||value.object?.type!=='Group'||JSON.stringify(value).length>12000000)return false;
 if((value.geometries?.length||0)>3000||(value.materials?.length||0)>2000||(value.images?.length||0)>30)return false;
 if((value.images||[]).some(image=>typeof image.url!=='string'||!/^data:image\/(png|jpeg|webp);base64,/.test(image.url)))return false;
 if((value.materials||[]).some(m=>!['MeshStandardMaterial','MeshBasicMaterial','MeshPhongMaterial','LineBasicMaterial'].includes(m.type)))return false;
 function node(o,depth=0){return depth<32&&['Group','Mesh','Line','LineSegments','Object3D'].includes(o.type)&&(!o.children||o.children.every(c=>node(c,depth+1)));}
 return node(value.object);
}
