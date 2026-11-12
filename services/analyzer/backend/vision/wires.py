"""Conservative color-contour proposals, NOT electrical endpoint detection."""
import cv2
import numpy as np
from PIL import Image
from ..circuit.schema import Evidence, Point, WireCandidate


def detect_color_candidates(image: Image.Image, asset_id: str):
    work = image.copy()
    work.thumbnail((1200, 1200))
    hsv = cv2.cvtColor(np.asarray(work.convert("RGB")), cv2.COLOR_RGB2HSV)
    h, w = hsv.shape[:2]
    ranges = {"red": [(0, 10), (170, 179)], "yellow": [(18, 36)],
              "green": [(38, 86)], "blue": [(90, 133)]}
    evidence, candidates = [], []
    for color, bands in ranges.items():
        mask = np.zeros((h, w), dtype=np.uint8)
        for lo, hi in bands:
            mask |= cv2.inRange(hsv, np.array([lo, 100, 65]), np.array([hi, 255, 255]))
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:20]:
            x, y, cw, ch = cv2.boundingRect(contour)
            area = cv2.contourArea(contour)
            if area < 25 or max(cw, ch) < min(w, h) * .06:
                continue
            rect = cv2.minAreaRect(contour)[1]
            if min(rect) == 0 or max(rect) / min(rect) < 2.5:
                continue
            eid = f"cv_{color}_{len(candidates)}"
            bbox = [Point(x=x/w, y=y/h), Point(x=min((x+cw)/w, 1), y=min((y+ch)/h, 1))]
            evidence.append(Evidence(id=eid, asset_id=asset_id, method="color_segmentation", points=bbox,
                                     text=f"OpenCV HSV v1: {color} 색상 윤곽. 실제 전선·끝점·핀 연결은 확인되지 않았습니다."))
            candidates.append(WireCandidate(id=f"candidate_{len(candidates)+1}", color=color, bbox=bbox, evidence_id=eid))
    return evidence, candidates
