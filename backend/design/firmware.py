"""Deterministic firmware generated from the same validated new-design connection contract."""
import json
from ..circuit.profiles import readiness

def lcd_firmware(graph,message='Hello circuit!',show_elapsed=True):
    if readiness(graph):raise ValueError('부품·핀·연결이 LCD 코드 사양과 일치해야 합니다.')
    import re
    if not re.fullmatch(r'[A-Za-z0-9 .,!?_-]{1,16}',message):raise ValueError('LCD 메시지는 16자 이내 영문·숫자·기본 문장부호로 입력하세요.')
    source='''// New design, NOT recovered firmware. Arduino UNO + parallel 16x2 HD44780 LCD.
// RS=D12, E=D11, LCD D4..D7 = Arduino D5,D4,D3,D2. RW=GND.
// Contrast: 10k pot wiper -> VO. Backlight: 5V -> 220 ohm -> A, K -> GND.
#include <Arduino.h>
constexpr uint8_t LCD_RS = 12, LCD_EN = 11;
constexpr uint8_t LCD_D4 = 5, LCD_D5 = 4, LCD_D6 = 3, LCD_D7 = 2;
// Self-contained HD44780 4-bit writer: no external library installation needed.
class LCD4Bit : public Print {
  uint8_t rs, en, data[4];
  void nibble(uint8_t n) {
    for (uint8_t i = 0; i < 4; ++i) digitalWrite(data[i], (n >> i) & 1);
    digitalWrite(en, LOW); delayMicroseconds(1);
    digitalWrite(en, HIGH); delayMicroseconds(1);
    digitalWrite(en, LOW); delayMicroseconds(100);
  }
  void send(uint8_t b, bool isData) {
    digitalWrite(rs, isData ? HIGH : LOW);
    nibble(b >> 4); nibble(b & 15);
  }
public:
  LCD4Bit(uint8_t r, uint8_t e, uint8_t a, uint8_t b, uint8_t c, uint8_t d)
    : rs(r), en(e), data{a,b,c,d} {}
  void begin(uint8_t, uint8_t) {
    pinMode(rs, OUTPUT); pinMode(en, OUTPUT);
    for (uint8_t i=0; i<4; ++i) pinMode(data[i], OUTPUT);
    digitalWrite(rs, LOW); digitalWrite(en, LOW); delay(50);
    nibble(3); delayMicroseconds(4500); nibble(3); delayMicroseconds(4500);
    nibble(3); delayMicroseconds(150); nibble(2);
    send(0x28, false); send(0x0c, false); send(0x01, false); delay(2);
    send(0x06, false);
  }
  void setCursor(uint8_t col, uint8_t row) { send(0x80 | (row ? 0x40 : 0) | col, false); }
  using Print::write;
  size_t write(uint8_t b) override { send(b, true); return 1; }
};
LCD4Bit lcd(LCD_RS, LCD_EN, LCD_D4, LCD_D5, LCD_D6, LCD_D7);
unsigned long lastSecond = 0;
void setup() {
  lcd.begin(16, 2);
  lcd.print(MESSAGE);
  lcd.setCursor(0, 1);
  lcd.print("Elapsed 0 s");
}
void loop() {
  const unsigned long seconds = millis() / 1000;
  if (seconds == lastSecond) return;
  lastSecond = seconds;
  lcd.setCursor(0, 1);
  lcd.print("                ");
  lcd.setCursor(0, 1);
  lcd.print("Elapsed "); lcd.print(seconds); lcd.print(" s");
}
'''.replace('MESSAGE',json.dumps(message))
    if not show_elapsed:
        source=source[:source.index('unsigned long lastSecond')] + 'void setup() {\n  lcd.begin(16, 2);\n  lcd.print('+json.dumps(message)+');\n}\nvoid loop() {}\n'
    return {'source':source,'filename':'arduino_lcd_new_design.ino' ,'revision':graph.revision,'compiled':False,
     'execution':'새 회로에 맞춘 코드 생성 완료 · 컴파일·업로드·실물 동작 미검증',
     'commands':[{'function':'LCD4Bit(RS, EN, D4, D5, D6, D7)','terminal':'U1.D12 / D11 / D5 / D4 / D3 / D2','net':'LCD parallel interface','meaning':'새 회로의 LCD 신호 연결을 사용합니다.'},
                 {'function':'lcd.print(...)','terminal':'LCD1','net':'LCD parallel interface','meaning':'지정 문구를 표시합니다.' if not show_elapsed else '새 메시지와 경과 시간을 화면에 출력합니다.'}]}


def divider_firmware(graph):
    if readiness(graph):raise ValueError('부품·핀·연결이 분압 회로 코드 사양과 일치해야 합니다.')
    source='''// NEW DESIGN, not recovered firmware. Arduino UNO R3 only.
// UNO 5V -> R1 10k -> A0 -> R2 10k -> UNO GND.
// 10k values are NEW specifications, not values read from the photo.
// No external measured source. Verify board and resistor values before power-on.
#include <Arduino.h>
constexpr uint8_t SENSE_PIN = A0;
constexpr float NOMINAL_REFERENCE_V = 5.0f; // estimate; USB/AVcc varies
unsigned long lastSample = 0;
void setup() {
  analogReference(DEFAULT); // UNO R3: AVcc, nominal 5V
  pinMode(SENSE_PIN, INPUT); // no internal pull-up
  Serial.begin(115200);
  Serial.println("raw,ratio,estimated_voltage_V");
}
void loop() {
  const unsigned long now = millis();
  if (now - lastSample < 200) return;
  lastSample = now;
  const int raw = analogRead(SENSE_PIN); // UNO R3: 10-bit ADC
  const float ratio = raw / 1023.0f;
  Serial.print(raw); Serial.print(',');
  Serial.print(ratio, 4); Serial.print(',');
  Serial.println(ratio * NOMINAL_REFERENCE_V, 3);
}
'''
    return {'source':source,'filename':'arduino_voltage_divider.ino','revision':graph.revision,'compiled':False,
      'execution':'새 설계 코드 · 컴파일·업로드·실물 동작 미검증. 약 512 / 0.5 / 2.5V는 계산상 예상이며 측정값이 아닙니다.',
      'commands':[{'function':'analogRead(A0)','terminal':'U1.A0','net':'TP_DIVIDER','meaning':'두 저항 사이 전압을 0~1023의 숫자로 읽습니다.'},
                  {'function':'Serial.println(...)','terminal':'U1','net':'USB serial','meaning':'USB 시리얼 모니터(115200 baud)에 측정값과 5V 기준 추정 전압을 출력합니다.'}]}
