"""Reviewed new-design recipes. Image wires never feed these connections."""
import hashlib,io
from PIL import Image,ImageDraw
from ..circuit.schema import Graph,Component,Terminal,Link,Claim,Status,Point,Asset,Evidence
from ..circuit.profiles import reference
from ..datasheet.catalog import CATALOG,ARDUINO_LCD_SOURCE

RECIPES={
 'arduino_voltage_divider':{'name':'Arduino UNO · 저항 분압 읽기','behavior':'저항 두 개로 보드의 5V를 나눠 A0에서 읽고 USB 시리얼 모니터에 측정값을 출력합니다. 외부 전원 측정용은 아닙니다.',
  'slots':{'U1':('arduino_uno_analog_interface',None),'R1':('resistor_axial','10k'),'R2':('resistor_axial','10k')},'required_observed':['U1']},
 'esp32_led_button':{'name':'ESP32 · 버튼으로 LED 켜기','behavior':'버튼을 누르면 LED가 켜지고 놓으면 꺼집니다.',
  'slots':{'U1':('esp32_devkitc_v4',None),'D1':('wp7113id',None),'SW1':('b3f1000',None),'R1':('resistor_axial','220'),'R2':('resistor_axial','10k')},'required_observed':['U1']},
 'arduino_lcd':{'name':'Arduino UNO · LCD 고정 문구 표시','behavior':'LCD 첫째 줄에 지정한 문구를 표시합니다. 가변저항은 대비를 조절합니다.',
  'slots':{'U1':('arduino_uno_r3_interface',None),'LCD1':('hd44780_parallel_interface',None),'RV1':('potentiometer_interface','10k'),'R1':('resistor_axial','220')},'required_observed':['U1','LCD1']}
}
LIGHT_RECIPE='arduino_light_led'
RECIPES[LIGHT_RECIPE]={'name':'Arduino UNO · 어두우면 LED 켜기','behavior':'조도 센서의 아날로그 값을 읽어 어두울 때 LED를 켭니다.',
 'slots':{'U1':('arduino_uno_light_interface',None),'R1':('resistor_axial','220'),'D1':('wp7113id',None),'S1':('sim_photoresistor_module',None)},
 'required_observed':[]}
BUTTON_RECIPE='arduino_led_button'
RECIPES[BUTTON_RECIPE]={'name':'Arduino UNO · 버튼으로 LED 켜기','behavior':'버튼을 누르는 동안 LED를 켜고 놓으면 끕니다.',
 'slots':{'U1':('arduino_uno_r3_interface',None),'R1':('resistor_axial','220'),'D1':('wp7113id',None),'SW1':('b3f1000',None),'R2':('resistor_axial','10k')},
 'required_observed':['D1','SW1']}
LED_RECIPES={'arduino_led_output','arduino_led_blink','arduino_led_brightness'}
for key,title,behavior in [
 ('arduino_led_output','LED 지속 점등','외부 LED를 계속 켭니다.'),
 ('arduino_led_blink','LED 깜빡이기','LED를 0.5초 켜고 0.5초 끕니다.'),
 ('arduino_led_brightness','LED 밝기 자동 조절','20ms마다 PWM 값을 5씩 바꾸며 밝기를 올렸다 내립니다.')]:
    RECIPES[key]={'name':'Arduino UNO · '+title,'behavior':behavior,
      'slots':{'U1':('arduino_uno_r3_interface',None),'R1':('resistor_axial','220'),'D1':('wp7113id',None)},
      'required_observed':['D1']}
LIGHT_CONNECTIONS=[('U1.D5','R1.1'),('R1.2','D1.A'),('D1.K','U1.GND'),('U1.5V','S1.VCC'),('U1.GND','S1.GND'),('U1.A0','S1.AO')]
BUTTON_CONNECTIONS=[('U1.D5','R1.1'),('R1.2','D1.A'),('D1.K','U1.GND'),('U1.D2','SW1.1'),('U1.D2','R2.1'),('R2.2','U1.5V'),('SW1.2','U1.GND')]
LED_CONNECTIONS=[('U1.D5','R1.1'),('R1.2','D1.A'),('D1.K','U1.GND')]
LCD_CONNECTIONS=[('U1.5V','LCD1.VDD'),('U1.GND','LCD1.VSS'),('U1.GND','LCD1.RW'),
 ('U1.D12','LCD1.RS'),('U1.D11','LCD1.E'),('U1.D5','LCD1.D4'),('U1.D4','LCD1.D5'),('U1.D3','LCD1.D6'),('U1.D2','LCD1.D7'),
 ('U1.5V','RV1.END1'),('U1.GND','RV1.END2'),('RV1.WIPER','LCD1.VO'),('U1.5V','R1.1'),('R1.2','LCD1.A'),('LCD1.K','U1.GND')]

def recipe_info():
    return {key:{'name':r['name'],'behavior':r['behavior'],'required_observed':r['required_observed'],
         'slots':{ref:{'catalog_id':cid,'value':value,**CATALOG[cid]} for ref,(cid,value) in r['slots'].items()}} for key,r in RECIPES.items()}

def new_graph(pid,recipe):
    if recipe=='esp32_led_button':return reference(pid,recipe)
    r=RECIPES[recipe]
    image=Image.new('RGB',(1200,800),'#f2f6ed');draw=ImageDraw.Draw(image)
    draw.text((40,30),'NEW DESIGN / NOT ORIGINAL WIRING',fill='#305744',font_size=26)
    divider=recipe=='arduino_voltage_divider'
    led=recipe in LED_RECIPES or recipe in {BUTTON_RECIPE,LIGHT_RECIPE}
    draw.text((40,80),'Arduino UNO + LED / D5' if led else 'Arduino UNO + voltage divider' if divider else 'Arduino UNO + parallel LCD / 4-bit mode',fill='#305744',font_size=24)
    lines=['UNO 5V -> R1 10k -> A0 -> R2 10k -> GND','New resistor values, NOT read from photo.','Read A0 -> Serial Monitor 115200 baud.','USB disconnected while wiring. VERIFY ALL PARTS.'] if divider else ['UNO D12 -> LCD RS','UNO D11 -> LCD E','UNO D5/D4/D3/D2 -> LCD D4/D5/D6/D7',
      '10k potentiometer wiper -> LCD VO','220 ohm resistor -> LCD backlight A','USB disconnected while wiring. VERIFY ALL PARTS.']
    if led:lines=['UNO D5 -> R1 220 ohm -> LED A','LED K -> UNO GND','New design defaults, NOT measured photo values.','UNO R3 and red LED are specified simulation parts.','USB disconnected while wiring. VERIFY ALL PARTS.']
    if recipe==BUTTON_RECIPE:lines=['UNO D5 -> R1 220 ohm -> LED A; LED K -> GND','UNO D2 -> button -> GND','UNO 5V -> R2 10k -> D2','New design: check button contact pairs before wiring.']
    if recipe==LIGHT_RECIPE:lines=['UNO D5 -> R1 220 ohm -> LED A; LED K -> GND','UNO 5V -> sensor VCC; GND -> sensor GND','sensor AO -> UNO A0; calibrate threshold on real module.','Virtual sensor interface, not a manufacturer datasheet.']
    for i,line in enumerate(lines):
        draw.text((50,150+70*i),line,fill='#305744',font_size=22)
    buf=io.BytesIO();image.save(buf,format='PNG');data=buf.getvalue()
    g=Graph(project_id=pid,title='새 설계 · '+r['name'],revision=1,mode='reference_design',profile=recipe,
      assets=[Asset(id='image',sha256=hashlib.sha256(data).hexdigest(),width=1200,height=800,filename='new-design.png',synthetic=True)],
      evidence=[Evidence(id='design_spec',asset_id='image',method='design_spec',source_url=CATALOG[r['slots']['U1'][0]]['source'],
       text='새 회로의 설계 사양입니다. 원본 배선·저항값을 관측하거나 복원한 결과가 아닙니다. 인터페이스 심벌의 번호는 표시용입니다.')],parameters={'supply_voltage':5})
    def known(value,eid='design_spec'):return Claim(value=value,status=Status.CONFIRMED,evidence_ids=[eid],reason='새 설계의 명시적 사양·인터페이스 정의 (실물 검증과 별개)')
    for i,(ref,(cid,value)) in enumerate(r['slots'].items()):
        c=CATALOG[cid];eid='catalog_'+ref
        g.evidence.append(Evidence(id=eid,asset_id='image',method='design_spec' if cid=='sim_photoresistor_module' else 'datasheet',source_url=c['source'],text=c['note']))
        g.components.append(Component(id=ref,kind=c['kind'],catalog_id=cid,label=known(c['name']),value=known(value) if value else Claim(),
            bbox=[Point(x=.08+(i%2)*.5,y=.12+(i//2)*.26),Point(x=.4+(i%2)*.5,y=.34+(i//2)*.26)],
            terminals=[Terminal(id=ref+'.'+p,name=known(p),pin_mapping=known(number,eid)) for p,number in c['pins'].items()]))
    connections=LIGHT_CONNECTIONS if recipe==LIGHT_RECIPE else BUTTON_CONNECTIONS if recipe==BUTTON_RECIPE else LED_CONNECTIONS if led else DIVIDER_CONNECTIONS if divider else LCD_CONNECTIONS
    g.links=[Link(id=f'W{i+1}',from_terminal=a,to_terminal=b,connection=known('connected')) for i,(a,b) in enumerate(connections)]
    return Graph.model_validate(g.model_dump()),data

DIVIDER_CONNECTIONS=[('U1.5V','R1.1'),('R1.2','U1.A0'),('U1.A0','R2.1'),('R2.2','U1.GND')]

def lcd_contract(graph):
    return recipe_contract(graph,'arduino_lcd')

def recipe_contract(graph,recipe):
    """Firmware requires the exact new-design connection sets and component choices."""
    from ..circuit.connectivity import derive_nets
    expected,_=new_graph('0'*32,recipe)
    if {frozenset(n['terminals']) for n in derive_nets(graph)}!={frozenset(n['terminals']) for n in derive_nets(expected)}:
        return ['코드와 새 회로의 연결이 일치하지 않습니다.']
    byid={c.id:c for c in graph.components}
    if set(byid)!=set(RECIPES[recipe]['slots']):return ['구성 부품이 변경되었습니다.']
    for ref,(cid,value) in RECIPES[recipe]['slots'].items():
        c=byid[ref];entry=CATALOG[cid]
        if c.catalog_id!=cid or c.kind!=entry['kind'] or (value and (c.value.value!=value or c.value.status!=Status.CONFIRMED)):
            return ['부품·값이 검증된 새 설계 사양과 다릅니다.']
        expected_pins={ref+'.'+name:(name,mapping) for name,mapping in entry['pins'].items()}
        if {t.id for t in c.terminals}!=set(expected_pins):return ['LCD 설계의 단자 목록이 변경되었습니다.']
        for t in c.terminals:
            if (t.name.value,t.pin_mapping.value)!=expected_pins[t.id] or t.name.status!=Status.CONFIRMED or t.pin_mapping.status!=Status.CONFIRMED:
                return ['LCD 설계의 실제 핀 라벨·매핑이 변경되었습니다.']
    return []
