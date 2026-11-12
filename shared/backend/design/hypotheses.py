"""Grounded alternatives from existing observations; no new image/model call is implied."""
from .function import FunctionHypothesis,FunctionIntent,CATALOG

def validate_hypotheses(items,inventory,asset_ids):
    ids={p.id for p in inventory.parts};seen=set();result=[]
    for item in items:
        h=FunctionHypothesis.model_validate(item)
        if h.id in seen or not set(h.part_ids)<=ids:raise RuntimeError('기능 후보의 부품 참조가 관측 목록과 일치하지 않습니다.')
        if any(e.asset_id not in asset_ids for e in h.evidence):raise RuntimeError('기능 후보의 근거 이미지가 입력과 일치하지 않습니다.')
        seen.add(h.id);result.append(h)
    return result

def infer_candidates(inventory):
    """Qualitative hypotheses, not calibrated probabilities or confirmed behavior."""
    parts=inventory.parts
    def of(kind):return [p for p in parts if p.kind==kind]
    out=[]
    def is_light(part):
        import re
        text=' '.join([part.name,*part.model_candidates,*part.markings]).casefold()
        return bool(re.search(r'photoresistor|\bldr\b|light.?sensor|조도|광.?센서',text))
    lights=[p for p in of('sensor') if is_light(p)]
    def add(id,title,kind,used,reason,inputs,outputs,assumptions,check,strength='low',text=None):
        if not used:return
        out.append(FunctionHypothesis(id=id,title=title,kind=kind,status='INFERRED',plausibility=strength,
            rationale=reason,part_ids=[p.id for p in used],evidence=[{'asset_id':p.regions[0].asset_id,
            'observation':p.name+': '+p.evidence} for p in used[:4]],input_behavior=inputs,output_behavior=outputs,
            assumptions=assumptions,distinguishing_check=check,display_text=text))
    if lights:
        add('light_led','어두우면 LED 켜기','light_led',[lights[0],*of('led')[:1],*of('board')[:1]],
            '조도 센서와 제어 보드는 주변 밝기에 반응하는 장치에 사용할 수 있습니다.',
            '센서에 비치는 빛이 달라집니다.','어두워지면 LED를 켤 수 있습니다.',
            ['원래 기능과 실물 센서의 핀, 출력 방향은 사진만으로 확인되지 않습니다.'],
            '센서를 가리거나 비추며 LED 변화를 확인하세요.')
    if of('display'):
        display=of('display')[0];used=[display,*of('board')[:1]]
        import re
        text=next((m for m in display.markings if re.fullmatch(r'[A-Za-z0-9 .,!?_-]{1,16}',m) and re.search(r'\.(org|com|net)\b',m,re.I)),None)
        add('display_message','문자·상태 메시지 표시','lcd_text',used,
            '문자 디스플레이와 제어 보드 조합은 메시지나 상태를 출력하는 장치에 해당합니다.',
            '전원 공급 또는 프로그램 실행 시 표시 데이터를 전달하는 것으로 추정합니다.',
            '화면에 문구 또는 장치 상태를 표시합니다.',
            ['고정 문구인지, 값이 갱신되는지는 사진 한 장으로 구분되지 않습니다.'],
            '같은 문구가 유지되는지, 숫자·메시지가 바뀌는지 확인하세요.','medium',text)
        if of('potentiometer'):
            add('display_contrast','가변저항으로 LCD 대비 조절','unsupported',[display,of('potentiometer')[0]],
                'LCD 옆 가변저항은 글자의 대비 조절에 사용하는 구성과 일치할 수 있습니다.',
                '가변저항의 축을 돌립니다.','글자의 선명도·대비가 변할 가능성이 있습니다.',
                ['가변저항이 실제 대비 입력에 연결됐다는 것은 확인되지 않았습니다.'],
                '축을 돌릴 때 글자 농도가 바뀌는지, 표시 숫자가 바뀌는지 구분하세요.')
    elif of('led'):
        used=[*of('led')[:1],*of('resistor')[:1],*of('board')[:1]]
        if of('button'):
            add('button_led','버튼을 누르는 동안 LED 켜기','button_led',[of('led')[0],of('button')[0],*of('board')[:1]],
                '버튼과 LED를 함께 사용해 입력에 반응하는 회로일 수 있습니다.',
                '버튼을 누르거나 놓습니다.','누르는 동안 LED를 켤 수 있습니다.',
                ['버튼과 LED의 실제 연결과 프로그램 동작은 사진만으로 확인되지 않습니다.'],
                '버튼을 누르거나 놓을 때 LED가 변하는지 확인하세요.','medium')
        add('led_output','외부 LED 점등 제어 실습','led_output',used,
            '외부 LED·제어 보드와 배선은 LED 출력 제어 실습 구성에 부합합니다. 저항은 전류 제한용일 가능성이 있습니다.',
            '보드의 출력 신호 또는 전원 공급으로 LED를 구동하는 것으로 추정합니다.',
            '외부 LED를 켜거나 끄는 기능으로 추정합니다.',
            ['GPIO 제어인지 전원에 직접 연결한 것인지는 미확인입니다.','켜진 사진만으로 지속 점등을 확정하지 않습니다.'],
            '전원을 유지한 채 LED 상태가 변하는지 확인하면 다음 후보와 구분할 수 있습니다.','medium')
        add('led_blink','일정 간격으로 LED 깜빡이기','led_blink',used,
            '같은 LED·저항 회로는 프로그램으로 켜짐과 꺼짐을 반복하는 실습에도 사용됩니다.',
            '프로그램의 반복 실행 또는 타이머 신호가 있다고 가정합니다.',
            'LED가 일정 간격으로 켜졌다 꺼집니다.',
            ['사진은 점멸 중 켜진 순간일 수 있습니다.','점멸 여부와 주기는 관측되지 않았습니다.'],
            '몇 초 동안 켜짐·꺼짐이 반복되는지 확인하세요.')
        add('led_brightness','LED 밝기 조절','led_brightness',used,
            '보드가 빠른 켜짐·꺼짐 신호(PWM)를 출력하면 같은 LED 구성으로 밝기를 조절할 수 있습니다.',
            '프로그램이 켜져 있는 시간 비율을 바꾼다고 가정합니다.',
            'LED 밝기가 단계적 또는 연속적으로 변합니다.',
            ['PWM 신호와 밝기 변화는 관측되지 않았습니다.','밝기 조절용 입력 장치는 확인되지 않았습니다.'],
            '밝기가 부드럽게 바뀌는지, 완전히 켜짐·꺼짐만 반복되는지 비교하세요.')
    elif of('resistor') and of('board'):
        add('resistor_measurement','저항망의 전압·전류를 확인하는 실험','unsupported',[*of('board')[:1],*of('resistor')[:2]],
            '제어 보드와 여러 저항은 전압 분배·입력 상태 설정·측정 실험에 사용될 수 있습니다.',
            '전원이나 입력 신호를 저항망에 연결한 것으로 가정합니다.',
            '전압을 나누거나 입력 상태를 만들고, 보드에서 그 상태를 읽을 가능성이 있습니다.',
            ['저항이 있다는 사실만으로 분압·ADC·시리얼 출력을 특정할 수 없습니다.'],
            '화면·시리얼 출력이나 보드 핀 라벨을 확인하면 측정 회로인지 구분할 수 있습니다.')
    elif of('sensor'):
        add('sensor_monitor','센서 값을 읽는 모니터링 장치','unsupported',of('sensor')[:2],
            '센서 모듈은 환경이나 물리량을 입력으로 읽는 구성일 가능성을 뒷받침합니다.',
            '센서가 측정하는 물리량이 달라집니다.','값을 읽어 저장·표시·제어에 사용할 가능성이 있습니다.',
            ['센서 종류와 출력 대상, 제어 규칙은 미확인입니다.'],
            '센서 표식과 값이 나타나는 화면 또는 연결된 출력 장치를 확인하세요.')
    return out[:3]

def candidate_payload(plan,inventory):
    if plan.get('analysis_complete') is False:
        return {'function_hypotheses':[],'recommended_hypothesis_id':None,
                'hypothesis_source':'pending','hypothesis_note':'구성품 목록 저장 완료 · 기능 분석 중입니다.'}
    saved=plan.get('function_hypotheses')
    if saved:
        items=validate_hypotheses(saved,inventory,set(plan['asset_ids']));source=plan.get('hypothesis_source','multimodal_model')
    else:items=infer_candidates(inventory);source='stored_component_observations'
    # Preserve the model's explicitly observed behavior when it provides one:
    # it may not have separately repeated that behavior as a hypothesis.
    inferred=None
    if plan.get('function'):
        intent=FunctionIntent.model_validate(plan['function'])
        if intent.status=='INFERRED' and intent.kind!='unknown' and intent.evidence:
            inferred=next((h for h in items if h.kind==intent.kind and
                           (h.kind!='lcd_text' or h.display_text==intent.display_text)),None)
            if inferred is None:
                kinds={'lcd_text':{'display'},'voltage_readout':{'board','resistor'},
                       'button_led':{'button','led'},'light_led':{'sensor','led'},
                       'led_output':{'led'},'led_blink':{'led'},'led_brightness':{'led'}}
                used=[p for p in inventory.parts if p.kind in kinds.get(intent.kind,set()) and p.status!='UNKNOWN']
                if intent.kind=='unsupported':used=[p for p in inventory.parts if p.status!='UNKNOWN']
                selected_assets=set(plan.get('asset_ids',[]))
                if used and all(e.asset_id in selected_assets for e in intent.evidence):
                    taken={h.id for h in items};hid='observed_function'
                    while hid in taken:hid+='x'
                    inferred=FunctionHypothesis(id=hid,title=intent.summary[:120],kind=intent.kind,
                        status='INFERRED',plausibility='medium',rationale=intent.summary[:1000],
                        part_ids=[p.id for p in used[:20]],evidence=intent.evidence,
                        input_behavior=intent.input_behavior or '입력 조건을 확인해야 합니다.',
                        output_behavior=intent.output_behavior or '출력 동작을 확인해야 합니다.',
                        assumptions=(intent.unknowns[:10] or ['원래 기능과 새 설계의 일치 여부는 미확인입니다.']),
                        distinguishing_check='입력 변화에 따른 실제 출력과 새 설계의 동작을 비교하세요.',
                        display_text=intent.display_text)
                    items.insert(0,inferred)
    # Qualitative ranking, never a calibrated probability. Stable ordering
    # retains the model's order for equal strengths; simulation support plays
    # no part in selecting the recommendation.
    items=sorted(items,key=lambda h:(h is not inferred, h.plausibility!='medium'))
    return {'function_hypotheses':[h.model_dump(mode='json') for h in items],
            'recommended_hypothesis_id':items[0].id if items else None,
            'hypothesis_source':source,'hypothesis_note':'관측 기반 기능을 우선하고, 나머지는 추정 강도 순(중간 → 낮음), 동률은 분석 순서입니다. 측정된 정확도나 확률은 아닙니다.'}

def as_design_target(candidate):
    h=FunctionHypothesis.model_validate(candidate)
    # A candidate may describe a broader or uncertain behavior than the one
    # implemented by a recipe. Preserve it as an inference, while the selected
    # target describes the actual new simulation rather than the original.
    target=CATALOG.get(h.kind)
    unknowns=[*h.assumptions]
    if target:
        unknowns.append('사진·영상의 기능 후보: '+h.output_behavior)
    return FunctionIntent(kind=h.kind,status='USER_DEFINED',summary=h.title,
        input_behavior=target['input'] if target else h.input_behavior,output_behavior=target['output'] if target else h.output_behavior,evidence=h.evidence,
        unknowns=unknowns,acceptance_criteria=target['criteria'] if target else [h.output_behavior],display_text=h.display_text)
