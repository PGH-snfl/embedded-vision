"""New UNO LED specifications, never assertions about the photographed program."""
from .recipes import LED_RECIPES, recipe_contract


def led_firmware(graph):
    if graph.profile not in LED_RECIPES or recipe_contract(graph, graph.profile):
        raise ValueError('LED 코드의 보드·핀·저항·연결 사양이 일치하지 않습니다.')
    common = '''// NEW DESIGN: UNO R3 D5 -> 220 ohm -> LED A; LED K -> GND.
// Board/LED model, resistor value and timing are new specifications, not photo facts.
#include <Arduino.h>
constexpr uint8_t LED_PIN = 5;
void setup() {
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);
  Serial.begin(115200);
}
'''
    loops = {
        'arduino_led_output': '''void loop() {
  digitalWrite(LED_PIN, HIGH);
  Serial.println("LED ON");
  delay(1000);
}
''',
        'arduino_led_blink': '''constexpr unsigned long HALF_PERIOD_MS = 500;
void loop() {
  digitalWrite(LED_PIN, HIGH);
  Serial.println("LED ON");
  delay(HALF_PERIOD_MS);
  digitalWrite(LED_PIN, LOW);
  Serial.println("LED OFF");
  delay(HALF_PERIOD_MS);
}
''',
        'arduino_led_brightness': '''int brightness = 0;
int step = 5;
void loop() {
  analogWrite(LED_PIN, brightness);
  Serial.print("PWM="); Serial.println(brightness);
  delay(20);
  if (brightness == 255) step = -5;
  if (brightness == 0) step = 5;
  brightness += step;
}
''',
    }
    return {'source': common + loops[graph.profile], 'filename': graph.profile + '.ino',
            'revision': graph.revision, 'compiled': False,
            'execution': '새 설계 코드입니다. Velxio의 ▶ 실행에서 컴파일·가상 MCU 실행을 시작합니다. 실물 동작은 별도 확인합니다.',
            'commands': [{'function': 'analogWrite(LED_PIN, brightness)' if graph.profile.endswith('brightness') else 'digitalWrite(LED_PIN, HIGH/LOW)',
                          'terminal': 'U1.D5', 'net': 'TP_LED_DRIVE',
                          'meaning': 'D5 출력이 220Ω 저항을 거쳐 LED를 구동합니다.'}]}


def button_firmware(graph):
    from .recipes import BUTTON_RECIPE
    if graph.profile != BUTTON_RECIPE or recipe_contract(graph, BUTTON_RECIPE):
        raise ValueError('버튼 코드의 보드·핀·저항·연결 사양이 일치하지 않습니다.')
    source = '''// NEW DESIGN: D5 -> 220 ohm -> LED -> GND.
// D2 -> pushbutton -> GND; D2 -> 10k ohm -> 5V.
#include <Arduino.h>
constexpr uint8_t LED_PIN = 5;
constexpr uint8_t BUTTON_PIN = 2;
void setup() {
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);
  pinMode(BUTTON_PIN, INPUT); // external 10k pull-up
  Serial.begin(115200);
}
void loop() {
  digitalWrite(LED_PIN, digitalRead(BUTTON_PIN) == LOW ? HIGH : LOW);
}
'''
    return {'source':source,'filename':'arduino_led_button.ino','revision':graph.revision,'compiled':False,
            'execution':'새 설계 코드입니다. 시뮬레이터에서 버튼을 누르는 동안 LED가 켜집니다. 실물 검증은 별도입니다.',
            'commands':[{'function':'digitalRead(BUTTON_PIN)','terminal':'U1.D2','net':'TP_BUTTON','meaning':'버튼을 누르면 입력이 LOW가 됩니다.'},
                        {'function':'digitalWrite(LED_PIN, ...)','terminal':'U1.D5','net':'TP_LED_DRIVE','meaning':'D5 출력이 220Ω 저항을 거쳐 LED를 구동합니다.'}]}


def light_firmware(graph):
    from .recipes import LIGHT_RECIPE
    if graph.profile != LIGHT_RECIPE or recipe_contract(graph, LIGHT_RECIPE):
        raise ValueError('조도 센서 코드의 보드·핀·저항·연결 사양이 일치하지 않습니다.')
    source = '''// NEW DESIGN: D5 -> 220 ohm -> LED -> GND.
// Sensor VCC -> 5V, GND -> GND, AO -> A0.
// Threshold and AO polarity are for the simulated sensor; calibrate real hardware.
#include <Arduino.h>
constexpr uint8_t LED_PIN = 5;
constexpr uint8_t LIGHT_PIN = A0;
constexpr int DARK_THRESHOLD = 512;
void setup() {
  pinMode(LED_PIN, OUTPUT);
  Serial.begin(115200);
}
void loop() {
  int reading = analogRead(LIGHT_PIN);
  digitalWrite(LED_PIN, reading > DARK_THRESHOLD ? HIGH : LOW);
  Serial.println(reading);
  delay(100);
}
'''
    return {'source':source,'filename':'arduino_light_led.ino','revision':graph.revision,'compiled':False,
            'execution':'가상 조도 센서의 입력에 반응하는 새 코드입니다. 실물의 AO 방향과 임계값은 별도 보정합니다.',
            'commands':[{'function':'analogRead(LIGHT_PIN)','terminal':'U1.A0','net':'TP_LIGHT','meaning':'조도 센서 AO 전압을 0~1023 값으로 읽습니다.'},
                        {'function':'digitalWrite(LED_PIN, ...)','terminal':'U1.D5','net':'TP_LED_DRIVE','meaning':'어두운 가상 센서 입력에서 LED를 켭니다.'}]}
