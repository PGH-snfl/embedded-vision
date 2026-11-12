import json, re, threading,hashlib
from contextlib import asynccontextmanager
from fastapi import HTTPException
from fastapi.responses import FileResponse,Response
from .models import PlanInput,ExecuteInput,AutoAnalysisInput
from .provider import status
from .service import create_plan,digest
from .executor import execute
from .mcp import probe
from .jobs import AutoAnalysis


def planner_routes(app,store,get):
    auto=AutoAnalysis(store,get,dispatcher=getattr(app.state,'analysis_dispatch',None))
    auto.provider_ready=getattr(app.state,'provider_ready',None)
    app.state.auto_analysis=auto
    def provider_status():
        result=status()
        if auto.provider_ready:
            result['configured']=auto.provider_ready()
            result['note']='모델 키는 별도 작업 처리 프로세스에서 관리합니다.'
        return result
    previous_lifespan=app.router.lifespan_context
    @asynccontextmanager
    async def lifespan(application):
        async with previous_lifespan(application) as state:
            try:yield state
            finally:auto.close()
    app.router.lifespan_context=lifespan
    lock=threading.Lock()
    root=store.root/'planner';root.mkdir(exist_ok=True)
    def folder(project):
        get(project) # existing project and project id validation
        path=root/project;path.mkdir(exist_ok=True);return path
    def current(project,revision):
        graph=get(project)
        if graph.revision!=revision:raise HTTPException(409,'프로젝트가 변경되었습니다. 새 계획을 만드세요.')
        return graph
    def load(project,pid):
        if not re.fullmatch('[a-f0-9]{32}',pid):raise HTTPException(404,'Plan not found')
        path=folder(project)/(pid+'.json')
        if not path.exists():raise HTTPException(404,'Plan not found')
        return json.loads(path.read_text())
    from ..design.routes import design_routes
    design_routes(app,store,get,load)
    @app.get('/api/projects/{project}/auto-analysis')
    def automatic_status(project:str):
        get(project)
        return {'job':auto.read(project),'configured':provider_status()['configured']}
    @app.post('/api/projects/{project}/auto-analysis')
    def automatic_start(project:str,body:AutoAnalysisInput,retry:bool=False):
        graph=current(project,body.expected_revision)
        try:return {'job':auto.start(graph,retry=retry,model=body.model)}
        except ValueError as exc:raise HTTPException(422,str(exc))
    @app.get('/api/planner/status')
    def planner_status():return provider_status()
    @app.post('/api/planner/mcp/probe')
    def mcp_probe():
        if not lock.acquire(blocking=False):raise HTTPException(409,'다른 계획 작업이 진행 중입니다.')
        try:return probe(root/'probe')
        except RuntimeError as exc:raise HTTPException(503,str(exc))
        finally:lock.release()
    @app.get('/api/projects/{project}/planner/{pid}')
    def specific_plan(project:str,pid:str):
        data=load(project,pid);data['stale']=data['graph_sha256']!=digest(get(project))
        return {'plan':data,'execution':None}
    @app.get('/api/projects/{project}/planner/{pid}/inspection/{crop_id}')
    def inspection_crop(project:str,pid:str,crop_id:str):
        if not re.fullmatch(r'(?:CROP|TOOL)\d{1,3}',crop_id):raise HTTPException(404,'확대 이미지가 없습니다.')
        data=load(project,pid);report=data.get('component_inspection') or {}
        crops=[*report.get('crops',[]),*report.get('skill',{}).get('extra_crops',[])]
        crop=next((c for c in crops if c['crop_id']==crop_id),None)
        if not crop:raise HTTPException(404,'확대 이미지가 없습니다.')
        aid=crop['asset_id'];graph=get(project)
        source=next((s for s in report.get('sources',[]) if s['asset_id']==aid),None)
        if not source or aid not in {a.id for a in graph.assets}:raise HTTPException(404,'입력 이미지가 없습니다.')
        path=store.root/(project+'.png' if aid=='image' else project+'-'+aid+'.png')
        if path.is_symlink() or path.resolve().parent!=store.root.resolve() or not path.is_file():raise HTTPException(404,'입력 이미지가 없습니다.')
        if hashlib.sha256(path.read_bytes()).hexdigest()!=source['sha256']:raise HTTPException(409,'원본 이미지가 바뀌어 확대 결과를 재사용하지 않습니다.')
        from ..vision.component_crops import crop_image
        raw,meta=crop_image(path,crop['region'],padding=crop.get('padding',.06))
        if meta['sha256']!=crop['sha256']:raise HTTPException(409,'확대 이미지의 처리 버전이 바뀌었습니다.')
        return Response(raw,media_type='image/jpeg',headers={'Cache-Control':'private, no-store'})
    @app.get('/api/projects/{project}/planner')
    def latest(project:str):
        paths=sorted(folder(project).glob('*.json'),key=lambda p:p.stat().st_mtime)
        if not paths:return {'plan':None}
        data=json.loads(paths[-1].read_text());data['stale']=data['graph_sha256']!=digest(get(project))
        execution=folder(project)/data['id']/'execution.json'
        return {'plan':data,'execution':json.loads(execution.read_text()) if execution.exists() else None}
    @app.post('/api/projects/{project}/planner')
    def plan(project:str,body:PlanInput):
        graph=current(project,body.expected_revision)
        if not status()['configured']:raise HTTPException(503,status()['note'])
        aids=body.asset_ids or [a.id for a in graph.assets[:1]]
        if len(aids)!=len(set(aids)) or not set(aids)<={a.id for a in graph.assets}:
            raise HTTPException(422,'입력 이미지 ID를 확인하세요.')
        assets=[(a,store.root/(f'{project}.png' if a=='image' else f'{project}-{a}.png')) for a in aids]
        if any(not path.is_file() for _,path in assets):raise HTTPException(422,'입력 이미지 파일이 없습니다.')
        if not lock.acquire(blocking=False):raise HTTPException(409,'다른 계획 작업이 진행 중입니다.')
        try:
            result=create_plan(graph,body.prompt,body.task,assets,model=body.model)
            result['stale']=digest(get(project))!=result['graph_sha256']
            (folder(project)/(result['id']+'.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2))
            return {'plan':result,'execution':None}
        except RuntimeError as exc:raise HTTPException(502,str(exc))
        finally:lock.release()
    @app.post('/api/projects/{project}/planner/{pid}/execute')
    def execute_plan(project:str,pid:str,body:ExecuteInput):
        graph=current(project,body.expected_revision);plan=load(project,pid)
        if plan['graph_sha256']!=digest(graph):raise HTTPException(409,'그래프가 계획과 다릅니다. 다시 계획하세요.')
        if not plan['executable']:raise HTTPException(422,'검토 전용 계획입니다. 미확인 항목을 먼저 해결하세요.')
        if not lock.acquire(blocking=False):raise HTTPException(409,'다른 계획 작업이 진행 중입니다.')
        try:
            destination=folder(project)/pid
            if destination.exists():raise HTTPException(409,'이 계획은 이미 실행을 시도했습니다. 결과를 확인하고 새 계획을 만드세요.')
            result=execute(graph,destination)
            result['stale']=digest(get(project))!=plan['graph_sha256']
            return {'plan':plan,'execution':result}
        except ValueError as exc:raise HTTPException(422,str(exc))
        finally:lock.release()
    @app.get('/api/projects/{project}/planner/{pid}/artifacts/{kind}')
    def artifact(project:str,pid:str,kind:str):
        load(project,pid)
        base=folder(project)/pid
        paths={'sch':base/'circuit/circuit.kicad_sch','report':base/'execution.json'}
        if kind=='svg':
            svgs=list((base/'circuit').rglob('*.svg'))
            if len(svgs)==1:paths['svg']=svgs[0]
        if kind not in paths or not paths[kind].is_file():raise HTTPException(404,'Artifact not found')
        return FileResponse(paths[kind],filename=paths[kind].name)
