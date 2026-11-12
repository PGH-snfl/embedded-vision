"""Validation of failure atomicity, untrusted geometry and export gates."""
import io
import pytest
from PIL import Image
from fastapi.testclient import TestClient
from backend.api import create_app
from backend.circuit.schema import Graph,WireCandidate,TextObservation
import backend.vision.inspection as inspection

@pytest.fixture
def photo(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        buffer=io.BytesIO();Image.new('RGB',(400,300),'white').save(buffer,format='PNG')
        data=client.post('/api/projects',files={'image':('test.png',buffer.getvalue(),'image/png')}).json()
        yield client,'/api/projects/'+data['graph']['project_id'],data


def test_ocr_failure_does_not_commit_partial_observations(photo,monkeypatch):
    client,url,before=photo
    def fail(_):
        yield {'text':'GND','score':.8,'bbox':[5,5,30,20]}
        raise RuntimeError('Synthetic OCR failure after partial output')
    monkeypatch.setattr(inspection,'ocr_rows',fail)
    r=client.post(url+'/inspection',json={'expected_revision':1})
    assert r.status_code==422
    assert client.get(url).json()['graph']==before['graph']
    assert len(client.get(url+'/history').json())==1


@pytest.mark.parametrize('body',[
    {'component_id':'missing','label':'GND','position':{'x':.1,'y':.1},'note':'test note'},
    {'component_id':'missing','label':'','position':{'x':.1,'y':.1},'note':'test note'},
    {'component_id':'missing','label':'GND','position':{'x':1.1,'y':.1},'note':'test note'},
    {'component_id':'missing','label':'GND','position':{'x':.1,'y':.1},'note':'test note','status':'CONFIRMED'},
])
def test_invalid_pin_requests_preserve_revision(photo,body):
    client,url,before=photo
    assert client.post(url+'/inspection/pins',json={'expected_revision':1,**body}).status_code==422
    assert client.get(url).json()['graph']==before['graph']


def test_unresolved_photo_cannot_build_or_simulate(photo):
    client,url,before=photo
    for endpoint in ['/build','/simulate']:
        r=client.post(url+endpoint,json={'expected_revision':1})
        assert r.status_code in (409,422)
    after=client.get(url).json()
    assert after['graph']==before['graph']
    assert after['validation']['kicad']=='BLOCKED'
    assert after['integrated']['eda'] is None


@pytest.mark.parametrize('changes',[
    {'geometry':'segment','path':[{'x':.1,'y':.1},{'x':.8,'y':.8}],'endpoints':[{'x':.1,'y':.1},{'x':.7,'y':.8}]},
    {'geometry':'ambiguous','endpoints':[{'x':.1,'y':.1},{'x':.8,'y':.8}]},
    {'status':'CONFIRMED'},
])
def test_malformed_stroke_cannot_claim_valid_endpoints(changes):
    with pytest.raises(ValueError):WireCandidate.model_validate({'id':'s','color':'red','bbox':[{'x':0,'y':0},{'x':1,'y':1}],'evidence_id':'e',**changes})


def test_overlapping_endpoint_matches_require_disambiguation():
    from backend.circuit.schema import Graph,Asset,Component,Terminal,Point,Evidence
    from backend.vision.inspection import bind_segment,BindInput
    from fastapi import HTTPException
    p,q=Point(x=.475,y=.5),Point(x=.525,y=.5)
    g=Graph(project_id='ambiguity',title='Short stroke fixture',mode='photo',revision=1,
        assets=[Asset(id='image',sha256='test',width=400,height=300,filename='test.png')],
        evidence=[Evidence(id='e',asset_id='image',method='geometry',text='Synthetic stroke',points=[p,q])],
        components=[Component(id='U',kind='board',bbox=[Point(x=0,y=0),Point(x=1,y=1)],
            terminals=[Terminal(id='A',image_position=Point(x=.499,y=.5)),Terminal(id='B',image_position=Point(x=.501,y=.5))])],
        wire_candidates=[WireCandidate(id='s',color='red',bbox=[Point(x=.47,y=.48),Point(x=.53,y=.52)],
            evidence_id='e',geometry='segment',path=[p,q],endpoints=[p,q])])
    # Both endpoint assignments fit the 4% tolerance. Neither direction is uniquely supported.
    with pytest.raises(HTTPException) as error:
        bind_segment(g,'s',BindInput(expected_revision=1,from_terminal='A',to_terminal='B',endpoints_checked=True,note='Ambiguous positions checked'))
    assert error.value.status_code==422
    assert g.links==[]
