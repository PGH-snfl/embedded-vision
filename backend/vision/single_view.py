"""Single-image gap hypotheses. Heuristic ranks are not probabilities or truth."""
import hashlib
import math
import cv2
import numpy as np
from PIL import Image
from fastapi import HTTPException
from ..circuit.schema import StrictModel, Point, Evidence, WireHypothesis, Link, Claim
from .connections import thin

BANDS={'red':[(0,10),(170,179)],'orange':[(11,24)],'yellow':[(25,37)],
       'green':[(38,86)],'blue':[(90,133)]}


def chains(mask):
    """Split at junctions; never choose an arbitrary branch through a crossing."""
    nodes=set(map(tuple,np.argwhere(thin(mask)>0)))
    def neighbors(p):
        y,x=p;result=[]
        for dy,dx in [(-1,0),(1,0),(0,-1),(0,1),(-1,-1),(-1,1),(1,-1),(1,1)]:
            q=y+dy,x+dx
            if q in nodes and not (dy and dx and ((y+dy,x) in nodes or (y,x+dx) in nodes)):
                result.append(q)
        return sorted(result)
    adj={p:neighbors(p) for p in nodes};visited=set();result=[]
    for start in sorted(p for p in nodes if len(adj[p])!=2):
        for following in adj[start]:
            if (start,following) in visited:continue
            path=[start];previous,current=start,following
            while True:
                visited.add((previous,current));visited.add((current,previous));path.append(current)
                if len(adj[current])!=2:break
                following=next(p for p in adj[current] if p!=previous)
                previous,current=current,following
            if len(path)>=18:result.append(np.array(path,dtype=np.int32))
    return result


def fragments(image):
    image=image.convert('RGB');image.thumbnail((900,900))
    hsv=cv2.cvtColor(np.asarray(image),cv2.COLOR_RGB2HSV);h,w=hsv.shape[:2];result=[]
    for color,bands in BANDS.items():
        mask=np.zeros((h,w),np.uint8)
        for lo,hi in bands:mask|=cv2.inRange(hsv,np.array([lo,110,70]),np.array([hi,255,255]))
        n,labels,stats,_=cv2.connectedComponentsWithStats(mask)
        for region in sorted(range(1,n),key=lambda i:stats[i,cv2.CC_STAT_AREA],reverse=True)[:30]:
            x,y,bw,bh,area=map(int,stats[region])
            if area<40 or max(bw,bh)<25:continue
            crop=np.uint8(labels[y:y+bh,x:x+bw]==region)
            widths=cv2.distanceTransform(np.pad(crop,1),cv2.DIST_L2,3)[1:-1,1:-1]*2
            for path in chains(crop):
                width=float(np.median(widths[path[:,0],path[:,1]]))
                if width<1.5 or width>22:continue
                path=path+np.array([y,x]);xy=path[:,::-1].astype(float)
                if np.linalg.norm(xy[0]-xy[-1])<18:continue
                result.append(dict(color=color,width=width,xy=xy))
    result=sorted(result,key=lambda f:(-len(f['xy']),f['color'],tuple(f['xy'][0])))[:100]
    for i,f in enumerate(result):f['id']=str(i)
    return result,w,h


def propose(parts,w,h):
    """Both outward tangents must face the gap. Retain competing endpoints."""
    output=[];maximum=min(w,h)*.24
    for i,a in enumerate(parts):
        for b in parts[i+1:]:
            if a['color']!=b['color']:continue
            ratio=min(a['width'],b['width'])/max(a['width'],b['width'])
            if ratio<.4:continue
            for ai in (0,1):
                for bi in (0,1):
                    # A ends at the gap; B starts at it.
                    pa=a['xy'] if ai else a['xy'][::-1]
                    pb=b['xy'][::-1] if bi else b['xy']
                    gap=pb[0]-pa[-1];distance=float(np.linalg.norm(gap))
                    if not 4<=distance<=maximum:continue
                    u=pa[-1]-pa[max(0,len(pa)-12)];v=pb[0]-pb[min(11,len(pb)-1)]
                    if min(np.linalg.norm(u),np.linalg.norm(v))<3:continue
                    ca=float(np.dot(u,gap)/(np.linalg.norm(u)*distance))
                    cb=float(np.dot(v,-gap)/(np.linalg.norm(v)*distance))
                    if min(ca,cb)<.35:continue
                    score=100*(.45*(ca+cb)/2+.3*(1-distance/maximum)+.25*ratio)
                    if score<52:continue
                    output.append(dict(a=a,b=b,pa=pa,pb=pb,ends=[a['id']+':'+str(ai),b['id']+':'+str(bi)],
                        distance=distance,angle=math.degrees(math.acos(min(1,max(-1,min(ca,cb))))),ratio=ratio,score=score))
    return sorted(output,key=lambda r:(-r['score'],r['ends']))


def infer(graph,path,asset_id):
    asset=next((a for a in graph.assets if a.id==asset_id),None)
    if graph.mode not in {'photo','video'} or not asset:raise HTTPException(422,'선택한 실제 입력 사진이 필요합니다.')
    with Image.open(path) as image:parts,w,h=fragments(image)
    rows=propose(parts,w,h);known={p.id for p in graph.wire_hypotheses}
    # Colored PCB surfaces and silkscreen also produce strokes. Lower their rank
    # using existing object regions, without claiming that region detection is truth.
    regions=[c.bbox for c in graph.components if c.asset_id==asset_id and c.kind in {'board','display'}]
    for row in rows:
        xy=np.vstack([row['pa'],row['pb']])/np.array([w,h])
        inside=np.zeros(len(xy),dtype=bool)
        for lo,hi in regions:inside|=(xy[:,0]>=lo.x)&(xy[:,0]<=hi.x)&(xy[:,1]>=lo.y)&(xy[:,1]<=hi.y)
        row['surface']=float(inside.mean())
        row['score']-=30*row['surface']
    rows=sorted(rows,key=lambda r:(-r['score'],r['ends']))[:30]
    for row in rows:
        token=hashlib.sha256(f'single-v1:{asset.sha256}:{asset_id}:{row["ends"]}'.encode()).hexdigest()[:16]
        hid='gap_'+token;eid='gap_geometry_'+token
        if hid in known:continue
        paths=[]
        for xy in (row['pa'],row['pb']):
            xy=cv2.approxPolyDP(xy.astype(np.float32).reshape(-1,1,2),1.2,False).reshape(-1,2)
            if len(xy)>200:xy=xy[np.linspace(0,len(xy)-1,200).astype(int)]
            paths.append([Point(x=float(x)/w,y=float(y)/h) for x,y in xy])
        bridge=[paths[0][-1],paths[1][0]]
        reasons=[f'같은 색상 범위: {row["a"]["color"]}',f'가림 후보 간격: {row["distance"]*asset.width/w:.1f} px',
            f'끝점 진행 방향 차이 최대 {row["angle"]:.1f}°',f'선 굵기 유사도 {row["ratio"]:.2f}',
            '점선은 두 조각 사이의 연결 가설이며 실제 숨은 경로·도통은 관측하지 못함.']
        if row['surface']>.3:reasons.append('기존 부품 영역과 많이 겹쳐 PCB 표면·인쇄선일 가능성 때문에 순위를 낮춤.')
        graph.evidence.append(Evidence(id=eid,asset_id=asset_id,method='geometry',points=paths[0]+paths[1],
            text='단일 사진 HSV·골격 분할 single-v1. '+' / '.join(reasons)+' 순위 점수는 정답 확률이 아님.'))
        graph.wire_hypotheses.append(WireHypothesis(id=hid,asset_id=asset_id,evidence_id=eid,
            endpoint_ids=[asset_id+':'+e for e in row['ends']],visible_paths=paths,bridge=bridge,
            color=row['a']['color'],ranking_score=round(row['score'],1),reasons=reasons))
    return graph


def pin_matches(graph,hypothesis):
    asset=next(a for a in graph.assets if a.id==hypothesis.asset_id);limit=min(asset.width,asset.height)*.04
    pins=[t for c in graph.components if c.asset_id==asset.id for t in c.terminals if t.image_position and t.name.value]
    return [[t.id for t in pins if math.hypot((t.image_position.x-p.x)*asset.width,(t.image_position.y-p.y)*asset.height)<=limit]
            for p in (hypothesis.visible_paths[0][0],hypothesis.visible_paths[1][-1])]


def adopt(graph,hid):
    hypothesis=next((h for h in graph.wire_hypotheses if h.id==hid),None)
    if not hypothesis:raise HTTPException(404,'배선 추정 후보를 찾을 수 없습니다.')
    if hypothesis.link_id:raise HTTPException(409,'이미 회로 초안에 반영한 후보입니다.')
    matches=pin_matches(graph,hypothesis)
    if any(len(m)!=1 for m in matches) or matches[0][0]==matches[1][0]:
        raise HTTPException(422,'양끝의 실제 핀을 하나씩 식별해야 회로 초안에 반영할 수 있습니다. 경로 추정은 그대로 볼 수 있습니다.')
    a,b=matches[0][0],matches[1][0]
    if any({l.from_terminal,l.to_terminal}=={a,b} for l in graph.links):raise HTTPException(409,'기존 연결을 먼저 검토하세요.')
    if any(h.link_id and set(h.endpoint_ids)&set(hypothesis.endpoint_ids) for h in graph.wire_hypotheses):
        raise HTTPException(409,'같은 끝점을 사용하는 다른 가설이 이미 선택되었습니다.')
    eid='gap_choice_'+hid
    graph.evidence.append(Evidence(id=eid,asset_id=hypothesis.asset_id,method='manual_annotation',points=hypothesis.bridge,
        text='사용자가 단일 사진의 가림 연결 가설을 회로 초안에 반영함. 실제 연결 확인이 아님.'))
    lid='HYP_'+hid
    graph.links.append(Link(id=lid,asset_id=hypothesis.asset_id,from_terminal=a,to_terminal=b,
        path=hypothesis.visible_paths[0]+hypothesis.visible_paths[1],connection=Claim(value='connected',status='INFERRED',
        evidence_ids=[hypothesis.evidence_id,eid],reason='단일 사진의 가림 배선 추정. 다른 연결도 가능하며 조립 전 검증 필요.')))
    hypothesis.link_id=lid
    return graph


class InferInput(StrictModel):
    expected_revision:int
    asset_id:str='image'


def single_view_routes(app,store,get,save,view):
    def current(project,revision):
        graph=get(project)
        if graph.revision!=revision:raise HTTPException(409,'수정 버전이 변경되었습니다. 다시 열어주세요.')
        return graph

    @app.post('/api/projects/{project}/occlusion/infer')
    def analyze(project:str,body:InferInput):
        graph=current(project,body.expected_revision)
        path=store.root/(f'{project}.png' if body.asset_id=='image' else f'{project}-{body.asset_id}.png')
        before=len(graph.wire_hypotheses)
        graph=infer(graph,path,body.asset_id)
        return view(save(graph,body.expected_revision,'단일 사진의 가림 배선 가설 생성') if len(graph.wire_hypotheses)>before else graph)

    @app.post('/api/projects/{project}/occlusion/hypotheses/{hypothesis}/adopt')
    def choose(project:str,hypothesis:str,body:InferInput):
        return view(save(adopt(current(project,body.expected_revision),hypothesis),body.expected_revision,'가림 추정 연결을 INFERRED로 반영'))
