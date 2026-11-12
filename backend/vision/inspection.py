"""Evidence-backed human review between image observations and electrical graph."""
import hashlib
import math
import uuid
from fastapi import HTTPException
from PIL import Image
from pydantic import Field
from ..circuit.schema import StrictModel,Point,Claim,Status,Evidence,Terminal,Link,TextObservation
from .segments import detect_segments
from .staged import ocr_rows


class InspectInput(StrictModel):
    expected_revision:int
    asset_id:str='image'


class PinInput(InspectInput):
    component_id:str
    text_id:str|None=None
    text_span:list[int]|None=Field(default=None,min_length=2,max_length=2)
    label:str=Field(min_length=1,max_length=40)
    position:Point
    note:str=Field(min_length=5,max_length=500)


class BindInput(StrictModel):
    expected_revision:int
    from_terminal:str
    to_terminal:str
    endpoints_checked:bool
    note:str=Field(min_length=5,max_length=500)


def add_observations(graph,path,asset_id):
    asset=next(a for a in graph.assets if a.id==asset_id);known={e.id for e in graph.evidence}
    for row in ocr_rows(path):
        x,y,r,b=row['bbox'];x=max(0,x/asset.width);y=max(0,y/asset.height)
        r=min(1,r/asset.width);b=min(1,b/asset.height)
        if x>=r or y>=b:continue
        token=hashlib.sha256(f'{asset.sha256}:{asset_id}:{row["text"]}:{row["bbox"]}'.encode()).hexdigest()[:14]
        eid='text_ev_'+token
        if eid in known:continue
        box=[Point(x=x,y=y),Point(x=r,y=b)]
        graph.evidence.append(Evidence(id=eid,asset_id=asset_id,method='ocr',points=box,
            text=f'RapidOCR 원문: {row["text"]}. 문자 점수 {row["score"]:.3f}; 단자·핀 번호 검증 아님.'))
        graph.text_observations.append(TextObservation(id='text_'+token,asset_id=asset_id,
            text=row['text'],bbox=box,score=row['score'],evidence_id=eid));known.add(eid)
    with Image.open(path) as image:ev,candidates,stats=detect_segments(image,asset_id)
    mapping={e.id:e for e in ev}
    for candidate in candidates:
        if candidate.evidence_id not in known:
            graph.evidence.append(mapping[candidate.evidence_id]);graph.wire_candidates.append(candidate)
            known.add(candidate.evidence_id)
    return graph


def add_pin(graph,body):
    component=next((c for c in graph.components if c.id==body.component_id and c.asset_id==body.asset_id),None)
    if not component:raise HTTPException(422,'선택한 사진의 부품을 지정하세요.')
    label=body.label.strip()
    if not label:raise HTTPException(422,'단자 이름을 입력하세요.')
    if any((t.name.value or '').casefold()==label.casefold() for t in component.terminals):raise HTTPException(409,'이미 있는 단자입니다. 기존 핀 위치 지정 기능을 사용하세요.')
    a,b=component.bbox;p=body.position
    if not (a.x-.06<=p.x<=b.x+.06 and a.y-.06<=p.y<=b.y+.06):raise HTTPException(422,'선택한 부품에서 너무 멀리 떨어진 점입니다. 부품과 실제 핀을 다시 확인하세요.')
    refs=[];span_note=''
    if body.text_span is not None and not body.text_id:
        raise HTTPException(422,'문자 분리 후보에는 원문 근거가 필요합니다.')
    if body.text_id:
        text=next((t for t in graph.text_observations if t.id==body.text_id and t.asset_id==body.asset_id),None)
        if not text:raise HTTPException(422,'선택한 사진의 문자 근거가 아닙니다.')
        if body.text_span is not None:
            start,end=body.text_span
            if not 0<=start<end<=len(text.text) or text.text[start:end].upper()!=label.upper():
                raise HTTPException(422,'단자 이름이 선택한 OCR 원문 구간과 다릅니다. 직접 수정했으면 문자 후보를 다시 선택하세요.')
            span_note=f' OCR 원문 구간 [{start}:{end}]: {text.text[start:end]}.'
        refs.append(text.evidence_id)
    eid='pin_review_'+uuid.uuid4().hex[:10];refs.append(eid)
    graph.evidence.append(Evidence(id=eid,asset_id=body.asset_id,method='manual_annotation',points=[p],
        text=f'사용자가 문자와 별개로 실제 핀 위치를 지정함: {label}.{span_note} {body.note} 패키지 핀 번호·도통 미검증.'))
    tid=component.id+'.P'+uuid.uuid4().hex[:6]
    component.terminals.append(Terminal(id=tid,name=Claim(value=label,status=Status.INFERRED,
        evidence_ids=refs,reason='사용자가 읽은 단자 라벨. 데이터시트 핀 매핑은 UNKNOWN'),image_position=p))
    return graph


def bind_segment(graph,cid,body):
    candidate=next((c for c in graph.wire_candidates if c.id==cid),None)
    if not candidate or candidate.geometry!='segment' or len(candidate.endpoints)!=2 or len(candidate.path)<2:
        raise HTTPException(422,'분기 없는 선 조각과 두 끝점 후보가 필요합니다.')
    if not body.endpoints_checked:raise HTTPException(422,'두 끝점이 실제 핀에 닿는지 사진에서 확인하세요.')
    source=next(e for e in graph.evidence if e.id==candidate.evidence_id)
    terminals={t.id:t for c in graph.components if c.asset_id==source.asset_id for t in c.terminals}
    a=terminals.get(body.from_terminal);b=terminals.get(body.to_terminal)
    if not a or not b or a.id==b.id or not a.image_position or not b.image_position:
        raise HTTPException(422,'같은 사진에서 위치를 지정한 서로 다른 두 핀이 필요합니다.')
    asset=next(a for a in graph.assets if a.id==source.asset_id)
    def distance(p,q):return math.hypot((p.x-q.x)*asset.width,(p.y-q.y)*asset.height)
    p,q=candidate.endpoints;limit=min(asset.width,asset.height)*.04
    forward=distance(p,a.image_position)<=limit and distance(q,b.image_position)<=limit
    reverse=distance(p,b.image_position)<=limit and distance(q,a.image_position)<=limit
    if forward and reverse:
        raise HTTPException(422,'두 핀이 양쪽 끝점 모두에 대응되어 구분할 수 없습니다. 확대해서 실제 핀 위치를 다시 지정하세요.')
    if not (forward or reverse):raise HTTPException(422,'선 조각의 끝과 지정 핀 위치가 맞지 않습니다. 가려진 구간을 임의로 이어 붙이지 마세요.')
    pair={a.id,b.id}
    if any({l.from_terminal,l.to_terminal}==pair for l in graph.links):raise HTTPException(409,'이미 검토 중인 연결입니다.')
    eid='segment_review_'+uuid.uuid4().hex[:10]
    graph.evidence.append(Evidence(id=eid,asset_id=source.asset_id,method='manual_annotation',points=[a.image_position,b.image_position],
        text='사용자가 선 조각과 두 핀의 대응을 확인: '+body.note+' 실제 도통·핀 기능 검증 아님.'))
    graph.links.append(Link(id='LINK_'+uuid.uuid4().hex[:8],asset_id=source.asset_id,
        from_terminal=a.id,to_terminal=b.id,path=candidate.path if forward else list(reversed(candidate.path)),
        connection=Claim(value='connected',status=Status.INFERRED,evidence_ids=[candidate.evidence_id,eid],
            reason='색상 선 조각 + 사용자 핀 위치·끝점 확인. 실제 도통은 별도 검증 필요')))
    return graph


def inspection_routes(app,store,get,save,view):
    def current(project,expected):
        g=get(project)
        if g.revision!=expected:raise HTTPException(409,'수정 버전이 변경되었습니다. 다시 열어주세요.')
        if g.mode not in {'photo','video'}:raise HTTPException(422,'실제 사진·영상 프로젝트에서 사용하세요.')
        return g

    @app.post('/api/projects/{project}/inspection')
    def inspect(project:str,body:InspectInput):
        g=current(project,body.expected_revision)
        if not any(a.id==body.asset_id for a in g.assets):raise HTTPException(422,'사진을 찾을 수 없습니다.')
        path=store.root/(f'{project}.png' if body.asset_id=='image' else f'{project}-{body.asset_id}.png')
        try:g=add_observations(g,path,body.asset_id)
        except Exception as exc:raise HTTPException(422,'문자·선 조각 분석 실패. 기존 그래프는 유지됩니다.') from exc
        return view(save(g,body.expected_revision,'문자 영역·선 조각 관측 추가 · 전기적 연결 없음'))

    @app.post('/api/projects/{project}/inspection/pins')
    def pin(project:str,body:PinInput):
        g=add_pin(current(project,body.expected_revision),body)
        return view(save(g,body.expected_revision,'사진의 단자 라벨·실제 핀 위치 검토'))

    @app.post('/api/projects/{project}/inspection/wires/{candidate}/bind')
    def bind(project:str,candidate:str,body:BindInput):
        g=bind_segment(current(project,body.expected_revision),candidate,body)
        return view(save(g,body.expected_revision,'선 조각과 핀 대응 · INFERRED 연결 후보'))
