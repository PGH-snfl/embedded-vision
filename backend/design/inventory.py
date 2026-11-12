import re,uuid
from copy import deepcopy
from .models import Inventory
from .function import FunctionIntent,unknown_function
from .system_model import validate_system_model
from .virtual_model_proposal import normalize_virtual_model
from .hypotheses import validate_hypotheses,infer_candidates
from .simulator_catalog import load_simulator_catalog
from .catalog_matching import match_inventory
from .photo_structure import validate_photo_structure, STRUCTURE_PROMPT
from .component_completion import validate_required_parts, component_datasheet, inventory_digest
from .enclosure_analysis import ENCLOSURE_PROMPT, validate_enclosure_analysis
from .functional_build import BUILD_PROMPT, implementation_catalog, validate_build, build_workbench
from ..planner.provider import ResponsesProvider,PRIMARY,SPECIALIST
from ..planner.selection import analysis_model,model_label
from ..planner.service import digest
from ..workflow import workflow_stamp, workflow_prompt
from .runtime_repairs import complete_missing_grounds
from .board_profiles import board_profiles, board_catalog
from .analysis_context import observation_context

POLICY_VERSION='component-notes-final-json-v13'
PROMPT='사진·영상에서 실제 보이는 구성품을 먼저 목록화하세요. 개발보드·센서·표시기·구동부·전원·기구물·배선 등을 보이는 범위에서 식별합니다. 기능과 필요한 추가 부품은 다음 단계에서 판단하므로 suggested_function은 빈 문자열로 둡니다. 읽힌 표식, 모델 후보, 수량, 위치와 확인할 사항을 기록하세요. 사진에 보이지 않는 필수 부품을 관측 목록에 넣지 마세요. 모델·정격·값·핀 배열은 확정하지 않습니다. 시뮬레이터 목록은 이름 비교 자료이며 관측 근거가 아니며 원본 데이터시트도 아닙니다. 목록에 없는 부품을 억지로 다른 부품에 대응하지 마세요. 영상의 동일한 부품을 중복 계산하지 마세요.'
REASONING_PROMPT='저장된 observed_inventory를 변경하지 말고 해당 구성품 목록을 근거로 어떤 시스템인지, 입력·처리·출력 기능 후보 1~3개를 추론하세요. 모델 후보·표식·수량·위치를 참고하고 사진의 문맥으로 보완하세요. 그 뒤 기능 구현에 부족하거나 가려져 확인되지 않은 부품은 required_parts에만 추가합니다. 각 보완 부품에 목적·이유·근거 관측 부품 ID·기능 후보 ID·확인할 사양을 기록하세요. 보완 부품은 INFERRED, 사진 내 존재 여부는 UNKNOWN입니다. 원본에 해당 부품이 있다고 확정하지 않습니다. 필요한 구동 회로·전원·보호 부품·전류 제한·커넥터·배선도 검토하세요. 수량이 부족하면 부족분만 제안하고 사진의 기존 부품을 중복 추가하지 마세요. 시뮬레이터 목록은 관측 근거가 아니며 원본 정격 자료도 아닙니다. 새 회로·코드를 만들 수 있도록 기능을 설명하되 미지원 기능을 다른 간단한 기능으로 바꾸지 마세요. 모델·전압·핀·저항값은 확정하지 말고 데이터시트 확인 항목으로 남기세요.'

def inventory_plan(graph,assets,provider=None,progress=None,on_inventory=None,single_call=None,model=PRIMARY,on_inspection=None):
    model=analysis_model(model);label=model_label(model)
    progress=progress or (lambda stage,message:None);provider=provider or ResponsesProvider()
    # Normal photo/video analysis always finishes inventory before board design.
    # The explicit legacy single_call=True path is retained for internal callers.
    use_inspection=single_call is None and isinstance(provider,ResponsesProvider) and provider.component_inspection
    final_json=use_inspection and provider.photo_pipeline=='final_json'
    single_call=False if single_call is None else single_call
    progress('components','1/4 · 사진·영상에서 보이는 구성품과 표식을 먼저 확인합니다.')
    # Original links, wire paths and hidden-wire hypotheses are intentionally excluded.
    selected_ids=[aid for aid,_ in assets]
    selected=set(selected_ids)
    metadata={a.id:a.model_dump(mode='json') for a in graph.assets if a.id in selected}
    if graph.mode=='video':
        # Timestamp is supplied separately from a filename and bound to the
        # frame evidence created by our extractor. It is not a causal claim.
        for evidence in graph.evidence:
            if evidence.method!='video_frame' or evidence.asset_id not in metadata:continue
            match=re.match(r'^(\d+(?:\.\d+)?)초 프레임\.',evidence.text)
            if match:metadata[evidence.asset_id]['frame_timestamp_seconds']=float(match.group(1))
    # This is a vocabulary aid, not evidence about the photo or a component's ratings.
    catalog=load_simulator_catalog()
    catalog_result=({'status':'unavailable','source':catalog['source'],'entry_count':0,
                     'notice':catalog['notice'],'matches':[]} if catalog['status']=='unavailable' else None)
    context=observation_context(graph.mode,[metadata[aid] for aid in selected_ids if aid in metadata],workflow_stamp(),catalog)
    raw={};inspection=None;inspection_calls=[];inspection_budget=None
    if final_json:
        from .final_json import analyze_final_json
        observed,raw,inspection,inspection_calls,inspection_budget=analyze_final_json(context,assets,provider,model,progress,on_inspection)
        usage=inspection_calls[0]['call']
    elif use_inspection:
        from .component_inspection import inspect_inventory
        observed,inspection,inspection_calls,inspection_budget=inspect_inventory(context,assets,provider,model,progress,on_inspection)
        usage=inspection_calls[0]['call']
        context['component_inspection']={'skill':inspection['skill'],'status':inspection['status'],
            'final_ids':inspection['final_ids'],'uninspected_regions':inspection['uninspected_regions'],'notice':inspection['notice']}
    elif single_call:
        progress('components',label+'가 사진의 구성품·기능·선정 부품·배선·코드를 한 번의 AI 호출로 분석합니다.')
        context['implementation_catalog']=implementation_catalog()
        context['workflow']=workflow_stamp()
        context['board_profiles']=board_profiles()
        context['simulator_catalog']={'entries':catalog['entries'],'notice':catalog['notice']}
        context['purpose']='하나의 응답에서 inventory를 먼저 작성한 뒤 이를 참조하는 design을 완성합니다.'
        prompt=('한 번의 응답으로 inventory와 design을 작성하세요. inventory에는 사진에 실제 보이는 구성품만 먼저 기록하고, '
            'design에서 해당 ID를 참조해 기능과 실행 설계를 작성하세요. 원본 관측과 새 설계의 선정값을 구분하세요.\n'
            +workflow_prompt()+'\n'+PROMPT+'\n'+REASONING_PROMPT.replace('저장된 observed_inventory','동일 응답의 inventory')+'\n'+STRUCTURE_PROMPT+'\n'+ENCLOSURE_PROMPT+'\n'+BUILD_PROMPT)
        response,usage=provider.infer(model,context,prompt,'photo_system',assets)
        response=response.model_dump(mode='json') if hasattr(response,'model_dump') else dict(response)
        observed=response['inventory'];raw=response['design']
    else:observed,usage=provider.infer(model,context,'현재 호출은 보드 참고자료 없이 구성품 식별 단계만 수행합니다.\n'+PROMPT,'component_inventory',assets)
    observed_raw=observed.model_dump(mode='json') if hasattr(observed,'model_dump') else dict(observed)
    inventory=Inventory.model_validate({k:v for k,v in observed_raw.items() if k in Inventory.model_fields})
    inventory.suggested_function=''
    for part in inventory.parts:
        if any(r.asset_id not in selected for r in part.regions):raise RuntimeError('부품 위치가 입력 이미지와 일치하지 않습니다.')
    calls=[{'stage':'photo_system' if single_call else 'components',
        'decision':{'inventory':inventory.model_dump(mode='json'),'design':deepcopy(raw)} if single_call else inventory.model_dump(mode='json'),
        'call':usage,'validation_errors':[]}]
    if inspection_calls:calls=inspection_calls
    partial={'id':uuid.uuid4().hex,'project_id':graph.project_id,'revision':graph.revision,'graph_sha256':digest(graph),
        'task':'component_inventory','analysis_model':model,'component_inspection':inspection,'workflow':workflow_stamp(),'prompt':'구성품 목록 → 확대·재검토 → 누락 대조 → 기능 추론 → 보완 부품 → 데이터시트 → 회로·시뮬레이션',
        'asset_ids':selected_ids,'inventory':inventory.model_dump(mode='json'),
        'observed_inventory_sha256':inventory_digest(inventory),'analysis_complete':False,'analysis_stage':'components',
        'simulator_catalog':catalog_result or match_inventory(inventory,catalog),
        'function':unknown_function().model_dump(mode='json'),'function_hypotheses':[],
        'system_model':None,'virtual_model':None,'photo_structure':None,'enclosure_analysis':None,'functional_build':None,'required_parts':[],
        'component_datasheet':component_datasheet(inventory,[],[],False),
        'decision':{'summary':inventory.summary,'findings':[],'unresolved':inventory.unknowns,'conflicts':[],
                    'actions':['review_evidence'],'deep_review':[]},
        'attempts':deepcopy(calls),'routing':{'policy':POLICY_VERSION,'primary':model,'specialist':SPECIALIST,
                    'escalation_reasons':[],'specialist_called':False,'specialist_attempted':False,
                    'specialist_error':None,'no_escalation_reason':'관측 부품을 저장한 뒤 기능을 별도로 추론합니다.'},
        'executable':False,'blockers':['구성품 목록을 저장했습니다. 시스템 기능과 보완 부품을 분석하고 있습니다.'],
        'execution_steps':[],'validation_errors':[],'notice':'사진 관측과 기능 구현용 보완 부품을 구분합니다.'}
    if on_inventory:on_inventory(deepcopy(partial))
    if inventory.parts and not single_call and not final_json:
        progress('function',('4/6' if use_inspection else '2/4')+' · 구성품과 구조를 근거로 기능을 추론하고 실행할 부품·배선·코드를 선정합니다.')
        reasoning_context={**context,'purpose':'관측 목록을 참조해 기능을 추론하고 필요한 부품을 별도 보완합니다.',
            'stage':'circuit_design_after_inventory','workflow':workflow_stamp(),
            'board_profiles':board_profiles(),
            'simulator_catalog':{'entries':catalog['entries'],'notice':catalog['notice']},
            'observed_inventory':inventory.model_dump(mode='json'),
            'observed_inventory_sha256':inventory_digest(inventory),'implementation_catalog':implementation_catalog()}
        reasoning,call=provider.infer(model,reasoning_context,workflow_prompt()+'\n'+REASONING_PROMPT+'\n'+STRUCTURE_PROMPT+'\n'+ENCLOSURE_PROMPT+'\n'+BUILD_PROMPT,'system_reasoning',assets,
            **({'budget':inspection_budget} if inspection_budget else {}))
        raw=reasoning.model_dump(mode='json') if hasattr(reasoning,'model_dump') else dict(reasoning)
        calls.append({'stage':'function_and_completion','decision':raw,'call':call,'validation_errors':[]})
        if inspection_budget:
            inspection['skill']['http_calls']=inspection_budget.calls
            if on_inspection:on_inspection(deepcopy(inspection))
    if not inventory.parts:raw={}
    elif single_call:progress('function','통합 응답의 기능·구조·실행 설계 참조를 확인합니다.')
    intent=FunctionIntent.model_validate(raw['function']) if raw.get('function') else unknown_function()
    if intent.status=='USER_DEFINED':raise RuntimeError('모델은 사용자 확인 상태를 생성할 수 없습니다.')
    system_model_warnings=[]
    try:system_model=validate_system_model(raw.get('system_model'),selected)
    except (ValueError,RuntimeError):
        system_model=None;system_model_warnings.append('시스템 기능 추론의 근거 또는 형식이 올바르지 않아 제외했습니다.')
    try:virtual_model=normalize_virtual_model(raw.get('virtual_model'))
    except (ValueError,RuntimeError,TypeError):
        virtual_model=None;system_model_warnings.append('가상 기능 모델의 입력·출력 또는 규칙을 검증하지 못해 제외했습니다.')
    grounded=system_model is not None and any(item['status']=='INFERRED' and item['evidence_asset_ids']
        for key in ('inputs','logic','outputs') for item in system_model[key])
    if virtual_model is not None and not grounded:
        virtual_model=None;system_model_warnings.append('근거가 검증된 시스템 기능 추론이 없어 가상 모델을 제외했습니다.')
    try:photo_structure=validate_photo_structure(raw.get('photo_structure'),selected)
    except (ValueError,RuntimeError,TypeError):
        photo_structure=None;system_model_warnings.append('사진 구조물의 근거 또는 형상이 올바르지 않아 제외했습니다.')
    if any(e.asset_id not in selected for e in intent.evidence):raise RuntimeError('동작 근거가 입력 이미지와 일치하지 않습니다.')
    hypotheses=validate_hypotheses(raw.get('function_hypotheses') or [],inventory,selected) or infer_candidates(inventory)
    progress('completion',('5/6' if use_inspection else '3/4')+' · 기능 구현에 부족하거나 사진에서 확인되지 않은 부품을 분리합니다.')
    additions=validate_required_parts(raw.get('required_parts'),inventory,hypotheses)
    try:enclosure_analysis=validate_enclosure_analysis(raw.get('enclosure_analysis'),inventory,hypotheses,additions,photo_structure)
    except (ValueError,RuntimeError,TypeError):
        enclosure_analysis=None;system_model_warnings.append('내부 분해 추론의 참조 또는 계층 형식이 잘못되어 해당 결과만 제외했습니다.')
    prepared,simulation_repairs=complete_missing_grounds(raw.get('functional_build'))
    requested_boards=[p.get('model_id') for p in prepared.get('parts',[]) if isinstance(p,dict) and p.get('model_id') in board_catalog()] if isinstance(prepared,dict) else []
    board_selection={'requested':requested_boards,'fallback_allowed':not any(b!='arduino-uno' for b in requested_boards)}
    try:functional_build=validate_build(prepared,inventory,hypotheses,enclosure_analysis)
    except (ValueError,RuntimeError,TypeError):
        functional_build=None;simulation_repairs=[];system_model_warnings.append('새 실행 설계의 부품·핀·코드 형식을 확인하세요. 다른 보드로 자동 교체하지 않습니다.' if not board_selection['fallback_allowed'] else '새 실행 설계의 부품 또는 연결 형식을 읽을 수 없어 기존 참조 설계를 사용합니다.')
    progress('datasheet',('6/6' if use_inspection else '4/4')+' · 관측·보완 부품과 확인할 사양을 데이터시트로 정리합니다.')
    sheet=component_datasheet(inventory,additions,hypotheses,True)
    if inspection:
        sheet['component_inspection']={k:deepcopy(inspection[k]) for k in ['status','final_ids','reviewed_ids','grouped_ids','uninspected_regions','notice']}
    sheet['simulation_repairs']=simulation_repairs
    sheet['board_selection']=board_selection
    if enclosure_analysis is not None:sheet['enclosure_analysis']=enclosure_analysis
    if functional_build is not None:
        sheet['functional_build']=functional_build
        sheet['implementation_design']=build_workbench(functional_build,{},enclosure_analysis)['embeddedVision']['implementation_design']
    progress('validation','구성품 참조·기능·보완 목록을 검사하고 회로·시뮬레이션 단계에 전달합니다.')
    return {**partial,'analysis_complete':True,'analysis_stage':'datasheet',
            'analysis_stages':(['components','component_review','coverage'] if use_inspection else ['components'])+['function','completion','datasheet'],
            'required_parts':additions,'component_datasheet':sheet,'enclosure_analysis':enclosure_analysis,'functional_build':functional_build,'simulation_repairs':simulation_repairs,'board_selection':board_selection,
            'inventory':inventory.model_dump(mode='json'),'simulator_catalog':catalog_result or match_inventory(inventory,catalog),'function':intent.model_dump(mode='json'),'function_hypotheses':[h.model_dump(mode='json') for h in hypotheses],'hypothesis_source':'multimodal_model' if raw.get('function_hypotheses') else 'stored_component_observations','system_model':system_model,'virtual_model':virtual_model,'photo_structure':photo_structure,'system_model_warnings':system_model_warnings,
            'decision':{'summary':inventory.summary,'findings':[],'unresolved':inventory.unknowns,'conflicts':[],
                        'actions':['review_evidence'],'deep_review':[]},
            'attempts':calls,'analysis_mode':'final_json' if final_json else 'skill_inspection' if use_inspection else 'single_call' if single_call else 'staged','model_call_count':sum(c['call'].get('http_calls',1) for c in calls),
            'routing':{'policy':POLICY_VERSION,'primary':model,'specialist':SPECIALIST,'escalation_reasons':[],
                       'specialist_called':False,'specialist_attempted':False,'specialist_error':None,
                       'no_escalation_reason':label+'의 중간 분석은 자유 문장으로 연결하고 최종 JSON 한 개만 검증했습니다.' if final_json else label+' 한 번의 호출로 구성품·기능·실행 설계를 작성하고 서버에서 참조를 검사했습니다.' if single_call else label+'로 구성품 식별과 기능·보완 추론을 순서대로 처리했습니다.'},
            'executable':False,'blockers':['부품 모델·핀 라벨·전압을 검토한 뒤 새 설계를 생성하세요.'],
            'execution_steps':[],'validation_errors':[],
            'notice':'관측 부품 목록과 새 설계는 별도입니다. 원본 배선이 가려져 있어도 새 설계를 제안할 수 있습니다.'}
