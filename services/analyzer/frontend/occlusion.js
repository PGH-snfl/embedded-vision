import {apiPrefix} from './saas.js';
export function initOcclusion(ctx){
  const {state,api,post,run,accept,message,esc}=ctx;
  const $=s=>document.querySelector(s);
  let key='',open=false,draft={};
  const graph=()=>state.data.graph;
  const fresh=()=>({asset:'',from:'',to:'',points:[],note:'',same:false,ends:false,visible:false});
  const imageURL=asset=>`${apiPrefix}/projects/${graph().project_id}/assets/${asset}`;
  function resetTrace(){draft.points=[];draft.ends=false;draft.visible=false;}
  function terminals(){return graph().components.flatMap(c=>c.terminals.filter(t=>t.image_position&&t.name.value).map(t=>({c,t})));}
  function options(selected){return '<option value="">핀을 선택하세요</option>'+terminals().map(({c,t})=>`<option value="${esc(t.id)}" ${selected===t.id?'selected':''}>${esc(c.label.value||c.id)} · ${esc(t.name.value)} (${esc(t.id)})</option>`).join('');}
  function reference(id,number){
    const item=terminals().find(p=>p.t.id===id);if(!item)return '<p>원본의 핀을 먼저 선택하세요.</p>';
    const {c,t}=item,a=graph().assets.find(a=>a.id===c.asset_id),h=1000*a.height/a.width;
    const p=t.image_position,x=Math.max(0,Math.min(760,p.x*1000-120)),y=Math.max(0,Math.min(h-180,p.y*h-90));
    return `<figure><figcaption>원본 ${number} · ${esc(t.name.value)}</figcaption><svg viewBox="${x} ${y} 240 180" role="img" aria-label="원본 ${number} 핀 확대"><image href="${imageURL(c.asset_id)}" width="1000" height="${h}"/><circle class="occlusion-end" cx="${p.x*1000}" cy="${p.y*h}" r="5"/></svg></figure>`;
  }
  function canvas(){
    const asset=graph().assets.find(a=>a.id===draft.asset);if(!asset)return '<p>추가 사진을 선택하면 여기에서 접점과 배선 경로를 찍을 수 있습니다.</p>';
    const h=1000*asset.height/asset.width;
    return `<svg id="occlusion-image" viewBox="0 0 1000 ${h}" role="img" aria-label="추가 사진 배선 경로 지정"><image href="${imageURL(asset.id)}" width="1000" height="${h}"/>${draft.visible&&draft.points.length>=2?`<polyline class="occlusion-trace" points="${draft.points.map(p=>`${p.x*1000},${p.y*h}`).join(' ')}"/>`:''}${draft.points.map((p,i)=>`<g><circle class="occlusion-end" cx="${p.x*1000}" cy="${p.y*h}" r="7"/><text class="occlusion-label" x="${p.x*1000+12}" y="${p.y*h-10}">${i===0?'시작':i===draft.points.length-1?'끝':i+1}</text></g>`).join('')}</svg>`;
  }
  function render(){
    const g=graph(),panel=$('#occlusion-panel');panel.hidden=!['photo','video'].includes(g.mode);if(panel.hidden)return;
    const nextKey=`${g.project_id}:${g.revision}`;if(nextKey!==key){key=nextKey;draft=fresh();}
    const reviews=g.wire_reviews||[],pinCount=terminals().length;
    const sources=terminals().filter(p=>[draft.from,draft.to].includes(p.t.id)).map(p=>g.assets.find(a=>a.id===p.c.asset_id));
    const views=g.assets.filter(a=>!sources.some(s=>s.id===a.id||s.sha256===a.sha256));
    if(draft.asset&&!views.some(a=>a.id===draft.asset)){draft.asset='';resetTrace();}
    panel.innerHTML=`<details id="occlusion-details" ${open?'open':''}><summary>가려진 배선 해결 · 다른 각도 대조 <span class="tag">검토 ${reviews.length}건</span></summary>
      <p>같은 색의 선도 서로 다를 수 있습니다. 배선을 그대로 둔 채 반대쪽·옆쪽에서 커넥터 접점까지 보이게 촬영하세요. 두 사진의 같은 핀을 대조한 뒤 선을 따라 표시합니다.</p>
      <div class="occlusion-actions"><label class="button" for="occlusion-upload">＋ 다른 각도 사진 추가</label><input type="file" id="occlusion-upload" hidden><span>1 핀 선택 → 2 추가 사진 경로 표시 → 3 가림 여부 검토</span></div>
      ${pinCount<2?'<p class="review-warning">먼저 위의 ‘핀·선 끝점 검토’에서 원본 사진의 양쪽 핀 이름과 실제 위치를 저장하세요. 가려진 핀 이름을 임의로 채우지 않습니다.</p>':''}
      <form id="occlusion-form" ${pinCount<2?'hidden':''}><div class="occlusion-selects"><label>원본 시작 핀<select id="occlusion-from" required>${options(draft.from)}</select></label><label>원본 도착 핀<select id="occlusion-to" required>${options(draft.to)}</select></label><label>대조할 추가 사진<select id="occlusion-asset" required><option value="">다른 각도 선택</option>${views.map(a=>`<option value="${esc(a.id)}" ${draft.asset===a.id?'selected':''}>${esc(a.filename)} · ${esc(a.id)}</option>`).join('')}</select></label></div>
      <div class="occlusion-views"><div class="occlusion-originals">${reference(draft.from,1)}${reference(draft.to,2)}</div><section><p>첫 점 = 시작 핀 접점, 마지막 점 = 도착 핀 접점. 중간 점은 보이는 선을 따라 순서대로 찍으세요.</p><div id="occlusion-canvas">${canvas()}</div><div class="occlusion-actions"><button type="button" id="occlusion-undo">마지막 점 취소</button><button type="button" id="occlusion-clear">경로 초기화</button><span id="occlusion-count">지정 ${draft.points.length}점</span></div></section></div>
      <label class="check-label"><input type="checkbox" id="occlusion-same" required ${draft.same?'checked':''}> 배선을 바꾸지 않은 같은 장치의 추가 사진입니다.</label>
      <label class="check-label"><input type="checkbox" id="occlusion-ends" required ${draft.ends?'checked':''}> 첫 점과 마지막 점이 원본에서 선택한 두 핀의 실제 접점입니다.</label>
      <label class="check-label"><input type="checkbox" id="occlusion-visible" ${draft.visible?'checked':''}> 추가 사진에서 한 전선의 전체 경로가 끊김 없이 보입니다.</label>
      <label>대조 근거<input id="occlusion-note" required minlength="5" maxlength="1000" value="${esc(draft.note)}" placeholder="예: 옆면에서 같은 커넥터 번호와 연속된 전선을 확인"></label>
      <p id="occlusion-outcome" class="review-warning">${draft.visible?'저장 결과: INFERRED · 추론 연결. 사용자가 대조한 경로이며 자동 인식·도통 확인 결과가 아닙니다.':'저장 결과: UNKNOWN · 미확인. 가려진 부분을 선으로 이어 그리지 않습니다.'}</p><button id="occlusion-save" class="primary" ${pinCount>=2&&draft.points.length>=2?'':'disabled'}>대조 결과 저장</button></form>
      <details><summary>검토 이력과 다음 확인</summary>${reviews.map(r=>{const l=g.links.find(l=>l.id===r.link_id),e=g.evidence.find(e=>e.id===r.evidence_id);return `<article class="occlusion-history"><b>${esc(r.from_terminal)} → ${esc(r.to_terminal)}</b><p>현재 ${esc(l?.connection.status||'UNKNOWN')} · 당시 전체 경로 ${r.entire_wire_visible?'보임':'가림 남음'} · 사진 ${esc(r.asset_id)}</p><p>${esc(e?.text||'')}</p><button type="button" data-occlusion-link="${esc(r.link_id)}">연결 근거 열기</button></article>`;}).join('')||'<p>아직 대조 기록이 없습니다.</p>'}<p>여전히 가려졌다면 양끝 커넥터를 옆에서 가까이 촬영하세요. 계속 보이지 않는 선은 전원을 끄고 회로에서 분리한 뒤 도통(전기가 통하는지)을 측정해 별도로 확인해야 합니다.</p></details></details>`;
    $('#occlusion-details').ontoggle=e=>open=e.target.open;
    $('#occlusion-upload').onchange=()=>run(async()=>{const file=$('#occlusion-upload').files[0];if(!file)return;const body=new FormData();body.append('image',file);const data=await api(`${apiPrefix}/projects/${g.project_id}/assets?expected_revision=${g.revision}`,{method:'POST',body});await accept(data);draft.asset=data.graph.assets.at(-1).id;open=true;render();message('추가 사진을 저장했습니다. 원본 핀과 같은 실제 접점을 대조하세요.');});
    for(const [id,field] of [['from','from'],['to','to'],['asset','asset']])$(`#occlusion-${id}`).onchange=e=>{draft[field]=e.target.value;resetTrace();draft.same=false;render();};
    $('#occlusion-note').oninput=e=>draft.note=e.target.value;
    $('#occlusion-same').onchange=e=>draft.same=e.target.checked;
    $('#occlusion-ends').onchange=e=>draft.ends=e.target.checked;
    $('#occlusion-visible').onchange=e=>{draft.visible=e.target.checked;render();};
    $('#occlusion-undo').onclick=()=>{draft.points.pop();draft.ends=false;draft.visible=false;render();};
    $('#occlusion-clear').onclick=()=>{resetTrace();render();};
    const svg=$('#occlusion-image');if(svg)svg.onclick=e=>{if(!draft.from||!draft.to||draft.from===draft.to){message('서로 다른 시작·도착 핀을 먼저 선택하세요.',true);return;}if(draft.points.length>=200)return;const p=svg.createSVGPoint();p.x=e.clientX;p.y=e.clientY;const q=p.matrixTransform(svg.getScreenCTM().inverse());const a=g.assets.find(a=>a.id===draft.asset),h=1000*a.height/a.width;if(q.x<0||q.x>1000||q.y<0||q.y>h)return;draft.points.push({x:q.x/1000,y:q.y/h});draft.ends=false;draft.visible=false;render();};
    $('#occlusion-form').onsubmit=e=>{e.preventDefault();const body={asset_id:draft.asset,from_terminal:draft.from,to_terminal:draft.to,points:draft.points,same_system_checked:draft.same,endpoints_checked:draft.ends,entire_wire_visible:draft.visible,note:draft.note};run(async()=>{await accept(await post('/occlusion/resolve',body));message(body.entire_wire_visible?'다른 각도에서 대조한 연결을 추론 상태로 저장했습니다.':'가림이 남은 연결을 미확인 상태로 기록했습니다.');});};
    panel.querySelectorAll('[data-occlusion-link]').forEach(b=>b.onclick=()=>{const link=g.links.find(l=>l.id===b.dataset.occlusionLink);state.assetId=link.asset_id;ctx.select('link',link.id);$('#review-workspace').scrollIntoView({block:'start'});});
  }
  return {render};
}
