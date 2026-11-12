import {apiPrefix} from './saas.js';
export function initSingleView(ctx){
  const {state,post,run,accept,message,esc}=ctx;
  const $=s=>document.querySelector(s);
  let key='',selected='',open=true;
  const graph=()=>state.data.graph;
  const rows=()=>[...(graph().wire_hypotheses||[])].filter(h=>h.asset_id===state.assetId).sort((a,b)=>b.ranking_score-a.ranking_score);
  const names={red:'빨강',orange:'주황',yellow:'노랑',green:'초록',blue:'파랑'};
  function render(){
    const g=graph(),panel=$('#occlusion-panel');panel.hidden=!['photo','video'].includes(g.mode);if(panel.hidden)return;
    const current=g.project_id+':'+state.assetId;if(key!==current){key=current;selected='';}
    const hypotheses=rows();if(!hypotheses.some(h=>h.id===selected))selected=hypotheses[0]?.id||'';
    const chosen=hypotheses.find(h=>h.id===selected),asset=g.assets.find(a=>a.id===state.assetId);
    const h=1000*asset.height/asset.width,point=p=>`${p.x*1000},${p.y*h}`;
    const others=chosen?hypotheses.filter(p=>p.id!==chosen.id&&p.endpoint_ids.some(id=>chosen.endpoint_ids.includes(id))):[];
    const matches=chosen?state.data.hypothesis_pins?.[chosen.id]||[[],[]]:[[],[]];
    const pinLabel=id=>{for(const c of g.components){const t=c.terminals.find(t=>t.id===id);if(t)return `${c.label.value||c.id} · ${t.name.value||id}`;}return id;};
    const canAdopt=chosen&&!chosen.link_id&&matches.every(m=>m.length===1)&&matches[0][0]!==matches[1][0];
    panel.innerHTML=`<details id="single-view-details" ${open?'open':''}><summary>가려진 배선 추정 · 사진 1장 <span class="tag">경로 후보 ${hypotheses.length}개</span></summary>
      <div class="occlusion-actions"><button id="infer-hidden" class="primary">이 사진에서 가려진 배선 추정</button><span>색상 · 진행 방향 · 굵기 · 간격으로 후보 순위 계산</span></div>
      <p>청록 실선 = 검출한 선 조각 · 주황 점선 = 가려진 구간의 연결 가설. 점선 모양은 실제 숨은 전선의 모양이 아닙니다. 순위 점수는 정답 확률이 아닙니다.</p>
      ${chosen?`<div class="single-view-layout"><div><svg id="single-view-image" viewBox="0 0 1000 ${h}" role="img" aria-label="단일 사진의 가림 배선 추정"><image href="${apiPrefix}/projects/${g.project_id}/assets/${asset.id}" width="1000" height="${h}"/>${chosen.visible_paths.map(p=>`<polyline class="visible-fragment" points="${p.map(point).join(' ')}"/>`).join('')}<polyline class="hidden-bridge" points="${chosen.bridge.map(point).join(' ')}"/>${chosen.bridge.map((p,i)=>`<circle class="occlusion-end" cx="${p.x*1000}" cy="${p.y*h}" r="6"/><text class="occlusion-label" x="${p.x*1000+10}" y="${p.y*h-10}">${i+1}</text>`).join('')}</svg></div>
      <section><h3>연결 가설 · INFERRED</h3><p><b>${esc(names[chosen.color]||chosen.color)} · 순위 점수 ${chosen.ranking_score.toFixed(1)}/100</b><br>전기적 연결은 아직 미확인</p><ul>${chosen.reasons.map(r=>`<li>${esc(r)}</li>`).join('')}</ul><p class="review-warning">${others.length?`같은 끝점의 다른 가설 ${others.length}개가 있습니다. 아래 후보를 비교하세요.`:'표시된 대안이 없어도 정답으로 확정되지 않습니다.'}</p><p>시작 핀 후보: ${matches[0].map(id=>esc(pinLabel(id))).join(' / ')||'미확인'}<br>도착 핀 후보: ${matches[1].map(id=>esc(pinLabel(id))).join(' / ')||'미확인'}</p><button id="adopt-hidden" ${canAdopt?'':'disabled'}>${chosen.link_id?'회로 초안에 반영됨':'추론 연결로 회로 초안에 반영'}</button><small>양끝의 실제 핀이 하나씩 대응될 때 사용합니다. 확정 연결로 바꾸지 않습니다.</small></section></div>
      <div class="hypothesis-list">${hypotheses.map((p,i)=>`<button data-hypothesis="${esc(p.id)}" class="${p.id===selected?'selected':''}">${i+1}. ${esc(names[p.color]||p.color)} · ${p.ranking_score.toFixed(1)} ${others.some(o=>o.id===p.id)?'· 대안':''}</button>`).join('')}</div>`:'<p>사진 한 장으로 분석을 실행하세요. 핀 이름이 없어도 가려진 경로 후보를 표시합니다. 조건에 맞는 조각이 없으면 후보를 만들지 않습니다.</p>'}
      <small>현재 색상·형상 규칙을 이용한 추정입니다. 전선과 보드 인쇄선을 혼동할 수 있으며 검정·흰색 전선, 긴 완전 가림, 복잡한 선 묶음은 제한됩니다.</small></details>`;
    $('#single-view-details').ontoggle=e=>open=e.target.open;
    $('#infer-hidden').onclick=()=>run(async()=>{message('단일 사진에서 선 조각과 가려진 연결 후보를 추정합니다…');await accept(await post('/occlusion/infer',{asset_id:state.assetId}));message(`가림 경로 후보 ${rows().length}개. 순위 점수는 확률이 아니며 연결은 자동 확정하지 않습니다.`);});
    panel.querySelectorAll('[data-hypothesis]').forEach(b=>b.onclick=()=>{selected=b.dataset.hypothesis;render();});
    if($('#adopt-hidden'))$('#adopt-hidden').onclick=()=>run(async()=>{await accept(await post(`/occlusion/hypotheses/${selected}/adopt`,{asset_id:state.assetId}));message('선택한 가설을 INFERRED 연결로 반영했습니다. 실제 연결은 미검증입니다.');});
  }
  return {render};
}
