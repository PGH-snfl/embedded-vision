"""PCB generated strictly from KiCad-exported netlist; simple 2-layer grid router."""
import json,sys,heapq,math
from pathlib import Path
import xml.etree.ElementTree as ET
import pcbnew as pcb

def main(spec):
    board=pcb.BOARD();board.SetCopperLayerCount(2)
    nets={};tree=ET.parse(spec['netlist'])
    for n in tree.findall('./nets/net'):
        name=n.attrib['name'];net=pcb.NETINFO_ITEM(board,name);board.Add(net);nets[name]=net
    assigns={(n.attrib['ref'],n.attrib['pin']):net.attrib['name'] for net in tree.findall('./nets/net') for n in net.findall('node')}
    locations={'U1':(35,40),'R1':(50,35),'D1':(65,35),'R2':(50,52),'SW1':(65,50),'V1':(35,40),'C1':(65,40)}
    pads=[];geometry={'pads':[],'tracks':[],'outline':[28,27,84,65]}
    for idx,(ref,info) in enumerate(spec['layout'].items()):
        lib,name=info['footprint'].split(':');foot=pcb.FootprintLoad(f'/usr/share/kicad/footprints/{lib}.pretty',name)
        if not foot:raise RuntimeError('Missing footprint '+info['footprint'])
        xy=locations.get(ref,(35+(idx%3)*16,35+(idx//3)*17))
        if idx>=6:raise ValueError('프로토타입 PCB 자동 배치는 6개 부품까지 지원합니다.')
        foot.SetReference(ref);foot.SetValue(info['value']);foot.SetPosition(pcb.VECTOR2I(pcb.FromMM(xy[0]),pcb.FromMM(xy[1])))
        foot.SetPath(pcb.KIID_PATH('/'+spec['root_uuid']+'/'+info['uuid']))
        board.Add(foot)
        # Keep references outside component body; hide values to avoid accidental silk/pad overlaps.
        foot.Value().SetVisible(False);foot.Reference().SetPosition(pcb.VECTOR2I(foot.GetPosition().x,foot.GetPosition().y-pcb.FromMM(5)))
        for p in foot.Pads():
            name=assigns.get((ref,p.GetNumber()))
            if name:p.SetNet(nets[name])
            x,y=pcb.ToMM(p.GetPosition().x),pcb.ToMM(p.GetPosition().y)
            r=math.hypot(pcb.ToMM(p.GetSize().x),pcb.ToMM(p.GetSize().y))/2
            pads.append((x,y,r,name,p));geometry['pads'].append({'ref':ref,'pin':p.GetNumber(),'x':x,'y':y,'net':name})
    for a,b in [((28,27),(84,27)),((84,27),(84,65)),((84,65),(28,65)),((28,65),(28,27))]:
        edge=pcb.PCB_SHAPE();edge.SetShape(pcb.SHAPE_T_SEGMENT);edge.SetStart(pcb.VECTOR2I(pcb.FromMM(a[0]),pcb.FromMM(a[1])));edge.SetEnd(pcb.VECTOR2I(pcb.FromMM(b[0]),pcb.FromMM(b[1])));edge.SetLayer(pcb.Edge_Cuts);edge.SetWidth(pcb.FromMM(.05));board.Add(edge)
    # 0.25 mm grid, tracks .25 mm, clearance .25 mm. Vias only in free grid regions.
    step=.25;bounds=(int(29/step),int(83/step),int(28/step),int(64/step));occupied={};routes=[]
    def cell(x,y):return round(x/step),round(y/step)
    def clear(x,y,layer,net):
        if not(bounds[0]<=x<=bounds[1] and bounds[2]<=y<=bounds[3]):return False
        for dx in range(-2,3):
            for dy in range(-2,3):
                other=occupied.get((x+dx,y+dy,layer))
                if other and other!=net:return False
        for px,py,r,pnet,_ in pads:
            if pnet!=net and (x*step-px)**2+(y*step-py)**2<(r+.5)**2:return False
        return True
    def astar(start,goal,net):
        queue=[(0,0,start)];cost={start:0};prev={}
        while queue:
            _,g,node=heapq.heappop(queue)
            if g!=cost.get(node):continue
            x,y,l=node
            if (x,y)==goal:
                path=[node]
                while node in prev:node=prev[node];path.append(node)
                return path[::-1]
            for dx,dy,dl in [(1,0,0),(-1,0,0),(0,1,0),(0,-1,0),(0,0,1)]:
                target=(x+dx,y+dy,l^dl)
                if not clear(*target,net):continue
                if dl and (not clear(x,y,l,net) or any((x*step-px)**2+(y*step-py)**2<(r+.8)**2 for px,py,r,_,_ in pads)):continue
                ng=g+(12 if dl else 1)
                if ng<cost.get(target,1e12):cost[target]=ng;prev[target]=node;heapq.heappush(queue,(ng+abs(target[0]-goal[0])+abs(target[1]-goal[1]),ng,target))
        raise RuntimeError('Router could not connect '+net)
    for net in sorted(nets):
        ps=[p for p in pads if p[3]==net]
        if len(ps)<2:continue
        connected=[ps[0]]
        for p in ps[1:]:
            q=min(connected,key=lambda q:(q[0]-p[0])**2+(q[1]-p[1])**2);start=(*cell(q[0],q[1]),0);goal=cell(p[0],p[1]);path=astar(start,goal,net)
            coords=[(q[0],q[1],0)]+[(x*step,y*step,l) for x,y,l in path]+[(p[0],p[1],path[-1][2])]
            compact=[]
            for point in coords:
                if compact and point==compact[-1]:continue
                while len(compact)>1 and compact[-2][2]==compact[-1][2]==point[2] and (compact[-1][0]-compact[-2][0])*(point[1]-compact[-1][1])==(compact[-1][1]-compact[-2][1])*(point[0]-compact[-1][0]):compact.pop()
                compact.append(point)
            coords=compact
            for a,b in zip(coords,coords[1:]):
                if a[2]!=b[2]:
                    via=pcb.PCB_VIA(board);via.SetPosition(pcb.VECTOR2I(pcb.FromMM(a[0]),pcb.FromMM(a[1])));via.SetWidth(pcb.FromMM(.8));via.SetDrill(pcb.FromMM(.4));via.SetViaType(pcb.VIATYPE_THROUGH);via.SetLayerPair(pcb.F_Cu,pcb.B_Cu);via.SetNet(nets[net]);board.Add(via)
                elif a[:2]!=b[:2]:
                    track=pcb.PCB_TRACK(board);track.SetStart(pcb.VECTOR2I(pcb.FromMM(a[0]),pcb.FromMM(a[1])));track.SetEnd(pcb.VECTOR2I(pcb.FromMM(b[0]),pcb.FromMM(b[1])));track.SetWidth(pcb.FromMM(.25));track.SetLayer(pcb.F_Cu if a[2]==0 else pcb.B_Cu);track.SetNet(nets[net]);board.Add(track);geometry['tracks'].append({'from':a[:2],'to':b[:2],'layer':a[2],'net':net})
            for x,y,l in path:occupied[x,y,l]=net
            connected.append(p)
    board.BuildConnectivity();pcb.SaveBoard(spec['output'],board)
    Path(spec['output']).with_name('pcb-geometry.json').write_text(json.dumps(geometry))

if __name__=='__main__':main(json.loads(Path(sys.argv[1]).read_text()))
