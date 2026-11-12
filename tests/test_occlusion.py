import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from backend.api import create_app
from backend.circuit.schema import Asset, Graph, Link, Point
from backend.circuit.connectivity import derive_nets
from backend.vision.occlusion import ResolveInput, resolve
from test_review_assist import with_wire


def fixture():
    g = with_wire()
    g.assets.append(Asset(id='side', sha256='different-view', width=400, height=300, filename='side.png'))
    return g


def request(**changes):
    data = dict(expected_revision=1, asset_id='side', from_terminal='A', to_terminal='B',
        points=[dict(x=.1,y=.2),dict(x=.5,y=.1),dict(x=.9,y=.2)],
        same_system_checked=True, endpoints_checked=True, entire_wire_visible=True,
        note='Unchanged circuit, terminal identities and continuous wire reviewed in side view')
    return ResolveInput(**(data | changes))


def test_cross_view_correspondence_keeps_original_anchors_and_never_confirms():
    g=fixture();original=g.components[0].model_dump();resolve(g, request())
    link=g.links[0]
    assert link.asset_id=='side' and link.connection.status=='INFERRED'
    assert link.path==request().points and link.connection.score is None
    assert g.components[0].model_dump()==original
    assert all(len(n["terminals"])==1 for n in derive_nets(g))
    assert len(g.wire_reviews)==1 and g.wire_reviews[0].evidence_id in link.connection.evidence_ids
    Graph.model_validate(g.model_dump())


def test_remaining_occlusion_has_no_drawn_path_or_inferred_net():
    g=resolve(fixture(),request(entire_wire_visible=False));link=g.links[0]
    assert link.connection.status=='UNKNOWN' and link.connection.value is None and link.path==[]
    assert all(len(n["terminals"])==1 for n in derive_nets(g,include_inferred=True))
    assert not g.wire_reviews[0].entire_wire_visible


def test_existing_unknown_upgrades_without_duplicate_or_lost_history():
    g=resolve(fixture(),request(entire_wire_visible=False));old=g.wire_reviews[0].model_dump()
    refs=g.links[0].connection.evidence_ids.copy();lid=g.links[0].id
    resolve(g,request(from_terminal='B',to_terminal='A'))
    assert len(g.links)==1 and g.links[0].id==lid and g.links[0].connection.status=='INFERRED'
    assert set(refs)<=set(g.links[0].connection.evidence_ids)
    assert g.wire_reviews[0].model_dump()==old and len(g.wire_reviews)==2
    Graph.model_validate(g.model_dump())


@pytest.mark.parametrize('changes',[
    dict(asset_id='image'),dict(asset_id='missing'),dict(from_terminal='missing'),
    dict(to_terminal='A'),dict(same_system_checked=False),dict(endpoints_checked=False),
    dict(note='     '),dict(points=[dict(x=.1,y=.2),dict(x=.1001,y=.2)])])
def test_invalid_evidence_does_not_mutate(changes):
    g=fixture();before=g.model_dump()
    with pytest.raises(HTTPException):resolve(g,request(**changes))
    assert g.model_dump()==before


@pytest.mark.parametrize('reason',['same_hash','missing_anchor','unknown_name','existing_known','duplicate_pairs'])
def test_unsafe_merge_is_blocked(reason):
    g=fixture()
    if reason=='same_hash':g.assets[1].sha256=g.assets[0].sha256
    elif reason=='missing_anchor':g.components[0].terminals[0].image_position=None
    elif reason=='unknown_name':g.components[0].terminals[0].name=g.components[0].value
    elif reason=='existing_known':resolve(g,request())
    else:g.links=[Link(id='L1',from_terminal='A',to_terminal='B'),Link(id='L2',from_terminal='B',to_terminal='A')]
    before=g.model_dump()
    with pytest.raises(HTTPException):resolve(g,request())
    assert g.model_dump()==before


def test_api_revisions_history_and_anchor_change(tmp_path):
    app=create_app(tmp_path);g=fixture();app.state.store.save(g,0,'Fixture')
    url='/api/projects/'+g.project_id
    with TestClient(app) as c:
        r=c.post(url+'/occlusion/resolve',json=request().model_dump());assert r.status_code==200,r.text
        result=r.json();assert result['graph']['revision']==2
        assert all(len(n['terminals'])==1 for n in result['confirmed_nets'])
        assert c.post(url+'/occlusion/resolve',json=request().model_dump()).status_code==409
        r=c.post(url+'/anchor',json=dict(expected_revision=2,terminal_id='A',position=dict(x=.21,y=.5)))
        assert r.status_code==200,r.text
        assert r.json()['graph']['links'][0]['connection']['status']=='UNKNOWN'
        assert len(r.json()['graph']['wire_reviews'])==1
    g=app.state.store.get(g.project_id);g.wire_reviews=[]
    with pytest.raises(ValueError,match='immutable'):app.state.store.save(g,3,'Forbidden history deletion')
    assert app.state.store.get(g.project_id).revision==3


def test_forged_review_references_fail_schema():
    g=resolve(fixture(),request());g.wire_reviews[0].from_terminal='missing'
    with pytest.raises(ValidationError):Graph.model_validate(g.model_dump())
