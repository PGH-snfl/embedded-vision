import importlib.util
import hashlib
import base64
import re
from pathlib import Path
import socket

import pytest
from fastapi.testclient import TestClient
from backend.application import create_app

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('ev_launch', ROOT/'scripts/launch.py')
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


def test_custom_editor_port_reaches_frontend_and_frame_policy(tmp_path, monkeypatch):
    monkeypatch.setenv('EMBEDDED_VISION_EDITOR_PORT', '18968')
    with TestClient(create_app(tmp_path)) as client:
        response = client.get('/runtime-config.js')
        assert response.text == 'window.EMBEDDED_VISION_EDITOR_PORT=18968;'
        assert response.headers['Cache-Control'] == 'no-store'
        assert 'http://127.0.0.1:18968' in response.headers['Content-Security-Policy']
        assert '/runtime-config.js' in client.get('/').text
        assert '/runtime-config.js' in client.get('/board-workflow.html').text
        tutorial=client.get('/tutorial')
        assert tutorial.status_code == 200
        for tag in ('script','style'):
            for source in re.findall(r'<'+tag+r'>(.*?)</'+tag+r'>',tutorial.text,re.S):
                digest=base64.b64encode(hashlib.sha256(source.encode()).digest()).decode()
                assert "'sha256-"+digest+"'" in tutorial.headers['Content-Security-Policy']
        assert 'unsafe-inline' not in tutorial.headers['Content-Security-Policy']
        local=client.get('/tutorial.html')
        assert '<script src="/tutorial.js"></script>' in local.text
        assert client.get('/tutorial.js').status_code==200
        assert client.get('/tutorial.css').status_code==200


def test_invalid_ports_fail_before_any_server(monkeypatch):
    monkeypatch.setenv('EMBEDDED_VISION_PORT', '80')
    with pytest.raises(ValueError, match='1024'):
        launcher.port_number('EMBEDDED_VISION_PORT', 8766)
    monkeypatch.setenv('EMBEDDED_VISION_EDITOR_PORT', '0')
    with pytest.raises(ValueError):
        create_app()


def test_busy_port_is_not_reused_or_terminated(monkeypatch):
    with socket.socket() as server:
        server.bind(('127.0.0.1', 0))
        server.listen()
        port = server.getsockname()[1]
        monkeypatch.setenv('EMBEDDED_VISION_EDITOR_PORT', str(port))
        monkeypatch.setattr('sys.argv', ['launch.py', '--no-open'])
        monkeypatch.setattr(launcher.subprocess, 'Popen', lambda *a, **kw: pytest.fail('Must not launch on a busy port'))
        with pytest.raises(RuntimeError, match='사용 중'):
            launcher.main()
        with socket.create_connection(('127.0.0.1', port), timeout=1):
            pass
