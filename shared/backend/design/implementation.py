"""Materialize a selected function as parts, wiring, code and structural choices."""
from copy import deepcopy
from .functional_build import build_workbench, implementation_catalog, validate_build
from .models import Inventory
from .hypotheses import validate_hypotheses
from .prototype_match import prototype_kind
from .enclosure_analysis import validate_enclosure_analysis
from .photo_appearance import attach_photo_appearance


def realize(plan,candidate,provenance):
    if not candidate:return None
    raw=plan.get('functional_build')
    inv=Inventory.model_validate(plan['inventory'])
    hs=validate_hypotheses(plan.get('function_hypotheses',[]),inv,set(plan['asset_ids']))
    validate_enclosure_analysis(plan.get('enclosure_analysis'),inv,hs,plan.get('required_parts',[]),plan.get('photo_structure'))
    if raw and raw.get('hypothesis_id')==candidate['id']:
        raw=validate_build(raw,inv,hs,plan.get('enclosure_analysis'))
        workbench=build_workbench(raw,provenance,plan.get('enclosure_analysis'))
        workbench=attach_photo_appearance(workbench,plan.get('photo_structure'))
        return {'workbench':workbench,'design':workbench['embeddedVision']['implementation_design']}
    if plan.get('board_selection',{}).get('fallback_allowed') is False:
        return None
    # Existing saved analyses can become concrete designs without a billed reanalysis.
    kind=prototype_kind(candidate);workbench=None;description=candidate['output_behavior']
    if kind=='watering':
        from .watering_prototype import watering_workbench
        workbench=watering_workbench(provenance)
    elif kind=='distance_indicator':
        from .distance_indicator import distance_design
        workbench=distance_design()['workbench']
    elif kind=='obstacle_rover':
        from .obstacle_rover import export_obstacle_project
        workbench=export_obstacle_project(provenance)
    elif candidate['kind'] not in {'unsupported','unknown'}:
        from .function import CATALOG
        from .recipes import new_graph
        from ..workbench.export import export_project
        recipe=CATALOG.get(candidate['kind'],{}).get('recipe')
        if recipe:
            function={'display_text':candidate.get('display_text') or 'Ready'}
            # An unreadable original display can still use an explicit new-design message.
            workbench=export_project(new_graph('0'*32,recipe)[0],{**provenance,'function':function})
    if workbench is None:return None
    workbench=complete_reference(workbench,plan.get('enclosure_analysis'),candidate)
    workbench['embeddedVision'].update(provenance)
    workbench=attach_photo_appearance(workbench,plan.get('photo_structure'))
    design=workbench['embeddedVision']['implementation_design'];design['behavior']=description
    return {'workbench':workbench,'design':design}


def complete_reference(original,enclosure,candidate):
    project=deepcopy(original);catalog=implementation_catalog();parts=[]
    for item in [*project.get('boards',[]),*project.get('components',[])]:
        model=item.get('boardKind') or item.get('metadataId');props=item.setdefault('properties',{})
        profile=catalog.get(model,{})
        name=profile.get('name') or props.get('label') or item.get('name') or model
        value=props.get('value')
        if value is not None and model in {'resistor','capacitor','capacitor-electrolytic'}:name+=f' · {value}'+('Ω' if model=='resistor' else '')
        purpose='기능 실행용 전자 부품' if model!='ev-structure' else '동작·장착을 위한 구조물'
        chosen={'status':'DESIGN_SELECTED','model_id':model,'name':name,'quantity':1,'purpose':purpose,
            'selection_reason':'선택한 기능의 기존 실행 회로에서 부품·배선·값을 구체적으로 선정했습니다.',
            'parameters':{k:v for k,v in props.items() if k in {'value','voltage','color','nominalVoltage'}},
            'module_refs':[],'location':'external' if props.get('environmentKind') else 'internal'}
        props['evSelectedDesign']=chosen;props['evDesignMount']=chosen['location'];parts.append({'id':item['id'],**chosen})
    choices=['사진의 기능을 수행하는 새 회로의 부품·값·코드를 선정했습니다.']
    if enclosure and enclosure.get('enclosures'):
        # Keep reviewed breadboard seating and wire geometry together. Size the new housing
        # around the complete electrical assembly rather than moving individual contacts.
        fit=[p for p in [*project.get('boards',[]),*project.get('components',[])] if p.get('metadataId') not in {'ev-structure','dc-water-pump'}]
        factor=96/25.4;bounds=[]
        for p in fit:
            model=p.get('boardKind') or p.get('metadataId');sz=catalog.get(model,{}).get('size_mm',[170,20,65] if model=='breadboard' else [45,20,30])
            x=(p.get('x',0)+(0 if p.get('boardKind') else 6))/factor;z=(p.get('y',0)+(0 if p.get('boardKind') else 6))/factor
            bounds.append((x,z,x+sz[0],z+sz[2]))
        if bounds:
            x=min(b[0] for b in bounds)-18;z=min(b[1] for b in bounds)-18
            w=max(b[2] for b in bounds)-x+18;d=max(b[3] for b in bounds)-z+18
            case=enclosure['enclosures'][0]
            shell={'id':'build-case-'+case['id'],'metadataId':'ev-structure','x':x*factor-6,'y':z*factor-6,
                'properties':{'label':case['name'],'shape':'box','width':w,'height':100,'depth':d,'elevation':-8,'color':'#8c9ca7',
                  'visualOnly':True,'dimensionsStatus':'DESIGN_SELECTED','designBasis':'functional_implementation',
                  'evEnclosure':{'id':case['id'],'name':case['name'],'design_selected':True,'rationale':'선정한 회로·빵판 배치와 배선 여유를 수용하도록 설계한 외장입니다.','assumptions':choices,'unknowns':[]}}}
            project['components'].append(shell)
            for item in [*project.get('boards',[]),*project.get('components',[])]:
                if item.get('properties',{}).get('evDesignMount')=='internal':item['properties']['evDesignEnclosure']=shell['id']
    structures=[{'id':p['id'],'label':p['properties'].get('label',p['id']),
        'size_mm':[p['properties'].get(k,0) for k in ['width','height','depth']],
        'purpose':p['properties'].get('evEnclosure',{}).get('rationale') or '기능 동작과 장착에 필요한 구조'}
        for p in project.get('components',[]) if p.get('metadataId')=='ev-structure']
    connections=[{'source':w['start']['componentId']+'.'+w['start']['pinName'],
        'target':w['end']['componentId']+'.'+w['end']['pinName']} for w in project.get('wires',[])]
    project['embeddedVision'].update(implementation_design={'status':'DESIGN_SELECTED','hypothesis_id':candidate['id'],'title':project['name'],
        'behavior':candidate['output_behavior'],'parts':parts,'structures':structures,'connections':connections,
        'design_choices':choices,'acceptance_tests':[candidate['distinguishing_check']],'not_implemented':[],
        'firmware':{'language':'arduino_cpp','source':project.get('fileGroups',{}).get('group-U1',[{}])[0].get('content','')}},
        enclosure_analysis=enclosure)
    return project
