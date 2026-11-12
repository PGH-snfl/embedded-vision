"""Run independently selected services; editor is the default."""
import argparse
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser

ROOT = Path(__file__).resolve().parents[1]


def port_number(name, default):
    value = int(os.environ.get(name, default))
    if not 1024 <= value <= 65535:
        raise ValueError(f'{name}: 1024~65535 범위가 필요합니다.')
    return value


def wait_ready(url, child, timeout=60):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if child.poll() is not None:
            raise RuntimeError('서버가 종료됐습니다. .runtime/launcher 로그를 확인하세요.')
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if json.load(response).get('status') == 'ok':
                    return
        except (OSError, ValueError):
            time.sleep(.2)
    raise RuntimeError('서버 준비 시간이 초과됐습니다. .runtime/launcher 로그를 확인하세요.')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--no-open', action='store_true')
    parser.add_argument('--service',choices=('editor','analyzer','all'),default='editor')
    args = parser.parse_args()
    os.umask(0o077)
    os.chdir(ROOT)
    api_port=port_number('EMBEDDED_VISION_PORT',8766) if args.service in {'analyzer','all'} else None
    editor_port=port_number('EMBEDDED_VISION_EDITOR_PORT',8768) if args.service in {'editor','all'} else None
    if api_port is not None and api_port==editor_port:
        raise ValueError('분석 화면과 편집기 포트는 달라야 합니다.')
    targets=[]
    if editor_port:
        if not (ROOT/'services/editor/vendor/velxio/frontend/dist/index.html').is_file():
            raise RuntimeError('편집기가 없습니다. bash start.sh --setup-only를 실행하세요.')
        targets.append(('editor','services.editor.app:app',editor_port))
    if api_port:targets.append(('analyzer','services.analyzer.app:app',api_port))
    for name,_,port in targets:
        python=ROOT/f'services/{name}/.venv/bin/python'
        if not python.is_file():raise RuntimeError(f'{name} 설치가 필요합니다. bash services/{name}/start.sh --setup-only')
        with socket.socket() as probe:
            probe.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
            try:probe.bind(('127.0.0.1',port))
            except OSError:raise RuntimeError(f'{port} 포트가 사용 중입니다. 기존 서버를 종료하거나 포트 환경변수를 바꾸세요.') from None
    folder = ROOT/'.runtime/launcher'
    folder.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.pop('EV_SAAS_MODE', None)
    if editor_port:env['EMBEDDED_VISION_EDITOR_PORT']=str(editor_port)
    children, logs = [], []
    def interrupted(signum, frame):
        raise KeyboardInterrupt
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, interrupted)
    try:
        for name,module,port in targets:
            service_env=env.copy()
            service_env['EMBEDDED_SERVICE']=name
            if name=='editor':service_env['EMBEDDED_VISION_DATA']=env.get('EMBEDDED_EDITOR_DATA',str(ROOT/'.runtime/editor'))
            else:service_env['EMBEDDED_VISION_DATA']=env.get('EMBEDDED_ANALYZER_DATA',env.get('EMBEDDED_VISION_DATA',str(ROOT/'.runtime')))
            log = (folder/f'{name}.log').open('w')
            logs.append(log)
            children.append(subprocess.Popen([str(ROOT/f'services/{name}/.venv/bin/python'), '-m', 'uvicorn', module, '--host', '127.0.0.1', '--port', str(port)], cwd=ROOT, env=service_env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True))
        for (_,_,port),child in zip(targets,children):
            wait_ready(f'http://127.0.0.1:{port}/api/health', child)
        url=f'http://127.0.0.1:{editor_port or api_port}/'
        for name,_,port in targets:print(f'{name}: http://127.0.0.1:{port}/',flush=True)
        print('종료: Ctrl+C · 선택하지 않은 서비스는 시작하지 않습니다.',flush=True)
        if not args.no_open and not webbrowser.open(url):print('브라우저에서 위 주소를 열어주세요.',flush=True)
        reported=set()
        while any(child.poll() is None for child in children):
            for (name,_,_),child in zip(targets,children):
                if child.poll() is not None and name not in reported:
                    print(f'{name} 서버가 종료됐습니다. 다른 서비스는 계속 실행합니다.',flush=True);reported.add(name)
            time.sleep(.5)
        raise RuntimeError('선택한 서버가 모두 종료됐습니다. 서비스별 로그를 확인하세요.')
    except KeyboardInterrupt:
        print('\n서버를 종료합니다.', flush=True)
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
        for child in children:
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
        for log in logs:
            log.close()


if __name__ == '__main__':
    try:
        main()
    except (ValueError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
