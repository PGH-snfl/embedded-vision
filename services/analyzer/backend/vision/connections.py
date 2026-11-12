"""Infer only isolated color strokes with two unambiguous, manually anchored terminals."""
import uuid
import cv2
import numpy as np
from PIL import Image
from ..circuit.schema import Evidence,Link,Point,Claim,Status

def thin(region):
    image=np.pad(np.uint8(region>0),1)
    for _ in range(100):
        changed=False
        for phase in (0,1):
            p=[image[:-2,1:-1],image[:-2,2:],image[1:-1,2:],image[2:,2:],image[2:,1:-1],image[2:,:-2],image[1:-1,:-2],image[:-2,:-2]]
            count=sum(p);transitions=sum((a==0)&(b==1) for a,b in zip(p,p[1:]+p[:1]))
            a,b=(p[0]*p[2]*p[4],p[2]*p[4]*p[6]) if phase==0 else (p[0]*p[2]*p[6],p[0]*p[4]*p[6])
            remove=(image[1:-1,1:-1]==1)&(count>=2)&(count<=6)&(transitions==1)&(a==0)&(b==0)
            if remove.any():image[1:-1,1:-1][remove]=0;changed=True
        if not changed:break
    return image[1:-1,1:-1]

def infer_anchored_wires(graph,path,asset_id='image'):
    image=Image.open(path).convert('RGB');image.thumbnail((1200,1200))
    hsv=cv2.cvtColor(np.array(image),cv2.COLOR_RGB2HSV);h,w=hsv.shape[:2]
    anchors=[(t,c) for c in graph.components if c.asset_id==asset_id for t in c.terminals if t.image_position]
    existing={frozenset([link.from_terminal,link.to_terminal]) for link in graph.links}
    added=[];ambiguous=0
    for color,bands in {'red':[(0,10),(170,179)],'green':[(38,86)],'blue':[(90,133)],'yellow':[(18,36)]}.items():
        mask=np.zeros((h,w),np.uint8)
        for lo,hi in bands:mask|=cv2.inRange(hsv,np.array([lo,110,70]),np.array([hi,255,255]))
        count,regions,stats,_=cv2.connectedComponentsWithStats(mask)
        for index in sorted(range(1,count),key=lambda i:stats[i,cv2.CC_STAT_AREA],reverse=True)[:30]:
            if stats[index,cv2.CC_STAT_AREA]<30:continue
            bx,by,bw,bh,area=stats[index]
            if area/(bw*bh)>.6 and max(bw,bh)/max(1,min(bw,bh))<3:continue
            binary=thin(regions[by:by+bh,bx:bx+bw]==index);neighbors=cv2.filter2D(binary,-1,np.ones((3,3),np.uint8),borderType=cv2.BORDER_CONSTANT)-binary
            endpoints=np.argwhere((binary==1)&(neighbors==1))
            if len(endpoints)!=2:ambiguous+=1;continue
            endpoints=endpoints+np.array([by,bx])
            if np.linalg.norm(endpoints[0]-endpoints[1])<min(h,w)*.05:continue
            candidates=[]
            for y,x in endpoints:
                near=[t for t,c in anchors if ((t.image_position.x-x/w)*w)**2+((t.image_position.y-y/h)*h)**2<(min(h,w)*.035)**2]
                candidates.append(near)
            if any(len(items)!=1 for items in candidates):ambiguous+=1;continue
            a,b=candidates[0][0],candidates[1][0]
            if a.id==b.id or frozenset([a.id,b.id]) in existing:continue
            eid='wire_geometry_'+uuid.uuid4().hex[:8]
            points=[Point(x=float(x)/w,y=float(y)/h) for y,x in endpoints]
            graph.evidence.append(Evidence(id=eid,asset_id=asset_id,method='geometry',points=points,text=f'{color} 독립 색상 선의 두 끝점과 사용자가 지정한 핀 위치가 일치합니다. 색만으로 실제 도통은 확정하지 않습니다.'))
            link=Link(id='AUTO_'+uuid.uuid4().hex[:6],from_terminal=a.id,to_terminal=b.id,path=points,asset_id=asset_id,
                connection=Claim(value='connected',status=Status.INFERRED,evidence_ids=[eid],reason='분리된 색상 윤곽 + 사용자 핀 위치 기반 연결 후보. 가림/끝점을 추가 확인하세요.'))
            graph.links.append(link);existing.add(frozenset([a.id,b.id]));added.append(link.id)
    return {'proposed_links':added,'ambiguous_strokes':ambiguous}
