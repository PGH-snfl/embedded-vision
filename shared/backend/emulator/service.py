"""UNO firmware execution, with one-way analog input from ngspice.

Only the application's reviewed UNO divider firmware is compiled. No external
source, ELF, command, arbitrary MCU, or unbounded duration is accepted by the API.
"""
import hashlib,json,math,uuid
from pathlib import Path
from ..firmware import firmware
from ..circuit.profiles import readiness
from ..planner.service import digest
from ..simulation.service import simulate
from .toolchain import compile_firmware,command,fingerprint


def parse_execution(events,scenario):
    adcs=[];rows=[];serial=[];line='';headers=[];complete=None
    for e in events:
        if e['event']=='adc':adcs.append(e)
        elif e['event']=='uart':
            ch=chr(e['byte']);serial.append(ch)
            if ch=='\n':
                text=line.strip();line=''
                if text=='raw,ratio,estimated_voltage_V':headers.append(text);continue
                try:
                    parts=text.split(',')
                    if len(parts)!=3:continue
                    raw=int(parts[0]);ratio=float(parts[1]);voltage=float(parts[2])
                    if not adcs or not all(math.isfinite(v) for v in [ratio,voltage]):continue
                    a=adcs[-1]
                    rows.append({'time_ms':e['ms'],'adc_time_ms':a['ms'],'input_mv':a['mv'],
                       'channel':a['channel'],'raw':raw,'ratio':ratio,'estimated_voltage_v':voltage,'text':text})
                except ValueError:continue
            else:line+=ch
        elif e['event']=='complete':complete=e
    checks=[{'name':'컴파일한 MCU 명령을 가상 1.5초 실행','passed':bool(complete and not complete['crashed'] and complete['cycles']>=24000000)},
      {'name':'실제 ADC0 변환과 시리얼 출력 수신','passed':len(rows)>=7 and len(headers)==1 and len(adcs)==len(rows) and all(a['channel']==0 for a in adcs)},
      {'name':'입력 전압과 ADC 읽기 일치 (양자화 오차 ±1)','passed':bool(rows) and all(0<=r['raw']<=1023 and abs(r['raw']-r['input_mv']/5000*1023)<=1 for r in rows)},
      {'name':'코드가 계산한 비율·전압 출력 일치','passed':bool(rows) and all(abs(r['ratio']-r['raw']/1023)<=.00006 and abs(r['estimated_voltage_v']-r['raw']/1023*5)<=.0006 for r in rows)},
      {'name':'약 200ms 간격의 반복 실행','passed':len(rows)>=7 and all(195<=b['adc_time_ms']-a['adc_time_ms']<=205 for a,b in zip(rows,rows[1:]))}]
    if scenario=='input_steps':checks.append({'name':'1.25→2.5→3.75V 시험 입력에 응답','passed':{r['input_mv'] for r in rows}=={1250,2500,3750}})
    return {'status':'PASS' if all(c['passed'] for c in checks) else 'FAIL','checks':checks,
        'samples':rows,'adc_events':adcs,'serial_output':''.join(serial),'execution':complete}


def emulate(graph,folder,scenario='circuit'):
    if scenario not in {'circuit','input_steps'}:raise ValueError('지원 시험: circuit, input_steps')
    if graph.profile!='arduino_voltage_divider' or readiness(graph):raise ValueError('검토된 UNO R3 저항 분압 설계만 MCU 실행을 지원합니다.')
    source=firmware(graph)['source'];folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    (folder/'latest.json').unlink(missing_ok=True) # Prior attempts remain; never show an old PASS after a failed run.
    attempt=folder/uuid.uuid4().hex;attempt.mkdir()
    analog=simulate(graph,attempt/'analog','dc')
    if analog['validation']['status']!='PASS':raise ValueError('회로 계산이 PASS가 아니므로 MCU 실행을 중단합니다.')
    input_mv=round(analog['validation']['metrics']['a0_voltage_v']*1000)
    build=compile_firmware(source,attempt/'firmware')
    output=command([build['runner'],build['elf'],input_mv,scenario],timeout=20)
    (attempt/'events.jsonl').write_text(output)
    events=[json.loads(line) for line in output.splitlines() if line.startswith('{')]
    observed=parse_execution(events,scenario)
    result={**observed,'engine':'simavr','board':'Arduino UNO R3','mcu':'ATmega328P','clock_hz':16000000,
      'scenario':scenario,'compiled':True,'firmware_executed':True,'hardware_tested':False,
      'revision':graph.revision,'graph_sha256':digest(graph),'firmware_sha256':build['firmware_sha256'],
      'elf_sha256':build['elf_sha256'],'toolchain_sha256':build['toolchain_sha256'],'size_report':build['size_report'],
      'implementation_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'run_id':attempt.name,'analog':{'engine':analog['engine'],'status':analog['validation']['status'],'metrics':analog['validation']['metrics']},
      'input_source':'ngspice가 계산한 정상 상태 A0 전압' if scenario=='circuit' else 'ADC 테스트 입력 1.25/2.5/3.75V. 실제 분압 회로의 파형이 아닌 가상 핀 자극.',
      'coupling':'ngspice DC 정상 상태 → simavr ADC0의 단방향 연결. 시간 동기화·GPIO 피드백 연동은 아닙니다.',
      'limitations':['UNO R3의 생성된 분압 코드만 지원합니다. ESP32·Pico·LCD·모터 모델은 미지원입니다.',
        '부품값·배선의 실물 검증, ADC 잡음·공차·샘플링 부하, USB 전송 및 부트로더는 모델에 포함되지 않습니다.',
        '시리얼 로그는 ATmega328P UART 실행 결과입니다. 가상 시간 재생은 저장된 실행 결과를 재생합니다.']}
    (attempt/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False))
    (folder/'latest.json').write_text(json.dumps(result,ensure_ascii=False,allow_nan=False))
    return result


def saved_result(graph,folder):
    path=Path(folder)/'latest.json'
    if not path.exists():return None
    r=json.loads(path.read_text())
    try:
        source=firmware(graph)['source']
        if r.get('implementation_sha256')!=hashlib.sha256(Path(__file__).read_bytes()).hexdigest() or r.get('graph_sha256')!=digest(graph) or r.get('toolchain_sha256')!=fingerprint() or r.get('firmware_sha256')!=hashlib.sha256(source.encode()).hexdigest():return None
    except ValueError:return None
    return r
