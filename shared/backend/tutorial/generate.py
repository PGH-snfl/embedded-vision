from ..circuit.schema import Graph, Status


def tutorial(graph: Graph):
    names = {t.id: f"{c.id} · {t.name.value or '미확인 단자'}" for c in graph.components for t in c.terminals}
    steps=[]
    for link in graph.links:
        confirmed = link.connection.status == Status.CONFIRMED
        color='검정' if any('GND' in (t or '') for t in [link.from_terminal,link.to_terminal]) else '빨강' if any(('3V3' in (t or '') or '.5V' in (t or '')) for t in [link.from_terminal,link.to_terminal]) else '노랑'
        why='GND는 모든 신호 전압의 공통 기준입니다.' if color=='검정' else '전원선은 부품에 필요한 전압을 공급합니다.' if color=='빨강' else '신호선은 입력 상태 또는 출력 명령을 전달합니다.'
        if any('R1' in (t or '') for t in [link.from_terminal,link.to_terminal]) and (graph.profile in {'esp32_led_button','arduino_light_led'} or (graph.profile or '').startswith('arduino_led_')):why='R1은 LED에 흐르는 전류를 제한합니다. 저항 없이 LED를 GPIO에 직접 연결하지 않습니다.'
        if graph.profile in {'esp32_led_button','arduino_led_button'} and any('R2' in (t or '') for t in [link.from_terminal,link.to_terminal]):why='R2는 버튼이 열려 있을 때 입력을 HIGH로 유지하는 pull-up 저항입니다. 입력 전압이 떠서 오동작하는 것을 막습니다.'
        if graph.profile=='arduino_voltage_divider':why='10kΩ 저항 두 개가 보드의 5V를 약 절반으로 나눕니다. A0는 두 저항 사이의 전압을 읽고 GND를 기준으로 삼습니다. 10kΩ은 사진에서 읽은 값이 아닌 새 설계값입니다.'
        physical={t.id:t.pin_mapping.value for c in graph.components for t in c.terminals}
        steps.append({"link_id":link.id,"from":names.get(link.from_terminal,"미확인"),"to":names.get(link.to_terminal,"끝점 미확인"),
                      "status":link.connection.status,"action":"새 설계대로 연결하세요. 원본 사진의 배선을 따를 필요는 없습니다." if graph.mode=="reference_design" else "사진에서 연결을 대조하세요." if confirmed else "추가 사진 또는 도통 측정으로 끝점을 확인하세요.",
                      "reason":link.connection.reason,"can_assemble":False,"wire_color":color,"why":why,
                      "physical_from":physical.get(link.from_terminal),"physical_to":physical.get(link.to_terminal),
                      "caution":"신호 발생기를 분리하고 연결하세요. 커패시터 값과 접지 연결을 확인하세요." if graph.profile=='rc_filter' else "USB/외부 전원을 분리하고 연결하세요. LCD 핀 라벨·5V 호환·백라이트 극성과 와이퍼를 확인하세요." if graph.profile=="arduino_lcd" else "USB/외부 전원을 분리하고 연결하세요. LED 극성과 버튼의 내부 공통 접점을 확인하세요."})
    if (graph.profile or '').startswith('arduino_led_'):
        for step in steps:step['caution']='USB 전원을 분리하고 UNO R3 D5/GND, 220Ω 저항, LED A(양극)/K(음극)를 확인하세요. 사진 속 모델·값을 확인한 결과가 아닌 새 설계입니다.'
    if graph.profile=='arduino_led_button':
        for step in steps:step['caution']='USB 전원을 분리하고 LED 극성과 버튼 접점군, 10kΩ 저항을 확인하세요.'
    if graph.profile=='arduino_light_led':
        for step in steps:step['caution']='USB 전원을 분리하고 LED 극성, 조도 모듈의 5V·GND·AO 라벨과 실제 출력 방향을 확인하세요.'
    if graph.profile=='arduino_voltage_divider':
        for step in steps:step['caution']='USB 전원을 분리하고 UNO R3·10kΩ 저항 2개·5V/GND/A0 라벨을 확인하세요. 외부 전원은 연결하지 않습니다.'
    return {"mode":"review_only", "title":"배선 검토 순서 · 조립 허가가 아닙니다", "steps":steps,
            "notice":"설계 예제의 핀 매핑을 실제 부품과 대조하세요. 실물 조립·작동은 아직 검증하지 않았습니다." if graph.mode=='reference_design' else "전원·핀 배치·LED 극성·버튼 내부 연결을 아직 검증하지 않았습니다. 이 초안으로 전원을 연결하지 마세요."}
