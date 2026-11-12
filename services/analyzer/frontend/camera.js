import {selectedAnalysisModel,analysisModelLabel} from './analysis-model.js?v=analysis-model-1';
import {apiPrefix} from './saas.js';
export function initCamera(ctx) {
  const {state,api,accept,run,esc,message}=ctx;
  const $=s=>document.querySelector(s);
  let active=null, timer=null, renderedProject=null;
  async function openExample(){
    await accept(await api('/api/projects/camera-example',{method:'POST'}));
    await ctx.post('/auto-analysis',{model:selectedAnalysisModel()});
    await ctx.refreshAnalysis?.();
    message('실제 촬영 예제를 '+analysisModelLabel(selectedAnalysisModel())+' 분석으로 제출했습니다. 처리 상태는 분석 패널에서 확인하세요.');
  }
  $('#camera-example').onclick=()=>run(openExample);
  async function start(all=false){
    if(active){message('이미 VLM 분석이 진행 중입니다.');return;}
    const g=state.data.graph;
    const asset_ids=all?g.assets.map(a=>a.id).slice(0,6):[state.assetId];
    const job=await api(`${apiPrefix}/projects/${g.project_id}/vision`,{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({expected_revision:g.revision,asset_ids})});
    active=job;render();message('실사 VLM 분석을 시작했습니다. CPU에서는 사진당 수십 초~수 분이 걸릴 수 있습니다.');
    poll();
  }
  async function poll(){
    if(!active)return;
    try{
      active=await api(`${apiPrefix}/projects/${active.project_id}/vision/jobs/${active.id}`);
      render();
      if(active.status==='done'){
        const pid=active.project_id;active=null;
        if(state.data.graph.project_id===pid){
          await accept(await api(`${apiPrefix}/projects/${pid}`));
          message('부품 분석 완료. 같은 사진에서 가림 배선 후보를 추정합니다…');
          await accept(await ctx.post('/occlusion/infer',{asset_id:state.assetId}));
        }
        message('실사 분석 완료. 가림 경로는 추론 후보이며 실제 연결은 미검증입니다.');return;
      }
      if(active.status==='error'){message(active.error,true);active=null;render();return;}
      timer=setTimeout(poll,1500);
    }catch(e){active=null;message(e.message,true);render();}
  }
  function render(){
    const g=state.data.graph, photo=['photo','video'].includes(g.mode);
    const target=$('#camera-panel');target.hidden=!photo;if(!photo)return;
    const vision=state.data.integrated.vision;
    const details=renderedProject===g.project_id?[...target.querySelectorAll('details')].map(d=>d.open):null;
    renderedProject=g.project_id;
    target.innerHTML=`<div class="camera-heading"><div><strong>실사 사진·영상 분석</strong><small>Qwen3-VL 2B · 로컬 시각언어 모델 · 로봇 제어용 VLA 미연결</small></div><div><button id="camera-analyze" class="primary" ${active?'disabled':''}>현재 사진 VLM 분석</button>${g.assets.length>1?`<button id="camera-all" ${active?'disabled':''}>전체 ${Math.min(g.assets.length,6)}개 프레임 분석</button>`:''}</div></div>
    ${active?`<p role="status">${esc(active.progress)} · 분석 중에도 사진을 볼 수 있습니다. 편집하면 분석 결과 저장이 충돌할 수 있습니다.</p>`:''}
    <p class="camera-note">AI의 부품 영역·핀 라벨·연결은 오인식할 수 있습니다. 확인되지 않은 값과 핀 번호는 UNKNOWN으로 남깁니다. 영상은 선택한 프레임별로 분석하며 동일 부품을 자동 합치지 않습니다.</p>
    ${g.evidence.some(e=>e.id==='photo_source')?'<small>실사 사진: <a href="https://commons.wikimedia.org/wiki/File:Arduino_Uno_with_breadboard.jpg" target="_blank" rel="noreferrer">Thctamm · Arduino Uno with breadboard</a> · <a href="https://creativecommons.org/licenses/by-sa/3.0/" target="_blank" rel="noreferrer">CC BY-SA 3.0</a> · EXIF 제거·재인코딩</small>':''}
    ${vision?`${state.data.validation.connectivity==='BLOCKED'?`<div class="camera-unresolved" role="status"><strong>배선 미복원 · 연결 0개는 검증 완료가 아닙니다.</strong><p>부품 후보를 확인한 다음, 실제 핀 위치와 선의 양 끝점을 지정하세요. 이 단계의 결과는 조립용 회로가 아닙니다.</p></div>`:''}<details open><summary>모델 분석 결과 · r${vision.revision}${vision.revision!==g.revision?' (이후 수정 있음)':''}</summary>${vision.frames.map(f=>`<article class="camera-result"><b>${esc(f.asset_id)} · ${f.component_ids.length}개 부품 후보 · ${f.elapsed_seconds}초</b><p>${esc(f.summary)}</p>${f.pipeline?'<p>전체 탐색 → 부품별 확대 검토 → 문자 위치 대조 · AI 재검토는 실물 검증이 아닙니다.</p>':''}<p>배선 제안 ${f.wiring?.proposed??f.raw?.connections?.length??0}개 · 제외 ${f.wiring?.rejected??f.review_questions.filter(q=>q.startsWith('연결 ')).length}개 · 자동 확정 0개${f.wiring_mode==='geometry_only'?' · AI의 문장만으로 배선을 생성하지 않습니다.':''}</p>${f.rejected_components?.length?`<details><summary>보류한 부품 후보 ${f.rejected_components.length}개</summary><ul>${f.rejected_components.map(c=>`<li>${esc(c.label)}: ${esc(c.reason)}</li>`).join('')}</ul></details>`:''}<strong>추가로 확인할 부분</strong><ul>${f.review_questions.map(q=>`<li>${esc(q)}</li>`).join('')||'<li>추가 질문이 없어도 자동 검증 완료를 뜻하지 않습니다.</li>'}</ul><small>자동 확정 0개 · confidence 숫자는 부여하지 않음</small></article>`).join('')}</details>`:''}`;
    const candidates=g.components.filter(c=>g.evidence.some(e=>e.method==='vlm'&&c.label.evidence_ids.includes(e.id)));
    if(candidates.length){
      target.insertAdjacentHTML('beforeend',`<details><summary>오인식 후보 제외 · 단자 라벨 보완</summary><form id="candidate-edit"><label>부품 후보<select name="component">${candidates.map(c=>`<option value="${esc(c.id)}">${esc(c.label.value)} · ${esc(c.id)}</option>`).join('')}</select></label><label>추가할 단자 라벨<input name="terminals" placeholder="예: 3V3, GND, GPIO23"></label><label>확인 근거<input name="note" required minlength="5" placeholder="실제 사진에서 확인한 내용을 입력"></label><button type="submit">단자 라벨 추가</button><button type="button" id="reject-candidate">이 후보 제외</button><small>기존 근거와 수정 이력은 보존됩니다. 이름·값 수정은 사진의 부품을 선택하세요.</small></form></details>`);
      const edit=async(action)=>{const form=$('#candidate-edit');if(!form.reportValidity())return;const data=new FormData(form);await accept(await api(`${apiPrefix}/projects/${g.project_id}/vision/candidates/${data.get('component')}/${action}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({expected_revision:g.revision,note:data.get('note'),terminal_names:String(data.get('terminals')).split(',').map(n=>n.trim()).filter(Boolean)})}));};
      $('#candidate-edit').onsubmit=e=>{e.preventDefault();run(()=>edit('terminals'));};
      $('#reject-candidate').onclick=()=>run(()=>edit('reject'));
    }
    if(details)target.querySelectorAll('details').forEach((d,i)=>{if(i<details.length)d.open=details[i];});
    $('#camera-analyze').onclick=()=>run(()=>start(false));
    if($('#camera-all'))$('#camera-all').onclick=()=>run(()=>start(true));
  }
  return {render,start,openExample};
}
