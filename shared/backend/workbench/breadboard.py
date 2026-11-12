"""Physical seating for the reviewed UNO recipes; hole groups are electrical nodes."""
from collections import defaultdict

LAYOUT_VERSION='full-breadboard-v2'
BB_X,BB_Y=400,115
ROW_Y={row:y*4/3 for row,y in zip('abcdefghij',[36,43.2,50.4,57.6,64.8,86.4,93.6,100.8,108,115.2])}


def hole(name):
    col,side,row=name.partition('.')
    number=int(col[:-1]);bank=col[-1]
    if not 1<=number<=63 or row not in ROW_Y or bank!=('t' if row in 'abcde' else 'b'):
        raise ValueError('830구 빵판 구멍 이름이 올바르지 않습니다.')
    return {'x':BB_X+6+14.56+(number-1)*9.6,'y':BB_Y+6+ROW_Y[row]}


def assemble(components,led,button=False,light=False):
    """Use real 5-hole strips, with distinct holes for every lead/jumper."""
    seats={'R1':{'1':'23t.b','2':'29t.b'}}
    jumpers=[('U1','5' if led else '5V','23t.a','#d3a31c')]
    if led:
        seats['D1']={'A':'29t.d','C':'28t.d'}
        jumpers.append(('U1','GND','28t.a','#263238'))
    else:
        seats['R2']={'1':'29t.d','2':'35t.d'}
        jumpers.extend([('U1','A0','29t.c','#159957'),('U1','GND','35t.a','#263238')])
    if button:
        seats['R2']={'1':'40t.b','2':'46t.b'}
        # Rotated 90 degrees, opposite contact groups lie in separate columns;
        # each common pair straddles the middle gap. Pin pitch differs <1px.
        seats['SW1']={'1.l':'42t.e','2.l':'40t.e','1.r':'42b.f','2.r':'40b.f'}
        jumpers.extend([('U1','2','40t.a','#e17b20'),('U1','5V','46t.a','#c52f2f'),
                        ('U1','GND','42t.a','#263238')])
    if light:
        jumpers.extend([('U1','A0','40t.a','#159957'),('S1','AO','40t.b','#159957'),
                        ('U1','5V','46t.a','#c52f2f'),('S1','VCC','46t.b','#c52f2f'),
                        ('U1','GND','52t.a','#263238'),('S1','GND','52t.b','#263238')])
    for c in components:
        if c['id']=='S1':
            # Breakout mounted next to the breadboard; jumper pins are not hidden seats.
            c.update(x=810,y=335)
            continue
        if c['id']=='SW1':
            pos=hole(seats['SW1']['1.l'])
            # 6mm button SVG 7.4129977 x 6 mm, rotated about its centre.
            width,height=7.4129977*96/25.4,6*96/25.4
            c.update(x=round(pos['x']-6-(width/2+height/2-2.2),3),
                     y=round(pos['y']-6-(height/2-width/2),3))
            c['properties']['rotation']=90
            continue
        first=next(iter(seats[c['id']].items()));pin,pos=first[0],hole(first[1])
        # Match pinned Wokwi geometry: resistor pin1=(0,5.65); LED A=(25,42).
        dx,dy=(25,42) if c['metadataId']=='led' else (0,5.65)
        c.update(x=round(pos['x']-6-dx,3),y=round(pos['y']-6-dy,3))
    components.insert(0,{'id':'BB1','metadataId':'breadboard','x':BB_X,'y':BB_Y,'properties':{}})
    def endpoint(ref,pin):
        return {'componentId':ref,'pinName':pin,**(hole(pin) if ref=='BB1' else {'x':0,'y':0})}
    wires=[];steps=[]
    for i,(ref,pin,h,color) in enumerate(jumpers):
        wires.append({'id':f'J{i+1}','start':endpoint(ref,pin),'end':endpoint('BB1',h),'color':color,'waypoints':[],'autoRouted':True})
        steps.append({'from':ref+'.'+pin,'to':'BB1.'+h,'kind':'jumper'})
    for ref,pins in seats.items():
        for pin,h in pins.items():
            wires.append({'id':f'SEAT_{ref}_{pin}','start':endpoint(ref,pin),'end':endpoint('BB1',h),'color':'#87988a','waypoints':[],'bb':True})
            steps.append({'from':ref+'.'+pin,'to':'BB1.'+h,'kind':'insert'})
    return wires,{'layout_version':'full-breadboard-light-v1' if light else 'full-breadboard-button-v3' if button else LAYOUT_VERSION,'breadboard':'830-point full-size / 63 columns / 4 power rails',
                  'steps':steps,'note':'같은 열의 a~e 다섯 구멍은 연결됩니다. f~j는 별도 그룹이며 가운데 홈을 건너 연결되지 않습니다. 빨강·파랑 전원 레일은 신호 열과 연결되지 않으며 이 예제에서는 사용하지 않습니다.'}


def assemble_lcd(components):
    """Parallel LCD with a breadboard power distribution and backlight resistor."""
    by_id={c['id']:c for c in components}
    # Keep the LCD's lower pin header well outside the breadboard. If it sits
    # on a power rail, mount-time seating silently joins every nearby LCD pin.
    by_id['LCD1'].update(x=805,y=-125)
    by_id['RV1'].update(x=760,y=335)
    pos=hole('23t.b')
    by_id['R1'].update(x=round(pos['x']-6,3),y=round(pos['y']-6-5.65,3))
    components.insert(0,{'id':'BB1','metadataId':'breadboard','x':BB_X,'y':BB_Y,'properties':{}})
    # Every occupied breadboard hole is unique. Pins on each strip are a net.
    jumpers=[
        ('U1','5V','BB1','23t.a','#c52f2f'),
        ('LCD1','VDD','BB1','23t.c','#c52f2f'),
        ('RV1','VCC','BB1','23t.d','#c52f2f'),
        ('U1','GND','BB1','40t.a','#263238'),
        ('LCD1','VSS','BB1','40t.b','#263238'),
        ('LCD1','RW','BB1','40t.c','#263238'),
        ('LCD1','K','BB1','40t.d','#263238'),
        ('RV1','GND','BB1','40t.e','#263238'),
        ('LCD1','A','BB1','29t.a','#d3a31c'),
        ('RV1','SIG','LCD1','V0','#d3a31c'),
        ('U1','12','LCD1','RS','#159957'),('U1','11','LCD1','E','#159957'),
        ('U1','5','LCD1','D4','#3478c0'),('U1','4','LCD1','D5','#3478c0'),
        ('U1','3','LCD1','D6','#3478c0'),('U1','2','LCD1','D7','#3478c0'),
    ]
    def ep(ref,pin):return {'componentId':ref,'pinName':pin,**(hole(pin) if ref=='BB1' else {'x':0,'y':0})}
    wires=[];steps=[]
    for i,(a,ap,b,bp,color) in enumerate(jumpers):
        wires.append({'id':f'J{i+1}','start':ep(a,ap),'end':ep(b,bp),'color':color,'waypoints':[],'autoRouted':True})
        steps.append({'from':a+'.'+ap,'to':b+'.'+bp,'kind':'jumper'})
    for pin,h in [('1','23t.b'),('2','29t.b')]:
        wires.append({'id':f'SEAT_R1_{pin}','start':ep('R1',pin),'end':ep('BB1',h),'color':'#87988a','waypoints':[],'bb':True})
        steps.append({'from':'R1.'+pin,'to':'BB1.'+h,'kind':'insert'})
    return wires,{'layout_version':'full-breadboard-lcd-v1','breadboard':'830-point full-size / 63 columns / 4 power rails',
        'steps':steps,'note':'실물 연결 전 LCD와 가변저항의 실제 핀·정격을 확인하세요. 같은 열의 a~e 다섯 구멍이 연결됩니다.'}


def projected_nets(wires):
    """Project physical breadboard connections onto the original device pins."""
    parent={}
    def find(v):
        parent.setdefault(v,v)
        if parent[v]!=v:parent[v]=find(parent[v])
        return parent[v]
    def union(a,b):parent[find(a)]=find(b)
    for w in wires:
        ends=[]
        for e in (w['start'],w['end']):
            node=e['componentId']+'.'+e['pinName']
            # 1.l/1.r and 2.l/2.r are permanent common contact pairs.
            if e['componentId']=='SW1':node=node.replace('.1.r','.1.l').replace('.2.r','.2.l')
            ends.append(node)
            if e['componentId']=='BB1':
                hole(e['pinName'])
                union(node,'BBGROUP.'+e['pinName'].split('.')[0])
        union(*ends)
    groups=defaultdict(set)
    for key in list(parent):
        if not key.startswith(('BB1.','BBGROUP.')):groups[find(key)].add(key)
    return {frozenset(g) for g in groups.values() if len(g)>1}
