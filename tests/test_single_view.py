import numpy as np
import pytest
from PIL import Image,ImageDraw
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from backend.api import create_app
from backend.circuit.schema import Graph,Asset,Component,Terminal,Claim,Point
from backend.circuit.connectivity import derive_nets
from backend.vision.single_view import infer,adopt,fragments,propose,chains,pin_matches


def picture(color='red',gap=True):
    im=Image.new('RGB',(400,300),'white');d=ImageDraw.Draw(im)
    d.line([(40,120),(165 if gap else 360,120)],fill='red',width=7)
    if gap:d.line([(215,120),(360,120)],fill=color,width=7)
    return im


def graph():
    return Graph(project_id='d'*32,title='Single-view synthetic fixture',revision=1,mode='photo',
        assets=[Asset(id='image',sha256='fixture',width=400,height=300,filename='fixture.png')])


def inferred(tmp_path):
    g=graph();path=tmp_path/(g.project_id+'.png');picture().save(path)
    return infer(g,path,'image')


def anchors(g):
    h=g.wire_hypotheses[0]
    g.components=[Component(id='U',kind='board',bbox=[Point(x=0,y=0),Point(x=1,y=1)],terminals=[
        Terminal(id='A',name=Claim(value='A',status='INFERRED'),image_position=h.visible_paths[0][0]),
        Terminal(id='B',name=Claim(value='B',status='INFERRED'),image_position=h.visible_paths[1][-1])])]
    return g


def test_single_photo_gap_is_inferred_without_invented_terminals(tmp_path):
    g=inferred(tmp_path);assert len(g.wire_hypotheses)==1
    h=g.wire_hypotheses[0];assert h.status=='INFERRED' and 0<h.ranking_score<100
    assert not g.links and not g.components and not derive_nets(g)
    assert pin_matches(g,h)==[[],[]]
    assert h.bridge==[h.visible_paths[0][-1],h.visible_paths[1][0]]
    Graph.model_validate(g.model_dump())


def test_repeat_analysis_is_idempotent(tmp_path):
    g=inferred(tmp_path);before=g.model_dump();infer(g,tmp_path/(g.project_id+'.png'),'image')
    assert g.model_dump()==before


@pytest.mark.parametrize('kind',['different_color','continuous','blank','black'])
def test_no_fabricated_gap_when_support_absent(kind):
    im=picture('blue') if kind=='different_color' else picture(gap=False) if kind=='continuous' else Image.new('RGB',(400,300),'white')
    if kind=='black':ImageDraw.Draw(im).line([(30,100),(370,100)],fill='black',width=8)
    parts,w,h=fragments(im);assert propose(parts,w,h)==[]


def part(id,xy,color='red',width=5):return dict(id=id,xy=np.array(xy,dtype=float),color=color,width=width)


def test_competing_continuations_are_kept_not_arbitrarily_chosen():
    a=part('a',[(x,100) for x in range(20,100)])
    b=part('b',[(x,95) for x in range(140,220)])
    c=part('c',[(x,105) for x in range(140,220)])
    rows=propose([a,b,c],400,300)
    assert len(rows)==2 and all('a:1' in r['ends'] for r in rows)


@pytest.mark.parametrize('case',['away','far','thickness'])
def test_direction_distance_and_width_filters(case):
    a=part('a',[(x,100) for x in range(20,100)])
    b=part('b',[(99,y) for y in range(130,210)]) if case=='away' else part('b',[(x,100) for x in range(300,380)] if case=='far' else [(x,100) for x in range(140,220)],width=20 if case=='thickness' else 5)
    assert not propose([a,b],400,300)


def test_junction_is_split_into_branches():
    mask=np.zeros((100,100),np.uint8);mask[50,10:90]=1;mask[10:90,50]=1
    paths=chains(mask);assert len(paths)==4
    assert all(any(np.array_equal(p,np.array([50,50])) for p in (path[0],path[-1])) for path in paths)


def test_missing_pins_block_electrical_adoption(tmp_path):
    g=inferred(tmp_path);before=g.model_dump()
    with pytest.raises(HTTPException):adopt(g,g.wire_hypotheses[0].id)
    assert g.model_dump()==before


def test_named_unique_anchors_allow_only_inferred_connection(tmp_path):
    g=anchors(inferred(tmp_path));h=g.wire_hypotheses[0];adopt(g,h.id)
    assert len(g.links)==1 and h.link_id==g.links[0].id
    assert g.links[0].connection.status=='INFERRED' and g.links[0].connection.score is None
    assert all(len(n['terminals'])==1 for n in derive_nets(g))
    assert len(derive_nets(g,True))==1
    with pytest.raises(HTTPException):adopt(g,h.id)


def test_ambiguous_pin_or_different_image_cannot_be_adopted(tmp_path):
    g=anchors(inferred(tmp_path));g.components[0].terminals.append(g.components[0].terminals[0].model_copy(update={'id':'C'}))
    with pytest.raises(HTTPException):adopt(g,g.wire_hypotheses[0].id)
    g.components[0].asset_id='other'
    with pytest.raises(HTTPException):adopt(g,g.wire_hypotheses[0].id)


def test_api_stale_revision_and_anchor_invalidation(tmp_path):
    app=create_app(tmp_path);g=graph();picture().save(tmp_path/(g.project_id+'.png'));app.state.store.save(g,0,'Fixture')
    url='/api/projects/'+g.project_id
    with TestClient(app) as client:
        r=client.post(url+'/occlusion/infer',json=dict(expected_revision=1));assert r.status_code==200,r.text
        assert r.json()['graph']['revision']==2
        assert client.post(url+'/occlusion/infer',json=dict(expected_revision=1)).status_code==409
        r=client.post(url+'/occlusion/infer',json=dict(expected_revision=2));assert r.json()['graph']['revision']==2
        g=anchors(app.state.store.get(g.project_id));app.state.store.save(g,2,'Anchor fixture')
        h=g.wire_hypotheses[0];r=client.post(url+f'/occlusion/hypotheses/{h.id}/adopt',json=dict(expected_revision=3))
        assert r.status_code==200,r.text
        r=client.post(url+'/anchor',json=dict(expected_revision=4,terminal_id='A',position=dict(x=.12,y=.4)))
        assert r.status_code==200 and r.json()['graph']['links'][0]['connection']['status']=='UNKNOWN'


def test_forged_geometry_reference_rejected(tmp_path):
    g=inferred(tmp_path);g.wire_hypotheses[0].evidence_id='missing'
    with pytest.raises(ValidationError):Graph.model_validate(g.model_dump())
