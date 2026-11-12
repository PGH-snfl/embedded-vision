"""Free-form observation/recheck/design notes; one final typed program result."""
from copy import deepcopy
import hashlib
from pathlib import Path
import re
from tempfile import TemporaryDirectory

from PIL import Image
from pydantic import Field

from .component_completion import PhotoSystemAnalysis,inventory_digest
from .board_profiles import board_profiles
from .functional_build import implementation_catalog,BUILD_PROMPT
from .photo_structure import STRUCTURE_PROMPT
from .enclosure_analysis import ENCLOSURE_PROMPT
from ..planner.models import Region
from ..planner.inspection_skill import InspectionRuntime
from ..vision.component_crops import crop_image
from ..workflow import workflow_prompt


class FinalPhotoAnalysis(PhotoSystemAnalysis):
    reviewed_part_ids:list[str]=Field(max_length=40)
    uninspected_regions:list[Region]=Field(max_length=20)
    review_summary:str=Field(max_length=1600)


def analyze_final_json(context,assets,provider,model,progress,on_update=None):
    from .inventory import PROMPT,REASONING_PROMPT
    runtime=InspectionRuntime(assets)
    report={'mode':'final_json','status':'running','skill':runtime.report(),
            'sources':[],'crops':[],'reviews':[],'notes':[],'initial_ids':[],
            'added_ids':[],'duplicates':[],'uninspected_regions':[],'skipped':[],
            'final_ids':[],'reviewed_ids':[],'grouped_ids':[],
            'notice':'중간 분석은 자유 문장입니다. 원본 분할 확대에서 부품별로 재검토하고 최종 JSON에서 검토 ID를 받습니다. 최종 부품별 잘라보기 이미지는 확인용이며 별도 모델 호출은 아닙니다. 원본 내부·실물 작동은 검증하지 않았습니다.'}
    paths=dict(assets);calls=[]
    for aid,path in assets:
        with Image.open(path) as im:width,height=im.size
        report['sources'].append({'asset_id':aid,'sha256':hashlib.sha256(Path(path).read_bytes()).hexdigest(),'width':width,'height':height})
    def emit():
        report['skill']=runtime.report()
        if on_update:on_update(deepcopy(report))
    def notes(task,payload,prompt,images,*,tools=False):
        try:
            text,usage=provider.infer(model,payload,prompt,task,images,
                **({'skill_runtime':runtime} if tools else {'budget':runtime.budget}))
        finally:emit()
        calls.append({'stage':task,'call':usage,'decision':{'notes':text},'validation_errors':[]})
        report['notes'].append({'stage':task,'text':text});emit()
        return text
    progress('components','1/6 · 사진의 구성품·표식을 자유 문장으로 분석합니다.')
    initial=notes('component_notes',context,
        PROMPT+'\nJSON을 작성하지 말고 P1, P2 같은 고유 ID를 붙여 각 관측 후보의 위치·수량·표식·불확실성을 자유 문장이나 표로 기록하세요. 기능 추론은 아직 하지 않습니다.',assets,tools=True)
    with TemporaryDirectory(prefix='ev-final-json-crops-') as directory:
        tiles=[]
        views=[assets[0],assets[-1]] if len(assets)>1 else assets
        for aid,path in views:
            for box in [(0,0,.55,.55),(.45,0,1,.55),(0,.45,.55,1),(.45,.45,1,1)]:
                region=Region(asset_id=aid,x0=box[0],y0=box[1],x1=box[2],y1=box[3])
                try:raw,meta=crop_image(path,region)
                except ValueError:continue
                cid='TILE'+str(len(tiles)+1)
                dest=Path(directory)/(cid+'.jpg');dest.write_bytes(raw)
                meta.update(crop_id=cid,part_ids=[],purpose='coverage_tile')
                report['crops'].append(meta);tiles.append((cid,dest))
        progress('component_review','2/6 · 원본 확대에서 후보별 표식·누락·중복을 재검토합니다.')
        reviewed=notes('component_recheck_notes',{
            **context,'component_notes':initial,'crop_mapping':report['crops']},
            '원본 전체와 분할 확대를 대조해 후보 ID별로 하나씩 재검토하세요. 누락·중복·부품이 아닌 후보를 정리하고 최종 관측 목록을 자유 문장으로 작성하세요. '
            'ID는 유지하고 새 후보만 새 ID를 붙이세요. 각 부품에 원본 asset ID와 정규화 위치, 수량, 표식, 모델 후보와 확인 한계를 적으세요. '
            '확대 이미지 좌표가 아닌 원본 좌표를 사용하세요. 보드 참고자료 없이 보이는 구성품만 판단하고 기능·설계 부품을 섞지 마세요. JSON은 필요 없습니다.',[*assets,*tiles])
        progress('coverage','3/6 · 재검토한 관측 메모를 확정해 설계 단계에 전달합니다.')
        frozen=hashlib.sha256(reviewed.encode()).hexdigest()
        design_context={**context,'stage':'circuit_design_after_inventory',
            'finalized_component_notes':reviewed,'component_notes_sha256':frozen,
            'board_profiles':board_profiles(),'implementation_catalog':implementation_catalog()}
        progress('function','4/6 · 관측 메모를 근거로 기능·회로·코드를 자유롭게 설계합니다.')
        design=notes('system_reasoning_notes',design_context,
            REASONING_PROMPT.replace('저장된 observed_inventory','확정된 finalized_component_notes')+'\n'+workflow_prompt()+'\n'+STRUCTURE_PROMPT+'\n'+ENCLOSURE_PROMPT+'\n'+BUILD_PROMPT+
            '\n관측 메모를 변경하지 마세요. 기능 후보·부족한 부품·선정 보드·전원·핀 연결·코드·구조·확인할 사항을 자유 문장과 표/코드 블록으로 자세히 완성하세요. JSON은 마지막 별도 단계에서 작성하므로 여기서는 작성하지 않습니다.',assets)
    progress('completion','5/6 · 완료된 분석을 프로그램용 최종 JSON 한 개로 정리합니다.')
    try:
        result,usage=provider.infer(model,{**design_context,'design_notes':design,
            'review_notes':reviewed,'source_asset_ids':list(paths)},
            '이미 끝난 관측·재검토·기능·회로 분석 메모를 최종 JSON으로 옮기세요. 부품 ID와 관측 사실을 바꾸거나 새 기능을 추측하지 마세요.',
            'final_photo_json',[],budget=runtime.budget)
    finally:emit()
    calls.append({'stage':'final_photo_json','call':usage,'decision':result.model_dump(mode='json'),'validation_errors':[]})
    result.inventory.suggested_function=''
    ids=[p.id for p in result.inventory.parts]
    if len(result.reviewed_part_ids)!=len(set(result.reviewed_part_ids)) or set(result.reviewed_part_ids)!=set(ids):
        raise RuntimeError('최종 JSON의 관측 부품과 재검토 ID가 일치하지 않습니다. 중간 메모는 보존합니다.')
    for part in result.inventory.parts:
        if not re.search(r'(?<![A-Za-z0-9_-])'+re.escape(part.id)+r'(?![A-Za-z0-9_-])',reviewed):
            raise RuntimeError('최종 JSON에 관측 메모에 없던 부품 ID가 있습니다.')
        if any(r.asset_id not in paths for r in part.regions):
            raise RuntimeError('최종 JSON의 부품 위치가 등록한 원본과 다릅니다.')
    if any(r.asset_id not in paths for r in result.uninspected_regions):
        raise RuntimeError('최종 JSON의 미검토 영역이 등록한 원본과 다릅니다.')
    # These are UI crops, not additional model reviews after serialization.
    for part in result.inventory.parts:
        region=part.regions[0]
        try:_,meta=crop_image(paths[region.asset_id],region)
        except ValueError:
            report['skipped'].append({'part_id':part.id,'reason':'원본 픽셀이 부족해 개별 확대를 표시하지 못합니다.'})
            continue
        meta.update(crop_id='CROP'+str(len([c for c in report['crops'] if c['part_ids']])+1),part_ids=[part.id],purpose='final_inventory_display')
        report['crops'].append(meta)
        report['reviews'].append({'part_id':part.id,'name':part.name,'markings':part.markings,
                                  'disposition':'unclear' if part.status=='UNKNOWN' else 'visible'})
    report.update(initial_ids=ids,final_ids=ids,reviewed_ids=result.reviewed_part_ids,
        grouped_ids=[p.id for p in result.inventory.parts if p.quantity>1],
        uninspected_regions=[r.model_dump(mode='json') for r in result.uninspected_regions],
        audit_summary=result.review_summary,component_notes_sha256=frozen,
        final_inventory_sha256=inventory_digest(result.inventory),
        status='partial' if report['skipped'] or result.uninspected_regions or any(p.quantity>1 for p in result.inventory.parts) else 'reviewed_candidates')
    emit()
    return result.inventory,result.design.model_dump(mode='json'),report,calls,runtime.budget
