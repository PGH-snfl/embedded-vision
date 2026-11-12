"""Export the editor's name-only picker hints for the independent analyzer."""
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.design.simulator_catalog import load_simulator_catalog
from shared.paths import EDITOR_FRONTEND,DATA_ROOT

catalog=load_simulator_catalog(EDITOR_FRONTEND)
if catalog['status']!='available':raise SystemExit('실제 편집기 목록을 읽지 못해 기존 공용 목록을 유지합니다.')
(DATA_ROOT/'simulator-catalog-snapshot.json').write_text(json.dumps(catalog,ensure_ascii=False,indent=2)+'\n')
print('Shared component catalogue:',len(catalog['entries']))
