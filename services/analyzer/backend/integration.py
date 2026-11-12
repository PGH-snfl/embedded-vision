import hashlib,io,json,uuid,subprocess,threading
from pathlib import Path
from fastapi import File,Form,HTTPException,UploadFile
from .planner.selection import AnalysisModel,PRIMARY
from fastapi.responses import FileResponse,Response
from PIL import Image,ImageOps,UnidentifiedImageError
from pydantic import Field
from .circuit.schema import Asset,Claim,Evidence,Graph,Point,Status,StrictModel
from .circuit.profiles import reference,readiness,named_nets
from .datasheet.catalog import CATALOG,search_catalog
from .vision.analyze import analyze,keyframes
from .kicad.exporter import build
from .simulation.service import simulate
from .firmware import firmware
from .agent import answer
from .upload_files import PendingUploadFiles

_jobs=threading.Lock()
class RevisionInput(StrictModel):
    expected_revision:int
class AnalyzeInput(RevisionInput):
    asset_id:str='image'
    pcb:bool=False
class ReferenceInput(StrictModel):
    profile:str='esp32_led_button'
class SimInput(RevisionInput):
    analysis:str='transient'
class CatalogInput(RevisionInput):
    catalog_id:str
    note:str=Field(min_length=5,max_length=1000)
class AgentInput(RevisionInput):
    prompt:str=Field(min_length=1,max_length=1000)
class AnchorInput(RevisionInput):
    terminal_id:str
    position:Point
class ParamsInput(RevisionInput):
    values:dict[str,str]=Field(default_factory=dict)
    frequency:float|None=Field(default=None,ge=.1,le=1e6)
    amplitude:float|None=Field(default=None,ge=.001,le=3.3)

def artifact_folder(store,graph):return store.root/'artifacts'/graph.project_id/f'r{graph.revision}'
def integrated_state(store,graph):
    folder=artifact_folder(store,graph);eda=folder/'eda'/'result.json';sim=folder/'simulation'/'simulation.json'
    return {'readiness':readiness(graph),'test_points':named_nets(graph),'eda':json.loads(eda.read_text()) if eda.exists() else None,
            'vision':json.loads((store.root/f'{graph.project_id}-vision.json').read_text()) if (store.root/f'{graph.project_id}-vision.json').exists() else None,
            'simulation':json.loads(sim.read_text()) if sim.exists() else None,
            'bom':[{'id':c.id,'label':c.label.value,'value':c.value.value,'status':c.label.status,'catalog':CATALOG.get(c.catalog_id)} for c in graph.components],
            'catalog':CATALOG,'analysis':json.loads((store.root/f'{graph.project_id}-analysis.json').read_text()) if (store.root/f'{graph.project_id}-analysis.json').exists() else None}

def routes(app,store,get,save,view):
    from .planner.routes import planner_routes
    planner_routes(app,store,get)
    from .vision.routes import vision_routes
    vision_routes(app,store,get,save,view)
    from .vision.inspection import inspection_routes
    inspection_routes(app,store,get,save,view)
    from .vision.occlusion import occlusion_routes
    occlusion_routes(app,store,get,save,view)
    from .vision.single_view import single_view_routes
    single_view_routes(app,store,get,save,view)
    def current(project,expected):
        graph=get(project)
        if graph.revision!=expected:raise HTTPException(409,'수정 버전이 변경되었습니다. 다시 열어주세요.')
        return graph
    def imagepath(graph,asset_id):
        if not any(a.id==asset_id for a in graph.assets):raise HTTPException(404,'Asset not found')
        return store.root/f'{graph.project_id}.png' if asset_id=='image' else store.root/f'{graph.project_id}-{asset_id}.png'
    def handled(func,*args,**kwargs):
        try:return func(*args,**kwargs)
        except (ValueError,RuntimeError,subprocess.TimeoutExpired) as exc:raise HTTPException(422,str(exc))

    @app.post('/api/projects/reference',status_code=201)
    def create_reference(body:ReferenceInput):
        graph,data=handled(reference,uuid.uuid4().hex,body.profile)
        (store.root/f'{graph.project_id}.png').write_bytes(data)
        return view(save(graph,0,'새 설계 예제 생성: '+body.profile))

    @app.get('/api/catalog')
    def catalog(q:str=''):return search_catalog(q)

    @app.post('/api/projects/{project}/components/{component_id}/catalog')
    def assign_catalog(project:str,component_id:str,body:CatalogInput):
        graph=current(project,body.expected_revision);component=next((c for c in graph.components if c.id==component_id),None)
        if component is None or body.catalog_id not in CATALOG:raise HTTPException(404,'Component/catalog not found')
        entry=CATALOG[body.catalog_id]
        if component.kind!=entry['kind']:raise HTTPException(422,'부품 종류가 카탈로그와 다릅니다.')
        if not component.terminals or any(t.name.value not in entry['pins'] for t in component.terminals):raise HTTPException(422,'단자 라벨을 카탈로그와 일치시킨 뒤 확인하세요: '+', '.join(entry['pins']))
        eid='catalog_'+uuid.uuid4().hex[:8]
        graph.evidence.append(Evidence(id=eid,asset_id=component.asset_id,method='datasheet',source_url=entry['source'],text=body.note+' / '+entry['note']))
        component.catalog_id=body.catalog_id;component.label=Claim(value=entry['name'],status=Status.CONFIRMED,evidence_ids=[eid],reason='사용자 식별 확인 + 카탈로그')
        for t in component.terminals:t.pin_mapping=Claim(value=entry['pins'][t.name.value],status=Status.CONFIRMED,evidence_ids=[eid],reason='선택한 카탈로그 매핑')
        return view(save(graph,body.expected_revision,'부품 카탈로그 확인: '+component_id))

    @app.post('/api/projects/{project}/analyze')
    def analyze_image(project:str,body:AnalyzeInput):
        graph=current(project,body.expected_revision)
        graph,report=handled(analyze,graph,imagepath(graph,body.asset_id),body.asset_id,body.pcb)
        graph=save(graph,body.expected_revision,'로컬 OCR·윤곽 분석')
        report['revision']=graph.revision
        (store.root/f'{project}-analysis.json').write_text(json.dumps(report,ensure_ascii=False))
        return view(graph)

    @app.post('/api/projects/{project}/anchor')
    def anchor(project:str,body:AnchorInput):
        graph=current(project,body.expected_revision)
        match=next(((c,t) for c in graph.components for t in c.terminals if t.id==body.terminal_id),None)
        if match is None:raise HTTPException(404,'Terminal not found')
        component,terminal=match
        if terminal.image_position != body.position:
            for link in graph.links:
                if terminal.id in (link.from_terminal,link.to_terminal) and any(
                    e.method=='geometry' and e.id in link.connection.evidence_ids for e in graph.evidence):
                    link.connection=Claim(evidence_ids=link.connection.evidence_ids,
                        reason='핀 위치가 변경되어 선 조각과의 대응을 다시 확인해야 합니다.')
        terminal.image_position=body.position
        graph.evidence.append(Evidence(id='anchor_'+uuid.uuid4().hex[:8],asset_id=component.asset_id,method='manual_annotation',points=[body.position],text=f'사용자가 {terminal.id} 핀의 사진 위치를 지정했습니다.'))
        return view(save(graph,body.expected_revision,'사진의 핀 위치 지정'))

    @app.get('/api/projects/{project}/assets/{asset_id}')
    def asset(project:str,asset_id:str):return FileResponse(imagepath(get(project),asset_id),media_type='image/png')

    @app.post('/api/projects/{project}/assets')
    async def add_image(project:str,expected_revision:int,image:UploadFile=File(...)):
        graph=current(project,expected_revision);raw=await image.read(12*1024*1024+1)
        if len(raw)>12*1024*1024:raise HTTPException(413,'사진은 12MB 이하입니다.')
        try:
            pic=Image.open(io.BytesIO(raw))
            if pic.format not in {'PNG','JPEG'} or pic.width*pic.height>20_000_000:raise ValueError('PNG/JPEG 최대 2천만 화소')
            pic=ImageOps.exif_transpose(pic).convert('RGB');pic.load()
        except (ValueError,OSError,UnidentifiedImageError,Image.DecompressionBombError):raise HTTPException(422,'유효한 이미지가 필요합니다.')
        aid='view_'+uuid.uuid4().hex[:8];buf=io.BytesIO();pic.save(buf,format='PNG');data=buf.getvalue()
        with PendingUploadFiles() as upload_files:
            upload_files.write(store.root/f'{project}-{aid}.png',data)
            graph.assets.append(Asset(id=aid,sha256=hashlib.sha256(data).hexdigest(),width=pic.width,height=pic.height,filename=aid+'.png'))
            graph=save(graph,expected_revision,'다른 각도의 사진 추가')
            upload_files.commit()
        return view(graph)

    @app.post('/api/projects/video',status_code=201)
    async def video(video:UploadFile=File(...),analysis_model:AnalysisModel=Form(PRIMARY)):
        raw=await video.read(64*1024*1024+1)
        if len(raw)>64*1024*1024:raise HTTPException(413,'영상은 64MB 이하입니다.')
        pid=uuid.uuid4().hex;path=store.root/f'{pid}.video'
        with PendingUploadFiles() as upload_files:
            upload_files.write(path,raw)
            frames=handled(keyframes,path);assets=[];evidence=[]
            for i,(time,pic) in enumerate(frames):
                aid='image' if i==0 else f'frame_{i}';buf=io.BytesIO();pic.save(buf,format='PNG');data=buf.getvalue()
                target=store.root/(f'{pid}.png' if i==0 else f'{pid}-{aid}.png');upload_files.write(target,data)
                assets.append(Asset(id=aid,sha256=hashlib.sha256(data).hexdigest(),width=pic.width,height=pic.height,filename=f'frame-{time:.2f}s.png'))
                evidence.append(Evidence(id=f'frame_evidence_{i}',asset_id=aid,method='video_frame',text=f'{time:.2f}초 프레임. 시간 구간, 선명도와 화면 변화 기준으로 선택한 관측입니다. 화면 변화만으로 원인이나 반복 주기를 확정하지 않습니다. 동일 부품/도통의 자동 병합은 하지 않습니다.'))
            graph=Graph(project_id=pid,title='영상 주요 프레임 검토',revision=1,mode='video',assets=assets,evidence=evidence)
            graph=save(graph,0,'영상 주요 프레임 추출 · 부품 자동 확인')
            upload_files.commit()
        job=app.state.auto_analysis.start(graph,model=analysis_model)
        result=view(graph);result['auto_analysis']=job
        return result

    @app.post('/api/projects/{project}/build')
    def build_project(project:str,body:RevisionInput):
        graph=current(project,body.expected_revision)
        with _jobs:handled(build,graph,artifact_folder(store,graph)/'eda')
        return view(graph)

    @app.get('/api/projects/{project}/artifacts/{kind}')
    def artifact(project:str,kind:str):
        graph=get(project);folder=artifact_folder(store,graph)/'eda'
        paths={'zip':folder/'project.zip','pcb':folder/'pcb.svg','schematic':next(iter((folder/'schematic').glob('*.svg')),folder/'missing'),'sch':folder/'circuit.kicad_sch','board':folder/'circuit.kicad_pcb','erc':folder/'erc.json','drc':folder/'drc.json'}
        if kind not in paths or not paths[kind].exists():raise HTTPException(404,'현재 버전의 결과가 없습니다. 먼저 생성하세요.')
        return FileResponse(paths[kind],filename=paths[kind].name if kind in {'zip','sch','board','erc','drc'} else None)

    @app.post('/api/projects/{project}/simulate')
    def simulation(project:str,body:SimInput):
        graph=current(project,body.expected_revision)
        with _jobs:handled(simulate,graph,artifact_folder(store,graph)/'simulation',body.analysis)
        return view(graph)

    @app.post('/api/projects/{project}/parameters')
    def parameters(project:str,body:ParamsInput):
        graph=current(project,body.expected_revision)
        if graph.mode!='reference_design':raise HTTPException(422,'설계 예제 프로젝트에서만 파라미터를 변경합니다.')
        from .circuit.profiles import number
        eid='parameter_'+uuid.uuid4().hex[:8];graph.evidence.append(Evidence(id=eid,asset_id='image',method='design_spec',text='사용자가 웹에서 설계 값을 변경했습니다.'))
        for ref,value in body.values.items():
            c=next((c for c in graph.components if c.id==ref and c.kind in {'resistor','capacitor'}),None)
            if c is None:raise HTTPException(422,'지원하지 않는 부품 값')
            handled(number,value);c.value=Claim(value=value,status=Status.CONFIRMED,evidence_ids=[eid],reason='사용자가 지정한 설계 값')
        for key in ['frequency','amplitude']:
            if getattr(body,key) is not None:graph.parameters[key]=getattr(body,key)
        if readiness(graph):raise HTTPException(422,' / '.join(readiness(graph)))
        graph=save(graph,body.expected_revision,'설계 파라미터 변경')
        # Recompute with the new graph revision; no stale waveform is reused.
        error=None
        try:simulate(graph,artifact_folder(store,graph)/'simulation','transient')
        except (ValueError,subprocess.TimeoutExpired) as exc:error=str(exc)
        result=view(graph)
        if error:result['simulation_error']=error
        return result

    @app.get('/api/projects/{project}/firmware')
    def code(project:str,download:bool=False):
        graph=get(project)
        result=handled(firmware,graph)
        provenance=store.root/'designs'/project/'provenance.json'
        if graph.profile=='arduino_lcd' and provenance.exists():
            from .design.firmware import lcd_firmware
            design=json.loads(provenance.read_text())
            result=handled(lcd_firmware,graph,design['message'],design.get('lcd_show_elapsed',True))
        if download:return Response(result['source'],media_type='text/plain',headers={'Content-Disposition':f'attachment; filename="{result["filename"]}"'})
        return result

    @app.post('/api/projects/{project}/agent')
    def agent(project:str,body:AgentInput):
        graph=current(project,body.expected_revision);graph,response=handled(answer,graph,body.prompt)
        if response['changed']:
            if readiness(graph):raise HTTPException(422,' / '.join(readiness(graph)))
            graph=save(graph,body.expected_revision,'자연어 설계 변경: '+body.prompt)
            try:simulate(graph,artifact_folder(store,graph)/'simulation')
            except (ValueError,subprocess.TimeoutExpired) as exc:response['simulation_error']=str(exc)
        if response.get('action')=='build':
            with _jobs:handled(build,graph,artifact_folder(store,graph)/'eda')
        return {'project':view(graph),'reply':response}
