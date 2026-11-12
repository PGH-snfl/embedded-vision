"""Inventory -> mandatory original crops -> per-ID review -> omission audit.

This inspects visible evidence, not concealed hardware. Coverage is reported for
detected candidate IDs; it is never a claim of exhaustive recognition accuracy.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal

from PIL import Image
from pydantic import Field

from ..circuit.schema import StrictModel,ComponentKind
from ..planner.models import Region
from ..planner.inspection_skill import InspectionRuntime
from ..vision.component_crops import crop_image
from .models import Inventory,ObservedPart
from .component_completion import inventory_digest


class ComponentReview(StrictModel):
    part_id: str
    disposition: Literal['visible','unclear','not_component']
    kind: ComponentKind
    name: str=Field(min_length=1,max_length=300)
    model_candidates: list[str]=Field(max_length=6)
    markings: list[str]=Field(max_length=15)
    quantity: int=Field(ge=1,le=50)
    evidence: str=Field(min_length=1,max_length=1600)
    checks_needed: list[str]=Field(max_length=10)


class ReviewBatch(StrictModel):
    reviews: list[ComponentReview]=Field(min_length=1,max_length=6)


class DuplicatePart(StrictModel):
    duplicate_id: str
    keep_id: str
    reason: str=Field(min_length=1,max_length=500)


class CoverageAudit(StrictModel):
    summary: str=Field(min_length=1,max_length=1200)
    added_parts: list[ObservedPart]=Field(max_length=8)
    duplicates: list[DuplicatePart]=Field(max_length=12)
    uninspected_regions: list[Region]=Field(max_length=20)


def inspect_inventory(context,assets,provider,model,progress,on_update=None):
    runtime=InspectionRuntime(assets);paths=dict(assets);calls=[]
    report={'skill':runtime.report(),'status':'running','sources':[],'crops':[],'reviews':[],
            'initial_ids':[],'added_ids':[],'duplicates':[],'uninspected_regions':[],
            'skipped':[],'final_ids':[],'reviewed_ids':[],'grouped_ids':[],
            'notice':'검출한 후보별 확대 검토입니다. 모든 실제 부품의 발견이나 가려진 내부 확인을 보장하지 않습니다.'}
    for aid,path in assets:
        with Image.open(path) as image:width,height=image.size
        report['sources'].append({'asset_id':aid,'sha256':hashlib.sha256(Path(path).read_bytes()).hexdigest(),'width':width,'height':height})
    def emit():
        report['skill']=runtime.report()
        if on_update:on_update(deepcopy(report))
    def checked(inv):
        inv=Inventory.model_validate(inv)
        if any(r.asset_id not in paths for p in inv.parts for r in p.regions):raise RuntimeError('부품 확대 영역이 등록 입력과 일치하지 않습니다.')
        return inv
    def invoke(task,payload,prompt,images):
        try:
            response,usage=provider.infer(model,payload,prompt,task,images,skill_runtime=runtime)
        finally:
            emit() # Preserve attempted calls and earlier reviews even when the API rejects a request.
        raw=response.model_dump(mode='json') if hasattr(response,'model_dump') else response
        calls.append({'stage':task,'decision':deepcopy(raw),'call':usage,'validation_errors':[]});emit()
        return raw
    progress('components','1/6 · 스킬로 보이는 구성품을 각각 목록화합니다.')
    observed=checked(invoke('component_inventory',context,
        'embedded-system-inspection 스킬을 적용하세요. 사진의 기능을 먼저 추측하지 말고 실제 보이는 부품별 ID·수량·표식·영역을 작성하세요. '
        '구분되는 동일 종류 부품도 개별 ID로 기록하고, 구분할 수 없는 묶음은 수량과 한계를 명시하세요. 각 부품 regions의 첫 영역은 표식·핀을 가장 잘 볼 수 있는 영역으로 고르세요. suggested_function은 빈 문자열입니다.',assets))
    observed.suggested_function='';report['initial_ids']=[p.id for p in observed.parts]
    report['initial_inventory']=observed.model_dump(mode='json');emit()
    objects={p.id:p.model_copy(deep=True) for p in observed.parts}
    with TemporaryDirectory(prefix='ev-component-inspection-') as directory:
        def crop(aid,region,part_ids,purpose):
            raw,meta=crop_image(paths[aid],region)
            cid='CROP'+str(len(report['crops'])+1);meta.update(crop_id=cid,part_ids=part_ids,purpose=purpose)
            dest=Path(directory)/(cid+'.jpg');dest.write_bytes(raw);report['crops'].append(meta)
            return cid,dest
        def review(ids):
            pending=[]
            for pid in ids:
                part=objects[pid];region=part.regions[0]
                try:
                    cid,path=crop(region.asset_id,region,[pid],'component_review');pending.append((pid,cid,path))
                except ValueError:
                    part.status='UNKNOWN';part.checks_needed=list(dict.fromkeys([*part.checks_needed,'원본 해상도가 부족해 확대 검토하지 못함']))[:10]
                    report['skipped'].append({'part_id':pid,'reason':'영역의 원본 픽셀이 부족합니다.'})
            for offset in range(0,len(pending),6):
                batch=pending[offset:offset+6];ids=[p for p,_,_ in batch]
                progress('component_review',f'2/6 · 부품 확대 재검토 {offset+1}~{offset+len(batch)} / {len(pending)}')
                payload={'candidates':[objects[p].model_dump(mode='json') for p in ids],
                         'crop_mapping':[m for m in report['crops'] if m['crop_id'] in {cid for _,cid,_ in batch}],
                         'coordinate_space':'crop metadata region is in original image coordinates; do not replace it with crop-relative coordinates'}
                raw=ReviewBatch.model_validate(invoke('component_review',payload,
                    '각 확대 이미지의 부품을 하나씩 재검토하세요. 주어진 part_id를 모두 정확히 한 번씩 반환하세요. 읽힌 마킹을 그대로 기록하고 '
                    '모델 후보·패키지·수량을 대조하세요. 보이지 않는 내부·정격·핀을 확정하지 마세요. 부품이 아니면 not_component, '
                    '구분이 어려우면 unclear입니다. 새 부품 추가는 다음 누락 검사에서 합니다.',[(cid,path) for _,cid,path in batch]))
                received=[r.part_id for r in raw.reviews]
                if len(received)!=len(set(received)) or set(received)!=set(ids):raise RuntimeError('확대 검토에서 부품 ID가 누락·중복되거나 바뀌었습니다.')
                for item in raw.reviews:
                    old=objects[item.part_id]
                    report['reviews'].append(item.model_dump(mode='json'))
                    report['reviewed_ids'].append(item.part_id)
                    if item.disposition=='not_component':del objects[item.part_id];continue
                    objects[item.part_id]=old.model_copy(update={k:getattr(item,k) for k in ['kind','name','model_candidates','markings','quantity','evidence','checks_needed']})
                    objects[item.part_id].status='UNKNOWN' if item.disposition=='unclear' else 'INFERRED'
                emit()
        review(list(objects))
        progress('coverage','3/6 · 원본 분할 확대와 부품 목록을 대조해 누락·중복을 찾습니다.')
        tiles=[]
        # Photo: four overlapping tiles. Video: first and last selected views,
        # plus every whole frame, keep the audit image budget bounded.
        for aid,_ in ([assets[0],assets[-1]] if len(assets)>1 else assets):
            for x0,y0,x1,y1 in [(0,0,.55,.55),(.45,0,1,.55),(0,.45,.55,1),(.45,.45,1,1)]:
                try:
                    cid,path=crop(aid,Region(asset_id=aid,x0=x0,y0=y0,x1=x1,y1=y1),[],'coverage_tile');tiles.append((cid,path))
                except ValueError:continue
        audit=CoverageAudit.model_validate(invoke('component_coverage',{
            'reviewed_inventory':[p.model_dump(mode='json') for p in objects.values()],
            'crop_mapping':[m for m in report['crops'] if m['purpose']=='coverage_tile'],
            'existing_ids':report['initial_ids'],'maximum_new_parts':min(8,40-len(objects))},
            '원본 전체와 겹치는 분할 확대 이미지를 목록과 대조하세요. 새로 보이는 부품만 새 ID와 원본 좌표로 추가하고, '
            '이미 있는 부품을 중복 추가하지 마세요. 같은 물체를 중복 기록한 경우만 duplicate_id와 남길 keep_id를 보고하세요. '
            '부품이 많은데 구분하기 어렵거나 가려진 영역은 uninspected_regions에 남기세요. 숨은 부품은 관측 목록에 넣지 마세요.',
            [*assets,*tiles]))
        if any(r.asset_id not in paths for r in audit.uninspected_regions):raise RuntimeError('누락 검사 영역이 등록 입력과 다릅니다.')
        used=set(report['initial_ids']);added=[]
        if len(objects)+len(audit.added_parts)>40:raise RuntimeError('누락 부품을 포함한 관측 목록이 40개 한도를 넘었습니다. 개별 검토 범위를 줄이세요.')
        for part in audit.added_parts:
            if part.id in used or any(r.asset_id not in paths for r in part.regions):raise RuntimeError('새 부품 ID 또는 원본 영역이 잘못되었습니다.')
            used.add(part.id);objects[part.id]=part;added.append(part.id)
        deleted=set()
        for duplicate in audit.duplicates:
            if duplicate.duplicate_id not in objects or duplicate.keep_id not in objects or duplicate.keep_id==duplicate.duplicate_id or duplicate.duplicate_id in deleted:
                raise RuntimeError('중복 부품 검사 결과의 참조가 잘못되었습니다.')
            deleted.add(duplicate.duplicate_id)
        if any(d.keep_id in deleted for d in audit.duplicates):raise RuntimeError('중복 제거 결과가 서로 충돌합니다.')
        for pid in deleted:del objects[pid]
        report.update(added_ids=added,duplicates=[d.model_dump(mode='json') for d in audit.duplicates],
                      uninspected_regions=[r.model_dump(mode='json') for r in audit.uninspected_regions],audit_summary=audit.summary)
        review([pid for pid in added if pid in objects])
    result=checked({'summary':observed.summary+' · '+audit.summary,'parts':[p.model_dump(mode='json') for p in objects.values()],
                    'suggested_function':'','unknowns':observed.unknowns})
    report['final_ids']=[p.id for p in result.parts];report['grouped_ids']=[p.id for p in result.parts if p.quantity>1]
    report['status']='partial' if report['skipped'] or report['uninspected_regions'] or report['grouped_ids'] else 'reviewed_candidates'
    report['final_inventory_sha256']=inventory_digest(result);emit()
    return result,report,calls,runtime.budget
