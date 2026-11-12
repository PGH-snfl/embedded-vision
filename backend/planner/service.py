import hashlib, json, uuid
from .models import FocusedReview
from .provider import ResponsesProvider, PRIMARY, SPECIALIST
from .selection import analysis_model,model_label
from ..circuit.profiles import readiness

POLICY_VERSION='focused-v2'

def digest(graph):
    return hashlib.sha256(json.dumps(graph.model_dump(mode='json'),sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def reference_errors(decision,graph,selected):
    assets=set(selected); evidence={e.id for e in graph.evidence}; terminals={t.id for c in graph.components for t in c.terminals}
    errors=[]
    for index,f in enumerate(decision.findings):
        if not set(f.asset_ids)<=assets:errors.append(f'finding {index}: 입력에 없는 이미지 참조')
        if not set(f.evidence_ids)<=evidence:errors.append(f'finding {index}: 없는 근거 참조')
        if not set(f.terminal_ids)<=terminals:errors.append(f'finding {index}: 없는 단자 참조')
        if f.status=='INFERRED' and not (f.asset_ids or f.evidence_ids):errors.append(f'finding {index}: 추정 근거 없음')
    return errors

def focused_scope(primary,graph,assets):
    """Reject blanket escalation. Compile crops and only context associated with nominated findings."""
    selected=dict(assets);accepted=[];skipped=[];indices=set();crop_assets=[]
    for issue in primary.deep_review:
        r=issue.region;ix=issue.finding_indices
        reason=None
        if not issue.solvable_from_visible_evidence:reason='추가 추론으로 보완할 관측 근거가 없음'
        elif len(set(a.strip() for a in issue.alternatives if a.strip()))<2:reason='서로 다른 회로 후보가 부족함'
        elif not issue.visible_evidence.strip() or not issue.question.strip():reason='검토 질문·관측 근거 부족'
        elif len(set(ix))!=len(ix) or any(i<0 or i>=len(primary.findings) for i in ix):reason='잘못된 검토 항목 참조'
        elif r.asset_id not in selected:reason='입력에 없는 이미지 영역'
        elif (r.x1-r.x0)*(r.y1-r.y0)>.55:reason='전체 사진 재분석에 가까운 요청'
        elif any(r.asset_id not in primary.findings[i].asset_ids for i in ix):reason='검토 항목과 이미지가 일치하지 않음'
        if reason:skipped.append({'question':issue.question,'reason':reason});continue
        accepted.append(issue);indices.update(ix);crop_assets.append((r.asset_id,(selected[r.asset_id],r)))
    findings=[{'finding_index':i,**primary.findings[i].model_dump(mode='json')} for i in sorted(indices)]
    tids={t for i in indices for t in primary.findings[i].terminal_ids}
    eids={e for i in indices for e in primary.findings[i].evidence_ids}
    components=[c.model_dump(mode='json') for c in graph.components if any(t.id in tids for t in c.terminals)]
    context={'mode':graph.mode,'findings':findings,'components':components,
             'evidence':[e.model_dump(mode='json') for e in graph.evidence if e.id in eids],
             'links':[w.model_dump(mode='json') for w in graph.links if w.from_terminal in tids or w.to_terminal in tids],
             'questions':[a.model_dump(mode='json') for a in accepted]}
    return accepted,skipped,indices,context,crop_assets

def create_plan(graph,prompt,task,assets,provider=None,progress=None,model=PRIMARY):
    model=analysis_model(model)
    provider=provider or ResponsesProvider();progress=progress or (lambda stage,message:None)
    progress('sol',model_label(model)+'가 부품·배선과 보이는 근거를 분석하고 있습니다.')
    primary,usage=provider.infer(model,graph,prompt,task,assets)
    selected=[aid for aid,_ in assets];errors=reference_errors(primary,graph,selected)
    attempts=[{'decision':primary.model_dump(mode='json'),'call':usage,'validation_errors':errors.copy()}]
    decision=primary.model_copy(deep=True);fallback_error=None;specialist_summary=None
    accepted=[];skipped=[];indices=set();specialist_attempted=False
    progress('routing','심화 추론이 필요한 구간과 단순 미확인 정보를 구분하고 있습니다.')
    if task=='circuit_inference' and not errors and model==PRIMARY:
        accepted,skipped,indices,context,crops=focused_scope(primary,graph,assets)
        if accepted:
            progress('astra',f'어려운 회로 질문 {len(accepted)}건의 해당 이미지 영역만 심화 검토합니다.')
            specialist_attempted=True
            try:
                review,usage=provider.infer(SPECIALIST,context,'지정한 회로 질문과 이미지 잘라낸 영역만 검토하세요.',task,crops,
                    prior={'scope':'focused_only','finding_indices':sorted(indices)})
                review=FocusedReview.model_validate(review)
                got=[r.finding_index for r in review.reviews]
                if set(got)!=indices or len(got)!=len(set(got)):
                    raise RuntimeError('상위 모델이 지정한 검토 범위를 벗어나거나 항목을 누락했습니다. 기본 결과를 유지합니다.')
                for r in review.reviews:
                    f=decision.findings[r.finding_index]
                    f.status=r.status;f.hypothesis=r.hypothesis;f.rationale=r.rationale;f.verification_needed=r.verification_needed
                decision.unresolved=list(dict.fromkeys(primary.unresolved+review.unresolved))
                decision.conflicts=list(dict.fromkeys(primary.conflicts+review.conflicts))
                specialist_summary=review.summary
                attempts.append({'decision':review.model_dump(mode='json'),'call':usage,'validation_errors':[]})
            except (RuntimeError,ValueError) as exc:
                fallback_error=str(exc) if isinstance(exc,RuntimeError) else '상위 모델 응답 형식이 잘못되어 기본 결과를 유지합니다.'
    if task!='build_schematic' and 'build_schematic' in decision.actions:errors.append('사용자가 요청한 작업 범위 밖의 회로도 생성 요청')
    if len(decision.actions)!=len(set(decision.actions)):errors.append('중복 작업 요청')
    progress('validation','추정 상태·근거 참조·실행 조건을 검사하고 있습니다.')
    blockers=readiness(graph)
    if decision.unresolved or decision.conflicts or decision.findings:
        blockers+=['모델의 검토 항목이 남아 있습니다. 원본 그래프에서 확인한 뒤 새 계획을 만드세요.']
    blockers+=errors
    if fallback_error:blockers.append(fallback_error)
    executable=task=='build_schematic' and 'build_schematic' in decision.actions and not blockers
    return {'id':uuid.uuid4().hex,'project_id':graph.project_id,'revision':graph.revision,'graph_sha256':digest(graph),
            'task':task,'analysis_model':model,'prompt':prompt,'asset_ids':selected,'decision':decision.model_dump(mode='json'),
            'specialist_summary':specialist_summary,'attempts':attempts,
            'routing':{'policy':POLICY_VERSION,'primary':model,'specialist':SPECIALIST,
              'escalation_reasons':[i.question for i in accepted],'specialist_attempted':specialist_attempted,
              'specialist_called':len(attempts)==2,'specialist_error':fallback_error,'max_specialist_calls':int(model==PRIMARY),
              'focused_finding_indices':sorted(indices),'review_regions':[i.region.model_dump() for i in accepted],
              'skipped_reviews':skipped,'no_escalation_reason':None if accepted else '깊은 추론 대상 없음 · 가림/정보 부족만으로 상위 모델을 호출하지 않습니다.'},
            'executable':executable,'blockers':blockers,'validation_errors':errors,
            'execution_steps':['MCP 새 프로젝트 생성','MCP 회로도 생성·저장','MCP netlist 내보내기 → Graph 연결 대조','MCP ERC','MCP SVG 내보내기'] if executable else [],
            'notice':'모델 제안은 원본 Circuit Graph를 변경하지 않습니다. 정확도 수치는 실측하지 않았습니다. PCB 작업은 이번 실행 범위에 포함되지 않습니다.'}
