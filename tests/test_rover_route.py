"""A new rover design is offered only for an explicitly selected matching goal."""
import json
from fastapi.testclient import TestClient
from backend.api import create_app
from backend.design.models import ObservedPart
from test_parts_first import setup


def test_rover_selection_and_stale_download(tmp_path):
    app=create_app(tmp_path)
    with TestClient(app) as c:
        original,url,_=setup(c,app,tmp_path)
        base=url.removesuffix('/design');pid=base.split('/')[-1]
        plan_path=tmp_path/'planner'/original['project_id']/(pid+'.json')
        plan=json.loads(plan_path.read_text())
        wheel=ObservedPart(id='wheel',kind='other',name='바퀴',model_candidates=['바퀴'],quantity=1,
          status='INFERRED',markings=[],regions=[dict(asset_id='image',x0=0,y0=0,x1=.5,y1=.5)],
          evidence='바퀴 후보',checks_needed=['구동 방식 확인'])
        plan['inventory']['parts'].append(wheel.model_dump(mode='json'))
        plan['function_hypotheses']=[{'id':'rover','title':'외부 명령에 따른 이동 로봇',
          'kind':'unsupported','status':'INFERRED','plausibility':'medium','rationale':'바퀴가 관측됨',
          'part_ids':['wheel','board'],'evidence':[{'asset_id':'image','observation':'바퀴 후보'}],
          'input_behavior':'주행 또는 정지 명령','output_behavior':'바퀴를 움직여 차체를 이동',
          'assumptions':['방향 및 속도는 미확인'],'distinguishing_check':'실제 동작을 확인','display_text':None}]
        plan_path.write_text(json.dumps(plan,ensure_ascii=False))
        assert c.get(base+'/proposals').json()['robot_design'] is None
        chosen=c.post(base+'/function-candidate',json={'expected_revision':original['revision'],'candidate_id':'rover'})
        assert chosen.status_code==200,chosen.text
        result=chosen.json();design=result['robot_design']
        assert design and design['hardware_tested'] is False and design['parts'] and design['connections']
        assert design['selected_candidate_id']=='rover'
        code=c.get(base+'/robot-design/python',params={'function_version':result['function_version']})
        assert code.status_code==200 and code.text==design['code']['source']
        assert c.get(base+'/robot-design/python',params={'function_version':'invalid'}).status_code==409
        circuit_url=base+'/robot-design/circuit';version=result['function_version']
        initial=c.get(circuit_url,params={'function_version':version}).json()
        assert initial['revision']==0 and initial['validation']['allowed']
        circuit=initial['circuit'];circuit['components'][0]['x']=321
        body={'function_version':version,'expected_revision':0,'circuit':circuit}
        saved_circuit=c.put(circuit_url,json=body)
        assert saved_circuit.status_code==200,saved_circuit.text
        assert saved_circuit.json()['revision']==1 and saved_circuit.json()['validation']['allowed']
        assert c.put(circuit_url,json=body).status_code==409
        check={'function_version':version,'expected_revision':1}
        assert c.post(circuit_url+'/validate',json=check).json()['allowed']
        circuit['connections'].pop()
        body.update(expected_revision=1,circuit=circuit)
        assert not c.put(circuit_url,json=body).json()['validation']['allowed']
        assert c.post(circuit_url+'/validate',json=check).status_code==409
        check['expected_revision']=2
        assert not c.post(circuit_url+'/validate',json=check).json()['allowed']
        assert c.get(base+'/robot-design/python',params={'function_version':version}).status_code==409
        body.update(expected_revision=2,circuit=initial['circuit'])
        # Initial's dictionary was mutated above; restore the missing wire.
        from backend.design.rover_circuit import default_rover_circuit
        body['circuit']=default_rover_circuit()
        assert c.put(circuit_url,json=body).json()['validation']['allowed']
        assert c.get(base+'/robot-design/python',params={'function_version':version}).status_code==200
        structure_url=base+'/robot-design/structure'
        empty=c.get(structure_url,params={'function_version':version}).json()
        assert empty=={'revision':0,'structure':None}
        shape={'id':'body1','shape':'box','label':'새 차체','position':[0,0.1,0],
               'size':[0.2,0.1,0.1],'color':'#cc8844'}
        body={'function_version':version,'expected_revision':0,'structure':{'version':1,'objects':[shape]}}
        saved=c.put(structure_url,json=body)
        assert saved.status_code==200,saved.text
        assert saved.json()['revision']==1
        assert c.get(structure_url,params={'function_version':version}).json()==saved.json()
        assert c.put(structure_url,json=body).status_code==409
        body['expected_revision']=1
        body['structure']['objects']=[shape,shape]
        assert c.put(structure_url,json=body).status_code==422
        body['structure']['objects']=[{**shape,'size':[0,0.1,0.1]}]
        assert c.put(structure_url,json=body).status_code==422
        body['structure']['objects']=[{**shape,'rotation':[0,7,0]}]
        assert c.put(structure_url,json=body).status_code==422
        body['structure']['objects']=[{**shape,'rotation':[0,1.5707963267948966,0]}]
        rotated=c.put(structure_url,json=body)
        assert rotated.status_code==200,rotated.text
        assert rotated.json()['structure']['objects'][0]['rotation'][1]==1.5707963267948966
        assert c.get(structure_url,params={'function_version':version}).json()['revision']==2
        # An autonomous/obstacle task cannot be replaced by simple manual drive.
        plan['function_hypotheses'][0]['title']='장애물을 회피하는 자율 주행 로봇'
        plan_path.write_text(json.dumps(plan,ensure_ascii=False))
        assert c.get(base+'/proposals').json()['robot_design'] is None
        assert c.get(structure_url,params={'function_version':version}).status_code==422
        assert c.delete('/api/projects/'+original['project_id'],params={'expected_revision':original['revision']}).status_code==200
        with app.state.store.connect() as conn:
            assert conn.execute('SELECT count(*) FROM rover_structures').fetchone()[0]==0
            assert conn.execute('SELECT count(*) FROM rover_circuits').fetchone()[0]==0

