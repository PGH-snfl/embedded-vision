"""Local OCR plus bounded component proposals; never fills hidden electrical nets."""
import threading, re, uuid
import cv2
import numpy as np
from PIL import Image
from .wires import detect_color_candidates
from ..circuit.schema import Component, Claim, Evidence, Point, Status

_engine=None
_lock=threading.Lock()


def read_text(path):
    global _engine
    from rapidocr_onnxruntime import RapidOCR
    import onnxruntime
    onnxruntime.disable_telemetry_events()
    with _lock:
        if _engine is None:
            _engine=RapidOCR(intra_op_num_threads=2,inter_op_num_threads=2, det_limit_side_len=1280)
        source=cv2.cvtColor(np.asarray(path.convert('RGB')),cv2.COLOR_RGB2BGR) if isinstance(path,Image.Image) else str(path)
        result,_=_engine(source)
    return result or []


def analyze(graph, path, asset_id="image", pcb=False):
    asset=next(a for a in graph.assets if a.id==asset_id)
    existing={e.id for e in graph.evidence}
    texts=read_text(path); rows=[]; added=0
    for i,(box,raw,score) in enumerate(texts):
        eid=f"ocr_{asset_id}_{i}"
        x0,y0=np.min(box,axis=0);x1,y1=np.max(box,axis=0)
        pts=[Point(x=max(0,float(x0)/asset.width),y=max(0,float(y0)/asset.height)),Point(x=min(1,float(x1)/asset.width),y=min(1,float(y1)/asset.height))]
        rows.append({"text":raw,"score":float(score),"bbox":[p.model_dump() for p in pts]})
        if eid in existing: continue
        graph.evidence.append(Evidence(id=eid,asset_id=asset_id,method="ocr",points=pts,text=f"RapidOCR 문자 후보: {raw}; 문자 인식 점수 {score:.3f}. 부품 식별 확률은 아닙니다."))
        upper=raw.upper().replace(" ","")
        if re.search(r"ESP32|ARDUINO|RASPBERRY|PICO|LM358|NE555|MPU6050|AMS1117",upper):
            kind="board" if any(k in upper for k in ["ESP32","ARDUINO","PICO","RASPBERRY"]) else "sensor"
            if any(c.asset_id==asset_id and c.kind==kind and c.bbox[0].x<=pts[0].x<=c.bbox[1].x and c.bbox[0].y<=pts[0].y<=c.bbox[1].y for c in graph.components):
                continue
            # Marking box, not a falsely precise full component box.
            graph.components.append(Component(id=f"OCR_{uuid.uuid4().hex[:6]}",kind=kind,asset_id=asset_id,bbox=pts,
                label=Claim(value=raw,status=Status.INFERRED,score=float(score),evidence_ids=[eid],reason="OCR 표식 영역 후보. 보드 전체/모델 식별은 별도 확인 필요")))
            added+=1
    # Real contour candidates, with no inferred electrical endpoint assignments.
    image=Image.open(path).convert("RGB")
    ev,candidates=detect_color_candidates(image,asset_id)
    for e,c in zip(ev,candidates):
        old=e.id;e.id=f"analysis_{asset_id}_{old}";c.id=f"analysis_{asset_id}_{c.id}";c.evidence_id=e.id
        if e.id not in existing:graph.evidence.append(e);graph.wire_candidates.append(c)
    traces=[]
    if pcb:
        gray=np.array(image.convert("L"));scale=min(1,1200/max(gray.shape));gray=cv2.resize(gray,None,fx=scale,fy=scale)
        lines=cv2.HoughLinesP(cv2.Canny(gray,80,180),1,np.pi/180,40,minLineLength=35,maxLineGap=5)
        if lines is not None:
            h,w=gray.shape
            traces=[{"from":{"x":int(v[0])/w,"y":int(v[1])/h},"to":{"x":int(v[2])/w,"y":int(v[3])/h},"status":"UNKNOWN"} for [v] in lines[:100]]
    from .connections import infer_anchored_wires
    inferred=infer_anchored_wires(graph,path,asset_id)
    return graph,{"asset_id":asset_id,"engine":"RapidOCR / ONNX CPU + OpenCV", "ocr":rows,"component_proposals_added":added,**inferred,
        "trace_candidates":traces,"inner_layers":"UNKNOWN","electrical_nets_inferred":0,
        "limitations":["OCR는 IC 마킹 후보이며 정확한 보드 모델 확정이 아닙니다.","겹침·가림·브레드보드 내부 도통·PCB 내층은 자동 연결하지 않습니다."]}


def _frame_signature(frame):
    """Small, spatial grayscale summary; variation is not proof of a function."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return cv2.resize(gray, (160, 120), interpolation=cv2.INTER_AREA)


def _visual_difference(a, b):
    # Preserve small changes, such as an LED turning on: a global mean alone
    # would drown a few changed pixels in the unchanged background. Averaging
    # the strongest tiles is less sensitive to a single noisy pixel.
    delta = cv2.absdiff(a, b).astype(np.float32)
    tiles = delta.reshape(15, 8, 20, 8).mean(axis=(1, 3)).ravel()
    return float(np.mean(np.partition(tiles, -3)[-3:]))


def keyframes(path, max_frames=6):
    if not isinstance(max_frames, int) or not 1 <= max_frames <= 24:
        raise ValueError('영상 프레임 수는 1~24장만 지원합니다.')
    cap=cv2.VideoCapture(str(path))
    if not cap.isOpened():
        cap.release();raise ValueError("읽을 수 없는 영상입니다.")
    fps=cap.get(cv2.CAP_PROP_FPS);count=cap.get(cv2.CAP_PROP_FRAME_COUNT)
    if not np.isfinite(fps) or not np.isfinite(count) or fps<=0 or count<1 or count/fps>300:
        cap.release();raise ValueError("5분 이하의 유효한 영상만 지원합니다.")
    frames=[];previous=None
    try:
        # At most 24 samples, split over the entire video. Unique indices avoid
        # presenting one short-video frame several times as separate evidence.
        indices=np.unique(np.linspace(0,int(count)-1,min(24,int(count)),dtype=int))
        for group in np.array_split(indices,min(max_frames,len(indices))):
            candidates=[]
            for idx in group:
                cap.set(cv2.CAP_PROP_POS_FRAMES,int(idx));ok,frame=cap.read()
                if not ok or frame is None or frame.shape[0]*frame.shape[1]>20_000_000:continue
                gray=cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY)
                sharp=float(cv2.Laplacian(gray,cv2.CV_64F).var())
                signature=_frame_signature(frame)
                candidates.append((int(idx),sharp,signature))
            if not candidates:continue
            max_sharp=max(item[1] for item in candidates)
            # Reject substantially blurred samples first; among sufficiently
            # clear choices prefer a visual state different from the prior
            # interval. Changes remain observations, not inferred causes.
            clear=[item for item in candidates if item[1]>=max_sharp*.55]
            if previous is None:
                clear.sort(key=lambda item:(item[1],-item[0]),reverse=True)
            else:
                clear.sort(key=lambda item:(_visual_difference(previous,item[2]),item[1],-item[0]),reverse=True)
            # Decode the selected image again so candidate buffering does not
            # retain several full-resolution frames simultaneously.
            for idx,_,signature in clear:
                cap.set(cv2.CAP_PROP_POS_FRAMES,idx);ok,frame=cap.read()
                if ok and frame is not None and frame.shape[0]*frame.shape[1]<=20_000_000:
                    frames.append((float(idx/fps),Image.fromarray(cv2.cvtColor(frame,cv2.COLOR_BGR2RGB))))
                    previous=signature;break
    finally:
        cap.release()
    if not frames:raise ValueError("영상에서 프레임을 읽지 못했습니다.")
    return frames
