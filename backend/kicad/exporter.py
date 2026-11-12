"""Graph -> schematic -> exported connectivity -> ERC -> PCB. Immutable per revision."""
import copy, hashlib, json, math, subprocess, sys, uuid, zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
import sexpdata as sx
from ..circuit.profiles import readiness, named_nets
from ..datasheet.catalog import CATALOG

def tag(node):return str(node[0]) if isinstance(node,list) and node else None
def children(node,name):return [c for c in node if tag(c)==name]
def one(node,name):return next((c for c in node if tag(c)==name),None)
def walk(node,name):
    for child in node:
        if isinstance(child,list):
            if tag(child)==name:yield child
            yield from walk(child,name)
def S(name,*args):return [sx.Symbol(name),*args]
def uid():return str(uuid.uuid4())
def effects():return S('effects',S('font',S('size',1.27,1.27)))

def command(args):
    p=subprocess.run(args,capture_output=True,text=True,timeout=60)
    if p.returncode not in {0,5}:raise ValueError('KiCad command failed: '+p.stderr[-1200:]+p.stdout[-1200:])
    return p

def create_schematic(graph,folder):
    if graph.profile in {'arduino_lcd','arduino_voltage_divider','arduino_led_output','arduino_led_blink','arduino_led_brightness','arduino_led_button','arduino_light_led'}:raise ValueError('새 Arduino 설계는 MCP 회로도 경로를 사용하세요. PCB 풋프린트는 미지정입니다.')
    blockers=readiness(graph)
    if blockers:raise ValueError(' / '.join(blockers[:12]))
    folder.mkdir(parents=True,exist_ok=True)
    root_id=uid();symbol_defs={};placed=[];pins={};mapping={};layout={}
    nets=named_nets(graph);net_for={t:n['name'] for n in nets for t in n['terminals']}
    for i,c in enumerate(c for c in graph.components if c.kind!='breadboard'):
        entry=CATALOG[c.catalog_id]
        if c.kind=='board':
            # This PCB contains an external 4-pin interface, not a guessed DevKit footprint.
            lib_id='Connector_Generic:Conn_01x04';footprint='Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical'
            pinmap={"3V3":"1","GND":"2","GPIO23":"3","GPIO18":"4"}
        else:lib_id=entry['symbol'];footprint=entry['footprint'];pinmap=entry['pins']
        lib,name=lib_id.split(':')
        if lib_id not in symbol_defs:
            libtree=sx.loads((Path('/usr/share/kicad/symbols')/f'{lib}.kicad_sym').read_text())
            definition=copy.deepcopy(next(d for d in children(libtree,'symbol') if d[1]==name))
            if one(definition,'extends'):raise ValueError('Inherited symbol not supported')
            definition[1]=lib_id;symbol_defs[lib_id]=definition
        x=50.8+(i%3)*63.5;y=50.8+(i//3)*63.5;instance=uid()
        display=c.value.value or ('ESP32 external interface' if c.kind=='board' else entry['name'])
        props=[S('property','Reference',c.id,S('at',x+7.62,y-5.08,0),effects()),S('property','Value',display,S('at',x+7.62,y-2.54,0),effects()),
               S('property','Footprint',footprint,S('at',x,y,0),S('effects',S('font',S('size',1.27,1.27)),S('hide',sx.Symbol('yes')))),
               S('property','Datasheet',entry['source'] if entry.get('source_type')=='manufacturer_datasheet' else '',S('at',x,y,0),S('effects',S('font',S('size',1.27,1.27)),S('hide',sx.Symbol('yes')))),
               S('property','Reference_URL',entry['source'],S('at',x,y,0),S('effects',S('font',S('size',1.27,1.27)),S('hide',sx.Symbol('yes')))),
               S('property','Reference_Type',entry.get('source_type','unknown'),S('at',x,y,0),S('effects',S('font',S('size',1.27,1.27)),S('hide',sx.Symbol('yes'))))]
        symbol=S('symbol',S('lib_id',lib_id),S('at',x,y,0),S('unit',1),S('in_bom',sx.Symbol('yes')),S('on_board',sx.Symbol('yes')),S('dnp',sx.Symbol('no')),S('uuid',instance),*props,
                 S('instances',S('project','circuit',S('path','/'+root_id,S('reference',c.id),S('unit',1)))))
        pin_defs={str(one(p,'number')[1]):p for p in walk(symbol_defs[lib_id],'pin')}
        for t in c.terminals:
            label=t.name.value
            if label not in pinmap:raise ValueError(f'{t.id}: catalog pin label mismatch')
            num=pinmap[label];p=pin_defs[num];a=one(p,'at');px=round(x+float(a[1]),5);py=round(y-float(a[2]),5)
            angle=math.radians(float(a[3]));end=(round(px-5.08*math.cos(angle),5),round(py+5.08*math.sin(angle),5))
            pins[t.id]={'xy':(px,py),'end':end,'ref':c.id,'pin':num,'net':net_for[t.id]}
            symbol.append(S('pin',num,S('uuid',uid())))
            mapping[t.id]={'reference':c.id,'symbol_pin':num,'physical_pin':t.pin_mapping.value,'net':net_for[t.id],'symbol_uuid':instance}
        layout[c.id]={'footprint':footprint,'uuid':instance,'value':display}
        placed.append(symbol)
    root=S('kicad_sch',S('version',20250114),S('generator','embedded_vision'),S('uuid',root_id),S('paper','A4'),S('lib_symbols',*symbol_defs.values()))
    for pin in pins.values():
        a,b=pin['xy'],pin['end']
        root.append(S('wire',S('pts',S('xy',*a),S('xy',*b)),S('stroke',S('width',0),S('type',sx.Symbol('default'))),S('uuid',uid())))
        root.append(S('global_label',pin['net'],S('shape',sx.Symbol('bidirectional')),S('at',*b,0),effects(),S('uuid',uid())))
    root.extend(placed)
    note='DRAFT - External ESP32 interface header, not DevKit mounting footprint.' if any(c.kind=='board' for c in graph.components) else 'DRAFT - RC filter. Input connector includes signal and ground.'
    root.append(S('text',note+' Check hardware before power.',S('at',30.48,154.94,0),effects(),S('uuid',uid())))
    root.append(S('sheet_instances',S('path','/',S('page','1'))))
    path=folder/'circuit.kicad_sch';path.write_text(sx.dumps(root))
    # Local symbol table lets ERC compare against the installed, explicitly selected libraries.
    libnames=sorted({key.split(':')[0] for key in symbol_defs})
    (folder/'sym-lib-table').write_text(sx.dumps(S('sym_lib_table',S('version',7),*[S('lib',S('name',n),S('type','KiCad'),S('uri',f'/usr/share/kicad/symbols/{n}.kicad_sym'),S('options',''),S('descr','')) for n in libnames])))
    (folder/'circuit.kicad_pro').write_text('{}')
    (folder/'mapping.json').write_text(json.dumps(mapping,ensure_ascii=False,indent=2))
    return path,mapping,layout,root_id

def build(graph,folder,with_pcb=True):
    path,mapping,layout,root_id=create_schematic(graph,folder)
    xml=folder/'netlist.xml';command(['kicad-cli','sch','export','netlist','--format','kicadxml','-o',str(xml),str(path)])
    tree=ET.parse(xml)
    observed={frozenset((n.attrib['ref'],n.attrib['pin']) for n in net.findall('node')) for net in tree.findall('./nets/net')}
    expected={frozenset((mapping[t]['reference'],mapping[t]['symbol_pin']) for t in net['terminals']) for net in named_nets(graph)}
    if observed!=expected:raise ValueError(f'Schematic connectivity mismatch: expected {expected}, observed {observed}')
    erc=folder/'erc.json';command(['kicad-cli','sch','erc','--format','json','--severity-all','-o',str(erc),str(path)])
    report=json.loads(erc.read_text());violations=[v for sheet in report.get('sheets',[]) for v in sheet.get('violations',[])]
    command(['kicad-cli','sch','export','svg','-o',str(folder/'schematic'),str(path)])
    result={'revision':graph.revision,'schematic_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'connectivity':'PASS','erc':'PASS' if not violations else 'FAIL','erc_violations':violations,'pcb':'BLOCKED','drc':'NOT_RUN','mapping':mapping,
            'note':('PCB는 ESP32 보드 자체가 아닌 4핀 외부 연결용 LED/버튼 보드입니다. ' if any(c.kind=='board' for c in graph.components) else 'RC 필터 PCB입니다. 입력 커넥터의 신호/GND를 구분하세요. ')+'설계 검사는 실제 조립·작동 검증을 대체하지 않습니다.'}
    if with_pcb and not violations:
        spec={'layout':layout,'root_uuid':root_id,'netlist':str(xml),'output':str(folder/'circuit.kicad_pcb')}
        (folder/'pcb-input.json').write_text(json.dumps(spec))
        p=subprocess.run(['/usr/bin/python3',str(Path(__file__).with_name('pcb.py')),str(folder/'pcb-input.json')],capture_output=True,text=True,timeout=90)
        if p.returncode:raise ValueError('PCB build: '+p.stderr[-2000:])
        result['pcb']='GENERATED'
        drc=folder/'drc.json';command(['kicad-cli','pcb','drc','--format','json','--severity-all','-o',str(drc),str(folder/'circuit.kicad_pcb')])
        dr=json.loads(drc.read_text());issues=dr.get('violations',[])+dr.get('unconnected_items',[])+dr.get('schematic_parity',[])
        result['drc']='PASS' if not issues else 'FAIL';result['drc_violations']=issues
        command(['kicad-cli','pcb','export','svg','--layers','F.Cu,B.Cu,F.Silkscreen,Edge.Cuts','--page-size-mode','2','--exclude-drawing-sheet','--mode-single','-o',str(folder/'pcb.svg'),str(folder/'circuit.kicad_pcb')])
        geometry=folder/'pcb-geometry.json'
        if geometry.exists():result['pcb_geometry']=json.loads(geometry.read_text())
    result['files']=[str(p.relative_to(folder)) for p in folder.rglob('*') if p.is_file()]
    (folder/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    with zipfile.ZipFile(folder/'project.zip','w',zipfile.ZIP_DEFLATED) as z:
        for f in folder.rglob('*'):
            if f.is_file() and f.name!='project.zip':z.write(f,str(f.relative_to(folder)))
    return result
