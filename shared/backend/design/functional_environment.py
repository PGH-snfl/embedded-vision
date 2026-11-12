"""Bind a generated, matching pump circuit to the existing watering world."""
from copy import deepcopy
from .environment_objects import environment_components,watering_environment


def attach_watering_environment(components,wires):
    by_model={}
    for p in components:by_model.setdefault(p['metadataId'],[]).append(p)
    models=['dc-water-pump','soil-moisture-sen0193','mosfet-irlz44n','dc-power-supply']
    if any(len(by_model.get(m,[]))!=1 for m in models):return []
    pump,sensor,driver,supply=[by_model[m][0] for m in models]
    pairs=[(w['start']['componentId']+'.'+w['start']['pinName'],w['end']['componentId']+'.'+w['end']['pinName']) for w in wires]
    edges={frozenset(p) for p in pairs}
    # Feedback reader has an explicit UNO A0 sensor contract. Other arrangements
    # keep their own circuit simulation and are not assigned a fictitious water loop.
    if frozenset([sensor['id']+'.SIG','U1.A0']) not in edges:return []
    gate=None
    for resistor in by_model.get('resistor',[]):
        for a,b in [('1','2'),('2','1')]:
            if frozenset([resistor['id']+'.'+a,driver['id']+'.G']) not in edges:continue
            end=resistor['id']+'.'+b
            match=next((other for x,y in pairs for pin,other in [(x,y),(y,x)] if pin==end and other.startswith('U1.') and other[3:].isdigit()),None)
            if match:gate=(resistor['id'],int(match[3:]));break
        if gate:break
    if not gate:return []
    existing={p['id'] for p in components};added=[];mapping={}
    factor=96/25.4;px=(pump['x']+6)/factor+16;pz=(pump['y']+6)/factor+12.5
    for p in environment_components():
        if p['metadataId']=='dc-water-pump':continue
        old=p['id'];name='BUILD_'+old
        while name in existing:name+='_1'
        existing.add(name);mapping[old]=name;p['id']=name
        p['x']+=(px-115)*factor;p['y']+=(pz+10)*factor
        p['properties']['dimensionsStatus']='DESIGN_SELECTED'
        p['properties']['evSelectedDesign']={'status':'DESIGN_SELECTED','name':p['properties']['label'],
            'purpose':'관측한 급수 기능을 실행하고 물 이동을 표시하는 구성물','selection_reason':'선정한 펌프 회로와 토양 센서를 연결한 동작 환경','quantity':1}
        added.append(p)
    binding=deepcopy(watering_environment()['binding'])
    binding.update(boardId='U1',sensorId=sensor['id'],pumpId=pump['id'],driverId=driver['id'],supplyId=supply['id'],
        gateResistorId=gate[0],controlPin=gate[1],outputId=next((p['id'] for p in by_model.get('led',[])),pump['id']),
        planterId=mapping['ENV_PLANTER'],reservoirId=mapping['ENV_TANK'],hoseId=mapping['ENV_HOSE'])
    props=pump['properties'];props.update(environmentKind='pump',waterSystem=binding,width=32,height=25,depth=25,visualOnly=False)
    return added
