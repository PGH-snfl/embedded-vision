"""One-way export of a proposed design, never a claim about observed wiring."""
from datetime import datetime, timezone
from ..circuit.schema import Status
from ..design.recipes import new_graph, LED_RECIPES, BUTTON_RECIPE, LIGHT_RECIPE
from ..firmware import firmware
from ..workflow import workflow_stamp


def export_project(graph, provenance=None):
    if graph.profile not in LED_RECIPES | {'arduino_voltage_divider','arduino_lcd',BUTTON_RECIPE,LIGHT_RECIPE}:
        raise ValueError('현재 자동 가져오기는 UNO 분압, LCD 및 LED 예제를 지원합니다.')
    from ..design.recipes import recipe_contract
    errors = recipe_contract(graph, graph.profile)
    if errors:
        raise ValueError(' / '.join(errors))
    components = []
    for c in graph.components:
        if c.kind == 'board': continue
        components.append({'id':c.id, 'metadataId':'lcd1602' if c.kind=='display' else 'potentiometer' if c.kind=='potentiometer' else 'led' if c.kind=='led' else 'pushbutton-6mm' if c.kind=='button' else 'photoresistor-sensor' if c.kind=='sensor' else 'resistor',
            'properties':{'pins':'full','background':'blue'} if c.kind=='display' else {'value':512} if c.kind=='potentiometer' else {'color':'red'} if c.kind in {'led','button'} else {'lux':500,'ldrModel':'wokwi'} if c.kind=='sensor' else {'value':'220' if c.id=='R1' and graph.profile in LED_RECIPES | {BUTTON_RECIPE,LIGHT_RECIPE,'arduino_lcd'} else '10000'}})
    from .breadboard import assemble,assemble_lcd,projected_nets
    wires,assembly=assemble_lcd(components) if graph.profile=='arduino_lcd' else assemble(components,graph.profile in LED_RECIPES | {BUTTON_RECIPE,LIGHT_RECIPE},graph.profile==BUTTON_RECIPE,graph.profile==LIGHT_RECIPE)
    logical=[]
    for i, link in enumerate(graph.links):
        if link.connection.status != Status.CONFIRMED:
            raise ValueError('미확인 연결은 편집기 배선으로 내보내지 않습니다.')
        def endpoint(t):
            ref,pin=t.split('.',1)
            if ref=='U1' and pin.startswith('D') and pin[1:].isdigit():pin=pin[1:]
            if ref=='D1' and pin=='K':pin='C'
            if ref=='SW1':pin={'1':'2.l','2':'1.l'}[pin]
            if ref=='RV1':pin={'END1':'VCC','END2':'GND','WIPER':'SIG'}[pin]
            if ref=='LCD1' and pin=='VO':pin='V0'
            return {'componentId':ref,'pinName':pin,'x':0,'y':0}
        logical.append({'start':endpoint(link.from_terminal),'end':endpoint(link.to_terminal)})
    if projected_nets(wires)!=projected_nets(logical):
        raise ValueError('빵판 배선과 논리 회로의 연결이 일치하지 않습니다.')
    if graph.profile=='arduino_lcd':
        from ..design.firmware import lcd_firmware
        message=(provenance or {}).get('function',{}).get('display_text')
        if not message:raise ValueError('LCD에 표시할 문구를 먼저 확인하세요.')
        source=lcd_firmware(graph,message,show_elapsed=False)['source']
    else:source=firmware(graph)['source']
    return {'format':'velxio-project','version':1,'exportedAt':datetime.now(timezone.utc).isoformat(),
        'name':graph.title,
        'boards':[{'id':'U1','name':'Arduino UNO · 새 설계','boardKind':'arduino-uno',
            'x':40,'y':80,'activeFileGroupId':'group-U1','languageMode':'arduino','serialBaudRate':115200}],
        'fileGroups':{'group-U1':[{'name':'sketch.ino','content':source}]},
        'components':components,'wires':wires,'activeBoardId':'U1',
        'embeddedVision':{'basis':'proposed_design_only','physical_verified':False,
            'original_wiring_reused':False,'assembly':assembly,'recipe':graph.profile,**(provenance or {}),'workflow':workflow_stamp()}}


def workbench_routes(app, get, proposals):
    from fastapi import HTTPException
    from ..planner.service import digest
    @app.get('/api/projects/{project}/inventory/{pid}/workbench')
    def proposal_workbench(project:str,pid:str,recipe:str='arduino_voltage_divider',function_version:str|None=None):
        offered=proposals(project,pid)
        if function_version is not None and function_version!=offered['function_version']:
            raise HTTPException(409,'설계 목표가 변경되었습니다. 현재 목표로 다시 여세요.')
        if recipe not in {p['recipe'] for p in offered['proposals']}:
            raise HTTPException(422,'현재 사진 부품에 맞는 제안이 아닙니다.')
        source=get(project)
        graph,_=new_graph('0'*32,recipe)
        try:
            proposal=next(p for p in offered['proposals'] if p['recipe']==recipe)
            return export_project(graph,{'source_project':project,'source_revision':source.revision,
                'source_graph_sha256':digest(source),'inventory_plan':pid,
                'function_version':offered['function_version'],'function':offered['function'],
                'component_datasheet':offered.get('component_datasheet'),
                'required_parts':[p for p in offered.get('required_parts',[]) if not p.get('hypothesis_ids') or offered.get('selected_hypothesis_id') in p['hypothesis_ids']],
                'simulation_behavior':proposal.get('simulation_behavior',''),
                'part_comparison':{'assignments':proposal['assignments'],'added_parts':proposal['added_parts'],
                    'replacements':proposal.get('replacements',[])},
                'simulation_notice':proposal.get('simulation_notice','')})
        except ValueError as e: raise HTTPException(422,str(e))
