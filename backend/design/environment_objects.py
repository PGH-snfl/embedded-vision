"""Environmental vessels are pinless; the pump is a two-terminal electrical part."""
import json
from copy import deepcopy
from pathlib import Path

PRESET = Path(__file__).resolve().parents[2]/'data/environment-objects.json'


def watering_environment():
    return json.loads(PRESET.read_text())


def environment_components():
    preset=watering_environment();scale=96/25.4;components=[]
    for item in preset['objects']:
        props={k:item[k] for k in ('width','height','depth','color','label')}
        props.update(shape='box' if item['kind'] in {'pump','hose'} else 'cylinder',
            elevation=0,rotation=0,rotationX=0,rotationZ=0,
            environmentKind=item['kind'],environmentPreset=f"watering-v{preset['version']}",
            visualOnly=True,designBasis='authored_functional_environment')
        if item['kind']=='pump':props.update(waterSystem=deepcopy(preset['binding']),nominalVoltage=12,resistance=48,inductance=0.005,visualOnly=False)
        if item['kind']=='hose':props['connected']=True
        components.append({'id':item['id'],'metadataId':'dc-water-pump' if item['kind']=='pump' else 'ev-structure',
            'x':round((item['center_mm'][0]-item['width']/2)*scale-6,4),
            'y':round((item['center_mm'][1]-item['depth']/2)*scale-6,4),
            'properties':props})
    return components
