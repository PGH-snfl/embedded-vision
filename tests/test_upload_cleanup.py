import io
from types import SimpleNamespace

from fastapi.testclient import TestClient
from PIL import Image

from backend.api import create_app
from backend.circuit.store import Conflict


def png():
    out = io.BytesIO()
    Image.new('RGB', (60, 60), 'white').save(out, format='PNG')
    return out.getvalue()


def test_invalid_photo_and_video_leave_no_uploaded_files(tmp_path):
    app = create_app(tmp_path)
    sentinel = tmp_path / 'unrelated.png'
    sentinel.write_bytes(b'keep')
    with TestClient(app) as client:
        photo = client.post('/api/projects', files={'image': ('bad.png', b'not an image', 'image/png')})
        video = client.post('/api/projects/video', files={'video': ('bad.mp4', b'not a video', 'video/mp4')})
        assert photo.status_code == 422
        assert video.status_code == 422
        assert list(tmp_path.glob('*.video')) == []
        assert list(tmp_path.glob('*.png')) == [sentinel]
        assert sentinel.read_bytes() == b'keep'
        assert client.get('/api/projects').json() == []


def test_partial_video_frame_failure_removes_only_new_files(tmp_path, monkeypatch):
    app = create_app(tmp_path)
    sentinel = tmp_path / 'existing.png'
    sentinel.write_bytes(b'existing')

    class BrokenFrame:
        def save(self, *_args, **_kwargs):
            raise ValueError('frame failed')

    monkeypatch.setattr('backend.integration.keyframes', lambda _: [
        (0.0, Image.new('RGB', (60, 60), 'white')),
        (1.0, BrokenFrame()),
    ])
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post('/api/projects/video', files={'video': ('video.mp4', b'video', 'video/mp4')})
        assert response.status_code == 500
        assert list(tmp_path.glob('*.video')) == []
        assert list(tmp_path.glob('*.png')) == [sentinel]
        assert sentinel.read_bytes() == b'existing'
        assert client.get('/api/projects').json() == []


def test_valid_video_preserves_original_and_frames(tmp_path, monkeypatch):
    app = create_app(tmp_path)
    monkeypatch.setattr('backend.integration.keyframes', lambda _: [
        (0.0, Image.new('RGB', (60, 60), 'white')),
        (1.0, Image.new('RGB', (60, 60), 'black')),
    ])
    with TestClient(app) as client:
        response = client.post('/api/projects/video', files={'video': ('video.mp4', b'valid-test', 'video/mp4')})
        assert response.status_code == 201
        project = response.json()['graph']['project_id']
        assert (tmp_path / f'{project}.video').read_bytes() == b'valid-test'
        assert (tmp_path / f'{project}.png').is_file()
        assert (tmp_path / f'{project}-frame_1.png').is_file()


def test_photo_save_failure_removes_new_file(tmp_path, monkeypatch):
    app = create_app(tmp_path)
    def conflict(*_args, **_kwargs):
        raise Conflict('simulated conflict')
    monkeypatch.setattr(app.state.store, 'save', conflict)
    with TestClient(app) as client:
        response = client.post('/api/projects', files={'image': ('photo.png', png(), 'image/png')})
        assert response.status_code == 409
        assert list(tmp_path.glob('*.png')) == []


def test_additional_photo_revision_conflict_preserves_original(tmp_path, monkeypatch):
    app = create_app(tmp_path)
    with TestClient(app) as client:
        response = client.post('/api/projects', files={'image': ('photo.png', png(), 'image/png')})
        assert response.status_code == 201
        graph = response.json()['graph']
        original = tmp_path / f"{graph['project_id']}.png"
        before = original.read_bytes()
        def conflict(*_args, **_kwargs):
            raise Conflict('simulated concurrent update')
        monkeypatch.setattr(app.state.store, 'save', conflict)
        result = client.post(f"/api/projects/{graph['project_id']}/assets?expected_revision={graph['revision']}",
                             files={'image': ('angle.png', png(), 'image/png')})
        assert result.status_code == 409
        assert list(tmp_path.glob('*.png')) == [original]
        assert original.read_bytes() == before
        assert len(app.state.store.get(graph['project_id']).assets) == 1


def test_video_id_collision_never_deletes_or_overwrites_existing_file(tmp_path, monkeypatch):
    app = create_app(tmp_path)
    pid = 'f' * 32
    sentinel = tmp_path / f'{pid}.video'
    sentinel.write_bytes(b'existing video')
    monkeypatch.setattr('backend.integration.uuid.uuid4', lambda: SimpleNamespace(hex=pid))
    with TestClient(app, raise_server_exceptions=False) as client:
        result = client.post('/api/projects/video', files={'video': ('video.mp4', b'new', 'video/mp4')})
        assert result.status_code == 500
        assert sentinel.read_bytes() == b'existing video'
