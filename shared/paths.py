"""Canonical monorepo locations, independent of import compatibility links."""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EDITOR_ROOT = PROJECT_ROOT / 'services/editor'
ANALYZER_ROOT = PROJECT_ROOT / 'services/analyzer'
DATA_ROOT = PROJECT_ROOT / 'shared/data'
EDITOR_FRONTEND = EDITOR_ROOT / 'vendor/velxio/frontend'
ANALYZER_FRONTEND = ANALYZER_ROOT / 'frontend'
