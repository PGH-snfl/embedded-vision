"""Upload-triggered background analysis, revision-bound and restart-visible. Never runs KiCad."""
import json, os, threading, uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from .provider import status
from .errors import ProviderFailure
from .selection import analysis_model,model_label,PRIMARY
from .service import digest
from ..design.inventory import inventory_plan,POLICY_VERSION
from ..circuit.project_lock import project_lock
from ..workflow import workflow_stamp

ACTIVE={'queued','sol','components','component_review','coverage','function','completion','datasheet','routing','astra','validation'}

class AutoAnalysis:
    def __init__(self,store,get,provider_factory=None,dispatcher=None):
        self.store=store;self.get=get;self.provider_factory=provider_factory
        self.dispatcher=dispatcher;self.queue_lookup=None;self.provider_ready=None
        self.root=store.root/'auto_jobs';self.root.mkdir(exist_ok=True)
        self.lock=threading.RLock();self.pool=ThreadPoolExecutor(max_workers=2,thread_name_prefix='circuit-analysis')
        self.pending=0
        # Never repeat a possibly billed request after restart.
        for path in ([] if dispatcher else self.root.glob('*.json')):
            job=json.loads(path.read_text())
            if job['status'] in ACTIVE:
                job.update(status='interrupted',message='서버가 재시작되어 분석을 중단했습니다. 자동 재호출하지 않습니다.')
                self._write(job)
    def _path(self,project):return self.root/(project+'.json')
    def _write(self,job):
        p=self._path(job['project_id']);temp=p.with_suffix('.tmp')
        temp.write_text(json.dumps(job,ensure_ascii=False,indent=2));temp.replace(p)
    def read(self,project):
        with self.lock:
            p=self._path(project)
            if not p.exists():return None
            job=json.loads(p.read_text())
        if self.queue_lookup and job.get('queue_id') and job['status'] in ACTIVE:
            queued=self.queue_lookup(job['queue_id'])
            if queued and queued['status'] in {'interrupted','failed'}:
                job.update(status='interrupted',message='서버 작업이 중단되었습니다. 자동 재호출하지 않습니다.')
        job['stale']=job['graph_sha256']!=digest(self.get(project)) or job.get('policy')!=POLICY_VERSION
        return job
    def start(self,graph,retry=False,model=None):
        with self.lock:
            old=self.read(graph.project_id)
            model=analysis_model(model if model is not None else old.get('analysis_model',PRIMARY) if old else PRIMARY)
            if old and old['status'] in ACTIVE:
                if old.get('analysis_model',PRIMARY)!=model:raise ValueError('현재 분석이 진행 중입니다. 완료 후 다른 모델로 다시 분석하세요.')
                return old
            if old and old['graph_sha256']==digest(graph) and old.get('policy')==POLICY_VERSION:
                if old['status'] not in {'waiting_credentials','disabled'} and not retry:return old
            job={'id':uuid.uuid4().hex,'project_id':graph.project_id,'revision':graph.revision,
                 'graph_sha256':digest(graph),'policy':POLICY_VERSION,'workflow':workflow_stamp(),'status':'queued',
                 'analysis_model':model,'message':model_label(model)+' 분석을 준비합니다.','plan_id':None}
            if graph.mode not in {'photo','video'}:raise ValueError('사진·영상 프로젝트에서 부품을 확인합니다.')
            if os.environ.get('EMBEDDED_VISION_AUTO_ANALYSIS','1')!='1':
                job.update(status='disabled',message='이 서버의 자동 분석이 비활성화되어 있습니다.')
            elif not (self.provider_ready() if self.provider_ready else status()['configured']):
                job.update(status='waiting_credentials',message='사진 저장 완료 · 서버 API 키 설정을 기다립니다.')
            elif self.pending>=8:
                job.update(status='error',message='분석 대기열이 가득 찼습니다. 잠시 후 다시 분석하세요.')
            if job['status']=='queued' and self.dispatcher:job['queue_id']=job['id']
            self._write(job)
            if job['status']=='queued':
                if self.dispatcher:
                    try:
                        self.dispatcher(job) # Publish only after the complete queued record is durable.
                    except Exception:
                        job.update(status='error',message='서버 작업 대기열에 등록하지 못했습니다. 한도를 확인하고 다시 시도하세요.');self._write(job)
                else:
                    self.pending+=1
                    self.pool.submit(self._worker,job,graph.model_copy(deep=True))
            return job.copy()
    def _worker(self,job,graph):
        with project_lock(self.store.root, graph.project_id, wait=True):
            try: self.get(graph.project_id)
            except Exception:
                # A queued worker from another process may acquire the lock
                # after deletion. Never recreate its deleted job/report files.
                with self.lock:self.pending=max(0,self.pending-1)
                return
            return self._worker_locked(job,graph)
    def _worker_locked(self,job,graph):
        def update(stage,message):
            with self.lock:
                job.update(status=stage,message=message);self._write(job)
        def save_plan(plan):
            plan['stale']=digest(self.get(graph.project_id))!=digest(graph)
            folder=self.store.root/'planner'/graph.project_id;folder.mkdir(parents=True,exist_ok=True)
            path=folder/(plan['id']+'.json');temp=path.with_suffix('.tmp')
            temp.write_text(json.dumps(plan,ensure_ascii=False,indent=2));temp.replace(path)
            job['plan_id']=plan['id']
        def inventory_ready(plan):
            save_plan(plan)
            update('components',f"통합 응답에서 구성품 {len(plan['inventory']['parts'])}종 저장 완료 · 기능·설계 참조를 검사합니다." if plan['attempts'][0]['stage']=='photo_system' else f"구성품 {len(plan['inventory']['parts'])}종 목록 저장 완료 · 이 목록을 근거로 기능을 분석합니다.")
        def inspection_ready(report):
            with self.lock:
                job['component_inspection']=report;self._write(job)
        try:
            assets=[(a.id,self.store.root/(graph.project_id+'.png' if a.id=='image' else graph.project_id+'-'+a.id+'.png')) for a in graph.assets[:6]]
            if any(not path.is_file() for _,path in assets):raise RuntimeError('입력 사진 파일이 없습니다.')
            plan=inventory_plan(graph,assets,
                 provider=self.provider_factory() if self.provider_factory else None,progress=update,on_inventory=inventory_ready,
                 model=analysis_model(job.get('analysis_model')),on_inspection=inspection_ready)
            save_plan(plan)
            update('stale' if plan['stale'] else 'done','분석 중 회로가 변경되어 이전 버전의 결과로 보존했습니다.' if plan['stale'] else '구성품 → 기능 → 보완 부품 → 데이터시트 완료 · 회로·시뮬레이션을 준비합니다.')
        except Exception as exc:
            # No raw provider bodies or secrets in user-facing job errors.
            job['failed_stage']=job['status']
            if isinstance(exc,ProviderFailure):job['error']=exc.diagnostic
            update('error',str(exc)[:500] if isinstance(exc,RuntimeError) else '분석 처리 실패. 원본 사진은 보존했습니다.')
        finally:
            with self.lock:self.pending=max(0,self.pending-1)
    def close(self):self.pool.shutdown(wait=False,cancel_futures=True)
