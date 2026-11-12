"""Authored 12 V low-side pump circuit. Product facts are separate from model assumptions."""
from .environment_objects import environment_components, watering_environment
from ..workbench.breadboard import BB_X, BB_Y, hole, projected_nets

SOURCES={
 'sensor':'https://wiki.dfrobot.com/sen0193/',
 'pump':'https://www.adafruit.com/product/1150',
 'mosfet':'https://www.infineon.com/assets/row/public/documents/24/49/infineon-irlz44n-datasheet-en.pdf',
 'diode':'https://www.vishay.com/docs/88526/1n5820.pdf',
 'uno':'https://docs.arduino.cc/resources/datasheets/A000066-datasheet.pdf',
}
CONNECTIONS=[('U1.5V','S1.VCC'),('U1.GND','S1.GND'),('U1.A0','S1.SIG'),
 ('U1.5','RG1.1'),('RG1.2','Q1.G'),('Q1.G','RPD1.1'),('RPD1.2','Q1.S'),
 ('Q1.S','PS1.-'),('PS1.-','U1.GND'),('PS1.+','M1.+'),('M1.-','Q1.D'),
 ('M1.-','D2.A'),('D2.C','M1.+'),('PS1.+','C1.+'),('PS1.-','C1.−'),
 ('M1.+','C2.1'),('M1.-','C2.2'),('U1.5','R1.1'),('R1.2','D1.A'),('D1.C','U1.GND')]

def physical_design():
    parts=[
      {'id':'U1','name':'Arduino UNO R3','quantity':1,'source':SOURCES['uno'],'note':'USB로 5V 전원 공급. 펌프 전원과 +를 연결하지 않습니다.'},
      {'id':'S1','name':'DFRobot SEN0193 정전용량 토양 수분 센서','quantity':1,'source':SOURCES['sensor'],'note':'공급 3.3–5.5V, 출력 0–3V. VCC→5V, GND→GND, SIG→A0. 실제 건조·젖음 ADC 값을 보정하세요.'},
      {'id':'M1','name':'Adafruit #1150 12V 연동 펌프','quantity':1,'source':SOURCES['pump'],'note':'제조사 동작 전류 200–300mA, 최대 유량 100mL/min. 기동·정지 전류는 미확인. 물통→흡입구, 배출구→화분.'},
      {'id':'Q1','name':'Infineon IRLZ44N · TO-220AB','quantity':1,'source':SOURCES['mosfet'],'note':'앞면 마킹을 보고 다리를 아래로 향하면 1=G, 2=D, 3=S. 금속 탭도 D. 5V 게이트 구동을 사용합니다.'},
      {'id':'D2','name':'Vishay 1N5822 · 3A / 40V 쇼트키 다이오드','quantity':1,'source':SOURCES['diode'],'note':'색 띠가 있는 C(캐소드)를 펌프 +에, A(애노드)를 펌프 −에 연결합니다. 모터 정지 시 역기전력을 우회합니다.'},
      {'id':'RG1','name':'330Ω · 1/4W 게이트 직렬 저항','quantity':1,'note':'설계 선정값. D5와 G 사이의 순간 전류를 제한합니다.'},
      {'id':'RPD1','name':'100kΩ · 1/4W 게이트 풀다운 저항','quantity':1,'note':'설계 선정값. 아두이노가 초기화 중일 때 G를 S 전압으로 내려 펌프를 끕니다.'},
      {'id':'PS1','name':'정전압 12V DC 전원 · 1A 이상 후보','quantity':1,'note':'제품 모델 UNKNOWN. 실제 기동·정지 전류에 맞는 전류 제한·보호 조건을 확인한 뒤 선정합니다.'},
      {'id':'C1','name':'470µF · 25V 전해 커패시터','quantity':1,'note':'설계 선정값. +는 12V, −는 전원 −에 연결합니다.'},
      {'id':'C2','name':'100nF · 25V 이상 세라믹 커패시터','quantity':1,'note':'설계 선정값. 모터 양 단자 가까이에 연결합니다.'},
      {'id':'D1','name':'녹색 표시용 LED','quantity':1,'note':'보조 상태 표시이며 펌프를 대신하지 않습니다.'},
      {'id':'R1','name':'1kΩ · 1/4W LED 직렬 저항','quantity':1,'note':'설계 선정값. 표시 LED 전류를 제한합니다.'},
    ]
    steps=[
      ('sensor','토양 센서 연결','제조사 연결도 기준 빨강 VCC→UNO 5V, 검정 GND→GND, 파랑 SIG→A0에 연결하세요. 제품의 단자 표기를 함께 확인하고 센서 상단 회로와 커넥터는 물에 담그지 않습니다.',['S1','U1']),
      ('gate','게이트 구동 연결','D5 → 330Ω → Q1의 1번 G. 100kΩ을 G와 3번 S 사이에 연결하세요.',['RG1','RPD1','Q1','U1']),
      ('pump','펌프 전류 경로 연결','12V + → 펌프 +, 펌프 − → Q1의 2번 D, Q1의 3번 S → 12V −. 펌프 전류는 단자대·납땜 보드로 연결하세요.',['M1','Q1','PS1']),
      ('protection','보호 부품과 공통 접지','1N5822의 띠 있는 쪽을 펌프 +에, 반대쪽을 펌프 −에 연결하세요. 커패시터를 연결하고 UNO GND와 12V −를 공통으로 묶으세요. 12V +는 UNO 5V에 연결하지 않습니다.',['D2','C1','C2','U1','PS1']),
      ('calibrate','센서 보정 후 시험','펌프 전원을 끈 채 건조한 흙과 젖은 흙의 ADC를 읽고 코드의 기준값을 수정하세요. 첫 시험은 전류 제한 전원으로 짧게 실행합니다.',['S1','M1','PS1']),
    ]
    return {'status':'REFERENCE_DESIGN','hardware_tested':False,'parts':parts,
      'connections':[{'from':a,'to':b} for a,b in CONNECTIONS],
      'steps':[{'id':i,'title':t,'description':d,'highlight':h} for i,t,d,h in steps],
      'sources':[{'title':k,'url':v} for k,v in SOURCES.items()],
      'unknowns':['사용자 펌프의 실제 모델·기동·정지 전류','12V 전원 제품·보호 조건','실제 토양과 센서의 건조·젖음 보정값','실물 배선·발열·유량 측정'],
      'note':'제조사 핀·정격을 확인한 참조 설계입니다. 실제 장치의 보정과 전원·발열 검증은 아직 수행하지 않았습니다.'}

def circuit_components():
    parts=[{'id':'BB1','metadataId':'breadboard','x':BB_X,'y':BB_Y,'properties':{}},
      {'id':'S1','metadataId':'soil-moisture-sen0193','x':90,'y':350,'properties':{'value':watering_environment()['initial_sensor_value']}},
      {'id':'Q1','metadataId':'mosfet-irlz44n','x':620,'y':-85,'properties':{}},
      {'id':'RG1','metadataId':'resistor','x':520,'y':250,'properties':{'value':'330'}},
      {'id':'RPD1','metadataId':'resistor','x':640,'y':300,'properties':{'value':'100k'}},
      {'id':'PS1','metadataId':'dc-power-supply','x':160,'y':-120,'properties':{'voltage':12,'enabled':True}},
      {'id':'D2','metadataId':'diode-1n5822','x':500,'y':-10,'properties':{}},
      {'id':'C1','metadataId':'capacitor-electrolytic','x':670,'y':-50,'properties':{'value':'470uF','voltageRating':25}},
      {'id':'C2','metadataId':'capacitor','x':540,'y':45,'properties':{'value':'100nF'}},
      {'id':'R1','metadataId':'resistor','x':460,'y':220,'properties':{'value':'1k'}},
      {'id':'D1','metadataId':'led','x':500,'y':230,'properties':{'color':'green'}},
      *environment_components()]
    # Seat only the low-current gate and status circuit. Power wiring stays external.
    seats={'RG1':{'1':'30t.b','2':'36t.b'},
           'RPD1':{'1':'36t.c','2':'42t.c'},'R1':{'1':'23t.b','2':'29t.b'},'D1':{'A':'29t.d','C':'28t.d'}}
    offsets={'Q1':(9.6,78),'RG1':(0,5.65),'RPD1':(0,5.65),'R1':(0,5.65),'D1':(25,42)}
    for p in parts:
        if p['id'] in seats:
            at=hole(next(iter(seats[p['id']].values())));dx,dy=offsets[p['id']]
            p.update(x=round(at['x']-6-dx,4),y=round(at['y']-6-dy,4))
    return parts,seats

def circuit_wires(seats):
    # Unique free holes on the same strips; a physical hole is never double occupied.
    contacts={'U1.5→RG1.1':'30t.a','RG1.2→Q1.G':'36t.a','Q1.G→RPD1.1':None,
      'RPD1.2→Q1.S':'42t.a',
      'U1.5→R1.1':'23t.a','R1.2→D1.A':None,'D1.C→U1.GND':'28t.a'}
    def ep(text):
        ref,pin=text.split('.',1);return {'componentId':ref,'pinName':pin,**(hole(pin) if ref=='BB1' else {'x':0,'y':0})}
    wires=[];steps=[]
    def add(a,b,insert=False):
        n=len(wires)+1;wires.append({'id':f'W{n}','start':ep(a),'end':ep(b),'color':'#87988a' if insert else '#263238' if any(x in a+b for x in ('GND','PS1.-','Q1.S')) else '#c52f2f' if any(x in a+b for x in ('PS1.+','M1.+','5V')) else '#159957','waypoints':[],**({'bb':True} if insert else {'autoRouted':True})})
        steps.append({'from':a,'to':b,'kind':'insert' if insert else 'jumper'})
    for a,b in CONNECTIONS:
        key=a+'→'+b
        if key in contacts:
            contact=contacts[key]
            if contact is None:continue
            if isinstance(contact,tuple):add('BB1.'+contact[0],'BB1.'+contact[1])
            elif a.split('.')[0] in seats:add('BB1.'+contact,b)
            else:add(a,'BB1.'+contact)
        else:add(a,b)
    for ref,pins in seats.items():
        for pin,h in pins.items():add(ref+'.'+pin,'BB1.'+h,True)
    direct=[{'start':ep(a),'end':ep(b)} for a,b in CONNECTIONS]
    assert projected_nets(wires)==projected_nets(direct),'급수 참조 회로와 빵판 연결이 다릅니다.'
    return wires,{'layout_version':'watering-mosfet-external-v2','breadboard':'830-point full-size / 63 columns',
       'steps':steps,'note':'빵판에는 게이트·상태 신호를 배치합니다. 펌프 전류 경로는 외부 단자대·납땜 보드를 사용합니다. 같은 열 a~e만 내부 연결됩니다.'}
