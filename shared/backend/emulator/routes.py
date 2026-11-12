import json,threading
from typing import Literal
from fastapi import HTTPException
from ..circuit.schema import StrictModel
from ..design.recipes import new_graph
from ..planner.service import digest
from .service import emulate,saved_result

class EmulationInput(StrictModel):
    expected_revision:int
    scenario:Literal['circuit','input_steps']='circuit'


def emulator_routes(app,store,get,proposals):
    lock=threading.Lock()
    def resolve(project,pid=None):
        source=get(project)
        if pid:
            offered=proposals(project,pid)
            if 'arduino_voltage_divider' not in {p['recipe'] for p in offered['proposals']}:
                raise HTTPException(422,'현재 부품에 맞는 UNO 분압 회로 제안이 필요합니다.')
            graph,_=new_graph('0'*32,'arduino_voltage_divider')
            folder=store.root/'emulations'/project/'inventory'/pid
        else:
            graph=source;folder=store.root/'emulations'/project/f'r{source.revision}'
        if graph.profile!='arduino_voltage_divider':raise HTTPException(422,'현재는 UNO R3 분압 회로의 펌웨어 실행만 지원합니다.')
        return source,graph,folder
    def read(project,pid=None):
        source,g,folder=resolve(project,pid);r=saved_result(g,folder)
        if r and r.get('source_graph_sha256')!=digest(source):r=None
        return {'result':r}
    def run(project,body,pid=None):
        with lock:
            source,g,folder=resolve(project,pid)
            if source.revision!=body.expected_revision:raise HTTPException(409,'프로젝트 버전이 변경되었습니다.')
            source_hash=digest(source)
            try:r=emulate(g,folder,body.scenario)
            except ValueError as exc:raise HTTPException(422,str(exc))
            if digest(get(project))!=source_hash:raise HTTPException(409,'실행 중 프로젝트가 변경되었습니다. 다시 실행하세요.')
            r.update({'source_project':project,'source_revision':source.revision,'source_graph_sha256':source_hash,
                'inventory_plan':pid,'basis':'proposed_design_only' if pid else 'current_design',
                'physical_parts_verified':False})
            data=json.dumps(r,ensure_ascii=False,allow_nan=False)
            (folder/'latest.json').write_text(data);(folder/r['run_id']/'result.json').write_text(data)
            return r
    @app.get('/api/projects/{project}/inventory/{pid}/emulator')
    def read_proposal(project:str,pid:str):return read(project,pid)
    @app.post('/api/projects/{project}/inventory/{pid}/emulator')
    def run_proposal(project:str,pid:str,body:EmulationInput):return run(project,body,pid)
    @app.get('/api/projects/{project}/emulator')
    def read_design(project:str):return read(project)
    @app.post('/api/projects/{project}/emulator')
    def run_design(project:str,body:EmulationInput):return run(project,body)
