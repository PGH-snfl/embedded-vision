"""Exercise the HTTP contract with an in-process ASGI transport."""
import asyncio
import io
import json

import httpx
from PIL import Image

from backend.api import create_app
from backend.design.inventory import inventory_plan
from backend.design.models import ObservedPart
from backend.design.robot_physical import robot_rover_design
from test_parts_first import Provider, seal_fixture_inventory


def test_workbench_restore_commit_and_conflicts(tmp_path):
    async def scenario():
        app = create_app(tmp_path)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://testserver') as c:
            image=io.BytesIO();Image.new('RGB',(60,60)).save(image,format='PNG')
            original=(await c.post('/api/projects',files={'image':('photo.png',image.getvalue(),'image/png')})).json()['graph']
            graph=app.state.store.get(original['project_id'])
            plan=inventory_plan(graph,[('image',tmp_path/'x')],Provider())
            wheel=ObservedPart(id='wheel',kind='other',name='바퀴',model_candidates=['바퀴'],quantity=1,
                status='INFERRED',markings=[],regions=[dict(asset_id='image',x0=0,y0=0,x1=.5,y1=.5)],
                evidence='바퀴 후보',checks_needed=['구동 방식 확인'])
            plan['inventory']['parts'].append(wheel.model_dump(mode='json'))
            plan['function_hypotheses']=[{'id':'rover','title':'주행 로봇','kind':'unsupported',
                'status':'INFERRED','plausibility':'medium','rationale':'바퀴',
                'part_ids':['wheel','board'],'evidence':[{'asset_id':'image','observation':'바퀴 후보'}],
                'input_behavior':'주행 명령','output_behavior':'바퀴 회전',
                'assumptions':['방향 미확인'],'distinguishing_check':'확인','display_text':None}]
            folder=tmp_path/'planner'/graph.project_id;folder.mkdir(exist_ok=True)
            (folder/(plan['id']+'.json')).write_text(json.dumps(seal_fixture_inventory(plan),ensure_ascii=False))
            base=f"/api/projects/{graph.project_id}/inventory/{plan['id']}"
            selected=await c.post(base+'/function-candidate',json={'expected_revision':graph.revision,'candidate_id':'rover'})
            assert selected.status_code==200, selected.text
            version=selected.json()['function_version']
            translate_url=base+'/robot-design/translate'
            source=robot_rover_design()['code']['source']
            for target in ('raspberry_pi_c','arduino_cpp'):
                translated=await c.post(translate_url,json={'function_version':version,'source':source,'target':target})
                assert translated.status_code==200, translated.text
                assert translated.json()['code'] and translated.json()['filename']
            modified=await c.post(translate_url,json={'function_version':version,'source':source+'\nprint("extra behavior")\n','target':'raspberry_pi_c'})
            assert modified.status_code==422
            assert (await c.post(translate_url,json={'function_version':'0'*64,'source':source,'target':'arduino_cpp'})).status_code==409
            assert (await c.post(translate_url,json={'function_version':version,'source':source,'target':'unknown'})).status_code==422
            assert (await c.post(translate_url,content=b' ' * 240001,headers={'Content-Type':'application/json'})).status_code==413
            circuit_url=base+'/robot-design/circuit';workbench_url=base+'/robot-design/workbench'
            initial=(await c.get(circuit_url,params={'function_version':version})).json()
            circuit=initial['circuit'];circuit['components'][0]['x']=321
            saved=await c.put(circuit_url,json={'function_version':version,'expected_revision':0,'circuit':circuit})
            assert saved.status_code==200
            opened=await c.get(workbench_url,params={'function_version':version})
            assert opened.status_code==200, opened.text
            data=opened.json();project=data['project']
            assert data['revision']==1 and data['validation']['allowed']
            assert project['components'][0]['x']==321
            assert project['embeddedVision']['source_graph_sha256']
            assert project['embeddedVision']['circuit_revision']==1 and not project['boards']
            # A separate, editable Arduino design has pins matching the code's
            # I2C shield and motor channels. The saved Pi design remains intact.
            snapshot=json.loads(json.dumps(project))
            translation={'function_version':version,'source':source,'target':'arduino_cpp','project':snapshot}
            converted=await c.post(translate_url,json=translation)
            assert converted.status_code==200,converted.text
            body=converted.json();target=body['workbench']
            assert target['boards'][0]['boardKind']=='arduino-uno'
            assert target['fileGroups']['group-U1'][0]['content']==body['code']
            assert target['embeddedVision']['recipe']=='translated_uno_motor_shield_rover'
            assert target['embeddedVision']['physical_verified'] is False
            instance=target['embeddedVision']['translation_instance']
            assert __import__('re').fullmatch('[a-f0-9]{32}',instance)
            again=await c.post(translate_url,json=translation)
            assert again.status_code==200 and again.json()['workbench']['embeddedVision']['translation_instance']!=instance
            actual={(w['start']['componentId']+'.'+w['start']['pinName'],w['end']['componentId']+'.'+w['end']['pinName']) for w in target['wires']}
            assert actual=={('U1.A4','SHIELD1.SDA'),('U1.A5','SHIELD1.SCL'),('U1.5V','SHIELD1.5V'),('U1.GND.2','SHIELD1.GND'),
                ('SHIELD1.M1.left','MOTOR_L.black'),('SHIELD1.M1.right','MOTOR_L.red'),('SHIELD1.M2.left','MOTOR_R.black'),('SHIELD1.M2.right','MOTOR_R.red'),
                ('SHIELD1.PWR.positive','BAT1.red'),('SHIELD1.PWR.negative','BAT1.black')}
            # Resolve each exported endpoint against the actual UNO element or
            # the destination custom-chip manifest, including repeated GND pins.
            uno=__import__('pathlib').Path(__file__).resolve().parents[1]/'third_party/velxio/frontend/node_modules/@wokwi/elements/dist/esm/arduino-uno-element.js'
            import re
            valid={'U1':set(re.findall(r"\{ name: '([^']+)'",uno.read_text().split('static get styles()')[0]))}
            for part in target['components']:
                if part['metadataId']=='custom-chip':
                    valid[part['id']]={pin['name'] for pin in json.loads(part['properties']['chipJson'])['pins']}
            for wire in target['wires']:
                for endpoint in (wire['start'],wire['end']):
                    assert endpoint['pinName'] in valid[endpoint['componentId']], endpoint
            assert '0x60' in body['code'] and '시각 부품' in body['circuit_notice']
            assert 'VIN 점퍼' in ' '.join(body['changes'])
            assert snapshot==project
            pi=await c.post(translate_url,json={**translation,'target':'raspberry_pi_c'})
            assert pi.status_code==200,pi.text
            assert pi.json()['workbench']['boards']==[]
            assert pi.json()['workbench']['embeddedVision']['translation_instance']!=instance
            assert pi.json()['workbench']['wires']==project['wires']
            assert any(f['name']=='pi_rover.c' and f['content']==pi.json()['code'] for group in pi.json()['workbench']['fileGroups'].values() for f in group)
            mismatch=json.loads(json.dumps(snapshot)); mismatch['wires'].pop()
            assert (await c.post(translate_url,json={**translation,'project':mismatch})).status_code==422
            mismatch=json.loads(json.dumps(snapshot)); mismatch['embeddedVision']['source_project']='0'*32
            assert (await c.post(translate_url,json={**translation,'project':mismatch})).status_code==409
            mismatch=json.loads(json.dumps(snapshot)); mismatch['fileGroups']['group-chip-U1'][0]['content']='changed'
            assert (await c.post(translate_url,json={**translation,'project':mismatch})).status_code==422
            # An additional short survives as an invalid draft; it is not
            # discarded to make the separate motion model appear valid.
            project['wires'].append({'id':'extra','start':{'componentId':'BAT1','pinName':'red','x':0,'y':0},
                'end':{'componentId':'HAT1','pinName':'PWR.negative','x':0,'y':0},
                'color':'red','waypoints':[]})
            request={'function_version':version,'expected_revision':1,'project':project}
            committed=await c.post(workbench_url+'/commit',json=request)
            assert committed.status_code==200,committed.text
            assert committed.json()['revision']==2 and not committed.json()['validation']['allowed']
            assert len(committed.json()['circuit']['connections'])==9
            assert (await c.post(workbench_url+'/commit',json=request)).status_code==409
            reopened=(await c.get(workbench_url,params={'function_version':version})).json()
            assert reopened['revision']==2 and len(reopened['project']['wires'])==9
            assert not reopened['validation']['allowed']
            check=await c.post(circuit_url+'/validate',json={'function_version':version,'expected_revision':2})
            assert check.json()['allowed'] is False
            project['components'].append({'id':'external','metadataId':'resistor','properties':{}})
            request['expected_revision']=2
            assert (await c.post(workbench_url+'/commit',json=request)).status_code==422
            assert (await c.post(workbench_url+'/commit',content=b'{bad json',headers={'Content-Type':'application/json'})).status_code==422
            assert (await c.post(workbench_url+'/commit',content=b' '*(1024*1024+1),headers={'Content-Type':'application/json'})).status_code==413
            assert (await c.get(workbench_url,params={'function_version':version})).json()['revision']==2
            assert (await c.get(workbench_url,params={'function_version':'invalid'})).status_code==409
            assert (await c.get('/api/projects/'+graph.project_id)).json()['graph']==original
    asyncio.run(scenario())
