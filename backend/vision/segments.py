"""Visible color segment geometry. Stroke ends are NOT electrical terminals."""
import hashlib
import cv2
import numpy as np
from PIL import Image
from .connections import thin
from ..circuit.schema import Evidence,Point,WireCandidate


def ordered_stroke(mask):
    nodes=set(map(tuple,np.argwhere(mask>0)))
    if len(nodes)<10 or len(nodes)>8000:return None,'선 길이가 너무 짧거나 영역이 복잡합니다.'
    def neighbors(p):
        y,x=p;out=[]
        for dy,dx in [(-1,0),(1,0),(0,-1),(0,1),(-1,-1),(-1,1),(1,-1),(1,1)]:
            q=(y+dy,x+dx)
            if q not in nodes:continue
            if dy and dx and ((y+dy,x) in nodes or (y,x+dx) in nodes):continue
            out.append(q)
        return out
    adjacency={p:neighbors(p) for p in nodes}
    ends=[p for p,ns in adjacency.items() if len(ns)==1]
    if len(ends)!=2 or any(len(ns)>2 for ns in adjacency.values()):
        return None,'분기·교차·닫힌 윤곽 또는 여러 끝점이 있어 한 전선으로 연결하지 않습니다.'
    path=[];last=None;current=min(ends)
    while current is not None:
        path.append(current)
        following=[p for p in adjacency[current] if p!=last]
        last,current=current,following[0] if following else None
        if len(path)>len(nodes):return None,'순환 경로는 자동 연결하지 않습니다.'
    if len(path)!=len(nodes):return None,'분리된 영역은 자동 연결하지 않습니다.'
    return np.array(path,dtype=np.int32),''


def detect_segments(image:Image.Image,asset_id:str):
    work=image.copy().convert('RGB');work.thumbnail((1000,1000))
    hsv=cv2.cvtColor(np.array(work),cv2.COLOR_RGB2HSV);h,w=hsv.shape[:2]
    evidence=[];candidates=[];ambiguous=0
    bands={'red':[(0,10),(170,179)],'orange':[(11,24)],'yellow':[(25,37)],
           'green':[(38,86)],'blue':[(90,133)]}
    for color,ranges in bands.items():
        mask=np.zeros((h,w),np.uint8)
        for lo,hi in ranges:mask|=cv2.inRange(hsv,np.array([lo,110,70]),np.array([hi,255,255]))
        count,regions,stats,_=cv2.connectedComponentsWithStats(mask)
        for index in sorted(range(1,count),key=lambda i:stats[i,cv2.CC_STAT_AREA],reverse=True)[:16]:
            x,y,bw,bh,area=map(int,stats[index])
            if area<45 or max(bw,bh)<min(w,h)*.08:continue
            if area/(bw*bh)>.45 and max(bw,bh)/max(1,min(bw,bh))<3:continue
            skeleton=thin(regions[y:y+bh,x:x+bw]==index)
            path,reason=ordered_stroke(skeleton)
            points=[];ends=[]
            if path is None:ambiguous+=1
            else:
                path+=np.array([y,x]);ends=[Point(x=float(p[1])/w,y=float(p[0])/h) for p in (path[0],path[-1])]
                if np.linalg.norm(path[0]-path[-1])<min(w,h)*.06:continue
                simplified=cv2.approxPolyDP(path[:,::-1].reshape(-1,1,2),1.5,False).reshape(-1,2)
                if len(simplified)>200:ambiguous+=1;path=None;ends=[];reason='경로가 너무 복잡합니다.'
                else:points=[Point(x=float(px)/w,y=float(py)/h) for px,py in simplified]
            token=hashlib.sha256(f'{asset_id}:{color}:{x},{y},{bw},{bh}'.encode()).hexdigest()[:14]
            eid='segment_ev_'+token;cid='segment_'+token
            bbox=[Point(x=x/w,y=y/h),Point(x=min(1,(x+bw)/w),y=min(1,(y+bh)/h))]
            reason=reason or '색상 선 조각의 끝입니다. 가림으로 끊긴 지점이나 인쇄선일 수 있어 실제 핀 끝점 확인이 필요합니다.'
            evidence.append(Evidence(id=eid,asset_id=asset_id,method='geometry',points=points or bbox,
                text=f'OpenCV HSV + skeleton v2, {color}. {reason} 전기적 도통 미검증.'))
            candidates.append(WireCandidate(id=cid,color=color,bbox=bbox,evidence_id=eid,path=points,
                endpoints=ends,geometry='segment' if path is not None else 'ambiguous',reason=reason))
    # Keep a bounded, deterministic set; never turn ambiguity into electrical nets.
    selected=sorted(candidates,key=lambda c:(c.geometry!='segment',c.id))[:40]
    ids={c.evidence_id for c in selected}
    return [e for e in evidence if e.id in ids],selected,{'ambiguous_regions':ambiguous,
        'visible_segments':sum(c.geometry=='segment' for c in selected),'automatic_connections':0}
