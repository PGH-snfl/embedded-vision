"""Local Velxio OSS frontend + isolated UNO compiler. No account or remote builds."""
import hashlib, json, os, re, subprocess, tempfile, threading, uuid
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware
from pydantic import BaseModel, Field
from ..emulator.toolchain import ROOT, PROJECT, prepare
from shared.paths import EDITOR_FRONTEND,EDITOR_ROOT

DIST=EDITOR_FRONTEND/'dist'
LOCK=threading.Lock()
JOBS={}
app=FastAPI(title='Embedded Editor · 회로·코드·3D 편집기')
from ..translation.system import conversion_routes
conversion_routes(app)
app.add_middleware(GZipMiddleware,minimum_size=1024,compresslevel=5)

class SketchFile(BaseModel):
    name:str=Field(min_length=1,max_length=100)
    content:str=Field(max_length=100000)
class CompileRequest(BaseModel):
    files:list[SketchFile]=Field(min_length=1,max_length=20)
    board:str='arduino:avr:uno'
    board_fqbn:str|None=None

@app.middleware('http')
async def local_only(request:Request,call_next):
    if request.url.hostname not in {'127.0.0.1','localhost','testserver'}:
        return JSONResponse({'detail':'Local access only'},403)
    if request.method not in {'GET','HEAD','OPTIONS'}:
        origin=request.headers.get('origin')
        if (origin and origin!=str(request.base_url).rstrip('/')) or request.headers.get('sec-fetch-site')=='cross-site':
            return JSONResponse({'detail':'Same-origin requests only'},403)
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='no-referrer'
    if request.method in {'GET','HEAD'} and response.status_code==200:
        if request.url.path.startswith('/assets/') and re.search(r'-[A-Za-z0-9_-]{8,}\.[A-Za-z0-9]+$',request.url.path):
            response.headers['Cache-Control']='public, max-age=31536000, immutable'
        elif response.headers.get('content-type','').startswith('text/html'):
            response.headers['Cache-Control']='no-cache'
    return response


def compile_edit(body):
    if (body.board_fqbn or body.board)!='arduino:avr:uno':
        raise ValueError('이 로컬 컴파일러는 Arduino UNO만 지원합니다. 다른 보드는 아직 연결하지 않았습니다.')
    names=[f.name for f in body.files]
    if len(names)!=len(set(names)) or any(not re.fullmatch(r'[A-Za-z0-9_-]+\.(ino|cpp|c|h|hpp)',n) for n in names):
        raise ValueError('파일은 중복 없는 영문 이름의 .ino/.cpp/.c/.h/.hpp 파일이어야 합니다.')
    if sum(len(f.content.encode()) for f in body.files)>250000:
        raise ValueError('프로젝트 크기는 250KB 이하로 제한합니다.')
    common,library,_,_=prepare()
    with tempfile.TemporaryDirectory(prefix='velxio-build-') as td:
        folder=Path(td)
        for f in body.files: (folder/f.name).write_text(f.content)
        sketches=[f.content for f in body.files if f.name.endswith('.ino')]
        if sketches:
            from .arduino_preprocess import prepare_sketch
            (folder/'_sketch.cpp').write_text(prepare_sketch('\n'.join(sketches)))
        # The compiler can see its toolchain and this scratch directory only;
        # /home, API keys, project data and the host network are not mounted.
        prefix=['bwrap','--die-with-parent','--new-session','--unshare-all','--clearenv',
            '--ro-bind','/usr','/usr','--ro-bind','/lib','/lib','--ro-bind','/lib64','/lib64',
            '--tmpfs','/tmp',
            '--ro-bind',str(ROOT),str(ROOT),'--ro-bind',str(library),str(library),
            '--bind',td,'/work','--proc','/proc','--dev','/dev',
            '--chdir','/work','--setenv','PATH',str(ROOT/'bin')+':/usr/bin',
            '/usr/bin/prlimit','--as=536870912','--cpu=15','--fsize=8388608','--']
        def run(args):
            p=subprocess.run(prefix+[str(a) for a in args],capture_output=True,text=True,timeout=25,
                env={'PATH':'/usr/bin:/bin'})
            if p.returncode: raise ValueError(p.stderr[-6000:] or p.stdout[-2000:] or '격리 컴파일 실패')
            return p.stdout
        objects=[]
        for src in sorted(folder.iterdir()):
            if src.suffix not in {'.cpp','.c'}: continue
            obj=src.name+'.o';objects.append(obj)
            cpp=src.suffix=='.cpp'
            run([ROOT/'bin'/('avr-g++' if cpp else 'avr-gcc'),*common,
                *(['-std=gnu++11','-fno-exceptions','-fno-threadsafe-statics'] if cpp else ['-std=gnu11']),
                '-I/work','-c',src.name,'-o',obj])
        if not objects:raise ValueError('컴파일할 소스가 없습니다.')
        run([ROOT/'bin/avr-g++','-mmcu=atmega328p','-Os','-Wl,--gc-sections',*objects,library,'-lm','-o','firmware.elf'])
        run([ROOT/'bin/avr-objcopy','-O','ihex','-R','.eeprom','firmware.elf','firmware.hex'])
        size=run([ROOT/'bin/avr-size','firmware.elf'])
        return {'success':True,'hex_content':(folder/'firmware.hex').read_text(),
            'stdout':size,'stderr':'','source_sha256':hashlib.sha256(json.dumps([f.model_dump() for f in body.files],sort_keys=True).encode()).hexdigest()}

@app.post('/api/compile/start')
def start(body:CompileRequest):
    with LOCK:
        try:result=compile_edit(body)
        except (ValueError,OSError,subprocess.TimeoutExpired) as e:
            result={'success':False,'stdout':'','stderr':str(e),'error':str(e)}
        job=uuid.uuid4().hex
        if len(JOBS)>=32:JOBS.pop(next(iter(JOBS)))
        JOBS[job]={'state':'done','stage':'done','progress':1,'result':result,'stdout':result['stdout']}
        return {'job_id':job}

@app.get('/api/compile/status/{job}')
def status(job:str):
    if job not in JOBS:raise HTTPException(404,'Job expired')
    return JOBS[job]
@app.get('/api/setup-status')
def setup():
    from ..design.board_profiles import board_profiles
    return {'ready':True,'supported_boards':['arduino:avr:uno'],
            'board_workflow':board_profiles()}
@app.get('/api/board-profiles')
def embedded_board_profiles():
    from ..design.board_profiles import board_profiles
    return board_profiles()
@app.get('/api/health')
def health():return {'status':'ok','service':'editor','compiler':'isolated avr-g++','boards':['arduino:avr:uno']}

@app.get('/api/editor/examples')
def editor_examples():
    from ..design.board_profiles import board_profiles
    return [{'id':key,'name':value['component']['name'],'runtime':value['runtime']['availability']}
            for key,value in board_profiles()['profiles'].items()]

@app.get('/api/editor/examples/{model}')
def editor_example(model:str):
    from ..design.board_profiles import board_example
    try:project=board_example(model)
    except (KeyError,ValueError):raise HTTPException(404,'등록된 편집기 예제가 없습니다.') from None
    project['embeddedVision'].update(standalone=True,inventory_plan='editor-example-'+model,
        design_origin='editor_template',analysis_origin='',
        standalone_notice='편집기 내장 예제입니다. 사진 분석 없이 회로·배선·코드를 편집합니다.')
    return project

def editor_projects():
    folder=Path(os.environ.get('EMBEDDED_EDITOR_DATA', os.environ.get('EMBEDDED_VISION_DATA', str(PROJECT/'.runtime/editor'))))/'projects'
    folder.mkdir(parents=True,exist_ok=True)
    return folder

@app.post('/api/editor/projects',status_code=201)
async def import_editor_project(request:Request):
    raw=bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw)>20*1024*1024:raise HTTPException(413,'프로젝트 파일은 20MB 이하로 선택하세요.')
    try:project=json.loads(raw)
    except (ValueError,UnicodeDecodeError):raise HTTPException(422,'프로젝트 JSON 파일을 읽지 못했습니다.') from None
    if not isinstance(project,dict) or project.get('format')!='velxio-project' or any(not isinstance(project.get(k),list) for k in ['boards','components','wires']) or not isinstance(project.get('fileGroups'),dict):
        raise HTTPException(422,'Velxio 프로젝트의 보드·부품·배선·코드를 확인하세요.')
    source=project.get('embeddedVision') or {}
    if not isinstance(source,dict):raise HTTPException(422,'프로젝트 정보를 확인하세요.')
    project_id=uuid.uuid4().hex
    project['embeddedVision']={**source,'standalone':True,'editor_project_id':project_id,
        'source_graph_sha256':source.get('source_graph_sha256') or hashlib.sha256(raw).hexdigest(),
        'inventory_plan':source.get('inventory_plan') or 'editor-file',
        'standalone_notice':source.get('standalone_notice') or '가져온 프로젝트입니다. 회로·배선·코드를 편집합니다.'}
    path=editor_projects()/(project_id+'.json')
    with os.fdopen(os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'w') as stream:
        json.dump(project,stream,ensure_ascii=False)
    return {'project_id':project_id,'editor_url':'/editor?embedded=1&standalone=1&editor_project='+project_id}

@app.get('/api/editor/projects/{project_id}')
def editor_project(project_id:str):
    if not re.fullmatch('[a-f0-9]{32}',project_id):raise HTTPException(404,'프로젝트가 없습니다.')
    path=editor_projects()/(project_id+'.json')
    if path.is_symlink() or not path.is_file():raise HTTPException(404,'프로젝트가 없습니다.')
    return FileResponse(path,media_type='application/json',headers={'Cache-Control':'private, no-store'})

@app.get('/',include_in_schema=False)
def editor_home():return FileResponse(EDITOR_ROOT/'web/index.html')

app.mount('/workspace-assets',StaticFiles(directory=EDITOR_ROOT/'web'),name='editor-home')
@app.get('/api/{path:path}')
def missing_api(path:str):raise HTTPException(404,'This optional hosted service is not enabled locally')

if DIST.exists():
    app.mount('/assets',StaticFiles(directory=DIST/'assets'),name='assets')
    @app.get('/{path:path}')
    def frontend(path:str):
        target=(DIST/path).resolve()
        if target.is_relative_to(DIST.resolve()) and target.is_file():return FileResponse(target)
        return FileResponse(DIST/'index.html')
