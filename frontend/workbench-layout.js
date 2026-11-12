// Upgrade freshly exported generator layouts; existing editor drafts are never rewritten.
export function fullBreadboardProject(input){
 if(input.embeddedVision?.assembly?.layout_version!=='mini-breadboard-v1')return input;
 const board=input.components?.find(c=>c.id==='BB1'&&c.metadataId==='breadboard-mini');
 if(!board)return input;
 const data=structuredClone(input),bb=data.components.find(c=>c.id==='BB1');
 const rows={a:48,b:57.6,c:67.2,d:76.8,e:86.4,f:115.2,g:124.8,h:134.4,i:144,j:153.6};
 const seated=new Set(data.wires.filter(w=>w.bb).flatMap(w=>[w.start,w.end]).filter(e=>e.componentId!=='BB1').map(e=>e.componentId));
 const dx=18*9.6-1.2,dy=21.52;
 for(const w of data.wires)for(const e of [w.start,w.end]){
  if(e.componentId==='BB1'){
   const m=/^(\d+)([tb])\.([a-j])$/.exec(e.pinName);if(!m||+m[1]>17||+m[1]<1)return input;
   const col=+m[1]+18;e.pinName=col+m[2]+'.'+m[3];e.x=bb.x+6+14.56+(col-1)*9.6;e.y=bb.y+6+rows[m[3]];
  }else if(seated.has(e.componentId)){e.x+=dx;e.y+=dy;}
 }
 for(const c of data.components)if(seated.has(c.id)){c.x+=dx;c.y+=dy;}
 bb.metadataId='breadboard';
 const assembly=data.embeddedVision.assembly;assembly.layout_version='full-breadboard-v2';assembly.breadboard='830-point full-size / 63 columns / 4 power rails';
 assembly.steps=assembly.steps.map(step=>({...step,from:step.from.replace(/BB1\.(\d+)([tb])\./,(_,n,b)=>'BB1.'+(+n+18)+b+'.'),to:step.to.replace(/BB1\.(\d+)([tb])\./,(_,n,b)=>'BB1.'+(+n+18)+b+'.')}));
 assembly.note='같은 열의 a~e 다섯 구멍은 연결됩니다. f~j는 별도 그룹입니다. 가운데 홈과 빨강·파랑 전원 레일은 자동으로 연결되지 않습니다.';
 return data;
}
