from fastapi.testclient import TestClient
from backend.api import create_app

def test_only_editor_pages_allow_same_origin_framing(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        for path in ['/prototype-editor.html','/rover-editor.html']:
            response=client.get(path)
            assert response.status_code==200
            assert "frame-ancestors 'self'" in response.headers['content-security-policy']
            assert response.headers['cache-control']=='no-store'
        for path in ['/','/api/projects']:
            response=client.get(path)
            assert "frame-ancestors 'none'" in response.headers['content-security-policy']
