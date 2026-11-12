from .circuit.profiles import readiness, named_nets


def firmware(graph):
    from .design.recipes import LED_RECIPES, BUTTON_RECIPE, LIGHT_RECIPE
    if graph.profile==LIGHT_RECIPE:
        from .design.led import light_firmware
        return light_firmware(graph)
    if graph.profile==BUTTON_RECIPE:
        from .design.led import button_firmware
        return button_firmware(graph)
    if graph.profile in LED_RECIPES:
        from .design.led import led_firmware
        return led_firmware(graph)
    if graph.profile=='arduino_voltage_divider':
        from .design.firmware import divider_firmware
        return divider_firmware(graph)
    if graph.profile=="arduino_lcd":
        from .design.firmware import lcd_firmware
        return lcd_firmware(graph)
    if graph.profile!="esp32_led_button" or readiness(graph):
        raise ValueError("확인된 ESP32 LED/버튼 프로필이 필요합니다.")
    nets=named_nets(graph)
    required=[{"U1.GPIO23","R1.1"},{"R1.2","D1.A"},{"D1.K","U1.GND","SW1.2"},{"U1.3V3","R2.1"},{"R2.2","SW1.1","U1.GPIO18"}]
    if {frozenset(n["terminals"]) for n in nets} != {frozenset(n) for n in required}:
        raise ValueError("현재 연결이 코드 템플릿의 LED/외부 pull-up 버튼 회로와 다릅니다.")
    source='''// ESP32-DevKitC V4 / external 10k pull-up button
// GPIO23 -> R1 -> LED A, LED K -> GND
// GPIO18 -> button -> GND, GPIO18 -> R2 -> 3V3
#include <Arduino.h>
constexpr uint8_t LED_PIN = 23;
constexpr uint8_t BUTTON_PIN = 18;
constexpr unsigned long DEBOUNCE_MS = 30;
bool lastReading = HIGH;
bool stableReading = HIGH;
unsigned long changedAt = 0;
void setup() {
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);
  pinMode(BUTTON_PIN, INPUT); // external pull-up resistor
  Serial.begin(115200);
}
void loop() {
  const bool reading = digitalRead(BUTTON_PIN);
  if (reading != lastReading) changedAt = millis();
  if (millis() - changedAt >= DEBOUNCE_MS && reading != stableReading) {
    stableReading = reading;
    const bool pressed = stableReading == LOW;
    digitalWrite(LED_PIN, pressed ? HIGH : LOW);
    Serial.println(pressed ? "BUTTON DOWN / LED ON" : "BUTTON UP / LED OFF");
  }
  lastReading = reading;
}
'''
    return {"source":source,"filename":"esp32_led_button.ino","revision":graph.revision,
            "compiled":False,"execution":"동작 설명 모델. 실제 MCU 에뮬레이션/플래싱 아님",
            "commands":[{"function":"digitalRead(BUTTON_PIN)","terminal":"U1.GPIO18","net":"TP_BUTTON","meaning":"버튼 입력 전압을 HIGH/LOW로 읽습니다."},
                        {"function":"digitalWrite(LED_PIN, HIGH)","terminal":"U1.GPIO23","net":"TP_LED_DRIVE","meaning":"GPIO23을 HIGH로 구동해 R1을 거쳐 LED를 켭니다."}]}
