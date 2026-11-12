import json, subprocess, sys
from pathlib import Path
from ..circuit.profiles import number, readiness, named_nets
from ..firmware import firmware

def simulate(graph,folder,analysis='transient'):
    if analysis not in {'transient','ac','dc'}:raise ValueError('지원 분석: transient, ac, dc')
    blockers=readiness(graph)
    if blockers:raise ValueError(' / '.join(blockers[:8]))
    values={c.id:number(c.value.value) for c in graph.components if c.kind in {'resistor','capacitor'}}
    frequency=graph.parameters.get('frequency',1000);amplitude=graph.parameters.get('amplitude',1)
    if not .1<=frequency<=1e6 or not .001<=amplitude<=3.3:raise ValueError('주파수 0.1 Hz~1 MHz, 진폭 0.001~3.3 V 범위입니다.')
    period=1/frequency
    if graph.profile=='arduino_voltage_divider':
        if analysis=='ac':raise ValueError('UNO 분압 회로는 시간 응답(transient)과 전원 스윕(dc)을 지원합니다.')
        if graph.parameters.get('supply_voltage')!=5:raise ValueError('UNO 분압 설계의 공급 전압은 5V로 고정됩니다.')
        # Same graph nets as KiCad, not an independent guessed wire template.
        net_for={t:('0' if 'U1.GND' in n['terminals'] else n['name']) for n in named_nets(graph) for t in n['terminals']}
        lines=['UNO voltage divider / ideal supply and resistors / NOT MCU execution',
               'VSUPPLY VCC_5V 0 DC 5 PWL(0 0 1m 5 5m 5)']
        for ref in ['R1','R2']:lines.append(f'{ref} {net_for[ref+".1"]} {net_for[ref+".2"]} {values[ref]}')
        deck='\n'.join(lines+['.end',''])
        nodes=['VCC_5V','TP_DIVIDER']
        command='tran 10u 5m' if analysis=='transient' else 'dc vsupply 0 5 0.05'
        note='실제 ngspice 해석. 이상적 5V 전원·10kΩ 저항 2개·부하 없는 A0 모델입니다. MCU/ADC·Arduino 코드·실물 동작은 실행하지 않았습니다.'
    elif graph.profile=='rc_filter':
        if not 10<=values['R1']<=1e7 or not 1e-12<=values['C1']<=.01:raise ValueError('RC 값이 지원 범위 밖입니다.')
        deck=f'RC filter\nVINPUT TP_INPUT 0 DC 0 AC {amplitude} SIN(0 {amplitude} {frequency})\nR1 TP_INPUT TP_FILTER_OUT {values["R1"]}\nC1 TP_FILTER_OUT 0 {values["C1"]}\n.end\n'
        nodes=['TP_INPUT','TP_FILTER_OUT'];note='실제 ngspice RC 해석. 이상적 신호원과 수동소자 모델입니다.'
        command={'transient':f'tran {period/150} {period*5}', 'ac':'ac dec 50 1 1000000','dc':f'dc vinput 0 {amplitude} {amplitude/100}'}[analysis]
    elif graph.profile=='esp32_led_button':
        firmware(graph)
        if analysis=='ac':raise ValueError('디지털 버튼 예제의 AC 소신호 분석은 지원하지 않습니다. RC 예제를 사용하세요.')
        if not 220<=values['R1']<=10000 or not 1000<=values['R2']<=100000:raise ValueError('예제의 R1 허용 범위 220~10kΩ, R2 1k~100kΩ입니다.')
        voltage=graph.parameters.get('supply_voltage',3.3)
        if voltage!=3.3:raise ValueError('ESP32 예제 전원은 3.3 V로 고정됩니다.')
        deck=f'''ESP32 LED behavioral driver / NOT MCU simulation
VCC VCC_3V3 0 3.3
VDRIVE TP_LED_DRIVE 0 PULSE(0 3.3 {period/4} 1u 1u {period/2} {period})
R1 TP_LED_DRIVE TP_LED_ANODE {values['R1']}
D1 TP_LED_ANODE 0 LED_APPROX
.model LED_APPROX D(Is=1e-17 N=2 Rs=5)
R2 VCC_3V3 TP_BUTTON {values['R2']}
S1 TP_BUTTON 0 TP_LED_DRIVE 0 SWMODEL
.model SWMODEL SW(Ron=0.1 Roff=1e9 Vt=1.65 Vh=0.1)
.end
'''
        nodes=['TP_LED_DRIVE','TP_LED_ANODE','TP_BUTTON'];note='ngspice 계산 결과. MCU는 이상적 출력원, LED는 근사 다이오드 모델이며 제조사 SPICE/펌웨어 실행 결과가 아닙니다.'
        command=f'tran {period/200} {period*3}' if analysis=='transient' else 'dc vdrive 0 3.3 0.033'
    else:raise ValueError('현재 그래프는 지원하는 시뮬레이션 프로필이 아닙니다.')
    folder.mkdir(parents=True,exist_ok=True);path=folder/'circuit.cir';path.write_text(deck)
    result=subprocess.run([sys.executable,'-m','backend.simulation.worker',str(path),command],capture_output=True,text=True,timeout=25)
    if result.returncode:raise ValueError(result.stderr[-1500:])
    # libngspice may print a banner before the worker JSON.
    vectors=json.loads(next(line for line in reversed(result.stdout.splitlines()) if line.startswith('{')))
    response={'revision':graph.revision,'analysis':analysis,'engine':'libngspice','nodes':nodes,'vectors':vectors,'deck':deck,'note':note,
              'current_reference':'전압원 branch 전류는 +단자로 들어가는 방향이 양수입니다. LED 경로 전류는 -i(VDRIVE), RC 입력 전류는 -i(VINPUT)입니다.'}
    if graph.profile=='arduino_voltage_divider':
        from .validation import validate_divider
        response['validation']=validate_divider(vectors,analysis,values)
        response['current_reference']='전원에서 저항 쪽으로 흐르는 전류 = -i(VSUPPLY). SPICE의 양수 방향은 전압원 +단자로 들어가는 방향입니다.'
        response['scope']={'analog':'SIMULATED','firmware':'NOT_RUN','adc':'NOT_EMULATED','hardware':'NOT_TESTED'}
        from ..planner.service import digest
        response['graph_sha256']=digest(graph)
    (folder/'simulation.json').write_text(json.dumps(response,ensure_ascii=False))
    return response
