from pathlib import Path
import pytest
from PIL import Image
from backend.vision import staged
from backend.vision.staged import Inventory,CropReview,inspect_photo,spatial_text,supported_labels,crop_box


def test_text_ownership_and_exact_pin_match():
    rows=[{'text':'D10 GND','score':.98,'bbox':[10,10,30,20]},
          {'text':'VCC','score':.99,'bbox':[100,100,120,110]},
          {'text':'D2','score':.4,'bbox':[12,12,22,16]}]
    local=spatial_text(rows,[0,0,50,50])
    assert supported_labels(['D1','D10','GND','VCC','D2'],local)==['D10','GND']


def test_crop_coordinate_clamping_and_full_terminal_capacity():
    assert crop_box([0,0,1000,1000],(1024,768))==(0,0,1024,768)
    r=CropReview(recognizable=True,kind='display',label='LCD',appearance='screen',markings='',
                 terminal_labels=[f'D{i}' for i in range(16)],uncertainty='')
    assert len(r.terminal_labels)==16


def test_duplicate_objects_and_wiring_in_inventory_are_rejected():
    c={'id':'U1','kind':'board','label':'board','bbox':[0,0,500,500],'appearance':'PCB'}
    with pytest.raises(ValueError):Inventory(components=[c,c])
    with pytest.raises(ValueError):Inventory(components=[c],connections=[{'from_pin':'GND'}])


def test_stages_preserve_raw_but_quarantine_nested_parts_and_unsupported_pins(tmp_path,monkeypatch):
    image=tmp_path/'photo.png';Image.new('RGB',(100,100),'white').save(image)
    monkeypatch.setattr(staged,'ocr_rows',lambda _:[])
    inventory=Inventory(components=[
        {'id':'U1','kind':'board','label':'board','bbox':[0,400,450,1000],'appearance':'large board'},
        {'id':'R1','kind':'resistor','label':'resistor','bbox':[100,600,130,630],'appearance':'small area'},
        {'id':'P1','kind':'potentiometer','label':'rotary control','bbox':[600,10,850,300],'appearance':'shaft'}])
    calls=[]
    def request(img,prompt,schema,limit):
        calls.append(schema)
        if schema==Inventory:return inventory,{'raw':inventory.model_dump(),'usage':{'completion_tokens':100}}
        review=CropReview(recognizable=True,kind='potentiometer' if len(calls)==3 else 'board',
            label='rotary candidate' if len(calls)==3 else 'board',appearance='visible',markings='',
            terminal_labels=['VCC','GND'],uncertainty='단자 근접 촬영 필요')
        return review,{'raw':review.model_dump(),'usage':{'completion_tokens':50}}
    o,report=inspect_photo(image,request)
    assert [c.id for c in o.components]==['U1','P1']
    assert all(c.terminals==[] for c in o.components)
    assert o.connections==[] and report['wiring_mode']=='geometry_only'
    assert report['rejected_components'][0]['id']=='R1'
    assert report['stages'][0]['raw']==inventory.model_dump()
    assert report['usage']['completion_tokens']==200
    assert len(calls)==3


def test_unrecognizable_crop_keeps_contested_candidate_without_pins(tmp_path,monkeypatch):
    image=tmp_path/'photo.png';Image.new('RGB',(100,100)).save(image)
    monkeypatch.setattr(staged,'ocr_rows',lambda _:[])
    def request(img,prompt,schema,limit):
        if schema==Inventory:
            return Inventory(components=[{'id':'U1','kind':'other','label':'unclear',
                'bbox':[100,100,900,900],'appearance':'occluded object'}]),{'raw':{'test':'inventory'}}
        return CropReview(recognizable=False,kind='other',label='',appearance='',markings='',
                          terminal_labels=[],uncertainty='가림'),{'raw':{'recognizable':False}}
    o,r=inspect_photo(image,request)
    assert len(o.components)==1 and not o.connections
    assert o.components[0].terminals==[]
    assert any('불일치/불명확' in q for q in r['detail_questions'])
    assert r['stages'][-1]['raw']['recognizable'] is False


def test_crop_failure_keeps_inventory_and_raw_error(tmp_path,monkeypatch):
    image=tmp_path/'photo.png';Image.new('RGB',(100,100)).save(image)
    monkeypatch.setattr(staged,'ocr_rows',lambda _:[])
    def request(img,prompt,schema,limit):
        if schema==Inventory:
            inv=Inventory(components=[{'id':'U1','kind':'board','label':'board',
                'bbox':[0,0,1000,1000],'appearance':'board'}])
            return inv,{'raw':inv.model_dump()}
        raise staged.VisionFailure('truncated',{'raw_text':'{"recognizable":'})
    with pytest.raises(staged.VisionFailure) as err:inspect_photo(image,request)
    assert err.value.report['stages'][0]['raw']['components'][0]['id']=='U1'
    assert err.value.report['failed_stage']['raw_text']=='{"recognizable":'


def test_wire_bundle_is_not_a_component_and_joined_text_is_not_a_pin(tmp_path,monkeypatch):
    image=tmp_path/'photo.png';Image.new('RGB',(100,100)).save(image)
    monkeypatch.setattr(staged,'ocr_rows',lambda _:[])
    def request(img,prompt,schema,limit):
        assert schema==Inventory
        inv=Inventory(components=[{'id':'W1','kind':'capacitor','label':'Wiring',
            'bbox':[0,0,1000,1000],'appearance':'colored wires'}])
        return inv,{'raw':inv.model_dump()}
    o,r=inspect_photo(image,request)
    assert not o.components and r['rejected_components'][0]['id']=='W1'
    text='VSS VDD V0 RS RW E D0 D1 D2 D3 D4 D5 D6 D7 A K'
    review=CropReview(recognizable=True,kind='display',label='LCD',appearance='screen',
        markings='',terminal_labels=[text],uncertainty='')
    assert supported_labels(review.terminal_labels,[{'text':text,'score':.99}])==[]
