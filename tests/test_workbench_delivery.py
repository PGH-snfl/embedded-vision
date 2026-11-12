"""The large editor bundle is compressed and content-hashed assets stay cached."""
from fastapi.testclient import TestClient
from backend.workbench.server import app,DIST


def test_html_revalidates_and_hashed_script_is_compressed():
    asset=next((DIST/'assets').glob('index-*.js'))
    with TestClient(app) as client:
        html=client.get('/editor',headers={'accept-encoding':'gzip'})
        assert html.status_code==200
        assert html.headers['cache-control']=='no-cache'
        assert html.headers['content-encoding']=='gzip'
        assert '편집기 프로그램을 불러오고 있습니다' in html.text
        script=client.get('/assets/'+asset.name,headers={'accept-encoding':'gzip'})
        assert script.headers['content-encoding']=='gzip'
        assert script.headers['cache-control']=='public, max-age=31536000, immutable'
        assert script.content==asset.read_bytes()
        old=client.get('/assets/'+asset.name,headers={'if-none-match':script.headers['etag']})
        assert old.status_code==304
