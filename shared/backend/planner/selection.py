"""Allowlisted analysis models, independent of credentials and request payloads."""
from typing import Literal

PRIMARY = 'gpt-6.1-sol'
SPECIALIST = 'gpt-6-astra'
AnalysisModel = Literal['gpt-6.1-sol', 'gpt-6-astra']


def analysis_model(value=None):
    model = PRIMARY if value is None else value
    if model not in (PRIMARY, SPECIALIST):
        raise ValueError('분석 모델은 Sol 또는 Astra를 선택하세요.')
    return model


def model_label(model):
    return 'Astra' if analysis_model(model) == SPECIALIST else 'Sol'
