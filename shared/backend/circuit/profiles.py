import hashlib, io, math, re
from PIL import Image, ImageDraw
from .schema import Graph, Claim, Component, Terminal, Link, Evidence, Point, Asset, Status
from ..vision.demo import create_demo
from ..datasheet.catalog import CATALOG


def number(value):
    text=str(value).strip().replace("Ω","").replace("ohm","").replace(" ","").replace("µ","u").replace("μ","u")
    m=re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)([kKMmunp]?)(?:[FfVvHh])?",text)
    if not m: raise ValueError("지원 값 형식: 220, 10k, 100nF, 1uF")
    result=float(m[1])*{"":1,"k":1e3,"K":1e3,"M":1e6,"m":1e-3,"u":1e-6,"n":1e-9,"p":1e-12}[m[2]]
    if not math.isfinite(result) or result<=0: raise ValueError("값은 0보다 커야 합니다.")
    return result


def reference(project_id, profile="esp32_led_button"):
    graph,data,image=create_demo(project_id)
    graph.mode="reference_design";graph.profile=profile
    graph.title="ESP32 · LED/버튼 전체 흐름 예제" if profile=="esp32_led_button" else "RC 필터 · 파형/PCB 예제"
    eid="reference_spec"
    graph.evidence.append(Evidence(id=eid,asset_id="image",method="design_spec",text="사용자가 선택한 새 설계 예제의 명시적 사양입니다. 업로드된 회로를 복원한 결과가 아닙니다."))
    def known(v): return Claim(value=v,status=Status.CONFIRMED,evidence_ids=[eid],reason="새 설계의 명시적 사양")
    if profile=="esp32_led_button":
        catalog={"U1":"esp32_devkitc_v4","R1":"resistor_axial","R2":"resistor_axial","D1":"wp7113id","SW1":"b3f1000"}
        graph.components=[c for c in graph.components if c.id!="BB1"]
        for w in graph.links:
            if w.id=="W6": w.to_terminal="U1.GND"
            w.connection=known("connected")
        graph.parameters={"supply_voltage":3.3,"frequency":2,"amplitude":3.3}
    elif profile=="rc_filter":
        image=Image.new("RGB",(1200,800),"#edf2e9");d=ImageDraw.Draw(image)
        d.text((60,60),"RC FILTER / DESIGN SPECIFICATION / NOT A PHOTO",fill="#315c47",font_size=25)
        d.line((170,300,960,300),fill="#378760",width=6);d.line((740,300,740,600,170,600,170,350),fill="#378760",width=6)
        d.rectangle((420,270,580,330),fill="#d9bd8d",outline="#475f45",width=3);d.text((435,230),"R1  1k",fill="#315c47",font_size=22)
        d.line((690,430,790,430),fill="#315c47",width=6);d.line((690,450,790,450),fill="#315c47",width=6)
        d.text((810,430),"C1  100nF",fill="#315c47",font_size=22);d.text((100,260),"INPUT",fill="#315c47",font_size=22)
        buf=io.BytesIO();image.save(buf,format="PNG");data=buf.getvalue()
        graph.assets=[Asset(id="image",sha256=hashlib.sha256(data).hexdigest(),width=1200,height=800,filename="rc-reference.png",synthetic=True)]
        graph.evidence=[graph.evidence[-1]];graph.components=[];graph.links=[]
        for cid,kind,name,value,pins,bounds in [("V1","source","External input",None,["OUT","GND"],[.07,.28,.23,.65]),("R1","resistor","Resistor","1k",["1","2"],[.35,.32,.49,.43]),("C1","capacitor","Capacitor","100nF",["1","2"],[.56,.50,.67,.60])]:
            graph.components.append(Component(id=cid,kind=kind,label=known(name),value=known(value) if value else Claim(),bbox=[Point(x=bounds[0],y=bounds[1]),Point(x=bounds[2],y=bounds[3])],terminals=[Terminal(id=f"{cid}.{p}",name=known(p)) for p in pins]))
        for n,(a,b) in enumerate([("V1.OUT","R1.1"),("R1.2","C1.1"),("C1.2","V1.GND")]):
            graph.links.append(Link(id=f"W{n+1}",from_terminal=a,to_terminal=b,connection=known("connected")))
        catalog={"V1":"input_connector","R1":"resistor_axial","C1":"capacitor_disc"}
        graph.parameters={"supply_voltage":3.3,"frequency":1000,"amplitude":1}
    else: raise ValueError("지원 예제: esp32_led_button, rc_filter")
    for c in graph.components:
        c.catalog_id=catalog[c.id];entry=CATALOG[c.catalog_id];dsid=f"datasheet_{c.id}"
        graph.evidence.append(Evidence(id=dsid,asset_id="image",method="datasheet",text=entry["note"],source_url=entry["source"]))
        c.label=known(entry["name"])
        for t in c.terminals:
            t.pin_mapping=Claim(value=entry["pins"][t.name.value],status=Status.CONFIRMED,evidence_ids=[dsid,eid],reason="선택한 설계 부품과 카탈로그 핀 매핑")
    return graph,data


def readiness(graph):
    blockers=[]
    if not graph.components or not graph.links: blockers.append("부품과 연결을 지정하세요.")
    for c in graph.components:
        if c.kind=="breadboard": continue
        if c.catalog_id not in CATALOG: blockers.append(f"{c.id}: 부품 카탈로그 지정 필요")
        if c.label.status!=Status.CONFIRMED: blockers.append(f"{c.id}: 부품 식별 확인 필요")
        if c.kind in {"resistor","capacitor"}:
            if c.value.status!=Status.CONFIRMED: blockers.append(f"{c.id}: 값 확인 필요")
            else:
                try: number(c.value.value)
                except ValueError: blockers.append(f"{c.id}: 해석할 수 없는 값")
        for t in c.terminals:
            if t.pin_mapping.status!=Status.CONFIRMED: blockers.append(f"{t.id}: 실제 핀 매핑 필요")
    for w in graph.links:
        if w.connection.status!=Status.CONFIRMED: blockers.append(f"{w.id}: 연결 미확정")
    from .connectivity import derive_nets
    actual={frozenset(n['terminals']) for n in derive_nets(graph)}
    for net in actual:
        if {'U1.3V3','U1.GND'}<=net:blockers.append('3V3와 GND가 단락되어 있습니다.')
        if 'U1.GPIO23' in net and ('U1.GND' in net or 'U1.3V3' in net):blockers.append('GPIO 출력이 전원/GND에 직접 연결되어 있습니다.')
    contracts={
        'esp32_led_button':[{"U1.GPIO23","R1.1"},{"R1.2","D1.A"},{"D1.K","U1.GND","SW1.2"},{"U1.3V3","R2.1"},{"R2.2","SW1.1","U1.GPIO18"}],
        'rc_filter':[{"V1.OUT","R1.1"},{"R1.2","C1.1"},{"C1.2","V1.GND"}]
    }
    if graph.profile in contracts and actual!={frozenset(n) for n in contracts[graph.profile]}:
        blockers.append('현재 연결이 선택한 시뮬레이션/코드 프로필의 회로와 다릅니다.')
    ranges={'esp32_led_button':{'R1':(220,10000),'R2':(1000,100000)},'rc_filter':{'R1':(10,1e7),'C1':(1e-12,.01)}}
    for c in graph.components:
        if c.id in ranges.get(graph.profile,{}) and c.value.value:
            try:
                lo,hi=ranges[graph.profile][c.id]
                if not lo<=number(c.value.value)<=hi:blockers.append(f'{c.id}: 지원 설계 범위 {lo:g}~{hi:g} 밖입니다.')
            except ValueError:pass
    if graph.profile in {'arduino_lcd','arduino_voltage_divider','arduino_led_output','arduino_led_blink','arduino_led_brightness','arduino_led_button','arduino_light_led'}:
        from ..design.recipes import recipe_contract
        blockers.extend(recipe_contract(graph,graph.profile))
    return blockers


def named_nets(graph):
    from .connectivity import derive_nets
    anchors={"U1.5V":"VCC_5V","LCD1.VO":"TP_CONTRAST","U1.GND":"TP_GND","U1.3V3":"VCC_3V3","U1.GPIO23":"TP_LED_DRIVE","U1.GPIO18":"TP_BUTTON","D1.A":"TP_LED_ANODE","V1.GND":"TP_GND","V1.OUT":"TP_INPUT","C1.1":"TP_FILTER_OUT"}
    anchors['U1.A0']='TP_LIGHT' if graph.profile=='arduino_light_led' else 'TP_DIVIDER'
    if graph.profile=='arduino_led_button':anchors['U1.D2']='TP_BUTTON'
    anchors['U1.D5']='TP_LED_DRIVE' if graph.profile and (graph.profile.startswith('arduino_led_') or graph.profile=='arduino_light_led') else 'LCD_D4'
    result=[]
    for net in derive_nets(graph):
        name=next((name for t,name in anchors.items() if t in net["terminals"]),net["id"])
        result.append({**net,"name":name})
    return result
