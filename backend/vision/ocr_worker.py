"""Short-lived OCR process: release ONNX arenas before the next VLM request."""
import json
import sys
from .analyze import read_text


def read_rows(path):
    rows=[]
    for points,text,score in read_text(path):
        rows.append({'text':str(text),'score':float(score),
                     'bbox':[float(min(p[0] for p in points)),float(min(p[1] for p in points)),
                             float(max(p[0] for p in points)),float(max(p[1] for p in points))]})
    return rows


if __name__=='__main__':
    print(json.dumps(read_rows(sys.argv[1]),ensure_ascii=False))
