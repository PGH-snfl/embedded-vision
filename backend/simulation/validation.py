"""Independent numerical checks; simulation success is not hardware certification."""
import math


def validate_divider(vectors,analysis,values):
    axis='time' if analysis=='transient' else 'v-sweep'
    required=[axis,'vcc_5v','tp_divider','vsupply#branch']
    for name in required:
        a=vectors.get(name)
        if not isinstance(a,list) or len(a)<2 or any(not isinstance(v,(float,int)) or not math.isfinite(v) for v in a):
            raise ValueError('ngspice 필수 결과가 누락되었거나 유효하지 않습니다: '+name)
    if len({len(vectors[n]) for n in required})!=1:raise ValueError('ngspice 결과 길이가 서로 다릅니다.')
    source=vectors['vcc_5v'];output=vectors['tp_divider'];current=[-x for x in vectors['vsupply#branch']]
    r1,r2=values['R1'],values['R2'];ratio=r2/(r1+r2)
    expected=[v*ratio for v in source]
    error=max(abs(a-b) for a,b in zip(output,expected))
    current_error=max(abs(a-v/(r1+r2)) for a,v in zip(current,source))
    checks=[{'name':'A0 전압이 분압 계산과 일치','passed':error<1e-6,'maximum_error_v':error},
            {'name':'직렬 저항 전류가 옴의 법칙과 일치','passed':current_error<1e-9,'maximum_error_a':current_error},
            {'name':'모든 시점에서 A0가 GND~공급 전압 범위','passed':all(-1e-9<=o<=v+1e-9 for o,v in zip(output,source))},
            {'name':'5V 공급 조건까지 계산 완료','passed':abs(source[-1]-5)<1e-6 and abs(output[-1]-5*ratio)<1e-6}]
    return {'status':'PASS' if all(c['passed'] for c in checks) else 'FAIL','checks':checks,
      'metrics':{'supply_voltage_v':source[-1],'a0_voltage_v':output[-1],'resistor_current_ma':current[-1]*1000,
        'r1_power_mw':current[-1]**2*r1*1000,'r2_power_mw':current[-1]**2*r2*1000,
        'ideal_adc_count_estimate':round(output[-1]/source[-1]*1023) if source[-1]>0 else None},
      'assumptions':['R1=R2=10kΩ은 새 설계 사양이며 사진에서 측정한 값이 아닙니다.',
                     '전원 상승 0→5V/1ms는 시험 자극이며 실제 USB 전원 파형이 아닙니다.' if analysis=='transient' else 'DC 스윕은 0~5V의 각 전압에서 정적 동작점을 계산합니다.',
                     '저항 오차·배선 기생성분·ADC 부하·부품 정격 검증은 포함하지 않습니다.'],
      'meaning':'PASS는 이 모델의 전압·전류 계산이 예상과 일치한다는 뜻입니다. 실제 조립·펌웨어 동작 보증이 아닙니다.'}
