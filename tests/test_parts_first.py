import io,json
from pathlib import Path
import pytest
from PIL import Image
from fastapi.testclient import TestClient
from pydantic import ValidationError
from backend.api import create_app
from backend.design.models import Inventory,ObservedPart
from backend.design.inventory import inventory_plan
from backend.design.recipes import new_graph
from backend.design.firmware import lcd_firmware
from backend.planner.service import digest
from backend.planner.executor import compile_graph
from backend.circuit.profiles import readiness
from backend.planner.provider import PRIMARY


def inventory():
    return Inventory(summary='UNO와 병렬 LCD 후보',parts=[ObservedPart(id=id,kind=kind,name=name,model_candidates=[name],quantity=1,status='INFERRED',markings=[],regions=[dict(asset_id='image',x0=0,y0=0,x1=.5,y1=.5)],evidence='사진 표식',checks_needed=['정격과 핀 라벨 확인']) for id,kind,name in [('board','board','UNO'),('lcd','display','LCD'),('pot','potentiometer','10k 후보')]],suggested_function='LCD 새 메시지',unknowns=['가변저항 값 미확인'])

def seal_fixture_inventory(plan):
    """A different fixture represents a fresh observation, not a changed saved plan."""
    from backend.design.component_completion import inventory_digest,component_datasheet
    observed=Inventory.model_validate(plan['inventory'])
    plan['observed_inventory_sha256']=inventory_digest(observed)
    plan['component_datasheet']=component_datasheet(observed,[],[],True)
    return plan
class Provider:
    def __init__(self):self.calls=[]
    def infer(self,model,context,prompt,task,assets):
        self.calls.append((model,context,task,assets));return inventory(),dict(model='TEST ONLY',elapsed_seconds=0)

def test_parts_only_context_no_original_wires():
    g,_=new_graph('a'*32,'arduino_lcd');before=digest(g);p=Provider()
    r=inventory_plan(g,[('image',Path('not-read'))],p)
    assert len(p.calls)==2 and [c[0] for c in p.calls]==[PRIMARY,PRIMARY]
    assert [c[2] for c in p.calls]==['component_inventory','system_reasoning']
    assert p.calls[1][1]['observed_inventory']==r['inventory']
    assert set(p.calls[0][1])=={'mode','assets','purpose','simulator_catalog','workflow'}
    assert p.calls[0][1]['simulator_catalog']['entries']
    assert r['simulator_catalog']['matches'][0]['part_id']=='board'
    assert r['task']=='component_inventory' and not r['executable']
    assert digest(g)==before and not r['routing']['specialist_called']

def test_virtual_simulation_uses_saved_photo_plan_and_selected_board(tmp_path):
    app=create_app(tmp_path)
    with TestClient(app) as c:
        original,design_url,_=setup(c,app,tmp_path)
        base=design_url.removesuffix('/design')
        plan_id=base.split('/')[-1]
        plan_path=tmp_path/'planner'/original['project_id']/(plan_id+'.json')
        plan=json.loads(plan_path.read_text())
        plan['system_model']={'summary':'차량과 빈 공간을 감지해 모터를 제어하는 가상 예시'}
        plan['virtual_model']={
            'target_board':'arduino',
            'inputs':[{'id':'car','label':'차량 감지','type':'boolean','default':False},
                      {'id':'space','label':'빈 공간','type':'boolean','default':False}],
            'outputs':[{'id':'motor','label':'모터','type':'boolean','default':False}],
            'rules':[{'id':'move','conditions':[{'input':'car','operator':'eq','value':True},
                      {'input':'space','operator':'eq','value':True}],'match':'all',
                      'set':{'motor':True},'status':'INFERRED'}],
            'assumptions':['차량과 빈 공간이 모두 감지되면 이동한다고 가정'],
            'unsupported_requirements':['자율 주행과 위치 제어는 모델에 없음']}
        plan_path.write_text(json.dumps(plan,ensure_ascii=False))
        proposal=c.get(base+'/proposals').json()
        assert proposal['virtual_model']['inputs'][0]['id']=='car'
        body={'target_board':'raspberry_pi','inputs':{'car':True,'space':True}}
        result=c.post(base+'/virtual-simulation',json=body)
        assert result.status_code==200,result.text
        data=result.json()
        assert data['target_board']=='raspberry_pi' and data['outputs']['motor'] is True
        assert data['simulation_type']=='abstract_functional' and data['status']=='partial'
        assert data['source_revision']==original['revision']
        exported=c.get(base+'/virtual-simulation/python?target_board=raspberry_pi')
        assert exported.status_code==200 and 'attachment' in exported.headers['content-disposition']
        import subprocess,sys
        executed=subprocess.run([sys.executable,'-c',exported.text],input=json.dumps(body['inputs']),
                                capture_output=True,text=True,timeout=5,check=True)
        assert json.loads(executed.stdout)['outputs']==data['outputs']
        assert c.get(base+'/virtual-simulation/python?target_board=arduino').status_code==422
        body['inputs']['space']=False
        assert c.post(base+'/virtual-simulation',json=body).json()['outputs']['motor'] is False
        body['inputs']={'unknown':True}
        assert c.post(base+'/virtual-simulation',json=body).status_code==422
        body.update(target_board='unsupported',inputs={})
        assert c.post(base+'/virtual-simulation',json=body).status_code==422
        # A stale plan cannot be evaluated even if its rules are syntactically valid.
        plan['graph_sha256']='outdated';plan_path.write_text(json.dumps(plan))
        assert c.post(base+'/virtual-simulation',json={'target_board':'arduino','inputs':{}}).status_code==409

def test_inventory_rejects_unobserved_asset():
    g,_=new_graph('a'*32,'arduino_lcd')
    with pytest.raises(RuntimeError):inventory_plan(g,[('wrong',Path('x'))],Provider())

def test_inventory_schema_strict_and_no_confirmed_candidates():
    schema=Inventory.model_json_schema()
    for n in [schema,*schema['$defs'].values()]:
        if n.get('type')=='object':assert n['additionalProperties'] is False and set(n['required'])==set(n['properties'])
    part=inventory().parts[0].model_dump();part['status']='CONFIRMED'
    with pytest.raises(ValidationError):ObservedPart(**part)

def setup(client,app,tmp):
    b=io.BytesIO();Image.new('RGB',(60,60)).save(b,format='PNG')
    original=client.post('/api/projects',files={'image':('photo.png',b.getvalue(),'image/png')}).json()['graph']
    g=app.state.store.get(original['project_id']);p=inventory_plan(g,[('image',tmp/'x')],Provider())
    folder=tmp/'planner'/g.project_id;folder.mkdir(exist_ok=True)
    (folder/(p['id']+'.json')).write_text(json.dumps(p))
    body=dict(expected_revision=g.revision,recipe='arduino_lcd',assignments={'U1':'board','LCD1':'lcd','RV1':'pot','R1':None},accept_added_parts=True,parts_verified=True,verification_note='테스트 전용 가상 부품 검토',message='New circuit!')
    endpoint=f"/api/projects/{g.project_id}/inventory/{p['id']}"
    target=client.post(endpoint+'/function',json={'expected_revision':g.revision,'kind':'lcd_text','description':'LCD에 고정 문구 New circuit! 표시','display_text':'New circuit!'}).json()
    body.update(function_version=target['function_version'],function_confirmed=True)
    return original,endpoint+'/design',body

def test_new_design_keeps_source_unchanged_and_firmware_matches(tmp_path):
    app=create_app(tmp_path)
    with TestClient(app) as c:
        original,url,body=setup(c,app,tmp_path);r=c.post(url,json=body)
        assert r.status_code==201,r.text
        data=r.json();pid=data['project_id'];assert pid!=original['project_id']
        assert c.get('/api/projects/'+original['project_id']).json()['graph']==original
        g=app.state.store.get(pid);assert not readiness(g)
        assert len(g.links)==15 and data['plan']['executable']
        assert data['provenance']['added_parts'][0]['reference']=='R1'
        code=c.get(f'/api/projects/{pid}/firmware').json();assert 'New circuit!' in code['source']
        assert 'LCD_RS = 12, LCD_EN = 11' in code['source'] and not code['compiled']
        assert 'New circuit!' in c.get(f'/api/projects/{pid}/firmware?download=true').text
        assert c.get(f'/api/projects/{pid}/new-design').json()['design']['original_wiring_reused'] is False
        spec,notes=compile_graph(g);assert len(spec['symbols'])==4
        assert not next(s for s in spec['symbols'] if s['reference']=='LCD1')['footprint']
        assert c.post(f'/api/projects/{pid}/build',json={'expected_revision':g.revision}).status_code==422

def test_pi_physical_design_requires_explicit_matching_target_and_fresh_version(tmp_path):
    app=create_app(tmp_path)
    with TestClient(app) as c:
        original,url,_=setup(c,app,tmp_path)
        base=url.removesuffix('/design')
        lcd=c.get(base+'/proposals').json()
        assert lcd['physical_design'] is None
        assert c.get(base+'/physical-design/python',params={'function_version':lcd['function_version']}).status_code==422
        target=c.post(base+'/function',json={'expected_revision':original['revision'],
                      'kind':'button_led','description':'버튼을 누르는 동안 LED가 켜집니다.'}).json()
        physical=target['physical_design']
        assert physical and physical['code']['source'] and physical['steps'] and physical['connections']
        # The photo has an UNO, not a Pi: the proposed Pi must not be identified as observed.
        board=next(p for p in physical['parts'] if p['kind']=='board')
        assert not board['photo_candidates']
        assert c.get(base+'/physical-design/python',params={'function_version':lcd['function_version']}).status_code==409
        result=c.get(base+'/physical-design/python',params={'function_version':target['function_version']})
        assert result.status_code==200 and result.text==physical['code']['source']
        assert 'attachment' in result.headers['content-disposition']
        stale=c.post(base+'/function',json={'expected_revision':original['revision'],
                     'kind':'unsupported','description':'자동 주차 로봇을 설계합니다.'}).json()
        assert stale['physical_design'] is None
        assert c.get(base+'/physical-design/python',params={'function_version':target['function_version']}).status_code==409

@pytest.mark.parametrize('change,status',[
    ({'parts_verified':False},422),({'accept_added_parts':False},422),({'expected_revision':999},409),
    ({'assignments':{'U1':None,'LCD1':'lcd','RV1':'pot','R1':None}},422),
    ({'assignments':{'U1':'lcd','LCD1':'lcd','RV1':'pot','R1':None}},422),
    ({'assignments':{'U1':'board','LCD1':'invented','RV1':'pot','R1':None}},422),
    ({'message':'bad";code'},422)])
def test_design_review_gates(tmp_path,change,status):
    app=create_app(tmp_path)
    with TestClient(app) as c:
        original,url,body=setup(c,app,tmp_path);body.update(change)
        assert c.post(url,json=body).status_code==status
        assert c.get('/api/projects/'+original['project_id']).json()['graph']==original

def test_lcd_firmware_rejects_changed_connections_or_values():
    g,_=new_graph('a'*32,'arduino_lcd');assert not readiness(g)
    g.links[0].to_terminal='LCD1.VSS'
    with pytest.raises(ValueError):lcd_firmware(g)
    g,_=new_graph('a'*32,'arduino_lcd');g.components[-1].value.value='10'
    with pytest.raises(ValueError):lcd_firmware(g)

def test_lcd_rejects_mislabelled_or_unverified_physical_pins():
    from backend.circuit.schema import Status
    g,_=new_graph('a'*32,'arduino_lcd');g.components[0].terminals[0].pin_mapping.value='wrong'
    with pytest.raises(ValueError):lcd_firmware(g)
    g,_=new_graph('a'*32,'arduino_lcd');g.components[2].value.status=Status.INFERRED
    with pytest.raises(ValueError):lcd_firmware(g)


def test_video_frames_are_passed_to_inventory_once(tmp_path,monkeypatch):
    from backend.circuit.schema import Asset
    from backend.planner.jobs import AutoAnalysis
    import time
    monkeypatch.setenv('EMBEDDED_VISION_AUTO_ANALYSIS','0')
    monkeypatch.setattr('backend.planner.jobs.status',lambda:{'configured':True})
    app=create_app(tmp_path);p=Provider()
    with TestClient(app) as c:
        original,_,_=setup(c,app,tmp_path);g=app.state.store.get(original['project_id'])
        import uuid
        image=(tmp_path/(g.project_id+'.png')).read_bytes()
        g.project_id=uuid.uuid4().hex;g.mode='video';g.assets.append(g.assets[0].model_copy(update={'id':'frame2'}))
        (tmp_path/(g.project_id+'.png')).write_bytes(image)
        (tmp_path/(g.project_id+'-frame2.png')).write_bytes(image)
        g=app.state.store.save(g,0,'video fixture')
        monkeypatch.setenv('EMBEDDED_VISION_AUTO_ANALYSIS','1')
        app.state.auto_analysis.provider_factory=lambda:p
        job=app.state.auto_analysis.start(g,retry=True)
        deadline=time.monotonic()+3
        while time.monotonic()<deadline:
            job=app.state.auto_analysis.read(g.project_id)
            if job['status'] in {'done','error'}:break
            time.sleep(.01)
        assert job['status']=='done' and len(p.calls)==2
        assert [a[0] for a in p.calls[0][3]]==['image','frame2']


def test_same_resistor_cannot_fill_two_roles(tmp_path):
    app=create_app(tmp_path)
    with TestClient(app) as c:
        original,url,body=setup(c,app,tmp_path)
        plan_path=next((tmp_path/'planner'/original['project_id']).glob('*.json'))
        plan=json.loads(plan_path.read_text())
        resistor=inventory().parts[0].model_dump();resistor.update(id='r',kind='resistor',name='저항',quantity=1)
        plan['inventory']['parts'].append(resistor);plan_path.write_text(json.dumps(seal_fixture_inventory(plan)))
        body.update(recipe='esp32_led_button',assignments={'U1':'board','D1':None,'SW1':None,'R1':'r','R2':'r'})
        response=c.post(url,json=body)
        assert response.status_code==422 and '수량' in response.text
