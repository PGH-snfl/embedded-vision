"""UNO + SEN0193 + MOSFET + separately powered DC pump reference circuit."""
from datetime import datetime, timezone
from .environment_objects import watering_environment
from .watering_circuit import physical_design, circuit_components, circuit_wires, CONNECTIONS

RECIPE='arduino_watering_control'
SOURCE='''// New reference circuit: SEN0193 -> A0; D5 -> 330 ohm -> IRLZ44N gate.
// Pump uses a SEPARATE 12V supply, flyback diode and common ground.
// ADC 560/280 and thresholds 500/360 are EXAMPLE calibration, not measured soil values.
#include <Arduino.h>
constexpr uint8_t SOIL_PIN=A0, PUMP_COMMAND_PIN=5;
constexpr int DRY_ON=500, WET_OFF=360, SENSOR_MAX=625;
constexpr unsigned long MAX_PUMP_MS=15000UL;
bool pumpCommand=false, fault=false;
unsigned long pumpStarted=0;
void setup() {
  digitalWrite(PUMP_COMMAND_PIN,LOW);
  pinMode(PUMP_COMMAND_PIN,OUTPUT);
  Serial.begin(115200);
}
void loop() {
  long total=0;
  for(byte i=0;i<8;i++)total+=analogRead(SOIL_PIN);
  const int soil=total/8;
  const unsigned long now=millis();
  if(soil>SENSOR_MAX)fault=true;
  if(pumpCommand && now-pumpStarted>=MAX_PUMP_MS)fault=true;
  if(fault)pumpCommand=false;
  else if(soil<=WET_OFF)pumpCommand=false;
  else if(soil>=DRY_ON && !pumpCommand){pumpCommand=true;pumpStarted=now;}
  digitalWrite(PUMP_COMMAND_PIN,pumpCommand?HIGH:LOW);
  Serial.print("soil_adc=");Serial.print(soil);
  Serial.print(",pump_command=");Serial.print(digitalRead(PUMP_COMMAND_PIN));
  Serial.print(",fault=");Serial.println(fault?1:0);
  delay(100);
}
'''
NOTICE=('SEN0193 토양 센서 → Arduino A0 → D5 → IRLZ44N → 별도 12V 펌프 회로입니다. '
        '물 흐름은 LED가 아니라 펌프의 SPICE 전압·전류를 읽습니다. '
        '센서 건조/젖음 560/280과 기준 500/360, 유량 1.5mL/s는 보정 전 예제값입니다. '
        '15초 연속 구동 또는 센서 상한 초과 시 정지하며 Reset 전까지 잠깁니다. '
        '모터의 48Ω/5mH 등가값과 흡수율은 설명용 모형이며 실물 기동·정지 전류, 발열과 배선 검증은 별도입니다.')

def watering_proposal():
    physical=physical_design()
    return {'recipe':RECIPE,'name':'Arduino UNO · MOSFET 자동 급수 제어',
      'behavior':'토양이 건조하면 MOSFET을 켜 별도 12V 전원의 펌프를 구동하고, 충분히 젖으면 끕니다.',
      'simulation_behavior':'실행 중인 UNO 코드 → 게이트 구동 → 펌프 전류 → 화분 급수 → 토양 센서 피드백을 연결합니다.',
      'environment':watering_environment(),'simulation_notice':NOTICE,'simulator_supported':True,
      'assignments':{p['id']:None for p in physical['parts']},'added_parts':[p['id'] for p in physical['parts']],
      'replacements':[],'remaining_parts':[],'parts':physical['parts'],
      'reason':'사진의 기능을 구현하도록 새로 선정한 참조 회로입니다. 원본 배선의 복원이 아닙니다.',
      'connections':[{'from':a,'to':b} for a,b in CONNECTIONS],
      'specifications':{p['id']:{'name':p['name'],'note':p['note'],'source':p.get('source')} for p in physical['parts']},
      'steps':physical['steps'],'sources':physical['sources'],
      'firmware':{'source':SOURCE,'filename':'watering_control.ino','compiled':False},
      'physical_design':physical,'review_required':True,'hardware_verified':False,'original_wiring_reused':False}

def watering_workbench(provenance=None):
    components,seats=circuit_components();wires,assembly=circuit_wires(seats)
    return {'format':'velxio-project','version':1,'exportedAt':datetime.now(timezone.utc).isoformat(),
      'name':'자동 급수 · 센서와 MOSFET 펌프 구동 회로',
      'boards':[{'id':'U1','name':'Arduino UNO · 새 설계','boardKind':'arduino-uno','x':40,'y':80,
        'activeFileGroupId':'group-U1','languageMode':'arduino','serialBaudRate':115200}],
      'fileGroups':{'group-U1':[{'name':'sketch.ino','content':SOURCE}]},
      'components':components,'wires':wires,'activeBoardId':'U1',
      'embeddedVision':{'basis':'proposed_design_only','physical_verified':False,'original_wiring_reused':False,
        'assembly':assembly,'recipe':RECIPE,'simulation_notice':NOTICE,**(provenance or {}),
        'environment_design_version':2,'watering_circuit_version':2,'hardware_design':physical_design()}}
