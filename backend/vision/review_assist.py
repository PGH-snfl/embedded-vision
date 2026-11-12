"""Read-only proposals from observed text and positioned terminals, never pinouts."""
import math
import re

# A text grammar, not a component database. Missing labels are never filled in.
COMMON = {'GND','VCC','VDD','VSS','VIN','VOUT','3V3','5V','3.3V','SDA','SCL',
          'MOSI','MISO','SCK','SCLK','CS','TX','RX','RST','RESET','EN','AREF','IOREF'}
DISPLAY = {'V0','VO','RS','RW','E','A','K'}
NUMBERED = {f'{prefix}{n}' for prefix in ('D','A','GPIO','IO','TX','RX') for n in range(40)}


def split_labels(text, kind):
    """Tokenize complete chunks only; offsets always refer to original OCR text."""
    words=sorted(COMMON | NUMBERED | (DISPLAY if kind=='display' else set()),key=lambda s:(-len(s),s))
    tokens=[];unparsed=[]
    for chunk in re.finditer(r'[^\s,;|/]+',text):
        raw=chunk.group();upper=raw.upper();offset=0;found=[]
        while offset<len(upper):
            word=next((w for w in words if upper.startswith(w,offset)),None)
            if word is None:break
            found.append({'label':word,'span':[chunk.start()+offset,chunk.start()+offset+len(word)],
                          'source_text':raw[offset:offset+len(word)],'status':'INFERRED'})
            offset+=len(word)
        # Do not extract A/D1 etc from unrecognized words or silently correct O/0.
        if offset==len(raw) and len(upper)==len(raw):tokens.extend(found)
        else:unparsed.append({'text':raw,'span':[chunk.start(),chunk.end()]})
    return {'tokens':tokens,'unparsed':unparsed}


def nearby_text(component, text):
    a,b=component.bbox;p,q=text.bbox
    overlap=max(0,min(b.x,q.x)-max(a.x,p.x))*max(0,min(b.y,q.y)-max(a.y,p.y))
    if overlap/((q.x-p.x)*(q.y-p.y))>=.6:return 'inside'
    # Coarse object boxes sometimes exclude the printed edge labels. This only
    # broadens review choices; it does not assert ownership or a contact location.
    cx,cy=(p.x+q.x)/2,(p.y+q.y)/2
    if a.x-.025<=cx<=b.x+.025 and a.y-.025<=cy<=b.y+.025:return 'near_edge'
    return None


def wire_proposals(graph, asset_id):
    asset=next(a for a in graph.assets if a.id==asset_id)
    evidence={e.id:e for e in graph.evidence};limit=min(asset.width,asset.height)*.04
    pins=[(c,t) for c in graph.components if c.asset_id==asset_id for t in c.terminals if t.image_position]
    proposals=[]
    for wire in graph.wire_candidates:
        if wire.geometry!='segment' or evidence[wire.evidence_id].asset_id!=asset_id:continue
        matches=[]
        for p in wire.endpoints:
            near=[]
            for c,t in pins:
                d=math.hypot((p.x-t.image_position.x)*asset.width,(p.y-t.image_position.y)*asset.height)
                if d<=limit:near.append({'terminal_id':t.id,'label':f'{c.label.value or c.id} · {t.name.value or "?"}',
                                        'distance_px':round(d,2)})
            matches.append(sorted(near,key=lambda m:(m['distance_px'],m['terminal_id'])))
        ids=[m[0]['terminal_id'] if len(m)==1 else None for m in matches]
        state='READY'
        if any(not m for m in matches):state='MISSING_PIN'
        elif any(len(m)!=1 for m in matches) or ids[0]==ids[1]:state='AMBIGUOUS'
        existing=None
        if state=='READY':
            existing=next((l.id for l in graph.links if {l.from_terminal,l.to_terminal}==set(ids)),None)
            if existing:state='EXISTING'
        proposals.append({'candidate_id':wire.id,'state':state,'matches':matches,
                          'from_terminal':ids[0] if state=='READY' else None,
                          'to_terminal':ids[1] if state=='READY' else None,'existing_link_id':existing,
                          'reason':{'READY':'각 끝점 가까이에 지정 핀이 하나씩 있습니다. 실제 접촉·가림 여부를 확인하세요.',
                                    'MISSING_PIN':'끝점 가까이에 지정한 핀이 없습니다. 실제 핀 위치를 먼저 확인하세요.',
                                    'AMBIGUOUS':'여러 핀 또는 같은 핀이 겹쳐 대응됩니다. 핀 위치를 확대해서 확인하세요.',
                                    'EXISTING':'이미 저장한 연결입니다. 기존 연결의 근거와 상태를 검토하세요.'}[state]})
    return proposals


def review_assist(graph):
    if graph.mode not in {'photo','video'}:return {}
    result={}
    for asset in graph.assets:
        rows=[]
        for text in graph.text_observations:
            if text.asset_id!=asset.id:continue
            owners=[]
            for c in graph.components:
                if c.asset_id!=asset.id:continue
                relation=nearby_text(c,text)
                if relation:owners.append({'component_id':c.id,'label':c.label.value or c.id,
                                           'relation':relation,**split_labels(text.text,c.kind)})
            rows.append({'text_id':text.id,'owners':owners,'ownership_ambiguous':len(owners)!=1})
        result[asset.id]={'texts':rows,'wires':wire_proposals(graph,asset.id),
                          'notice':'문자 분리·거리 기반 검토 제안입니다. 핀 번호·전압·도통을 검증하지 않습니다.'}
    return result
