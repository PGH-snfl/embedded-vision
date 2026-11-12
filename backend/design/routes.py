import json,uuid,threading,re
from pathlib import Path
from fastapi import HTTPException, Request
from fastapi.responses import PlainTextResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from typing import Literal
from .models import NewDesign,Inventory,ProposalSimulation
from .recipes import RECIPES,recipe_info,new_graph
from .proposals import propose,compatible,family
from .hypotheses import candidate_payload,as_design_target
from .preview import candidate_previews
from .function import HypothesisInput,FunctionInput,FunctionIntent,unknown_function,user_function,constrain,version
from .rover_structure import SaveRoverStructure
from .rover_circuit import RoverCircuit,default_rover_circuit,validate_rover_circuit
from .prototype_match import prototype_kind
from .component_completion import inventory_digest,component_datasheet
from ..planner.service import digest
from ..circuit.schema import Evidence
from ..circuit.profiles import readiness


class VirtualSimulationRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, allow_inf_nan=False)
    target_board: Literal['arduino', 'raspberry_pi']
    inputs: dict[str, bool | float] = Field(max_length=32)

class PhotoStructureRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    expected_revision: int = Field(ge=1)

class SaveRoverCircuit(BaseModel):
    model_config = ConfigDict(extra='forbid',strict=True)
    function_version: str = Field(pattern=r'^[a-f0-9]{64}$')
    expected_revision: int = Field(ge=0)
    circuit: RoverCircuit

class CheckRoverCircuit(BaseModel):
    model_config = ConfigDict(extra='forbid',strict=True)
    function_version: str = Field(pattern=r'^[a-f0-9]{64}$')
    expected_revision: int = Field(ge=0)

class CommitRoverWorkbench(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    function_version: str = Field(pattern=r'^[a-f0-9]{64}$')
    expected_revision: int = Field(ge=0)
    project: dict

class TranslateRoverCode(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    function_version: str = Field(pattern=r'^[a-f0-9]{64}$')
    source: str = Field(min_length=1, max_length=50000)
    target: Literal['raspberry_pi_c', 'arduino_cpp']
    project: dict | None = None

MAX_ROVER_WORKBENCH_BYTES = 1024 * 1024


def design_routes(app,store,get,load_plan):
    lock=threading.Lock()
    def target_path(project,pid):return store.root/'function_targets'/project/(pid+'.json')
    def materialized_for(project,pid,plan,offered):
        from .implementation import realize
        if plan.get('analysis_complete') is False:return None
        selected=offered.get('selected_hypothesis_id')
        if selected is None and target_path(project,pid).exists():return None
        selected=selected or offered.get('recommended_hypothesis_id')
        candidate=next((h for h in offered.get('function_hypotheses',[]) if h['id']==selected),None)
        source=get(project)
        design_function=offered['function']
        if candidate and design_function.get('kind')=='unknown':
            design_function=as_design_target(candidate).model_copy(update={'status':'INFERRED'}).model_dump(mode='json')
        provenance={'source_project':project,'source_revision':source.revision,'inventory_plan':pid,
            'source_graph_sha256':digest(source),'function_version':offered['function_version'],
            'function':design_function,'component_datasheet':plan.get('component_datasheet')}
        from ..workflow import workflow_stamp
        provenance['workflow']=workflow_stamp()
        try:return realize(plan,candidate,provenance)
        except (ValueError,RuntimeError):return None
    def photo_scene_for(project,pid,plan=None):
        from .photo_structure import validate_photo_structure
        source=get(project);plan=plan or load_plan(project,pid)
        if plan['graph_sha256']!=digest(source):raise HTTPException(409,'입력이 변경되어 사진 구조물을 다시 분석해야 합니다.')
        raw=plan.get('photo_structure')
        path=store.root/'planner'/project/(pid+'-structure.json')
        if path.exists():
            cached=json.loads(path.read_text())
            if cached.get('graph_sha256')==digest(source):raw=cached.get('photo_structure')
        try:return validate_photo_structure(raw,{a.id for a in source.assets})
        except ValueError:return None
    @app.get('/api/projects/{project}/inventory/{pid}/photo-structure')
    def get_photo_structure(project:str,pid:str):
        return {'photo_structure':photo_scene_for(project,pid)}
    @app.get('/api/projects/{project}/inventory/{pid}/photo-workbench')
    def photo_workbench(project:str,pid:str):
        from .photo_appearance import attach_photo_appearance
        scene=photo_scene_for(project,pid)
        if not scene or not any(o.get('geometry') for o in scene['objects']):raise HTTPException(422,'사진 구조 분석 결과가 필요합니다.')
        plan=load_plan(project,pid);offered=proposals(project,pid)
        built=materialized_for(project,pid,plan,offered)
        if built:return attach_photo_appearance(built['workbench'],scene)
        source=get(project)
        return attach_photo_appearance({'format':'velxio-project','version':1,'name':'사진 기반 3D 구조',
            'boards':[],'components':[],'wires':[],'fileGroups':{},'embeddedVision':{
              'recipe':'photo_appearance_view','source_project':project,'inventory_plan':pid,
              'source_graph_sha256':digest(source),'function_version':offered['function_version'],
              'simulation_notice':'입력 사진의 구조를 편집하는 화면입니다. 실행할 회로·코드가 있는 경우 함께 불러옵니다.'}},scene)
    @app.post('/api/projects/{project}/inventory/{pid}/photo-structure')
    def create_photo_structure(project:str,pid:str,body:PhotoStructureRequest):
        from .photo_structure import infer_photo_structure
        from ..circuit.project_lock import project_lock
        # Mutation middleware already holds the project's shared deletion lock.
        # A distinct lock serializes billed scene inference across workers.
        with project_lock(store.root/'planner',project,exclusive=True):
            source=get(project);plan=load_plan(project,pid)
            if source.revision!=body.expected_revision:raise HTTPException(409,'입력이 변경되었습니다.')
            if plan.get('task')!='component_inventory':raise HTTPException(422,'사진 부품 분석 결과가 필요합니다.')
            cached=photo_scene_for(project,pid,plan)
            if cached is not None:return {'photo_structure':cached,'cached':True}
            assets=[(a.id,store.root/(project+'.png' if a.id=='image' else project+'-'+a.id+'.png')) for a in source.assets[:6]]
            if not assets or any(not p.is_file() for _,p in assets):raise HTTPException(422,'입력 이미지가 없습니다.')
            factory=getattr(app.state,'photo_structure_provider_factory',None)
            try:scene,usage=infer_photo_structure(source,assets,factory() if factory else None)
            except RuntimeError as exc:raise HTTPException(502,str(exc)) from None
            except ValueError:raise HTTPException(422,'사진 구조물의 형상 또는 근거를 검증하지 못했습니다.') from None
            if digest(get(project))!=plan['graph_sha256']:raise HTTPException(409,'분석 중 입력이 변경되었습니다.')
            path=store.root/'planner'/project/(pid+'-structure.json')
            temp=path.with_suffix('.tmp')
            temp.write_text(json.dumps({'graph_sha256':digest(source),'photo_structure':scene,'call':usage},ensure_ascii=False))
            temp.replace(path)
            return {'photo_structure':scene,'cached':False}
    @app.get('/api/projects/{project}/inventory/{pid}/enclosure-study')
    def enclosure_study(project:str,pid:str):
        from .enclosure_analysis import validate_enclosure_analysis, enclosure_workbench
        source=get(project);plan=load_plan(project,pid)
        if plan['graph_sha256']!=digest(source):raise HTTPException(409,'입력이 변경되었습니다. 사진을 다시 분석하세요.')
        offered=proposals(project,pid)
        implementation=materialized_for(project,pid,plan,offered)
        if implementation:return {'available':True,'analysis':plan.get('enclosure_analysis'),
            'implementation':implementation['design'],'workbench':implementation['workbench']}
        raw=plan.get('enclosure_analysis')
        if not raw or not raw.get('enclosures'):return {'available':False,'analysis':None,'workbench':None}
        from .hypotheses import validate_hypotheses
        inventory=Inventory.model_validate(plan['inventory'])
        if plan.get('observed_inventory_sha256') and plan['observed_inventory_sha256']!=inventory_digest(inventory):
            raise HTTPException(409,'저장된 구성품 목록이 변경되어 다시 분석해야 합니다.')
        hypotheses=validate_hypotheses(plan.get('function_hypotheses',[]),inventory,{a.id for a in source.assets})
        try:study=validate_enclosure_analysis(raw,inventory,hypotheses,plan.get('required_parts',[]),plan.get('photo_structure'))
        except ValueError:raise HTTPException(422,'내부 추정의 근거·계층을 읽을 수 없습니다.') from None
        provenance={'source_project':project,'inventory_plan':pid,'source_graph_sha256':digest(source)}
        return {'available':True,'analysis':study,'workbench':enclosure_workbench(study,provenance,plan.get('photo_structure'))}
    def intent_for(project,pid,plan):
        path=target_path(project,pid)
        if path.exists():
            record=json.loads(path.read_text())
            if record['graph_sha256']!=digest(get(project)):raise HTTPException(409,'입력이 변경되어 기능 확인이 필요합니다.')
            return FunctionIntent.model_validate(record['function'])
        return FunctionIntent.model_validate(plan['function']) if plan.get('function') else unknown_function()
    def physical_for(intent,inv):
        # This reviewed design is offered only for a target the user selected.
        # It is never substituted for a different inferred system behavior.
        if intent.kind!='button_led' or intent.status!='USER_DEFINED':return None
        from .pi_physical import pi_button_led_design
        design=pi_button_led_design()
        for part in design['parts']:
            candidates=[p for p in inv.parts if p.kind==part.get('kind') and
                        (p.kind!='board' or family(p)=='raspberry_pi')]
            part['photo_candidates']=[{'id':p.id,'name':p.name,'status':p.status,
                                       'model_candidates':p.model_candidates} for p in candidates]
            part['photo_comparison_notice']=('사진의 같은 종류 후보입니다. 모델·규격·호환성은 직접 확인하세요.' if candidates
                                             else '사진에서 같은 종류를 확인하지 못했습니다. 별도로 준비하세요.')
        return design
    def robot_for(project,pid,intent,inv,candidates,selected_id=None):
        # A new two-wheel design is only relevant after the user chooses an
        # observed wheeled-movement hypothesis. It must not silently replace
        # flight, parking, obstacle avoidance, or other autonomous behaviors.
        if intent.status not in {'USER_DEFINED','INFERRED'} or intent.kind!='unsupported':return None
        if selected_id is not None:
            selected=selected_id
        else:
            path=target_path(project,pid)
            if not path.exists():return None
            record=json.loads(path.read_text()); selected=record.get('selected_hypothesis')
        candidate=next((h for h in candidates['function_hypotheses'] if h['id']==selected),None)
        if not candidate:return None
        text=' '.join([candidate.get('title',''),candidate.get('input_behavior',''),candidate.get('output_behavior','')]).casefold()
        if re.search(r'드론|비행|항공|프로펠러|주차|장애물|회피|자율|추적|라인|추종|drone|flight|quadcop|parking|obstacle|autonom|follow|track|navigation',text):return None
        if not re.search(r'로봇|이동|주행|바퀴|robot|rover|wheel|driv',text):return None
        observed=[p for p in inv.parts if p.id in candidate.get('part_ids',[])]
        if not any(re.search(r'바퀴|wheel',p.name.casefold()) for p in observed):return None
        from .robot_physical import robot_rover_design
        design=robot_rover_design()
        design['photo_structure']=photo_scene_for(project,pid)
        design['selected_candidate_id']=selected
        for part in design['parts']:
            # A broad 'other' label does not establish that two different
            # pieces of equipment are the same physical part.
            possible=[p for p in inv.parts if p.kind==part.get('kind') and p.kind!='other' and
                      (p.kind!='board' or family(p)=='raspberry_pi')]
            part['photo_candidates']=[{'id':p.id,'name':p.name,'status':p.status} for p in possible]
            part['photo_comparison_notice']=('사진에 같은 종류 후보가 있으나 모델과 호환성은 미확인입니다.' if possible else '사진에서 이 부품을 특정하지 못했습니다. 새로 준비할 부품입니다.')
        return design
    @app.get('/api/design/recipes')
    def recipes():return recipe_info()
    @app.get('/api/projects/{project}/inventory/{pid}/datasheet')
    def system_datasheet(project:str,pid:str,download:bool=False):
        source=get(project);plan=load_plan(project,pid)
        if plan['graph_sha256']!=digest(source):raise HTTPException(409,'입력이 변경되어 데이터시트를 다시 작성해야 합니다.')
        offered=proposals(project,pid)
        sheet=plan.get('component_datasheet')
        if not sheet:
            from .hypotheses import validate_hypotheses
            inventory=Inventory.model_validate(plan['inventory'])
            hypotheses=validate_hypotheses(offered.get('function_hypotheses',[]),inventory,{a.id for a in source.assets})
            sheet=component_datasheet(inventory,plan.get('required_parts',[]),hypotheses,plan.get('analysis_complete',True))
        data={**sheet,'project_id':project,'plan_id':pid,'revision':source.revision,'hardware_verified':False}
        data.pop('implementation_design',None)
        chosen=offered.get('functional_design')
        if chosen:data['implementation_design']=chosen
        headers={'Content-Disposition':f'attachment; filename="system-datasheet-{pid}.json"'} if download else None
        return JSONResponse(data,headers=headers)
    @app.get('/api/projects/{project}/inventory/{pid}/proposals')
    def proposals(project:str,pid:str):
        source=get(project);plan=load_plan(project,pid)
        if plan['graph_sha256']!=digest(source):raise HTTPException(409,'입력이 변경되어 새 분석이 필요합니다.')
        if plan.get('task')!='component_inventory' or not plan.get('inventory'):raise HTTPException(422,'부품 식별 결과가 필요합니다.')
        inv=Inventory.model_validate(plan['inventory'])
        if plan.get('observed_inventory_sha256') and plan['observed_inventory_sha256']!=inventory_digest(inv):
            raise HTTPException(409,'저장된 구성품 목록이 분석 당시와 다릅니다. 기능과 데이터시트를 다시 작성하세요.')
        pending=plan.get('analysis_complete') is False
        allow_completion=plan.get('analysis_complete') is True
        candidates=candidate_payload(plan,inv)
        if pending:
            result=constrain({'proposals':[],'unavailable':[],'boards':[]},unknown_function())
            return {**result,**candidates,'hypothesis_previews':[],
                'source_revision':source.revision,'inventory_plan':pid,'analysis_complete':False,
                'function_blockers':['구성품 목록 저장 완료 · 기능·보완 부품·데이터시트 분석 중입니다.'],
                'system_model':None,'virtual_model':None,'photo_structure':None,'system_model_warnings':[],
                'physical_design':None,'robot_design':None,'prototype_candidates':{},'prototype_design':None,
                'required_parts':[],'component_datasheet':plan.get('component_datasheet'),
                'selection_origin':None,'selected_hypothesis_id':None}
        prototype_candidates={h['id']:kind for h in candidates['function_hypotheses']
                              if (kind:=prototype_kind(h))}
        path=target_path(project,pid)
        intent=unknown_function() if pending else intent_for(project,pid,plan)
        selected=None;selection_origin='user' if path.exists() else None
        if path.exists() and not pending:selected=json.loads(path.read_text()).get('selected_hypothesis')
        # Only the fresh result of this project's finished automatic analysis
        # may supply a default. Never persist it as a user decision; a saved
        # target (including an explicit unknown) always takes precedence.
        if not path.exists() and not pending:
            job=app.state.auto_analysis.read(project)
            if job and job.get('status')=='done' and not job.get('stale') and job.get('plan_id')==pid:
                top=next((h for h in candidates['function_hypotheses'] if h['id']==candidates['recommended_hypothesis_id']),None)
                if top:
                    try:
                        tentative=as_design_target(top).model_copy(update={'status':'INFERRED'})
                        trial=constrain(propose(inv,function_kind=tentative.kind,allow_completion=allow_completion),tentative)
                        is_supported=bool((plan.get('functional_build') or {}).get('hypothesis_id')==top['id'] or prototype_candidates.get(top['id']) or
                            any(p.get('simulator_supported') for p in trial['proposals']) or
                            robot_for(project,pid,tentative,inv,candidates,selected_id=top['id']))
                        if is_supported:
                            intent=tentative;selected=top['id'];selection_origin='automatic'
                    except (ValueError,ValidationError):
                        pass
        offered=propose(inv,function_kind=intent.kind,allow_completion=allow_completion)
        result=constrain(offered,intent)
        previews=candidate_previews(inv,candidates['function_hypotheses'],allow_completion=allow_completion)
        kind=prototype_candidates.get(selected)
        prototype={'kind':kind,'selected_candidate_id':selected} if kind else None
        payload={**result,**candidates,'hypothesis_previews':previews,'source_revision':source.revision,'inventory_plan':pid,
                'system_model':plan.get('system_model'),'virtual_model':plan.get('virtual_model'),'photo_structure':photo_scene_for(project,pid,plan),'enclosure_analysis':plan.get('enclosure_analysis'),
                'system_model_warnings':plan.get('system_model_warnings',[]),'physical_design':physical_for(intent,inv),
                'robot_design':robot_for(project,pid,intent,inv,candidates,selected_id=selected),
                'prototype_candidates':prototype_candidates,'prototype_design':prototype,
                'analysis_complete':plan.get('analysis_complete',True),
                'required_parts':plan.get('required_parts',[]),
                'component_datasheet':plan.get('component_datasheet'),
                'selection_origin':selection_origin,'selected_hypothesis_id':selected}
        materialized=materialized_for(project,pid,plan,payload)
        payload['functional_design']=materialized['design'] if materialized else None
        return payload
    @app.get('/api/projects/{project}/inventory/{pid}/functional-workbench')
    def functional_workbench(project:str,pid:str,function_version:str|None=None):
        offered=proposals(project,pid)
        if function_version is not None and function_version!=offered['function_version']:
            raise HTTPException(409,'설계 기능이 변경되었습니다. 현재 결과에서 다시 열어 주세요.')
        result=materialized_for(project,pid,load_plan(project,pid),offered)
        if not result:raise HTTPException(422,'선정 부품·배선·코드를 생성할 기능 설계가 필요합니다.')
        return result['workbench']
    @app.get('/api/projects/{project}/inventory/{pid}/prototype')
    def selected_prototype(project:str,pid:str,function_version:str):
        offered=proposals(project,pid)
        if offered['function_version']!=function_version:
            raise HTTPException(409,'기능 선택이 변경되었습니다. 분석 화면에서 다시 열어 주세요.')
        prototype=offered.get('prototype_design')
        if not prototype:raise HTTPException(422,'선택한 기능의 시제품 설계가 없습니다.')
        source=get(project)
        provenance={'source_project':project,'source_revision':source.revision,
                    'source_graph_sha256':digest(source),'inventory_plan':pid,
                    'function_version':function_version,'function':offered['function'],
                    'component_datasheet':offered.get('component_datasheet'),
                    'required_parts':[p for p in offered.get('required_parts',[]) if not p.get('hypothesis_ids') or offered.get('selected_hypothesis_id') in p['hypothesis_ids']]}
        kind=prototype['kind']
        if kind=='distance_indicator':
            from .distance_indicator import distance_design
            design=distance_design(); workbench=design.pop('workbench')
        elif kind=='watering':
            from .watering_prototype import watering_proposal,watering_workbench
            design=watering_proposal();workbench=watering_workbench(provenance)
        elif kind=='obstacle_rover':
            from .obstacle_rover import obstacle_rover_design,export_obstacle_project
            design=obstacle_rover_design();workbench=export_obstacle_project(provenance)
        else:raise HTTPException(422,'지원하지 않는 시제품입니다.')
        workbench['embeddedVision']={**workbench.get('embeddedVision',{}),**provenance}
        if digest(get(project))!=provenance['source_graph_sha256']:
            raise HTTPException(409,'입력이 변경되었습니다. 분석 화면에서 다시 열어 주세요.')
        return {'kind':kind,'design':design,'workbench':workbench}
    @app.get('/api/projects/{project}/inventory/{pid}/robot-design/python')
    def robot_python(project:str,pid:str,function_version:str):
        offered=proposals(project,pid)
        if offered['function_version']!=function_version:
            raise HTTPException(409,'기능 선택이 변경되었습니다. 로봇 설계를 다시 확인하세요.')
        design=offered['robot_design']
        if not design:raise HTTPException(422,'선택한 기능의 이동 로봇 설계를 지원하지 않습니다.')
        source_hash=digest(get(project))
        _,circuit=read_rover_circuit(project,pid,function_version,source_hash)
        if not validate_rover_circuit(circuit)['allowed']:
            raise HTTPException(409,'편집한 회로가 코드의 기준 배선과 다릅니다. 회로 연결을 먼저 확인하세요.')
        return PlainTextResponse(design['code']['source'],media_type='text/x-python',
            headers={'Content-Disposition':'attachment; filename="rover.py"'})
    def structure_context(project,pid,function_version):
        offered=proposals(project,pid)
        if offered['function_version']!=function_version:
            raise HTTPException(409,'기능 선택이 변경되었습니다. 로봇 설계를 다시 확인하세요.')
        if not offered['robot_design']:
            raise HTTPException(422,'현재 선택한 기능에는 로봇 구조가 없습니다.')
        return digest(get(project))
    def read_rover_circuit(project,pid,function_version,source_hash):
        with store.connect() as conn:
            row=conn.execute('SELECT revision,body,graph_sha256 FROM rover_circuits WHERE project=? AND plan=? AND function_version=?',
                             (project,pid,function_version)).fetchone()
        if not row or row[2]!=source_hash:return 0,default_rover_circuit()
        return row[0],json.loads(row[1])
    @app.get('/api/projects/{project}/inventory/{pid}/robot-design/circuit')
    def get_rover_circuit(project:str,pid:str,function_version:str):
        source_hash=structure_context(project,pid,function_version)
        revision,circuit=read_rover_circuit(project,pid,function_version,source_hash)
        return {'revision':revision,'circuit':circuit,'validation':validate_rover_circuit(circuit)}
    @app.put('/api/projects/{project}/inventory/{pid}/robot-design/circuit')
    def save_rover_circuit(project:str,pid:str,body:SaveRoverCircuit):
        source_hash=structure_context(project,pid,body.function_version)
        circuit=body.circuit.model_dump(mode='json',by_alias=True)
        with store.connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            from ..circuit.schema import Graph
            current=conn.execute('SELECT body FROM revisions WHERE project=? ORDER BY revision DESC LIMIT 1',(project,)).fetchone()
            if not current or digest(Graph.model_validate_json(current[0]))!=source_hash:
                raise HTTPException(409,'입력이 변경되었습니다. 사진을 다시 분석하세요.')
            row=conn.execute('SELECT revision,graph_sha256 FROM rover_circuits WHERE project=? AND plan=? AND function_version=?',
                             (project,pid,body.function_version)).fetchone()
            revision=row[0] if row and row[1]==source_hash else 0
            if revision!=body.expected_revision:raise HTTPException(409,'다른 화면에서 회로를 변경했습니다. 새로고침 후 확인하세요.')
            revision+=1
            conn.execute('INSERT OR REPLACE INTO rover_circuits VALUES(?,?,?,?,?,?)',
                         (project,pid,body.function_version,source_hash,revision,json.dumps(circuit,ensure_ascii=False)))
        return {'revision':revision,'circuit':circuit,'validation':validate_rover_circuit(circuit)}
    @app.get('/api/projects/{project}/inventory/{pid}/robot-design/workbench')
    def get_rover_workbench(project:str,pid:str,function_version:str):
        from ..workbench.rover_export import export_rover_project
        source_hash=structure_context(project,pid,function_version)
        revision,circuit=read_rover_circuit(project,pid,function_version,source_hash)
        source=get(project)
        if digest(source)!=source_hash:
            raise HTTPException(409,'입력이 변경되었습니다. 사진을 다시 분석하세요.')
        offered=proposals(project,pid)
        payload=export_rover_project(circuit,{'source_project':project,
            'source_revision':source.revision,'source_graph_sha256':source_hash,
            'inventory_plan':pid,'function_version':function_version,'circuit_revision':revision,
            'function':offered['function'],'photo_structure':photo_scene_for(project,pid),
            'component_datasheet':offered.get('component_datasheet'),
            'required_parts':[p for p in offered.get('required_parts',[]) if not p.get('hypothesis_ids') or offered.get('selected_hypothesis_id') in p['hypothesis_ids']]})
        return {'revision':revision,'project':payload,'validation':validate_rover_circuit(circuit)}
    @app.post('/api/projects/{project}/inventory/{pid}/robot-design/workbench/commit')
    async def commit_rover_workbench(project:str,pid:str,request:Request):
        from ..workbench.rover_export import import_rover_project
        # Bound bodies while streaming, including requests without Content-Length.
        raw=bytearray()
        async for chunk in request.stream():
            if len(raw)+len(chunk)>MAX_ROVER_WORKBENCH_BYTES:
                raise HTTPException(413,'편집기 프로젝트는 1MB 이하로 저장하세요.')
            raw.extend(chunk)
        try:
            body=CommitRoverWorkbench.model_validate(json.loads(raw))
            circuit=import_rover_project(body.project)
            save=SaveRoverCircuit(function_version=body.function_version,
                expected_revision=body.expected_revision,circuit=RoverCircuit.model_validate(circuit))
        except (ValueError,TypeError,UnicodeDecodeError,RecursionError):
            raise HTTPException(422,'편집기 프로젝트 형식 또는 지원 부품·단자를 확인하세요.') from None
        # Reuse the same CAS, selected-goal and source-revision checks as the
        # regular circuit endpoint. Invalid wiring remains a saved draft.
        return save_rover_circuit(project,pid,save)
    @app.post('/api/projects/{project}/inventory/{pid}/robot-design/translate')
    async def translate_robot_code(project:str,pid:str,request:Request):
        from ..translation.rover import translate_rover_code
        raw=bytearray()
        async for chunk in request.stream():
            if len(raw)+len(chunk)>MAX_ROVER_WORKBENCH_BYTES + 240000:raise HTTPException(413,'편집기 프로젝트는 1MB 이하, 코드는 50,000자 이하로 입력하세요.')
            raw.extend(chunk)
        if len(raw)>240000 and b'"project"' not in raw:
            raise HTTPException(413,'코드는 50,000자 이하로 입력하세요.')
        try:
            body=TranslateRoverCode.model_validate(json.loads(raw))
        except (ValueError,TypeError,UnicodeDecodeError,RecursionError):
            raise HTTPException(422,'원본 코드와 번역 대상 보드를 확인하세요.') from None
        source_hash=structure_context(project,pid,body.function_version)
        if body.project is not None:
            source=body.project.get('embeddedVision')
            if not isinstance(source,dict) or any(source.get(key)!=value for key,value in (
                ('source_project',project),('inventory_plan',pid),('function_version',body.function_version),
                ('source_graph_sha256',source_hash))):
                raise HTTPException(409,'편집기 회로가 현재 사진 분석 또는 선택한 기능과 다릅니다.')
        try:
            result=translate_rover_code(body.source,body.target)
            if body.project is not None:
                from ..translation.rover_project import translate_rover_project
                result.update(translate_rover_project(body.project,body.source,body.target,result))
        except ValueError as exc:
            raise HTTPException(422,str(exc)) from None
        if digest(get(project))!=source_hash:
            raise HTTPException(409,'입력이 변경되었습니다. 사진을 다시 분석하세요.')
        return result
    @app.post('/api/projects/{project}/inventory/{pid}/robot-design/circuit/validate')
    def check_rover_circuit(project:str,pid:str,body:CheckRoverCircuit):
        source_hash=structure_context(project,pid,body.function_version)
        revision,circuit=read_rover_circuit(project,pid,body.function_version,source_hash)
        if revision!=body.expected_revision:
            raise HTTPException(409,'다른 화면에서 회로가 변경되었습니다. 새로고침 후 확인하세요.')
        return {'revision':revision,**validate_rover_circuit(circuit)}
    @app.get('/api/projects/{project}/inventory/{pid}/robot-design/structure')
    def get_rover_structure(project:str,pid:str,function_version:str):
        source_hash=structure_context(project,pid,function_version)
        with store.connect() as conn:
            row=conn.execute('SELECT revision,body,graph_sha256 FROM rover_structures WHERE project=? AND plan=? AND function_version=?',
                             (project,pid,function_version)).fetchone()
        if not row or row[2]!=source_hash:
            scene=photo_scene_for(project,pid)
            from .photo_structure import motion_structure
            return {'revision':0,'structure':motion_structure(scene) if scene is not None else None}
        return {'revision':row[0],'structure':json.loads(row[1])}
    @app.put('/api/projects/{project}/inventory/{pid}/robot-design/structure')
    def save_rover_structure(project:str,pid:str,body:SaveRoverStructure):
        source_hash=structure_context(project,pid,body.function_version)
        with store.connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            from ..circuit.schema import Graph
            current=conn.execute('SELECT body FROM revisions WHERE project=? ORDER BY revision DESC LIMIT 1',(project,)).fetchone()
            if not current or digest(Graph.model_validate_json(current[0]))!=source_hash:
                raise HTTPException(409,'입력이 변경되었습니다. 사진을 다시 분석하세요.')
            row=conn.execute('SELECT revision,graph_sha256 FROM rover_structures WHERE project=? AND plan=? AND function_version=?',
                             (project,pid,body.function_version)).fetchone()
            revision=row[0] if row and row[1]==source_hash else 0
            if revision!=body.expected_revision:
                raise HTTPException(409,'다른 화면에서 구조를 변경했습니다. 새로고침 후 확인하세요.')
            revision+=1
            conn.execute('INSERT OR REPLACE INTO rover_structures VALUES(?,?,?,?,?,?)',
                         (project,pid,body.function_version,source_hash,revision,body.structure.model_dump_json()))
        return {'revision':revision,'structure':body.structure.model_dump(mode='json')}
    @app.get('/api/projects/{project}/inventory/{pid}/physical-design/python')
    def physical_python(project:str,pid:str,function_version:str):
        offered=proposals(project,pid)
        if offered['function_version']!=function_version:
            raise HTTPException(409,'기능 선택이 변경되었습니다. 회로를 다시 확인하세요.')
        design=offered['physical_design']
        if not design:raise HTTPException(422,'선택한 기능의 실물 회로를 아직 지원하지 않습니다.')
        return PlainTextResponse(design['code']['source'],media_type='text/x-python',
            headers={'Content-Disposition':'attachment; filename="raspberry_pi_button_led.py"'})
    @app.post('/api/projects/{project}/inventory/{pid}/virtual-simulation')
    def virtual_simulation(project:str,pid:str,body:VirtualSimulationRequest):
        from ..simulation.virtual_system import validate_virtual_model, simulate_virtual_model
        source=get(project); source_hash=digest(source)
        # The same provenance and revision checks used by the normal design flow.
        offered=proposals(project,pid)
        model=offered.get('virtual_model')
        if not model:
            raise HTTPException(422,'이 분석에는 실행 가능한 가상 기능 모델이 없습니다. 사진을 다시 분석해 주세요.')
        try:
            model=validate_virtual_model({**model,'target_board':body.target_board})
            result=simulate_virtual_model(model,body.inputs)
        except (ValueError,ValidationError) as exc:
            raise HTTPException(422,'가상 기능 모델 또는 입력을 확인할 수 없습니다: '+str(exc))
        if digest(get(project))!=source_hash:
            raise HTTPException(409,'계산 중 입력이 변경되었습니다. 다시 분석하세요.')
        result.update({'source_revision':source.revision,'inventory_plan':pid,'source_graph_sha256':source_hash})
        return result
    @app.get('/api/projects/{project}/inventory/{pid}/virtual-simulation/python')
    def export_virtual_python(project:str,pid:str,target_board:Literal['raspberry_pi']='raspberry_pi'):
        from ..simulation.virtual_system import export_raspberry_pi_virtual_script
        model=proposals(project,pid).get('virtual_model')
        if not model:
            raise HTTPException(422,'이 분석에는 실행 가능한 가상 기능 모델이 없습니다.')
        try:
            script=export_raspberry_pi_virtual_script({**model,'target_board':target_board})
        except (ValueError,ValidationError) as exc:
            raise HTTPException(422,'가상 기능 모델을 내보낼 수 없습니다: '+str(exc))
        return PlainTextResponse(script,media_type='text/x-python',headers={'Content-Disposition':'attachment; filename="raspberry_pi_virtual.py"'})
    @app.post('/api/projects/{project}/inventory/{pid}/function-candidate')
    def select_candidate(project:str,pid:str,body:HypothesisInput):
        with lock:
            source=get(project)
            if source.revision!=body.expected_revision:raise HTTPException(409,'입력 버전이 변경되었습니다.')
            offered=proposals(project,pid)
            candidate=next((h for h in offered['function_hypotheses'] if h['id']==body.candidate_id),None)
            if not candidate:raise HTTPException(422,'현재 관측에 없는 기능 후보입니다.')
            try:intent=as_design_target(candidate)
            except (ValueError,ValidationError):
                raise HTTPException(422,'이 기능을 시뮬레이션할 수 없습니다. LCD 문구는 16자 이내 영문·숫자·기본 문장부호로 확인하세요.')
            path=target_path(project,pid);path.parent.mkdir(parents=True,exist_ok=True)
            tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps({'graph_sha256':digest(source),'function':intent.model_dump(mode='json'),'selected_hypothesis':body.candidate_id},ensure_ascii=False));tmp.replace(path)
            return proposals(project,pid)
    @app.post('/api/projects/{project}/inventory/{pid}/function')
    def set_function(project:str,pid:str,body:FunctionInput):
        with lock:
            source=get(project);plan=load_plan(project,pid)
            if source.revision!=body.expected_revision or plan['graph_sha256']!=digest(source):raise HTTPException(409,'입력 버전이 변경되었습니다.')
            if plan.get('task')!='component_inventory':raise HTTPException(422,'부품·기능 분석이 필요합니다.')
            if plan.get('analysis_complete') is False:raise HTTPException(409,'구성품 목록 저장 완료 · 기능·보완 부품·데이터시트 분석이 끝난 뒤 설계할 수 있습니다.')
            try:intent=user_function(body)
            except ValueError as exc:raise HTTPException(422,str(exc))
            path=target_path(project,pid);path.parent.mkdir(parents=True,exist_ok=True)
            tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps({'graph_sha256':digest(source),'function':intent.model_dump(mode='json')},ensure_ascii=False));tmp.replace(path)
            return proposals(project,pid)
    from ..workbench.export import workbench_routes
    workbench_routes(app,get,proposals)
    from ..emulator.routes import emulator_routes
    emulator_routes(app,store,get,proposals)
    @app.post('/api/projects/{project}/inventory/{pid}/simulate')
    def simulate_proposal(project:str,pid:str,body:ProposalSimulation):
        import subprocess
        from ..simulation.service import simulate
        with lock:
            source=get(project)
            if source.revision!=body.expected_revision:raise HTTPException(409,'입력 버전이 변경되었습니다.')
            offered=proposals(project,pid)
            if body.recipe not in {p['recipe'] for p in offered['proposals']}:raise HTTPException(422,'현재 사진 부품에 맞는 회로 제안이 아닙니다.')
            graph,_=new_graph('0'*32,body.recipe)
            folder=store.root/'proposal_simulations'/project/pid/body.recipe/body.analysis
            source_hash=digest(source)
            try:result=simulate(graph,folder,body.analysis)
            except (ValueError,RuntimeError,subprocess.TimeoutExpired) as exc:raise HTTPException(422,str(exc))
            if digest(get(project))!=source_hash:raise HTTPException(409,'계산 중 입력이 변경되었습니다. 다시 실행하세요.')
            result.update({'basis':'proposed_design_only','source_project':project,'source_revision':source.revision,
                'source_graph_sha256':source_hash,'inventory_plan':pid,'recipe':body.recipe,
                'physical_parts_verified':False,'original_wiring_reused':False})
            (folder/'simulation.json').write_text(json.dumps(result,ensure_ascii=False,allow_nan=False))
            return result
    @app.get('/api/projects/{project}/inventory/{pid}/simulation')
    def proposal_simulation(project:str,pid:str,recipe:str='arduino_voltage_divider',analysis:str='transient'):
        offered=proposals(project,pid)
        if recipe!='arduino_voltage_divider' or analysis not in {'transient','dc'}:raise HTTPException(422,'지원하지 않는 회로 또는 분석입니다.')
        if recipe not in {p['recipe'] for p in offered['proposals']}:raise HTTPException(422,'현재 사진에 맞는 회로 제안이 아닙니다.')
        path=store.root/'proposal_simulations'/project/pid/recipe/analysis/'simulation.json'
        if not path.exists():return {'simulation':None}
        result=json.loads(path.read_text());graph,_=new_graph('0'*32,recipe)
        if result.get('source_graph_sha256')!=digest(get(project)) or result.get('graph_sha256')!=digest(graph):
            return {'simulation':None}
        return {'simulation':result}
    @app.post('/api/projects/{project}/inventory/{pid}/design',status_code=201)
    def create_design(project:str,pid:str,body:NewDesign):
        with lock:
            source=get(project);plan=load_plan(project,pid)
            if source.revision!=body.expected_revision or plan['graph_sha256']!=digest(source):
                raise HTTPException(409,'입력 프로젝트가 변경되었습니다. 부품 목록을 다시 확인하세요.')
            if plan.get('task')!='component_inventory' or not plan.get('inventory'):raise HTTPException(422,'부품 식별 결과가 필요합니다.')
            offered=proposals(project,pid)
            if body.function_version!=offered['function_version']:raise HTTPException(409,'기능 요구사항이 변경되었습니다. 회로 구성을 다시 확인하세요.')
            if not body.function_confirmed:raise HTTPException(422,'입력·출력 동작이 원하는 기능인지 확인하세요.')
            intent=FunctionIntent.model_validate(offered['function'])
            if not body.parts_verified:raise HTTPException(422,'실물 모델·전압·핀 라벨 검토가 필요합니다.')
            inventory=Inventory.model_validate(plan['inventory']);parts={p.id:p for p in inventory.parts}
            recipe=RECIPES[body.recipe];slots=recipe_info()[body.recipe]['slots']
            if set(body.assignments)!=set(slots):raise HTTPException(422,'설계의 모든 부품 역할을 지정하세요.')
            used={};added=[]
            for ref,partid in body.assignments.items():
                if partid is None:
                    if ref in recipe['required_observed']:raise HTTPException(422,ref+': 입력에서 확인한 핵심 부품을 선택하세요.')
                    added.append(ref);continue
                if partid not in parts:raise HTTPException(422,'목록에 없는 부품입니다.')
                if parts[partid].kind!=slots[ref]['kind']:raise HTTPException(422,ref+': 부품 종류가 설계 역할과 다릅니다.')
                used[partid]=used.get(partid,0)+1
                if used[partid]>parts[partid].quantity:raise HTTPException(422,'같은 관측 부품을 실제 수량보다 많이 배정할 수 없습니다.')
            for ref,partid in body.assignments.items():
                if partid and not compatible(parts[partid],body.recipe,slots[ref]):
                    raise HTTPException(422,ref+': 관측된 보드 계열·부품 후보가 새 회로와 호환되지 않거나 미확인입니다.')
            if added and not body.accept_added_parts:raise HTTPException(422,'사진에 없는 추가 부품의 규격과 필요 수량을 확인하세요.')
            if body.recipe not in {p['recipe'] for p in offered['proposals']}:raise HTTPException(422,'확인한 기능에 맞는 회로가 아닙니다.')
            new_id=uuid.uuid4().hex;g,data=new_graph(new_id,body.recipe)
            g.title='기능 재구현 · '+recipe['name']
            g.evidence.append(Evidence(id='function_contract',asset_id='image',method='design_spec',text='목표 기능(원래 코드 복원 아님): '+intent.model_dump_json()))
            g.evidence.append(Evidence(id='source_inventory',asset_id='image',method='design_spec',
                text=f'원본 프로젝트 {project} r{source.revision}, 부품 목록 {pid}에서 새로 설계. 원본 배선·코드 복원 아님. 부품 배정: '+json.dumps(body.assignments,ensure_ascii=False)))
            g.evidence.append(Evidence(id='parts_review',asset_id='image',method='user_confirmation',text=body.verification_note))
            blockers=readiness(g)
            if blockers:raise HTTPException(422,' / '.join(blockers))
            from ..firmware import firmware
            if body.recipe=='arduino_lcd':
                from .firmware import lcd_firmware
                code=lcd_firmware(g,intent.display_text,show_elapsed=False)
            else:code=firmware(g)
            (store.root/(new_id+'.png')).write_bytes(data)
            g=store.save(g,0,'관측 부품을 검토한 새 설계 · 원본 보존')
            folder=store.root/'designs'/new_id;folder.mkdir(parents=True)
            provenance={'source_project':project,'source_revision':source.revision,'inventory_plan':pid,
               'recipe':body.recipe,'behavior':intent.output_behavior,'message':intent.display_text or body.message,'function':intent.model_dump(mode='json'),'function_version':version(intent),'function_confirmed':True,'functional_equivalence_verified':False,'lcd_show_elapsed':False,'assignments':body.assignments,
               'added_parts':[{'reference':ref,**slots[ref]} for ref in added],'verification_note':body.verification_note,
               'original_wiring_reused':False,'compiled':False,'hardware_tested':False}
            (folder/'provenance.json').write_text(json.dumps(provenance,ensure_ascii=False,indent=2))
            (folder/code['filename']).write_text(code['source'])
            # Deterministic reviewed plan; no extra model call for a prevalidated recipe.
            plan_id=uuid.uuid4().hex
            result={'id':plan_id,'project_id':new_id,'revision':g.revision,'graph_sha256':digest(g),'task':'build_schematic',
                'prompt':'부품 확인 후 새 회로 생성','asset_ids':['image'],'decision':{'summary':recipe['behavior']+' 원본 배선은 사용하지 않았습니다.',
                   'findings':[],'unresolved':[],'conflicts':[],'actions':['build_schematic'],'deep_review':[]},
                'attempts':[],'routing':{'primary':'reviewed_recipe','specialist':None,'escalation_reasons':[],
                  'specialist_called':False,'specialist_error':None,'no_escalation_reason':'검토된 설계 규칙을 사용하므로 추가 모델 호출이 없습니다.'},
                'executable':True,'blockers':[],'validation_errors':[],
                'execution_steps':['MCP 새 프로젝트 생성','새 회로도 생성·저장','회로 Graph와 netlist 대조','ERC 검사'],
                'notice':'관측 부품을 바탕으로 새로 선정한 배선·코드입니다. 실물 동작은 미검증입니다. 인터페이스 표시용 심벌은 실제 모듈 장착 풋프린트가 아닙니다.'}
            plans=store.root/'planner'/new_id;plans.mkdir(parents=True)
            (plans/(plan_id+'.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2))
            return {'project_id':new_id,'plan':result,'firmware':code,'provenance':provenance}
    @app.get('/api/projects/{project}/new-design')
    def new_design_info(project:str):
        g=get(project);path=store.root/'designs'/project/'provenance.json'
        if not path.exists():return {'design':None}
        design=json.loads(path.read_text())
        from ..firmware import firmware
        try:
            if g.profile=='arduino_lcd':
                from .firmware import lcd_firmware
                code=lcd_firmware(g,design['message'],show_elapsed=design.get('lcd_show_elapsed',True))
            else:code=firmware(g)
        except ValueError:code=None
        return {'design':design,'firmware':code}
