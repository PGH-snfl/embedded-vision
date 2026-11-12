"""New UNO distance indicator for the Velxio editor, not recovered photo wiring.

The Velxio HC-SR04 model provides a distance slider and timed ECHO pulses.
The new circuit uses the existing 4-bit LCD, plus a separate indicator LED.
"""
from copy import deepcopy
from datetime import datetime, timezone

from .firmware import lcd_firmware
from .recipes import new_graph
from ..workbench.breadboard import assemble_lcd, hole, projected_nets


DISTANCE_CONNECTIONS = [
    ('U1.5V', 'LCD1.VDD'), ('U1.GND', 'LCD1.VSS'), ('U1.GND', 'LCD1.RW'),
    ('U1.12', 'LCD1.RS'), ('U1.11', 'LCD1.E'), ('U1.5', 'LCD1.D4'),
    ('U1.4', 'LCD1.D5'), ('U1.3', 'LCD1.D6'), ('U1.2', 'LCD1.D7'),
    ('U1.5V', 'RV1.VCC'), ('U1.GND', 'RV1.GND'), ('RV1.SIG', 'LCD1.V0'),
    ('U1.5V', 'R1.1'), ('R1.2', 'LCD1.A'), ('LCD1.K', 'U1.GND'),
    ('U1.5V', 'S1.VCC'), ('U1.GND', 'S1.GND'), ('U1.7', 'S1.TRIG'),
    ('U1.6', 'S1.ECHO'), ('U1.8', 'R2.1'), ('R2.2', 'D1.A'), ('D1.C', 'U1.GND'),
]


def distance_firmware():
    lcd_graph, _ = new_graph('0' * 32, 'arduino_lcd')
    lcd = lcd_firmware(lcd_graph, 'Distance', show_elapsed=False)['source']
    lcd = lcd[:lcd.index('void setup()')]
    return lcd + '''// HC-SR04 TRIG=D7, ECHO=D6; LED D8 -> 220 ohm -> A, C -> GND.
// New demonstration thresholds, not measured from the input photo.
constexpr uint8_t TRIG = 7, ECHO = 6, LED = 8;
constexpr unsigned int NEAR_CM = 20;
void setup() {
  pinMode(TRIG, OUTPUT); pinMode(ECHO, INPUT); pinMode(LED, OUTPUT);
  digitalWrite(TRIG, LOW);
  Serial.begin(115200);
  lcd.begin(16, 2);
  lcd.print("Distance");
}
void loop() {
  digitalWrite(TRIG, LOW); delayMicroseconds(2);
  digitalWrite(TRIG, HIGH); delayMicroseconds(10);
  digitalWrite(TRIG, LOW);
  unsigned long duration = pulseIn(ECHO, HIGH, 30000UL);
  lcd.setCursor(0, 1);
  if (!duration) {
    digitalWrite(LED, LOW);
    lcd.print("No echo         ");
    Serial.println("No echo");
  } else {
    unsigned long cm = (duration * 343UL + 10000UL) / 20000UL;
    digitalWrite(LED, cm < NEAR_CM ? HIGH : LOW);
    lcd.print("                ");
    lcd.setCursor(0, 1); lcd.print(cm); lcd.print(" cm");
    Serial.print("Distance: "); Serial.print(cm); Serial.println(" cm");
  }
  delay(100);
}
'''


def _endpoint(ref, pin):
    return {'componentId': ref, 'pinName': pin, **(hole(pin) if ref == 'BB1' else {'x': 0, 'y': 0})}


def _append_wire(wires, steps, a, ap, b, bp, color, seat=False):
    wire = {'id': f'DIST_{len(wires)+1}', 'start': _endpoint(a, ap), 'end': _endpoint(b, bp),
            'color': color, 'waypoints': [], 'autoRouted': True}
    if seat:
        wire['bb'] = True
    wires.append(wire)
    steps.append({'from': f'{a}.{ap}', 'to': f'{b}.{bp}', 'kind': 'insert' if seat else 'jumper'})


def _expected_nets():
    return projected_nets([{'start': _endpoint(*a.split('.', 1)), 'end': _endpoint(*b.split('.', 1))}
                           for a, b in DISTANCE_CONNECTIONS])


def distance_design():
    components = [
        {'id': 'LCD1', 'metadataId': 'lcd1602', 'properties': {'pins': 'full', 'background': 'blue'}},
        {'id': 'RV1', 'metadataId': 'potentiometer', 'properties': {'value': 512}},
        {'id': 'R1', 'metadataId': 'resistor', 'properties': {'value': '220'}},
        {'id': 'S1', 'metadataId': 'hc-sr04', 'x': 820, 'y': 400, 'properties': {'distance': 34}},
        {'id': 'R2', 'metadataId': 'resistor', 'properties': {'value': '220'}},
        {'id': 'D1', 'metadataId': 'led', 'properties': {'color': 'red'}},
    ]
    wires, assembly = assemble_lcd(components)
    by_id = {c['id']: c for c in components}
    # Seat the extra resistor and LED in distinct breadboard strips.
    pos = hole('48t.b'); by_id['R2'].update(x=round(pos['x']-6, 3), y=round(pos['y']-6-5.65, 3))
    pos = hole('54t.d'); by_id['D1'].update(x=round(pos['x']-6-25, 3), y=round(pos['y']-6-42, 3))
    steps = assembly['steps']
    for a, ap, b, bp, color in [
        ('U1', '5V', 'S1', 'VCC', '#c52f2f'), ('U1', 'GND', 'S1', 'GND', '#263238'),
        ('U1', '7', 'S1', 'TRIG', '#159957'), ('U1', '6', 'S1', 'ECHO', '#3478c0'),
        ('U1', '8', 'BB1', '48t.a', '#e17b20'), ('U1', 'GND', 'BB1', '53t.a', '#263238'),
    ]:
        _append_wire(wires, steps, a, ap, b, bp, color)
    for ref, pin, h in [('R2', '1', '48t.b'), ('R2', '2', '54t.b'),
                        ('D1', 'A', '54t.d'), ('D1', 'C', '53t.d')]:
        _append_wire(wires, steps, ref, pin, 'BB1', h, '#87988a', seat=True)
    if projected_nets(wires) != _expected_nets():
        raise ValueError('거리 표시 회로의 빵판 배선과 논리 연결이 일치하지 않습니다.')
    assembly['layout_version'] = 'full-breadboard-distance-v1'
    assembly['note'] += ' HC-SR04의 실제 핀 배열과 전원 정격도 사용 전 확인하세요.'
    source = distance_firmware()
    code = {'filename': 'distance_indicator.ino', 'language': 'arduino', 'source': source}
    assumptions = [
        '사진의 배선과 원래 코드를 복원한 것이 아니라 기능에 맞춰 새로 구성했습니다.',
        '20 cm 미만에서 LED를 켜는 기준은 새 설계의 예시이며 사진에서 확인된 값이 아닙니다.',
        '5V HC-SR04와 UNO R3, 16×2 병렬 LCD를 사용합니다. 실물 부품의 모델과 정격은 별도 확인해야 합니다.',
    ]
    project = {'format': 'velxio-project', 'version': 1,
        'exportedAt': datetime.now(timezone.utc).isoformat(), 'name': 'Arduino · 거리 표시와 근접 LED',
        'boards': [{'id': 'U1', 'name': 'Arduino UNO · 새 설계', 'boardKind': 'arduino-uno', 'x': 40, 'y': 80,
                    'activeFileGroupId': 'group-U1', 'languageMode': 'arduino', 'serialBaudRate': 115200}],
        'fileGroups': {'group-U1': [{'name': 'sketch.ino', 'content': source}]},
        'components': components, 'wires': wires, 'activeBoardId': 'U1',
        'embeddedVision': {'basis': 'proposed_design_only', 'physical_verified': False,
                           'original_wiring_reused': False, 'assembly': assembly,
                           'recipe': 'arduino_distance_indicator'}}
    return {'id': 'arduino_distance_indicator', 'title': 'Arduino 거리 표시와 근접 알림',
        'summary': '초음파 거리 입력을 LCD에 표시하고 20 cm 미만이면 LED를 켭니다.',
        'components': [{'id': 'U1', 'name': 'Arduino UNO R3'}, {'id': 'S1', 'name': 'HC-SR04 초음파 거리 센서'},
                       {'id': 'LCD1', 'name': '16×2 병렬 LCD'}, {'id': 'RV1', 'name': '10 kΩ 가변저항'},
                       {'id': 'D1', 'name': '적색 LED'}, {'id': 'R1', 'name': '220 Ω LCD 저항'},
                       {'id': 'R2', 'name': '220 Ω LED 저항'}, {'id': 'BB1', 'name': '830구 빵판'}],
        'connections': [{'from': a, 'to': b} for a, b in DISTANCE_CONNECTIONS], 'code': code,
        'assumptions': assumptions, 'simulator': {'kind': 'velxio',
            'behavior': 'HC-SR04의 거리 조절값에 따라 LCD 거리와 LED 상태를 변경합니다.',
            'notice': '가상 보드와 센서 모델의 실행이며 실물 정확도 검증은 아닙니다.'},
        'assembly': deepcopy(assembly), 'workbench': project}
