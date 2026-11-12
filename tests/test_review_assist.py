"""Suggestions must remain observations, never hidden pinouts or committed nets."""
import io
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from PIL import Image
from backend.api import create_app
from backend.circuit.schema import Graph,Asset,Component,Terminal,Claim,Point,Evidence,TextObservation,WireCandidate
from backend.vision.review_assist import split_labels,review_assist,wire_proposals
from backend.vision.inspection import add_pin,PinInput


def fixture():
    return Graph(project_id='a'*32,title='Test observations',revision=1,mode='photo',
        assets=[Asset(id='image',sha256='test',width=400,height=300,filename='test.png')],
        evidence=[Evidence(id='ocr',asset_id='image',method='ocr',text='Original OCR: VSSVDDV0RSRWED0D1D2D3D4D5D6D7A')],
        components=[Component(id='LCD',kind='display',bbox=[Point(x=.1,y=.3),Point(x=.9,y=.9)])],
        text_observations=[TextObservation(id='t',asset_id='image',text='VSSVDDV0RSRWED0D1D2D3D4D5D6D7A',
            bbox=[Point(x=.2,y=.31),Point(x=.8,y=.35)],score=.9,evidence_id='ocr')])


def with_wire():
    g=fixture();g.components[0].terminals=[Terminal(id='A',name=Claim(value='A',status='INFERRED'),image_position=Point(x=.2,y=.5)),Terminal(id='B',name=Claim(value='B',status='INFERRED'),image_position=Point(x=.8,y=.5))]
    points=[Point(x=.2,y=.5),Point(x=.8,y=.5)]
    g.evidence.append(Evidence(id='line',asset_id='image',method='geometry',text='Synthetic test line',points=points))
    g.wire_candidates.append(WireCandidate(id='w',color='red',bbox=[Point(x=.19,y=.49),Point(x=.81,y=.51)],evidence_id='line',geometry='segment',path=points,endpoints=points))
    return g


def test_lcd_tokens_preserve_exact_source_and_do_not_fill_missing_k():
    raw=fixture().text_observations[0].text;r=split_labels(raw,'display')
    assert [t['label'] for t in r['tokens']]==['VSS','VDD','V0','RS','RW','E','D0','D1','D2','D3','D4','D5','D6','D7','A']
    assert 'K' not in [t['label'] for t in r['tokens']]
    assert not r['unparsed']
    assert all(raw[t['span'][0]:t['span'][1]]==t['source_text']==t['label'] for t in r['tokens'])


@pytest.mark.parametrize('raw',['ARDUINO','JavaLab.or9','DOD1','D100','LM358'])
def test_unrecognized_chunks_are_not_partial_pin_names(raw):
    r=split_labels(raw,'display');assert not r['tokens'];assert r['unparsed'][0]['text']==raw


def test_numbered_labels_are_longest_exact_match():
    r=split_labels('D10 D11 GPIO21, GND', 'board')
    assert [t['label'] for t in r['tokens']]==['D10','D11','GPIO21','GND']
    assert split_labels('EAK','board')['tokens']==[]


def test_overlapping_ownership_is_visible_and_graph_is_unchanged():
    g=fixture();g.components.append(Component(id='breadboard',kind='breadboard',bbox=[Point(x=.1,y=.1),Point(x=.9,y=.33)]))
    before=g.model_dump();r=review_assist(g)['image'];row=r['texts'][0]
    assert row['ownership_ambiguous'] and len(row['owners'])==2
    assert g.model_dump()==before and not g.links and not g.components[0].terminals


def test_other_image_text_and_pins_are_not_used():
    g=with_wire();g.assets.append(Asset(id='other',sha256='other',width=400,height=300,filename='other.png'))
    g.components[0].asset_id='other'
    r=review_assist(g)['image'];assert not r['texts'][0]['owners'];assert r['wires'][0]['state']=='MISSING_PIN'


def test_unique_endpoint_proposal_never_commits_link():
    g=with_wire();before=g.model_dump();p=wire_proposals(g,'image')[0]
    assert p['state']=='READY' and (p['from_terminal'],p['to_terminal'])==('A','B')
    assert g.model_dump()==before


def test_multiple_nearby_pins_are_not_auto_selected():
    g=with_wire();g.components[0].terminals.append(Terminal(id='C',image_position=Point(x=.205,y=.5)))
    p=wire_proposals(g,'image')[0]
    assert p['state']=='AMBIGUOUS' and p['from_terminal'] is None and p['to_terminal'] is None
    assert len(p['matches'][0])==2


def test_existing_unknown_connection_is_reviewed_instead_of_duplicated():
    from backend.circuit.schema import Link
    g=with_wire();g.links.append(Link(id='existing',from_terminal='A',to_terminal='B'))
    p=wire_proposals(g,'image')[0];assert p['state']=='EXISTING' and p['existing_link_id']=='existing'
    assert p['from_terminal'] is None


@pytest.mark.parametrize('span,label', [([3,6],'VSS'),([-1,3],'VSS'),([0,500],'VSS')])
def test_pin_token_cannot_forge_ocr_span(span,label):
    g=fixture();before=g.model_dump()
    with pytest.raises(HTTPException):add_pin(g,PinInput(expected_revision=1,component_id='LCD',text_id='t',text_span=span,label=label,position=Point(x=.2,y=.4),note='Observed test terminal'))
    assert g.model_dump()==before


def test_pin_keeps_raw_span_and_mapping_unknown():
    g=fixture();add_pin(g,PinInput(expected_revision=1,component_id='LCD',text_id='t',text_span=[3,6],label='VDD',position=Point(x=.2,y=.4),note='Observed test terminal'))
    t=g.components[0].terminals[0]
    assert t.name.status=='INFERRED' and t.pin_mapping.status=='UNKNOWN'
    assert '[3:6]: VDD' in g.evidence[-1].text
    assert g.text_observations[0].text=='VSSVDDV0RSRWED0D1D2D3D4D5D6D7A'
    Graph.model_validate(g.model_dump())


def test_api_exposes_read_only_assistance_and_rejects_stale_pin_save(tmp_path):
    app=create_app(tmp_path);g=fixture();app.state.store.save(g,0,'Test fixture')
    with TestClient(app) as c:
        url='/api/projects/'+g.project_id
        result=c.get(url).json();assert len(result['review_assist']['image']['texts'][0]['owners'][0]['tokens'])==15
        body={'expected_revision':1,'component_id':'LCD','text_id':'t','text_span':[0,3],'label':'VSS','position':{'x':.2,'y':.4},'note':'Test source review'}
        r=c.post(url+'/inspection/pins',json=body);assert r.status_code==200
        assert c.post(url+'/inspection/pins',json=body).status_code==409
        assert r.json()['graph']['revision']==2
        assert len(c.get(url+'/history').json())==2
