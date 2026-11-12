"""Draw a labeled synthetic fixture, not a photograph or model inference."""
import hashlib
import io
from PIL import Image, ImageDraw
from ..circuit.schema import Asset, Claim, Component, Evidence, Graph, Link, Point, Status, Terminal


def create_demo(project_id: str):
    image = Image.new("RGB", (1200, 800), "#e9ece8")
    draw = ImageDraw.Draw(image)
    def box(bounds, fill, outline="#90a096", width=2):
        xy = [int(bounds[0]*1200), int(bounds[1]*800), int(bounds[2]*1200), int(bounds[3]*800)]
        draw.rounded_rectangle(xy, radius=10, fill=fill, outline=outline, width=width)
    def label(x, y, text, fill="#263a36"):
        draw.text((int(x*1200), int(y*800)), text, fill=fill, font_size=17)
    box((.4,.12,.94,.85), "#fbfbf5")
    for x in range(505, 1100, 25):
        for y in range(130, 650, 25):
            draw.ellipse((x,y,x+5,y+5), fill="#aeb5b0")
    draw.rectangle((495, 380, 1115, 405), fill="#e0e5de")
    label(.43,.80,"BREADBOARD - rail continuity not verified")
    box((.07,.12,.29,.8), "#234b42", "#172b27", 4)
    box((.10,.18,.26,.42), "#a6b1b1")
    label(.11,.25,"ESP32", "#172b27")
    label(.085,.75,"DEVKIT CANDIDATE", "#ffffff")
    for y, name in [(.24,"3V3"),(.46,"GPIO23"),(.58,"GPIO18"),(.70,"GND")]:
        draw.rectangle((326,int(y*800)-5,353,int(y*800)+5), fill="#d1b465")
        label(.16,y-.01,name,"white")
    bounds = {"U1":(.07,.12,.29,.8), "R1":(.57,.29,.68,.37), "D1":(.77,.21,.83,.32),
              "SW1":(.54,.57,.63,.69), "R2":(.76,.55,.84,.63), "BB1":(.4,.12,.94,.85)}
    definitions = [
        ("U1","board","ESP32 DevKit (candidate)",None,["3V3","GND","GPIO23","GPIO18"]),
        ("R1","resistor","LED resistor","220 Ω",["1","2"]),
        ("D1","led","Red LED",None,["A","K"]),
        ("SW1","button","Push button",None,["1","2"]),
        ("R2","resistor","Input resistor","10 kΩ",["1","2"]),
        ("BB1","breadboard","Breadboard",None,[])]
    evidence, components = [], []
    for cid, kind, name, value, pins in definitions:
        eid = f"fixture_{cid}"
        a,b,c,d = bounds[cid]
        bbox = [Point(x=a,y=b),Point(x=c,y=d)]
        evidence.append(Evidence(id=eid, asset_id="image", method="synthetic_fixture", points=bbox,
                                 text="직접 작성한 합성 예제의 정의입니다. 실제 부품이나 사진에서 검증한 정보가 아닙니다."))
        def known(v):
            return Claim(value=v,status=Status.CONFIRMED,evidence_ids=[eid],reason="합성 예제의 정답 정의에 한정")
        components.append(Component(id=cid,kind=kind,label=known(name),value=known(value) if value else Claim(),bbox=bbox,
            terminals=[Terminal(id=f"{cid}.{p}",name=known(p)) for p in pins]))
    paths = [
        ("W1","U1.GPIO23","R1.1",[(.29,.46),(.44,.46),(.44,.33),(.57,.33)],"#e55341",Status.CONFIRMED),
        ("W2","R1.2","D1.A",[(.68,.33),(.78,.33),(.78,.29)],"#e6a62a",Status.CONFIRMED),
        ("W3","D1.K","U1.GND",[(.82,.29),(.90,.29),(.90,.74),(.33,.74),(.33,.70),(.29,.70)],"#354443",Status.CONFIRMED),
        ("W4","U1.3V3","R2.1",[(.29,.24),(.36,.24),(.36,.52),(.77,.52),(.77,.59)],"#d44338",Status.CONFIRMED),
        ("W5","R2.2","SW1.1",[(.83,.59),(.87,.59),(.87,.70),(.59,.70),(.59,.65)],"#347cbb",Status.CONFIRMED),
        ("W6","SW1.2",None,[(.55,.65),(.48,.65),(.48,.77),(.40,.77)],"#4b5753",Status.UNKNOWN),
        ("W7","U1.GPIO18","SW1.1",[(.29,.58),(.41,.58),(.41,.55),(.59,.55),(.59,.60)],"#439777",Status.INFERRED)]
    links=[]
    for wid,start,end,points,color,status in paths:
        pts=[Point(x=x,y=y) for x,y in points]
        draw.line([(int(p.x*1200),int(p.y*800)) for p in pts],fill=color,width=7,joint="curve")
        eid=f"fixture_{wid}"
        evidence.append(Evidence(id=eid,asset_id="image",method="synthetic_fixture",points=pts,
                                 text="합성 배선 예제. W6은 끝점 가림, W7은 미확인 핀 라벨을 의도적으로 포함합니다."))
        claim=Claim(evidence_ids=[eid],reason="끝점이 가려져 있습니다.") if status==Status.UNKNOWN else Claim(
            value="connected",status=status,evidence_ids=[eid],reason="합성 예제의 정답" if status==Status.CONFIRMED else "핀 라벨을 추가 확인해야 합니다.")
        links.append(Link(id=wid,from_terminal=start,to_terminal=end,path=pts,connection=claim))
    box((.57,.29,.68,.37),"#cfb68b");label(.575,.31,"220R")
    box((.76,.55,.84,.63),"#cfb68b");label(.77,.57,"10k")
    draw.ellipse((924,168,996,235),fill="#e34e4b",outline="#853b37",width=3)
    label(.77,.18,"LED")
    box((.54,.57,.63,.69),"#59625f");draw.ellipse((676,474,730,524),fill="#232e2a")
    box((.34,.75,.425,.81),"#bec7c2");label(.345,.765,"HIDDEN")
    label(.04,.035,"SYNTHETIC FIXTURE / NOT A PHOTO / NOT AI RECOGNITION")
    stream=io.BytesIO();image.save(stream,format="PNG");data=stream.getvalue()
    asset=Asset(id="image",sha256=hashlib.sha256(data).hexdigest(),width=1200,height=800,filename="synthetic-example.png",synthetic=True)
    graph=Graph(project_id=project_id,title="ESP32 · LED · 버튼 | 합성 검토 예제",revision=1,mode="synthetic_demo",assets=[asset],evidence=evidence,components=components,links=links)
    return graph,data,image
