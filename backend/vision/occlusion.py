"""Resolve an occlusion using explicitly reviewed evidence from a different view."""
import math
import uuid
from fastapi import HTTPException
from pydantic import Field
from ..circuit.schema import StrictModel, Point, Evidence, Claim, Link, WireReview, Status


class ResolveInput(StrictModel):
    expected_revision: int
    asset_id: str
    from_terminal: str
    to_terminal: str
    points: list[Point] = Field(min_length=2, max_length=200)
    same_system_checked: bool
    endpoints_checked: bool
    entire_wire_visible: bool
    note: str = Field(min_length=5, max_length=1000)


def resolve(graph, body):
    if graph.mode not in {'photo', 'video'}:
        raise HTTPException(422, '사진·영상 프로젝트에서 사용하세요.')
    if not body.same_system_checked or not body.endpoints_checked:
        raise HTTPException(422, '배선을 바꾸지 않은 같은 장치인지, 두 끝이 같은 실제 핀인지 확인하세요.')
    if len(body.note.strip()) < 5:
        raise HTTPException(422, '핀 대응과 경로를 확인한 근거를 기록하세요.')
    asset = next((a for a in graph.assets if a.id == body.asset_id), None)
    terminals = {t.id: (c, t) for c in graph.components for t in c.terminals}
    a = terminals.get(body.from_terminal)
    b = terminals.get(body.to_terminal)
    if not asset or not a or not b or body.from_terminal == body.to_terminal:
        raise HTTPException(422, '추가 사진과 서로 다른 기존 핀 두 개가 필요합니다.')
    for component, terminal in (a, b):
        original = next(s for s in graph.assets if s.id == component.asset_id)
        if asset.id == original.id or asset.sha256 == original.sha256:
            raise HTTPException(422, '원본과 다른 각도의 사진을 추가하세요. 같은 사진 복제는 추가 근거가 아닙니다.')
        if not terminal.image_position or terminal.name.status == Status.UNKNOWN:
            raise HTTPException(422, '먼저 원본 사진에서 핀 이름과 실제 위치를 지정하세요.')
    start, end = body.points[0], body.points[-1]
    if math.hypot((start.x-end.x)*asset.width, (start.y-end.y)*asset.height) < 3:
        raise HTTPException(422, '추가 사진의 양쪽 접점을 구분할 수 없습니다. 확대해서 다시 지정하세요.')
    pair = {body.from_terminal, body.to_terminal}
    existing = [l for l in graph.links if {l.from_terminal, l.to_terminal} == pair]
    if len(existing) > 1 or any(l.connection.status != Status.UNKNOWN for l in existing):
        raise HTTPException(409, '이미 연결 후보가 있습니다. 기존 연결을 먼저 검토하세요.')

    # All checks precede mutation. Retain original unknown observations in evidence/history.
    token = uuid.uuid4().hex[:12]
    eid, geometry_id = 'multiview_'+token, 'multiview_geometry_'+token
    note = (f'사용자 다각도 대조: {body.from_terminal} → {body.to_terminal}. '
            f'배선 변경 없는 동일 장치·양끝 핀 대응 확인. 전체 경로 보임={body.entire_wire_visible}. '
            f'{body.note.strip()} 자동 추적·실제 도통 측정 결과가 아님.')
    graph.evidence.append(Evidence(id=eid, asset_id=asset.id, method='manual_annotation', points=body.points, text=note))
    graph.evidence.append(Evidence(id=geometry_id, asset_id=asset.id, method='geometry', points=[start, end],
        text='사용자 지정 추가 시점 접점. 원본 핀 위치 변경 시 대응을 재검토해야 함.'))
    link = existing[0] if existing else Link(id='LINK_'+token, from_terminal=body.from_terminal, to_terminal=body.to_terminal)
    # Review direction can be opposite to the pre-existing unresolved link.
    link.from_terminal, link.to_terminal = body.from_terminal, body.to_terminal
    refs = list(dict.fromkeys([*link.connection.evidence_ids, eid, geometry_id]))
    link.asset_id = asset.id
    link.path = body.points if body.entire_wire_visible else []
    link.connection = Claim(value='connected' if body.entire_wire_visible else None,
        status=Status.INFERRED if body.entire_wire_visible else Status.UNKNOWN, evidence_ids=refs,
        reason='다른 각도에서 전체 경로와 양끝을 사용자가 대조함. 도통·핀 기능은 별도 검증 필요.' if body.entire_wire_visible
            else '추가 사진에도 가려진 구간이 남음. 더 다른 각도 또는 분리한 전선의 도통 확인이 필요함.')
    if not existing:
        graph.links.append(link)
    graph.wire_reviews.append(WireReview(id='review_'+token, link_id=link.id, asset_id=asset.id,
        from_terminal=body.from_terminal, to_terminal=body.to_terminal, points=body.points,
        entire_wire_visible=body.entire_wire_visible, evidence_id=eid))
    return graph


def occlusion_routes(app, store, get, save, view):
    @app.post('/api/projects/{project}/occlusion/resolve')
    def review(project: str, body: ResolveInput):
        graph = get(project)
        if graph.revision != body.expected_revision:
            raise HTTPException(409, '수정 버전이 변경되었습니다. 사진과 핀을 다시 대조하세요.')
        return view(save(resolve(graph, body), body.expected_revision, '가려진 배선의 추가 시점 검토'))
