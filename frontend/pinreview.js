import {apiPrefix} from './saas.js';
import {textAdvice,wireAdvice} from './pinassist.js?v=breadboard-3d-1';
export function initPinReview(ctx){
  const {state,post,run,accept,renderVisuals,message,esc}=ctx;
  const $=s=>document.querySelector(s);
  let key='',textId='',segmentId='',draft={},open=false;
  const graph=()=>state.data.graph;
  const activeText=()=>graph().text_observations?.find(t=>t.id===textId&&t.asset_id===state.assetId);
  const segments=()=>graph().wire_candidates.filter(c=>c.geometry&&c.geometry!=='contour'&&graph().evidence.find(e=>e.id===c.evidence_id)?.asset_id===state.assetId);
  const parts=()=>graph().components.filter(c=>c.asset_id===state.assetId);
  function reset(){const k=graph().project_id+':'+state.assetId;if(k!==key){key=k;textId='';segmentId='';draft={};state.pendingPinReview=null;state.pendingAnchor=null;}}
  function chooseText(id){reset();state.pendingPinReview=null;textId=id;draft={};open=true;state.showText=true;renderVisuals();message('문자를 확인하고 부품을 선택한 뒤 실제 핀 위치를 지정하세요.');}
  function chooseSegment(id){reset();state.pendingPinReview=null;segmentId=id;open=true;$('#candidates').checked=true;renderVisuals();message('표시된 점은 선 조각의 끝입니다. 실제 핀에 닿는지 확인하세요.');}
  function crop(text){
    if(!text)return '<p>문자 영역을 선택하거나 직접 읽은 단자 이름을 입력하세요.</p>';
    const asset=graph().assets.find(a=>a.id===state.assetId),h=1000*asset.height/asset.width;
    const x=Math.max(0,text.bbox[0].x*1000-20),y=Math.max(0,text.bbox[0].y*h-20);
    const w=(text.bbox[1].x-text.bbox[0].x)*1000+40,height=(text.bbox[1].y-text.bbox[0].y)*h+40;
    return `<svg class="text-crop" viewBox="${x} ${y} ${w} ${height}" role="img" aria-label="선택한 문자 확대"><image href="${apiPrefix}/projects/${graph().project_id}/assets/${state.assetId}" width="1000" height="${h}"/></svg><p>OCR 원문: <b>${esc(text.text)}</b> · 문자 점수 ${text.score.toFixed(2)}<br>붙여 읽은 문자는 직접 구분하세요. 글자의 위치와 핀 위치는 다릅니다.</p>`;
  }
  function render(){
    reset();const g=graph(),panel=$('#inspection-panel');panel.hidden=!['photo','video'].includes(g.mode);if(panel.hidden)return;
    const texts=(g.text_observations||[]).filter(t=>t.asset_id===state.assetId),wires=segments(),selected=wires.find(c=>c.id===segmentId);
    const proposal=state.data.review_assist?.[state.assetId]?.wires.find(w=>w.candidate_id===segmentId);
    const pins=parts().flatMap(c=>c.terminals.filter(t=>t.image_position).map(t=>({id:t.id,label:`${c.label.value||c.id} · ${t.name.value}`})));
    panel.innerHTML=`<div class="inspection-heading"><div><strong>핀·선 끝점 검토</strong><small>문자 영역 ${texts.length}개 · 선 조각 ${wires.filter(w=>w.geometry==='segment').length}개 · 복잡한 윤곽 ${wires.filter(w=>w.geometry==='ambiguous').length}개 · 지정 핀 ${pins.length}개</small></div><button id="inspect-observations">문자·선 끝점 후보 찾기</button></div><details id="inspection-details" ${open?'open':''}><summary>확대해서 핀과 배선 검토하기</summary><p class="review-warning">색상 선의 끝은 가림으로 끊긴 지점일 수 있습니다. 실제 핀 위치와 도통을 자동 확인한 결과가 아닙니다.</p><div class="inspection-grid"><section><h3>1. 문자 확인 → 실제 핀 위치</h3><div class="observation-list">${texts.map(t=>`<button type="button" data-text-observation="${esc(t.id)}" class="${textId===t.id?'selected':''}">${esc(t.text)}</button>`).join('')||'<p>후보 찾기를 실행하면 읽은 문자가 여기에 표시됩니다.</p>'}</div>${crop(activeText())}${textAdvice(state,textId,draft.component,esc)}<form id="pin-review-form"><label>부품<select name="component" required><option value="">부품을 선택하세요</option>${parts().map(c=>`<option value="${esc(c.id)}" ${draft.component===c.id?'selected':''}>${esc(c.label.value||c.id)}</option>`).join('')}</select></label><label>직접 확인한 단자 이름<input name="label" maxlength="40" required value="${esc(draft.label||'')}" placeholder="예: GND · 모르면 입력하지 마세요"></label><label>확인 근거<input name="note" required minlength="5" maxlength="500" value="${esc(draft.note||'')}" placeholder="어떤 글자와 핀을 확인했는지 기록"></label><div class="pin-position"><button type="button" id="pin-pick">사진에서 실제 핀 찍기</button><button type="button" id="pin-cancel">지정 취소</button><span>${draft.position?`위치 지정됨 (${draft.position.x.toFixed(3)}, ${draft.position.y.toFixed(3)})`:'핀 위치 미지정'}</span></div><button type="submit" ${draft.position?'':'disabled'}>검토한 핀 저장 · 추정</button><small>이름·위치만 저장합니다. 데이터시트 핀 번호는 UNKNOWN으로 유지합니다.</small></form></section><section><h3>2. 선 조각 → 양쪽 핀 대조</h3><div class="observation-list">${wires.map((w,i)=>`<button data-segment="${esc(w.id)}" class="${segmentId===w.id?'selected':''}">${i+1} · ${esc(w.color)} · ${w.geometry==='segment'?'끝점 2개':'분기/복잡'}</button>`).join('')||'<p>아직 선 조각 후보가 없습니다.</p>'}</div>${selected?`<p>${esc(selected.reason)}</p>`:'<p>선 조각을 선택하면 사진에 경로와 끝점을 표시합니다.</p>'}${wireAdvice(proposal,esc)}<form id="segment-bind"><label>시작 핀<select name="from" required><option value="">위치를 지정한 핀 선택</option>${pins.map(p=>`<option value="${esc(p.id)}" ${proposal?.from_terminal===p.id?'selected':''}>${esc(p.label)}</option>`).join('')}</select></label><label>도착 핀<select name="to" required><option value="">위치를 지정한 핀 선택</option>${pins.map(p=>`<option value="${esc(p.id)}" ${proposal?.to_terminal===p.id?'selected':''}>${esc(p.label)}</option>`).join('')}</select></label><label class="check-label"><input type="checkbox" name="checked" required> 두 선 끝이 선택한 핀에 닿는 것을 사진에서 확인했습니다.</label><label>확인 근거<input name="note" required minlength="5" maxlength="500" placeholder="두 끝점을 어떻게 확인했는지 기록"></label><button ${selected?.geometry==='segment'&&pins.length>=2&&proposal?.state!=='EXISTING'?'':'disabled'}>연결 후보 저장 · 추정</button><small>끝점 위치 불일치·분기는 차단합니다. 가림 여부는 사용자가 확인해야 하며 자동 확정하지 않습니다.</small></form></section></div></details>`;
    $('#inspection-details').ontoggle=e=>open=e.target.open;
    $('#inspect-observations').onclick=()=>run(async()=>{message('문자와 선 조각을 분석합니다. 전기적 연결은 생성하지 않습니다.');await accept(await post('/inspection',{asset_id:state.assetId}));open=true;state.showText=true;$('#candidates').checked=true;renderVisuals();message('문자·선 조각 후보를 표시했습니다. 실제 핀과 양 끝점을 검토하세요.');});
    panel.querySelectorAll('[data-text-observation]').forEach(b=>b.onclick=()=>chooseText(b.dataset.textObservation));
    panel.querySelectorAll('[data-segment]').forEach(b=>b.onclick=()=>chooseSegment(b.dataset.segment));
    const form=$('#pin-review-form');form.oninput=()=>{const d=new FormData(form);const component=d.get('component'),label=d.get('label');if(component!==draft.component||label!==draft.label){delete draft.position;delete draft.textSpan;state.pendingPinReview=null;form.querySelector('button[type=submit]').disabled=true;form.querySelector('.pin-position span').textContent='핀 위치 미지정';}draft={...draft,component,label,note:d.get('note')};};
    form.querySelector('select').onchange=()=>{form.oninput();renderVisuals();};
    panel.querySelectorAll('[data-text-owner]').forEach(b=>b.onclick=()=>{draft={component:b.dataset.textOwner};state.pendingPinReview=null;renderVisuals();});
    panel.querySelectorAll('[data-label-token]').forEach(b=>b.onclick=()=>{const row=state.data.review_assist?.[state.assetId]?.texts.find(t=>t.text_id===textId);const token=row?.owners.find(o=>o.component_id===draft.component)?.tokens[Number(b.dataset.labelToken)];if(!token)return;draft={component:draft.component,label:token.label,textSpan:token.span};state.pendingPinReview=null;renderVisuals();message('원문에 있는 이름을 선택했습니다. 실제 핀 위치와 근거를 따로 지정하세요.');});
    if($('#existing-proposal-link'))$('#existing-proposal-link').onclick=()=>ctx.select('link',proposal.existing_link_id);
    $('#pin-pick').onclick=()=>{form.oninput();if(!draft.component||!draft.label?.trim()){message('부품과 단자 이름을 먼저 입력하세요.',true);return;}ctx.setMode('inspect');state.pendingAnchor=null;state.pendingPinReview={key,revision:g.revision};message('아래 사진에서 실제 핀·커넥터 접점을 클릭하세요. 문자 중심을 찍지 마세요.');$('#image-view').scrollIntoView({block:'center'});};
    $('#pin-cancel').onclick=()=>{state.pendingPinReview=null;delete draft.position;renderVisuals();message('핀 위치 지정을 취소했습니다.');};
    form.onsubmit=e=>{e.preventDefault();if(!draft.position)return;if(draft.revision!==graph().revision){message('수정 버전이 바뀌었습니다. 핀 위치를 다시 지정하세요.',true);return;}form.oninput();run(async()=>{await accept(await post('/inspection/pins',{asset_id:state.assetId,component_id:draft.component,text_id:textId||null,text_span:draft.textSpan||null,label:draft.label,position:draft.position,note:draft.note}));draft={component:draft.component};renderVisuals();message('핀 이름과 위치를 추정 상태로 저장했습니다. 핀 번호는 미확인입니다.');});};
    $('#segment-bind').onsubmit=e=>{e.preventDefault();const f=new FormData(e.target);run(async()=>{await accept(await post(`/inspection/wires/${segmentId}/bind`,{from_terminal:f.get('from'),to_terminal:f.get('to'),endpoints_checked:f.get('checked')==='on',note:f.get('note')}));message('선 조각과 핀의 대응을 추정 연결로 저장했습니다. 실제 도통은 별도 확인이 필요합니다.');});};
  }
  function handlePoint(position){
    const pending=state.pendingPinReview;state.pendingPinReview=null;
    if(!pending||pending.key!==graph().project_id+':'+state.assetId||pending.revision!==graph().revision){message('사진이나 수정 버전이 바뀌었습니다. 핀 지정을 다시 시작하세요.',true);return;}
    draft.position=position;draft.revision=graph().revision;renderVisuals();message('위치를 표시했습니다. 근거를 확인한 뒤 검토한 핀 저장을 누르세요.');
  }
  function overlay(height){
    if(!state.data)return '';reset();const g=graph(),point=p=>`${p.x*1000},${p.y*height}`;
    let svg='';
    if(state.showText)svg+=(g.text_observations||[]).filter(t=>t.asset_id===state.assetId).map(t=>`<rect data-text-observation="${esc(t.id)}" class="text-observation ${textId===t.id?'selected':''}" x="${t.bbox[0].x*1000}" y="${t.bbox[0].y*height}" width="${(t.bbox[1].x-t.bbox[0].x)*1000}" height="${(t.bbox[1].y-t.bbox[0].y)*height}"><title>OCR: ${esc(t.text)} · 핀 위치 아님</title></rect>`).join('');
    if($('#candidates').checked)svg+=segments().filter(w=>w.geometry==='segment').map(w=>`<g data-segment="${esc(w.id)}" class="segment-overlay ${w.id===segmentId?'selected':''}"><polyline points="${w.path.map(point).join(' ')}"/>${w.endpoints.map((p,i)=>`<circle cx="${p.x*1000}" cy="${p.y*height}" r="7"/><text x="${p.x*1000+9}" y="${p.y*height-8}">${i+1}</text>`).join('')}<title>${esc(w.color)} 색상 선 조각 · 실제 접점 미확인</title></g>`).join('');
    const selected=segments().find(w=>w.id===segmentId&&w.geometry==='ambiguous');
    if($('#candidates').checked&&selected){const [a,b]=selected.bbox;svg+=`<rect class="ambiguous-segment" x="${a.x*1000}" y="${a.y*height}" width="${(b.x-a.x)*1000}" height="${(b.y-a.y)*height}"><title>복잡한 윤곽 · 실제 배선 연결 미확인</title></rect>`;}
    svg+=parts().flatMap(c=>c.terminals.filter(t=>t.image_position).map(t=>`<g class="pin-anchor"><circle cx="${t.image_position.x*1000}" cy="${t.image_position.y*height}" r="6"/><text x="${t.image_position.x*1000+8}" y="${t.image_position.y*height-8}">${esc(t.name.value)}</text><title>사용자 지정 핀 위치 · ${esc(t.name.value)} · 핀 번호 미확인</title></g>`)).join('');
    if(draft.position)svg+=`<circle class="draft-pin" cx="${draft.position.x*1000}" cy="${draft.position.y*height}" r="9"/>`;
    return svg;
  }
  return {render,handlePoint,overlay,chooseText,chooseSegment};
}
