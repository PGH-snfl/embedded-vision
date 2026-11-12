"""Run only our two local servers; never reuse or terminate unrelated services."""
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
    args = parser.parse_args()
    os.umask(0o077)
    os.chdir(ROOT)
    api_port = port_number('EMBEDDED_VISION_PORT', 8766)
    editor_port = port_number('EMBEDDED_VISION_EDITOR_PORT', 8768)
    if api_port == editor_port:
        raise ValueError('분석 화면과 편집기 포트는 달라야 합니다.')
    if not (ROOT/'third_party/velxio/frontend/dist/index.html').is_file():
        raise RuntimeError('편집기가 없습니다. bash start.sh --setup-only를 실행하세요.')
    for port in (api_port, editor_port):
        with socket.socket() as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind(('127.0.0.1', port))
            except OSError:
                raise RuntimeError(f'{port} 포트가 사용 중입니다. 기존 서버를 종료하거나 포트 환경변수를 바꾸세요.') from None
    folder = ROOT/'.runtime/launcher'
    folder.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.pop('EV_SAAS_MODE', None)
    env['EMBEDDED_VISION_EDITOR_PORT'] = str(editor_port)
    children, logs = [], []
    def interrupted(signum, frame):
        raise KeyboardInterrupt
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, interrupted)
    try:
        for name, module, port in [('analysis', 'backend.api:app', api_port), ('editor', 'backend.workbench.server:app', editor_port)]:
            log = (folder/f'{name}.log').open('w')
            logs.append(log)
            children.append(subprocess.Popen([sys.executable, '-m', 'uvicorn', module, '--host', '127.0.0.1', '--port', str(port)], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True))
        for port, child in zip((api_port, editor_port), children):
            wait_ready(f'http://127.0.0.1:{port}/api/health', child)
        url = f'http://127.0.0.1:{api_port}/'
        print(f'사진 분석: {url}\n편집기: http://127.0.0.1:{editor_port}/editor\n튜토리얼: {url}tutorial\n종료: Ctrl+C', flush=True)
        if not args.no_open:
            if not webbrowser.open(url):
                print('브라우저에서 위 주소를 열어주세요.', flush=True)
        while all(child.poll() is None for child in children):
            time.sleep(.5)
        raise RuntimeError('서버 하나가 종료되어 함께 종료합니다. 로그를 확인하세요.')
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
