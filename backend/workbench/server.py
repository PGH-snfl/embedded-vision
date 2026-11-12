"""Local Velxio OSS frontend + isolated UNO compiler. No account or remote builds."""
import hashlib, json, os, re, subprocess, tempfile, threading, uuid
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware
from pydantic import BaseModel, Field
from ..emulator.toolchain import ROOT, PROJECT, prepare

DIST=PROJECT/'third_party/velxio/frontend/dist'
LOCK=threading.Lock()
JOBS={}
app=FastAPI(title='Embedded Vision · Velxio local workbench')
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
def health():return {'status':'ok','compiler':'isolated avr-g++','boards':['arduino:avr:uno']}
@app.get('/api/{path:path}')
def missing_api(path:str):raise HTTPException(404,'This optional hosted service is not enabled locally')

if DIST.exists():
    app.mount('/assets',StaticFiles(directory=DIST/'assets'),name='assets')
    @app.get('/{path:path}')
    def frontend(path:str):
        target=(DIST/path).resolve()
        if target.is_relative_to(DIST.resolve()) and target.is_file():return FileResponse(target)
        return FileResponse(DIST/'index.html')
