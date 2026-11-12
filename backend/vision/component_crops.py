"""Deterministic original-image crops. No generative enhancement or hidden pixels."""
import hashlib
import io
import math

from PIL import Image
from ..planner.models import Region


def crop_image(path, region, *, padding=.06):
    region=Region.model_validate(region)
    with Image.open(path) as original:
        original=original.convert('RGB');width,height=original.size
        dx=(region.x1-region.x0)*padding;dy=(region.y1-region.y0)*padding
        box=(max(0,math.floor((region.x0-dx)*width)),max(0,math.floor((region.y0-dy)*height)),
             min(width,math.ceil((region.x1+dx)*width)),min(height,math.ceil((region.y1+dy)*height)))
        if box[2]-box[0]<2 or box[3]-box[1]<2:raise ValueError('확대할 원본 영역이 너무 작습니다.')
        image=original.crop(box);source_size=image.size
    scale=min(2.0,1200/max(image.size))
    if scale!=1:image=image.resize((max(2,round(image.width*scale)),max(2,round(image.height*scale))),Image.Resampling.LANCZOS)
    buffer=io.BytesIO();image.save(buffer,format='JPEG',quality=92)
    raw=buffer.getvalue()
    return raw,{'asset_id':region.asset_id,'region':region.model_dump(mode='json'),'pixel_box':list(box),
                'original_size':[width,height],'source_crop_size':list(source_size),'display_size':list(image.size),
                'sha256':hashlib.sha256(raw).hexdigest(),'method':'original_crop_lanczos','padding':padding}
