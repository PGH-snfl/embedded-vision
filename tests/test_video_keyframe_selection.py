"""Exercise temporal coverage without implying a recovered behavior."""
import numpy as np
import pytest

from backend.vision import analyze


class Video:
    def __init__(self, frames, fps=6):
        self.frames, self.fps, self.index, self.released = frames, fps, 0, False

    def isOpened(self): return True

    def get(self, prop):
        if prop == analyze.cv2.CAP_PROP_FPS: return self.fps
        if prop == analyze.cv2.CAP_PROP_FRAME_COUNT: return len(self.frames)
        return 0

    def set(self, prop, value):
        assert prop == analyze.cv2.CAP_PROP_POS_FRAMES
        self.index = int(value)

    def read(self):
        if self.index >= len(self.frames): return False, None
        return True, self.frames[self.index].copy()

    def release(self): self.released = True


def image(lit):
    # Detailed fixed background keeps sharpness similar; the bright square is
    # a small output whose state changes between otherwise identical frames.
    y, x = np.indices((120, 160))
    gray = np.where((x // 2 + y // 2) % 2, 100, 150).astype('uint8')
    frame = np.repeat(gray[:, :, None], 3, axis=2)
    frame[40:48, 72:80] = (255, 255, 255) if lit else (10, 10, 10)
    return frame


def test_chronological_video_keeps_both_visible_states(monkeypatch):
    # Every time window offers both states; quality-only selection repeatedly
    # picks the sharpest state, missing the other behavior altogether.
    video = Video([image(i % 4 != 0) for i in range(24)])
    monkeypatch.setattr(analyze.cv2, 'VideoCapture', lambda _path: video)
    frames = analyze.keyframes('unused')
    assert len(frames) == 6 and video.released
    assert [t for t, _ in frames] == sorted(t for t, _ in frames)
    states = {np.asarray(frame)[43, 75, 0] > 200 for _, frame in frames}
    assert states == {False, True}


def test_short_video_does_not_duplicate_frames(monkeypatch):
    video = Video([image(False), image(True)], fps=2)
    monkeypatch.setattr(analyze.cv2, 'VideoCapture', lambda _path: video)
    frames = analyze.keyframes('unused')
    assert [time for time, _ in frames] == [0.0, 0.5]
    assert video.released


@pytest.mark.parametrize('fps', [0, float('nan'), float('inf')])
def test_bad_video_metadata_releases_handle(monkeypatch, fps):
    video = Video([image(False)], fps=fps)
    monkeypatch.setattr(analyze.cv2, 'VideoCapture', lambda _path: video)
    with pytest.raises(ValueError): analyze.keyframes('unused')
    assert video.released


def test_inventory_receives_frame_timestamps_in_selected_order():
    from pathlib import Path
    from backend.circuit.schema import Asset, Evidence, Graph
    from backend.design.inventory import inventory_plan
    from backend.design.models import Inventory

    assets = [Asset(id=id, sha256='a'*64, width=10, height=10, filename=id+'.png')
              for id in ['image', 'frame_1', 'frame_2']]
    evidence = [Evidence(id='e'+str(i), asset_id=asset.id, method='video_frame',
                         text=f'{t:.2f}초 프레임. 선택된 화면입니다.')
                for i, (asset, t) in enumerate(zip(assets, [0.25, 1.50, 3.75]))]
    graph = Graph(project_id='a'*32, title='video', mode='video', revision=1, assets=assets, evidence=evidence)

    class Provider:
        def infer(self, model, context, prompt, task, received):
            self.context = context
            return Inventory(summary='분석 없음', parts=[], suggested_function='', unknowns=[]), {}

    provider = Provider()
    result = inventory_plan(graph, [(a.id, Path('/unused')) for a in assets], provider)
    assert result['asset_ids'] == ['image', 'frame_1', 'frame_2']
    assert [(a['id'], a['frame_timestamp_seconds']) for a in provider.context['assets']] == [
        ('image', .25), ('frame_1', 1.5), ('frame_2', 3.75)]
