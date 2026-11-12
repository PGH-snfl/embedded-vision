import io,math,json
from pathlib import Path
import cv2
import numpy as np
import pytest
from PIL import Image,ImageDraw
from fastapi.testclient import TestClient
from backend.api import create_app
from backend.circuit.profiles import reference,readiness,number
from backend.circuit.schema import Point,Status
from backend.kicad.exporter import build
from backend.simulation.service import simulate
from backend.vision.analyze import analyze,keyframes
from backend.vision.connections import infer_anchored_wires
from backend.firmware import firmware
from backend.agent import answer

@pytest.fixture
def client(tmp_path):return TestClient(create_app(tmp_path))

@pytest.mark.parametrize('profile',['esp32_led_button','rc_filter'])
def test_real_kicad_roundtrip_erc_pcb_drc(tmp_path,profile):
    graph,_=reference('a'*32,profile)
    result=build(graph,tmp_path/'eda')
    assert result['connectivity']==result['erc']==result['drc']=='PASS'
    assert (tmp_path/'eda/project.zip').stat().st_size>1000
    assert all(not p['net'].startswith('/') for p in result['pcb_geometry']['pads'])
    # Confirm pad net assignment matches the schematic mapping, including repeated switch pads.
    mapped={(v['reference'],v['symbol_pin']):v['net'] for v in result['mapping'].values()}
    for p in result['pcb_geometry']['pads']:assert mapped[p['ref'],p['pin']]==p['net']

def test_eda_blocks_unknown(tmp_path):
    g,_=reference('a'*32);g.links[0].connection.status=Status.INFERRED
    with pytest.raises(ValueError):build(g,tmp_path/'eda')
    assert not (tmp_path/'eda/circuit.kicad_sch').exists()

def test_profile_topology_change_cannot_reuse_spice(tmp_path):
    g,_=reference('a'*32,'rc_filter');g.links[0].to_terminal='C1.2'
    assert readiness(g)
    with pytest.raises(ValueError):simulate(g,tmp_path)

def test_power_short_is_blocked():
    g,_=reference('a'*32);g.links[0].from_terminal='U1.3V3';g.links[0].to_terminal='U1.GND'
    assert any('단락' in b for b in readiness(g))

@pytest.mark.parametrize('mode',['transient','ac','dc'])
def test_real_ngspice_rc_matches_theory(tmp_path,mode):
    g,_=reference('a'*32,'rc_filter');result=simulate(g,tmp_path,mode);v=result['vectors']
    assert result['engine']=='libngspice'
    if mode=='ac':
        idx=min(range(len(v['frequency'])),key=lambda i:abs(v['frequency'][i]-1000))
        gain=math.hypot(v['tp_filter_out']['real'][idx],v['tp_filter_out']['imag'][idx])
        expected=1/math.sqrt(1+(2*math.pi*v['frequency'][idx]*1000*100e-9)**2)
        assert abs(gain-expected)<1e-6
        assert v['tp_filter_out']['imag'][idx]<0
    elif mode=='dc':assert np.allclose(v['tp_input'],v['tp_filter_out'],atol=1e-8)
    else:assert len(v['time'])>100 and np.max(np.abs(np.array(v['tp_input'])-v['tp_filter_out']))>.1

def test_led_current_and_firmware_contract(tmp_path):
    g,_=reference('a'*32);code=firmware(g)
    assert 'LED_PIN = 23' in code['source'] and 'BUTTON_PIN = 18' in code['source']
    result=simulate(g,tmp_path);current=-np.array(result['vectors']['vdrive#branch'])
    assert .001<current.max()<.015
    g.links[0].to_terminal='D1.K'
    with pytest.raises(ValueError):firmware(g)

def test_ocr_model_reads_markings_without_confirming_connections(tmp_path):
    g,data=reference('a'*32);path=tmp_path/'source.png';path.write_bytes(data)
    g.mode='photo';g.profile=None;g.components=[];g.links=[];g.evidence=[]
    out,report=analyze(g,path)
    assert any('ESP32' in row['text'] for row in report['ocr'])
    assert any(c.kind=='board' for c in out.components)
    assert all(c.label.status==Status.INFERRED for c in out.components)
    assert out.links==[] and report['electrical_nets_inferred']==0

def wire_graph(tmp_path,ambiguous=False):
    g,_=reference('b'*32,'rc_filter');g.links=[]
    g.components[0].terminals[0].image_position=Point(x=.1,y=.5)
    g.components[1].terminals[0].image_position=Point(x=.9,y=.5)
    if ambiguous:g.components[1].terminals[1].image_position=Point(x=.9,y=.5)
    im=Image.new('RGB',(400,200),'white');ImageDraw.Draw(im).line((40,100,360,100),fill='red',width=5)
    path=tmp_path/'wire.png';im.save(path);return g,path

def test_anchored_wire_proposal_is_inferred_not_confirmed(tmp_path):
    g,path=wire_graph(tmp_path);report=infer_anchored_wires(g,path)
    assert len(report['proposed_links'])==1
    assert g.links[0].connection.status==Status.INFERRED
    assert {g.links[0].from_terminal,g.links[0].to_terminal}=={'V1.OUT','R1.1'}
    assert infer_anchored_wires(g,path)['proposed_links']==[]

def test_ambiguous_endpoint_is_not_guessed(tmp_path):
    g,path=wire_graph(tmp_path,True)
    assert infer_anchored_wires(g,path)['proposed_links']==[]

def test_video_keyframes_are_bounded(tmp_path):
    path=tmp_path/'video.avi';writer=cv2.VideoWriter(str(path),cv2.VideoWriter_fourcc(*'MJPG'),10,(320,240))
    for i in range(30):
        frame=np.full((240,320,3),240,np.uint8);cv2.putText(frame,f'FRAME {i}',(20,120),cv2.FONT_HERSHEY_SIMPLEX,1,(0,0,0),2);writer.write(frame)
    writer.release();frames=keyframes(path)
    assert 1<=len(frames)<=6
    assert [t for t,_ in frames]==sorted(t for t,_ in frames)

def test_local_agent_changes_only_requested_design_value():
    g,_=reference('a'*32,'rc_filter');g,response=answer(g,'R1을 1kΩ에서 10kΩ으로 바꿔')
    assert response['changed'] and number(g.components[1].value.value)==10000
    g,response=answer(g,'차단 주파수를 1kHz로 맞춰')
    assert abs(number(g.components[1].value.value)-1/(2*math.pi*1000*100e-9))<.001
    g.mode='photo'
    with pytest.raises(ValueError):answer(g,'R1을 1kΩ으로 바꿔')

def create(client,profile='rc_filter'):
    r=client.post('/api/projects/reference',json={'profile':profile});assert r.status_code==201
    return r.json()['graph']['project_id']

def test_api_parameter_recompute_and_stale_artifacts(client):
    pid=create(client)
    r=client.post(f'/api/projects/{pid}/simulate',json={'expected_revision':1});assert r.status_code==200
    r=client.post(f'/api/projects/{pid}/parameters',json={'expected_revision':1,'values':{'R1':'2k'},'frequency':500})
    assert r.status_code==200
    data=r.json();assert data['graph']['revision']==2 and data['integrated']['simulation']['revision']==2
    assert data['integrated']['eda'] is None
    assert client.post(f'/api/projects/{pid}/parameters',json={'expected_revision':1,'values':{'R1':'3k'}}).status_code==409

def test_invalid_parameter_does_not_commit(client):
    pid=create(client,'esp32_led_button')
    r=client.post(f'/api/projects/{pid}/parameters',json={'expected_revision':1,'values':{'R1':'1'}})
    assert r.status_code==422
    assert client.get(f'/api/projects/{pid}').json()['graph']['revision']==1

def test_catalog_search_and_photo_asset_append(client):
    pid=create(client);buf=io.BytesIO();Image.new('RGB',(100,100),'white').save(buf,format='PNG')
    r=client.post(f'/api/projects/{pid}/assets?expected_revision=1',files={'image':('new.png',buf.getvalue(),'image/png')})
    assert r.status_code==200 and len(r.json()['graph']['assets'])==2
    assert client.get('/api/catalog?q=ESP32').json()[0]['id']=='esp32_devkitc_v4'
    aid=r.json()['graph']['assets'][1]['id'];assert client.get(f'/api/projects/{pid}/assets/{aid}').status_code==200

def test_anchor_and_agent_api(client):
    pid=create(client)
    r=client.post(f'/api/projects/{pid}/anchor',json={'expected_revision':1,'terminal_id':'R1.1','position':{'x':.2,'y':.4}})
    assert r.status_code==200
    r=client.post(f'/api/projects/{pid}/agent',json={'expected_revision':2,'prompt':'왜 필터 출력이 둥글어?'})
    assert r.status_code==200 and not r.json()['reply']['changed']
    assert r.json()['reply']['engine']=='local_command_parser'

def test_invalid_manual_box_and_multi_image_evidence(client):
    pid=create(client);base=f'/api/projects/{pid}'
    body={'expected_revision':1,'kind':'capacitor','label':'C test','bbox':[{'x':.8,'y':.8},{'x':.2,'y':.2}]}
    assert client.post(base+'/components',json=body).status_code==422
    assert client.get(base).json()['graph']['revision']==1
    buf=io.BytesIO();Image.new('RGB',(100,100),'white').save(buf,format='PNG')
    data=client.post(base+'/assets?expected_revision=1',files={'image':('angle.png',buf.getvalue(),'image/png')}).json()
    aid=data['graph']['assets'][-1]['id']
    body.update(expected_revision=2,asset_id=aid,bbox=[{'x':.2,'y':.2},{'x':.8,'y':.8}])
    data=client.post(base+'/components',json=body).json();cid=data['graph']['components'][-1]['id']
    data=client.post(base+f'/components/{cid}/review',json={'expected_revision':3,'label':'C test','value':'100nF','status':'CONFIRMED','note':'두 번째 사진의 표기 확인'}).json()
    assert data['graph']['evidence'][-1]['asset_id']==aid
