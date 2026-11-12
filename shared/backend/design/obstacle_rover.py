"""New UNO/L293D ultrasonic two-wheel prototype, independent of the photo wiring.

The editor runs an Arduino sketch if its backend supports the selected parts;
kinematic motion is a separate, explicitly labeled approximation.
"""
from copy import deepcopy
from datetime import datetime, timezone
import json

UNO='https://docs.arduino.cc/resources/datasheets/A000066-datasheet.pdf'
DRIVER='https://www.ti.com/lit/ds/symlink/l293.pdf'
SENSOR='https://learn.adafruit.com/distance-measurement-ultrasound-hcsr04/connect-the-sensor'

CODE=r'''// New obstacle-avoidance prototype; verify wiring and motor ratings first.
// UNO + HC-SR04 + L293D: motor supply must be separate with common ground.
const byte TRIG=9, ECHO=10, EN_L=5, L1=2, L2=3, EN_R=6, R1=4, R2=7;
const unsigned long BACK_MS=400, TURN_MS=600;
const long NEAR_CM=20; // adjustable prototype assumption, not measured from photo
int mode=0; // 0=forward, 1=backing, 2=turning
unsigned long phaseStart=0;
void motor(int left, int right) {
  digitalWrite(L1,left>0); digitalWrite(L2,left<0); analogWrite(EN_L,left ? 150 : 0);
  digitalWrite(R1,right>0); digitalWrite(R2,right<0); analogWrite(EN_R,right ? 150 : 0);
}
long distanceCm() {
  digitalWrite(TRIG,LOW); delayMicroseconds(2);
  digitalWrite(TRIG,HIGH); delayMicroseconds(10); digitalWrite(TRIG,LOW);
  unsigned long duration=pulseIn(ECHO,HIGH,30000UL);
  return duration ? (long)(duration * 0.0343 / 2.0) : -1;
}
void setup() {
  pinMode(TRIG,OUTPUT); pinMode(ECHO,INPUT);
  pinMode(EN_L,OUTPUT); pinMode(L1,OUTPUT); pinMode(L2,OUTPUT);
  pinMode(EN_R,OUTPUT); pinMode(R1,OUTPUT); pinMode(R2,OUTPUT);
  motor(0,0); Serial.begin(115200);
}
void loop() {
  long cm=distanceCm(); unsigned long now=millis();
  Serial.print("distance_cm="); Serial.println(cm);
  // No echo: stop. Unreliable/missing measurements are not interpreted as clear.
  if (cm < 0) { motor(0,0); mode=0; delay(60); return; }
  if (mode==0 && cm<=NEAR_CM) { mode=1; phaseStart=now; }
  if (mode==1 && now-phaseStart>=BACK_MS) { mode=2; phaseStart=now; }
  if (mode==2 && now-phaseStart>=TURN_MS) { mode=0; }
  if (mode==1) motor(-1,-1);
  else if (mode==2) motor(-1,1);
  else motor(1,1);
  delay(60);
}
'''
PARTS=[
 ('U1','Arduino Uno R3','board',UNO),('S1','HC-SR04 초음파 센서','sensor',SENSOR),
 ('U2','L293D 16핀 모터 드라이버','motor_driver',DRIVER),
 ('M1','왼쪽 DC 기어 모터','motor',None),('M2','오른쪽 DC 기어 모터','motor',None),
 ('BAT','모터용 별도 전원','power',None),('C1','100 nF 세라믹 커패시터','capacitor',DRIVER),
 ('C2','100 nF 세라믹 커패시터','capacitor',DRIVER)]
# Driver pin names match the editor's DIP-16 metadata and TI datasheet.
CONNECTIONS=[
 ('U1.5V','S1.VCC'),('U1.GND','S1.GND'),('U1.9','S1.TRIG'),('U1.10','S1.ECHO'),
 ('U1.5','U2.EN1'),('U1.2','U2.IN1'),('U1.3','U2.IN2'),
 ('U1.6','U2.EN2'),('U1.4','U2.IN3'),('U1.7','U2.IN4'),
 ('U1.5V','U2.VCC1'),('BAT.+','U2.VCC2'),('BAT.-','U1.GND'),
 ('U1.GND','U2.GND.1'),('U1.GND','U2.GND.2'),('U1.GND','U2.GND.3'),('U1.GND','U2.GND.4'),
 ('U2.OUT1','M1.+'),('U2.OUT2','M1.-'),('U2.OUT3','M2.+'),('U2.OUT4','M2.-'),
 ('U2.VCC1','C1.1'),('U1.GND','C1.2'),('U2.VCC2','C2.1'),('U1.GND','C2.2')]

def obstacle_rover_design():
    parts=[{'id':i,'name':name,'kind':kind,'model':name,'quantity':1,'source':url,
            'note':'새 설계의 부품이며 사진 속 정확한 모델은 확인 필요' if url is None else '제조사 자료와 부품 정격을 확인하세요.'}
           for i,name,kind,url in PARTS]
    connections=[{'id':f'C{i}','from':a,'to':b,'color':'black' if '.GND' in a or '.GND' in b or a=='BAT.-' else 'red' if a in ('U1.5V','BAT.+') else 'green',
                  'description':f'{a} → {b}'} for i,(a,b) in enumerate(CONNECTIONS,1)]
    return {'id':'uno_obstacle_rover','title':'Arduino · 초음파 장애물 회피 로봇 새 설계',
        'behavior':'전방 거리 20 cm 초과면 전진, 20 cm 이하면 0.4초 후진하고 0.6초 좌회전합니다. 센서 무응답 시 정지합니다.',
        'simulation_kind':'obstacle_rover','parts':parts,'connections':connections,
        'steps':[{'id':'power','title':'전원과 정격 확인','description':'전원을 모두 분리하고 모터 공급 전압과 정지 전류, L293D 전류와 발열을 확인하세요. 모터 전원과 Arduino 전원은 분리하고 접지만 공통 연결합니다.','highlight':['U1','U2','BAT']},
                 {'id':'sensor','title':'거리 센서 연결','description':'HC-SR04 VCC·GND를 보드 5V·GND에, TRIG·ECHO를 D9·D10에 연결합니다.','highlight':['S1','U1']},
                 {'id':'driver','title':'드라이버와 모터 연결','description':'L293D의 방향·활성 핀을 연결표대로 꽂고 네 GND 핀을 공통 접지에 연결합니다. 양 모터는 OUT1–2와 OUT3–4에 각각 연결합니다.','highlight':['U2','M1','M2']},
                 {'id':'test','title':'바퀴를 띄우고 시험','description':'먼저 코드와 배선, 모터 회전 방향을 확인합니다. 전원을 즉시 끊을 수 있는 상태에서 낮은 속도로 시험하세요.','highlight':['M1','M2','BAT']}],
        'code':{'filename':'sketch.ino','language':'arduino','source':CODE,'dependencies':'Arduino Uno 표준 라이브러리','install':'Arduino IDE에서 보드 Arduino Uno 선택','run':'코드를 업로드한 뒤 별도 모터 전원을 켭니다.'},
        'structure':{'kind':'two_wheel_rover','description':'두 구동 바퀴와 전방 거리 센서의 가상 배치','dimensions_status':'UNKNOWN: 실제 치수는 미확인'},
        'sources':[{'title':'Arduino Uno R3','url':UNO},{'title':'L293D 핀 및 정격','url':DRIVER},{'title':'HC-SR04 연결','url':SENSOR}],
        'warnings':['사진의 원본 회로가 아닌 기능 가설에 따른 새 설계입니다.',
          '센서의 사각지대·미끄럼·낙하와 실제 안전성은 검증하지 않았습니다.',
          '모터 정지 전류와 발열, 전원 및 실제 배선을 확인하고 독립 전원 스위치를 사용하세요.',
          '3D 운동은 가상 거리 입력을 사용하는 동작 모델이며 코드·전기·물리의 실행 결과가 아닙니다.'],
        'hardware_tested':False}

def export_obstacle_project(provenance=None):
    design=obstacle_rover_design()
    # Motor and power blocks are explicit visual terminals; they do not model
    # electrical dynamics. The Uno and ultrasonic sensor are native parts.
    manifests={'M1':[('+',0,20),('-',0,40)],'M2':[('+',0,20),('-',0,40)],'BAT':[('+',160,20),('-',160,40)]}
    positions={'M1':(840,80),'M2':(840,210),'BAT':(650,380)}
    components=[{'id':'S1','metadataId':'hc-sr04','x':350,'y':15,'properties':{'distance':'50'}},
                {'id':'U2','metadataId':'motor-driver-l293d','x':570,'y':150,'properties':{}},
                {'id':'C1','metadataId':'capacitor','x':510,'y':305,'properties':{'value':'100nF'}},
                {'id':'C2','metadataId':'capacitor','x':610,'y':305,'properties':{'value':'100nF'}}]
    groups={'group-U1':[{'name':'sketch.ino','content':CODE}]}
    for cid,pins in manifests.items():
        manifest={'name':cid+' visual only','pins':[{'name':n,'x':x,'y':y} for n,x,y in pins]}
        manifest_json=json.dumps(manifest,ensure_ascii=False,separators=(',',':'))
        props={'chipName':cid+' visual only','chipJson':manifest_json,'sourceC':'// Visual only.\n','wasmBase64':''}
        x,y=positions[cid];components.append({'id':cid,'metadataId':'custom-chip','x':x,'y':y,'properties':props})
        groups['group-chip-'+cid]=[{'name':'chip.c','content':props['sourceC']},{'name':'chip.json','content':manifest_json}]
    def ep(text):
        cid,pin=text.split('.',1);return {'componentId':cid,'pinName':pin,'x':0,'y':0}
    wires=[{'id':c['id'],'start':ep(c['from']),'end':ep(c['to']),'color':{'black':'#263238','red':'#c52f2f','green':'#159957'}[c['color']],'waypoints':[],'autoRouted':True} for c in design['connections']]
    return {'format':'velxio-project','version':1,'exportedAt':datetime.now(timezone.utc).isoformat(),
        'name':design['title'],'boards':[{'id':'U1','name':'Arduino Uno','boardKind':'arduino-uno','x':30,'y':130,
        'activeFileGroupId':'group-U1','languageMode':'arduino','serialBaudRate':115200}],
        'fileGroups':groups,'components':components,'wires':wires,'activeBoardId':'U1',
        'embeddedVision':{'basis':'proposed_design_only','physical_verified':False,'original_wiring_reused':False,
        'recipe':'uno_obstacle_rover','robot_code':design['code'],'simulation_notice':'모터와 전원은 시각 전용이며, 3D 운동은 별도 가상 모델입니다.',**(provenance or {})}}
