"""Regression tests never trigger paid model calls from incidental fixture uploads."""
import pytest

@pytest.fixture(autouse=True)
def disable_automatic_paid_requests(monkeypatch,tmp_path):
    monkeypatch.setenv('EMBEDDED_VISION_AUTO_ANALYSIS','0')
    monkeypatch.setenv('EMBEDDED_VISION_DATA',str(tmp_path/'isolated-provider'))
    monkeypatch.delenv('OPENAI_API_KEY',raising=False)
