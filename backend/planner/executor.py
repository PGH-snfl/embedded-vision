"""Compile verified graph deterministically. All KiCad mutations run via MCP."""
import hashlib, json
from pathlib import Path
import sexpdata as sx
from ..circuit.profiles import readiness, named_nets
from ..datasheet.catalog import CATALOG
from .mcp import McpSession, REQUIRED

def compile_graph(graph):
    blockers=readiness(graph)
    if blockers:raise ValueError(' / '.join(blockers[:12]))
    symbols=[]; mapping={}; notes=[]
    for c in graph.components:
        if c.kind=='breadboard':continue
        entry=CATALOG[c.catalog_id]
        if entry.get('schematic_pins'):
            lib=entry['symbol'];pins=entry['schematic_pins'];fp=entry['footprint'];notes.append(entry['note'])
        elif c.kind=='board':
            lib='Connector_Generic:Conn_01x04'; pins={'3V3':'1','GND':'2','GPIO23':'3','GPIO18':'4'}
            fp='Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical'
            notes.append('ESP32는 기존 예제의 4핀 외부 인터페이스 헤더로 표현합니다. DevKit 장착 풋프린트가 아닙니다.')
        else:lib=entry['symbol'];pins=entry['pins'];fp=entry['footprint']
        library,symbol=lib.split(':',1)
        symbols.append({'library':library,'symbol_name':symbol,'reference':c.id,
                        'value':c.value.value or entry['name'],'footprint':fp,
                        'properties':{'Physical pin labels':'; '.join(f'{pins[t.name.value]}={t.name.value} ({t.pin_mapping.value})' for t in c.terminals)}})
        for t in c.terminals:
            mapping[t.id]={'reference':c.id,'pin':pins[t.name.value]}
    nets=[{'name':n['name'],'pins':[mapping[t] for t in n['terminals']]} for n in named_nets(graph)]
    return {'symbols':symbols,'nets':nets,'auto_layout':True,'unsafe_routed_wires':False},notes

def children(node,name):return [c for c in node if isinstance(c,list) and c and str(c[0])==name]
def child(node,name):return next(iter(children(node,name)),None)

def verify_netlist(path,spec):
    tree=sx.loads(path.read_text()); nets=child(tree,'nets')
    if nets is None:raise ValueError('MCP netlist에 nets가 없습니다.')
    observed={frozenset((str(child(node,'ref')[1]),str(child(node,'pin')[1])) for node in children(net,'node')) for net in children(nets,'net')}
    expected={frozenset((p['reference'],p['pin']) for p in net['pins']) for net in spec['nets']}
    if observed!=expected:raise ValueError('Circuit Graph와 KiCad netlist 연결 불일치. 다음 작업을 중단합니다.')

def verdict(result):
    data=result.get('structuredContent',{})
    if data.get('verdict') in {'PASS','WARN','FAIL'}:return data['verdict']
    for block in result.get('content',[]):
        try:data=json.loads(block.get('text',''))
        except (ValueError,TypeError):continue
        if isinstance(data,dict) and data.get('verdict') in {'PASS','WARN','FAIL'}:return data['verdict']
    return 'UNKNOWN'

def execute(graph,folder,session_factory=McpSession):
    spec,notes=compile_graph(graph)
    folder=Path(folder).resolve();folder.mkdir(parents=True,exist_ok=False)
    result={'revision':graph.revision,'executor':'KiCad MCP','status':'RUNNING','steps':[],
            'connectivity':'NOT_RUN','erc':'NOT_RUN','pcb':'NOT_RUN','drc':'NOT_RUN','notes':notes}
    def record(): (folder/'execution.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    record()
    try:
        with session_factory(folder) as mcp:
            if REQUIRED-set(mcp.tools):raise RuntimeError('필수 MCP 도구가 누락되어 실행을 중단했습니다.')
            def call(name,args):
                response=mcp.call(name,args);result['steps'].append({'tool':name,'result':response});record();return response
            call('kicad_create_new_project',{'path':str(folder),'name':'circuit','confirm_overwrite':False})
            call('sch_build_circuit',spec)
            call('export_netlist',{'format':'kicad'})
            netlists=list((folder/'circuit').rglob('netlist.net'))
            if len(netlists)!=1:raise RuntimeError('MCP가 내보낸 netlist 파일을 하나로 식별하지 못했습니다.')
            verify_netlist(netlists[0],spec);result['connectivity']='PASS';record()
            erc=call('run_erc',{'save_report':True});result['erc']=verdict(erc);record()
            if result['erc']!='PASS':raise RuntimeError('ERC가 PASS가 아니므로 다음 단계로 진행하지 않습니다.')
            if 'export_sch_svg' in mcp.tools:call('export_sch_svg',{})
            path=folder/'circuit/circuit.kicad_sch'
            result.update(status='DONE',schematic_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    except Exception as exc:
        result.update(status='FAILED',error=str(exc)[:600])
    record();return result
