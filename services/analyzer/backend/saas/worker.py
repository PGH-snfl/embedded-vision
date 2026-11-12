"""Separate durable-task consumer. Never automatically retries paid/tool actions."""
import argparse
import asyncio
import json
import os
import subprocess
import threading
import time
import uuid
import httpx
from .repository import Repository
from .settings import Settings
from .tenancy import TenantApps, actor


class Worker:
    def __init__(self, settings, compiler=None):
        self.repository = Repository(settings)
        self.tenants = TenantApps(self.repository)
        self.compiler = compiler
        self.worker_id = uuid.uuid4().hex
        self.stopping = threading.Event()
        from ..planner.provider import api_key
        self.model_ready = bool(api_key())
        self.repository.worker_heartbeat(self.worker_id,self.model_ready)

        def announce():
            while not self.stopping.wait(10):
                self.repository.worker_heartbeat(self.worker_id,self.model_ready)

        self.announcer = threading.Thread(target=announce,daemon=True)
        self.announcer.start()

    def run_once(self):
        job = self.repository.claim()
        if not job:
            return False
        stop = threading.Event()

        def heartbeat():
            while not stop.wait(20):
                self.repository.heartbeat(job["id"])

        pulse = threading.Thread(target=heartbeat,daemon=True)
        pulse.start()
        token = actor.set(job["actor"])
        try:
            if self.repository.role(job["workspace"],job["actor"]) not in {"owner","editor"}:
                raise ValueError("작업 제출자의 편집 권한이 없어졌습니다.")
            with self.repository.connect() as c:
                user = c.execute("SELECT enabled FROM users WHERE id=?", (job["actor"],)).fetchone()
            if not user or not user[0]:
                raise ValueError("작업 제출자 계정이 비활성화되었습니다.")
            payload = json.loads(job["payload"])
            if job["kind"] == "compile":
                from ..workbench.server import CompileRequest, compile_edit
                try:
                    result = (self.compiler or compile_edit)(CompileRequest.model_validate(payload))
                except (ValueError,OSError,subprocess.TimeoutExpired) as exc:
                    message = str(exc) if isinstance(exc,ValueError) else "격리 컴파일 실행 실패 · 작업 처리 환경을 확인하세요."
                    result = {"success":False,"stdout":"","stderr":message,"error":message}
                self.repository.finish(job["id"],result)
            elif job["kind"] == "inventory":
                app = self.tenants.get(job["workspace"])
                auto = app.state.auto_analysis
                graph = app.state.store.get(payload["project"])
                current = auto.read(payload["project"])
                if not current or current["id"] != payload["analysis_id"]:
                    raise ValueError("분석 작업이 변경되었습니다.")
                if payload.get('analysis_model', 'gpt-6.1-sol') != current.get('analysis_model', 'gpt-6.1-sol'):
                    raise ValueError('분석 작업의 모델 선택이 변경되었습니다.')
                if current["stale"]:
                    current.update(status="stale",message="입력이 변경되어 모델을 호출하지 않았습니다.")
                    auto._write(current)
                else:
                    auto._worker(current,graph)
                self.repository.finish(job["id"],{"status":auto.read(payload["project"])["status"]})
            elif job["kind"] == "http":
                app = self.tenants.get(job["workspace"])

                async def perform():
                    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url="http://worker") as client:
                        return await client.post(payload["path"],params=payload["query"],json=payload["body"])

                response = asyncio.run(perform())
                result = {"status_code":response.status_code,"data":response.json()}
                self.repository.finish(job["id"],result,failed=response.status_code >= 400)
            else:
                raise ValueError("지원하지 않는 작업입니다.")
        except Exception:
            # Never persist exception/provider bodies, credentials or user source in logs.
            self.repository.finish(job["id"],{"detail":"서버 작업이 실패했습니다. 자동 재실행하지 않습니다."},failed=True)
        finally:
            actor.reset(token)
            stop.set()
            pulse.join(timeout=1)
        return True

    def close(self):
        self.stopping.set()
        self.announcer.join(timeout=1)
        with self.repository.connect(True) as c:
            c.execute("DELETE FROM workers WHERE id=?",(self.worker_id,))
        self.tenants.close()


def main():
    os.environ["EV_SAAS_MODE"] = "1"
    from .envfile import WorkerEnvironment
    environment = WorkerEnvironment()
    environment.refresh()
    parser = argparse.ArgumentParser()
    parser.add_argument("--once",action="store_true")
    args = parser.parse_args()
    worker = Worker(Settings.from_env())
    try:
        if args.once:
            worker.run_once()
        else:
            while True:
                try:
                    ready = environment.refresh()
                except ValueError:
                    # No raw file contents or key values in logs. Invalid rotation revokes the old key.
                    ready = False
                if ready != worker.model_ready:
                    worker.model_ready = ready
                    worker.repository.worker_heartbeat(worker.worker_id,ready)
                if not worker.run_once():
                    time.sleep(.5)
    finally:
        worker.close()


if __name__ == "__main__":
    main()
