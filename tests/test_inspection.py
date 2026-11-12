"""Photo review must not turn text or hidden geometry into confirmed nets."""
import io
import numpy as np
import pytest
from PIL import Image,ImageDraw
from fastapi import HTTPException
from fastapi.testclient import TestClient
from backend.api import create_app
from backend.circuit.schema import Graph,Asset,Component,Claim,Point,Status
from backend.vision.segments import detect_segments,ordered_stroke
from backend.vision.inspection import add_observations,add_pin,bind_segment,PinInput,BindInput
import backend.vision.inspection as inspection


def picture(kind='straight'):
    im=Image.new('RGB',(400,300),'white');d=ImageDraw.Draw(im)
    if kind=='loop':d.ellipse((50,50,250,250),outline='red',width=7)
    else:
        d.line([(50,100),(350,100)],fill='red',width=7)
        if kind=='cross':d.line([(200,30),(200,200)],fill='red',width=7)
    return im


def graph():
    return Graph(project_id='review',title='Synthetic test input',revision=1,mode='photo',
        assets=[Asset(id='image',sha256='test',width=400,height=300,filename='test.png')],
        components=[Component(id='U1',kind='board',bbox=[Point(x=0,y=0),Point(x=1,y=1)])])


def pin(g,label,pos,text=None):
    add_pin(g,PinInput(expected_revision=1,component_id='U1',label=label,position=pos,text_id=text,note='Synthetic test review'))
    return g.components[0].terminals[-1].id


def prepared():
    g=graph();ev,cs,_=detect_segments(picture(),'image');g.evidence.extend(ev);g.wire_candidates.extend(cs)
    c=cs[0];a=pin(g,'A',c.endpoints[0]);b=pin(g,'B',c.endpoints[1])
    return g,c,a,b


@pytest.mark.parametrize('kind,geometry',[('straight','segment'),('cross','ambiguous'),('loop','ambiguous')])
def test_color_geometry_preserves_ambiguity(kind,geometry):
    ev,cs,stats=detect_segments(picture(kind),'image')
    assert len(cs)==1 and cs[0].geometry==geometry
    assert cs[0].status=='UNKNOWN' and stats['automatic_connections']==0
    assert len(cs[0].endpoints)==(2 if geometry=='segment' else 0)


def test_disconnected_skeleton_is_rejected():
    mask=np.zeros((100,100),dtype=np.uint8);mask[10,10:70]=1;mask[50,10:70]=1
    assert ordered_stroke(mask)[0] is None


def test_ocr_is_evidence_not_pins_and_repeated_inspection_is_idempotent(tmp_path,monkeypatch):
    path=tmp_path/'image.png';picture().save(path)
    monkeypatch.setattr(inspection,'ocr_rows',lambda path:[{'text':'GNDVCC','score':.85,'bbox':[10,10,100,30]}])
    g=add_observations(graph(),path,'image');before=g.model_dump()
    add_observations(g,path,'image')
    assert g.model_dump()==before
    assert not g.links and not g.components[0].terminals
    t=g.text_observations[0];pin(g,'GND',Point(x=.12,y=.33),t.id)
    terminal=g.components[0].terminals[0]
    assert terminal.name.status==Status.INFERRED and terminal.pin_mapping.status==Status.UNKNOWN
    assert t.evidence_id in terminal.name.evidence_ids
    assert terminal.image_position!=t.bbox[0]
    Graph.model_validate(g.model_dump())


@pytest.mark.parametrize('reverse',[False,True])
def test_reviewed_segment_is_only_inferred(reverse):
    g,c,a,b=prepared()
    if reverse:a,b=b,a
    body=BindInput(expected_revision=1,from_terminal=a,to_terminal=b,endpoints_checked=True,note='Synthetic endpoints checked')
    bind_segment(g,c.id,body)
    assert g.links[0].connection.status==Status.INFERRED
    assert g.links[0].path[0]==c.path[-1 if reverse else 0]
    assert all(t.pin_mapping.status==Status.UNKNOWN for t in g.components[0].terminals)
    Graph.model_validate(g.model_dump())
    with pytest.raises(HTTPException) as error:bind_segment(g,c.id,body)
    assert error.value.status_code==409


@pytest.mark.parametrize('failure',['unchecked','same_pin','far','different_asset','ambiguous'])
def test_binding_requires_two_visible_matching_pins(failure):
    g,c,a,b=prepared();checked=True
    if failure=='unchecked':checked=False
    if failure=='same_pin':b=a
    if failure=='far':g.components[0].terminals[1].image_position=Point(x=.5,y=.9)
    if failure=='different_asset':g.components[0].asset_id='other'
    if failure=='ambiguous':c.geometry='ambiguous'
    with pytest.raises(HTTPException):bind_segment(g,c.id,BindInput(expected_revision=1,from_terminal=a,to_terminal=b,endpoints_checked=checked,note='Synthetic endpoint review'))
    assert not g.links


def test_cross_asset_text_is_rejected(tmp_path,monkeypatch):
    path=tmp_path/'image.png';picture().save(path)
    monkeypatch.setattr(inspection,'ocr_rows',lambda path:[{'text':'GND','score':.9,'bbox':[10,10,30,20]}])
    g=add_observations(graph(),path,'image');g.text_observations[0].asset_id='other'
    with pytest.raises(HTTPException):pin(g,'GND',Point(x=.1,y=.1),g.text_observations[0].id)


def test_public_review_flow_and_anchor_change(tmp_path,monkeypatch):
    monkeypatch.setattr(inspection,'ocr_rows',lambda path:[])
    with TestClient(create_app(tmp_path)) as client:
        raw=io.BytesIO();picture().save(raw,format='PNG')
        g=client.post('/api/projects',files={'image':('test.png',raw.getvalue(),'image/png')}).json()['graph']
        url='/api/projects/'+g['project_id']
        def post(path,body):return client.post(url+path,json={'expected_revision':g['revision'],**body})
        r=post('/inspection',{});assert r.status_code==200;g=r.json()['graph']
        assert not g['links'] and not g['components']
        assert post('/inspection',{'expected_revision':1}).status_code==409
        assert post('/inspection',{'asset_id':'missing'}).status_code==422
        g=post('/components',{'kind':'board','label':'Synthetic test','bbox':[{'x':0,'y':0},{'x':1,'y':1}]}).json()['graph']
        cid=g['components'][0]['id'];c=next(c for c in g['wire_candidates'] if c['geometry']=='segment')
        for i,p in enumerate(c['endpoints']):
            r=post('/inspection/pins',{'component_id':cid,'label':str(i),'position':p,'note':'Synthetic user pin review'})
            assert r.status_code==200;g=r.json()['graph']
        a,b=[t['id'] for t in g['components'][0]['terminals']]
        g=post('/inspection/wires/'+c['id']+'/bind',{'from_terminal':a,'to_terminal':b,'endpoints_checked':True,'note':'Synthetic user endpoint review'}).json()['graph']
        assert g['links'][0]['connection']['status']=='INFERRED'
        g=post('/anchor',{'terminal_id':a,'position':{'x':.4,'y':.4}}).json()['graph']
        assert g['links'][0]['connection']['status']=='UNKNOWN'
        assert g['links'][0]['connection']['value'] is None
        demo=client.post('/api/projects/demo').json()['graph']
        assert client.post('/api/projects/'+demo['project_id']+'/inspection',json={'expected_revision':demo['revision']}).status_code==422
