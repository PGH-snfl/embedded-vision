"""Auditable local command parser. No hidden LLM service or unreviewed tool execution."""
import math,re,uuid
from .circuit.schema import Claim,Evidence,Status
from .circuit.profiles import number

def answer(graph,prompt):
    text=prompt.strip()
    if not text:raise ValueError('명령을 입력하세요.')
    response={'engine':'local_command_parser','changed':False,'revision':graph.revision}
    match=re.search(r'(?<![A-Za-z0-9_])([RC]\d+)(?![A-Za-z0-9_]).*?(?:([0-9.]+\s*[kKMmunpµμ]?(?:Ω|F|ohm)?))(?:\s*(?:에서|→|->)\s*([0-9.]+\s*[kKMmunpµμ]?(?:Ω|F|ohm)?))?',text)
    cutoff=re.search(r'(?:cutoff|차단\s*주파수).*?([0-9.]+)\s*(k?Hz)',text,re.I)
    frequency=re.search(r'(?:주파수|frequency).*?([0-9.]+)\s*(k?Hz)',text,re.I)
    if match or cutoff or frequency:
        if graph.mode!='reference_design':raise ValueError('관측된 사진을 설계 변경으로 덮어쓰지 않습니다. 설계 예제 프로젝트에서 값을 변경하세요.')
        eid='agent_'+uuid.uuid4().hex[:8]
        graph.evidence.append(Evidence(id=eid,asset_id='image',method='agent_edit',text='사용자 설계 명령: '+text))
        if cutoff:
            if graph.profile!='rc_filter':raise ValueError('차단 주파수 변경은 RC 예제에서 지원합니다.')
            hz=float(cutoff[1])*(1000 if cutoff[2].lower().startswith('k') else 1)
            if not .1<=hz<=1e6:raise ValueError('주파수 지원 범위: 0.1 Hz~1 MHz')
            capacitor=next(c for c in graph.components if c.id=='C1')
            component=next(c for c in graph.components if c.id=='R1')
            value=str(round(1/(2*math.pi*hz*number(capacitor.value.value)),5))
            component.value=Claim(value=value,status=Status.CONFIRMED,evidence_ids=[eid],reason='RC 차단 주파수 공식으로 계산한 설계 목표')
            response['message']=f'R1을 {value} Ω으로 변경했습니다. f_c=1/(2πRC)를 적용했습니다.'
        elif match:
            component=next((c for c in graph.components if c.id==match[1]),None)
            if component is None:raise ValueError('해당 부품이 없습니다.')
            value=(match[3] or match[2]).replace(' ','');number(value)
            component.value=Claim(value=value,status=Status.CONFIRMED,evidence_ids=[eid],reason='사용자가 지정한 새 설계 값')
            response['message']=f'{component.id}을 {value}로 변경했습니다. 이전 시뮬레이션·EDA 결과는 새 버전에 적용되지 않습니다.'
        else:
            hz=float(frequency[1])*(1000 if frequency[2].lower().startswith('k') else 1)
            if not .1<=hz<=1e6:raise ValueError('주파수 지원 범위: 0.1 Hz~1 MHz')
            graph.parameters['frequency']=hz;response['message']=f'주파수를 {hz:g} Hz로 변경했습니다.'
        response['changed']=True
    elif 'PCB' in text.upper() or '회로도' in text and ('만들' in text or '생성' in text):
        response.update(action='build',message='현재 리비전의 검증 조건을 확인한 뒤 회로도 → 연결 대조 → ERC → PCB → DRC를 실행합니다.')
    elif any(s in text for s in ['둥글','필터','커패시터']):
        response['message']='커패시터는 전하를 저장하므로 전압이 순간적으로 바뀌지 않습니다. 저항과 함께 빠른 변화(높은 주파수)를 줄여 출력이 완만해집니다. RC 예제의 CH1=TP_INPUT, CH2=TP_FILTER_OUT을 비교하세요.'
    elif any(s in text for s in ['버튼','LED','명령']):
        response['message']='GPIO18은 버튼을 읽습니다. 외부 10kΩ 저항이 평소 HIGH를 유지하고 버튼을 누르면 GND에 연결되어 LOW가 됩니다. 코드는 30ms 동안 안정된 입력을 확인한 뒤 GPIO23을 HIGH로 바꿔 LED를 켭니다.'
    elif any(s in text.upper() for s in ['UNKNOWN','미확인','근거']):
        unknown=[w.id for w in graph.links if w.connection.status!=Status.CONFIRMED]
        response['message']='확인이 필요한 연결: '+(', '.join(unknown) if unknown else '현재 지정한 배선에는 없음')+'. 사진에서 두 끝점을 확인하거나 전원을 끈 상태에서 도통(전기가 통하는지)을 측정하세요.'
    else:
        response['message']='지원 명령: “R1을 1kΩ으로 바꿔”, “차단 주파수를 1kHz로 맞춰”, “주파수 500Hz”, “PCB 만들어”, “왜 출력이 둥글어?”, “버튼 명령 설명”. 현재는 로컬 명령 해석기이며 범용 대화형 LLM은 연결되지 않았습니다.'
    return graph,response
