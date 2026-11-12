import {apiPrefix,workspaceId} from './saas.js';
import {renderFunctionIntent,prototypeEditorUrl} from './function-intent.js?v=photo-autorun-3';
import {initWorkbench} from './workbench.js?v=photo-autorun-1';
import {initEmulator} from './emulator.js?v=breadboard-3d-1';
import {renderSimulation} from './simulation.js?v=breadboard-3d-1';
import {designPreview,selectHypothesisPreview,hypothesisPreviewCopy,wrapHypothesisPreviews} from './design-preview.js?v=simulation-behavior-2';
import {catalogStatusMessage, renderCatalogReference} from './inventory-catalog.js';
import {renderVirtualSystem} from './virtual-system.js?v=photo-autorun-1';
import {renderPhysicalGuide} from './physical-guide.js?v=pi-hardware-3';
import {createAutoWorkbench} from './auto-workbench.js?v=functional-build-1';
import {buildDatasheet,completionBody} from './datasheet.js?v=multiboard-1';
import {renderEnclosureAnalysis} from './enclosure-analysis.js?v=multiboard-1';
import {renderPhotoAppearance} from './photo-appearance.js?v=photo-appearance-1';
// Observation and design remain separate projects; an explicit review joins them.
export function initInventory(ctx){
  const {state,api,post,run,accept,esc,message}=ctx;
  const simulations=new Map();
  const autoWorkbench=createAutoWorkbench({host:document.querySelector('#auto-simulation'),api,esc});
  let recipes=null,proposalKey='',proposalData=null,proposalError='';
  async function load(){recipes=await api('/api/design/recipes');}
  function render(host,plan,stale){
    const inv=plan.inventory;
    const key=`${state.data.graph.project_id}:${plan.id}:${state.data.graph.revision}:${plan.analysis_complete===false?'components':'complete'}`;
    if(key!==proposalKey){
      proposalKey=key;proposalData=null;proposalError='';
      if(!stale&&plan.analysis_complete!==false)api(`${apiPrefix}/projects/${state.data.graph.project_id}/inventory/${plan.id}/proposals`).then(data=>{
        if(proposalKey!==key||state.data.graph.project_id!==key.split(':')[0])return;
        proposalData=data;render(host,plan,false);ctx.renderVisuals();
      }).catch(e=>{if(proposalKey===key){proposalError=e.message;render(host,plan,stale);}});
    }
    state.designProposal=!stale&&proposalData?{project:state.data.graph.project_id,planId:plan.id,revision:plan.revision,data:proposalData}:null;
    void autoWorkbench.update({data:proposalData,project:state.data.graph.project_id,plan:plan.id,
      revision:state.data.graph.revision,stale,endpoint:`${apiPrefix}/projects/${state.data.graph.project_id}/inventory/${plan.id}`});
    const proposals=proposalData?.proposals||[];
    function thumbnail(p){
      const region=p.regions[0],asset=state.data.graph.assets.find(a=>a.id===region.asset_id);if(!asset)return '';
      return `<svg class="part-crop" viewBox="${region.x0*asset.width} ${region.y0*asset.height} ${(region.x1-region.x0)*asset.width} ${(region.y1-region.y0)*asset.height}" role="img" aria-label="${esc(p.name)} 관측 영역"><image href="${apiPrefix}/projects/${state.data.graph.project_id}/assets/${esc(asset.id)}" width="${asset.width}" height="${asset.height}"/></svg>`;
    }
    document.querySelector('#parts-stage').innerHTML=`<div class="panel inventory-stage"><div class="panel-heading"><h2>사진에서 먼저 확인한 구성품</h2><span class="tag">${inv.parts.length}종 · 관측 후보</span></div><div class="assistant-body">
    <p class="micro">${esc(catalogStatusMessage(plan.simulator_catalog))}</p><div class="inventory-grid">${inv.parts.map(p=>`<article class="part-card">${thumbnail(p)}<div class="part-card-title"><b>${esc(p.name)}</b><span class="part-quantity">× ${p.quantity}</span></div><span class="part-status ${p.status==='UNKNOWN'?'unknown':''}">${p.status==='UNKNOWN'?'미확인':'추정 · 실물 확인 필요'}</span><details class="compact-details"><summary>모델·인식 근거·목록 후보</summary><p><b>모델 후보</b> ${p.model_candidates.map(esc).join(' / ')||'미확인'}</p><p><b>읽힌 표식</b> ${p.markings.map(esc).join(', ')||'없음'}</p><p>${esc(p.evidence)}</p><p><b>확인할 사항</b> ${p.checks_needed.map(esc).join(' / ')||'실물 모델·전압·핀 라벨 대조'}</p>${renderCatalogReference(plan.simulator_catalog,p.id,esc)}<small>${esc(p.id)} · ${esc(p.status)} · 관측 프레임 ${[...new Set(p.regions.map(r=>r.asset_id))].map(esc).join(', ')}</small></details></article>`).join('')||'<p>식별한 부품이 없습니다.</p>'}</div>
    <details class="compact-details inventory-notes"><summary>분석 요약·미확인 정보 ${inv.unknowns.length}건</summary><p>${esc(inv.summary)}</p><p>부품은 식별 후보입니다. 모델·정격·핀 라벨은 실물과 대조하세요.</p><ul>${inv.unknowns.map(x=>`<li>${esc(x)}</li>`).join('')}</ul><p>모델의 기능 제안: ${esc(inv.suggested_function)}</p></details>
    </div></div>`;
    host.innerHTML=`<div class="panel-heading"><h2>구성품을 바탕으로 기능·보완 부품 판단</h2></div><div class="assistant-body"><div id="system-model"></div><div id="function-intent"></div><div id="component-completion"></div><div id="robot-circuit"></div><div id="physical-guide"></div><div id="hypothesis-preview"></div>${!proposalData?`<p role="status">${proposalError?esc(proposalError):plan.analysis_complete===false?'구성품 목록을 저장했습니다. 이 목록을 근거로 기능·보완 부품을 분석하고 있습니다.':'데이터시트의 구성품과 보완 사항으로 회로를 구성하고 있습니다…'}</p>`:''}
    ${proposalData&&!proposals.length&&!proposalData.robot_design&&!proposalData.prototype_design?'<p class="micro">기능이 확인되면 같은 동작을 수행하는 회로만 제안합니다.</p>':''}
    <details class="compact-details"><summary>설계 기준·지원 범위</summary><p>${esc(proposalData?.notice||'')}</p><p>현재는 UNO LED 점등·점멸·밝기 / UNO 저항 분압 / UNO 병렬 LCD / UNO 버튼·조도 센서 / ESP32 LED·버튼 회로 규칙으로 자동 구성합니다. 임의의 모든 부품 조합을 설계하는 기능은 아닙니다.</p>${(proposalData?.unavailable||[]).map(r=>`<p>${esc(r.name)}: ${esc(r.reason)}</p>`).join('')}</details>
    ${stale?'<p class="errors">입력 정보가 변경되었습니다. 위에서 부품 분석을 다시 실행하세요.</p>':''}
    <form id="inventory-design" ${!proposals.length?'hidden':''}><label>새 회로 구성<select id="design-recipe" required><option value="">만들 회로를 선택하세요</option>${proposals.map(r=>`<option value="${r.recipe}" ${r.recipe===proposalData.recommended?'selected':''}>${r.recipe===proposalData.recommended?'추천 · ':''}${esc(r.name)}</option>`).join('')}</select></label><div id="design-proposal-preview"></div><details class="compact-details design-assignment"><summary>사용 부품·사양 변경</summary><div id="design-roles"></div></details>
    <details id="parts-verification" class="compact-details"><summary>실물 제작·KiCad용 확인 사항</summary><label><input name="function_confirmed" type="checkbox" required ${proposalData?.function?.status==='USER_DEFINED'?'checked':''}> 위 입력·출력 동작이 재현하려는 기능과 일치합니다.</label><label><input name="parts_verified" type="checkbox" required> 선택한 실물 부품의 모델·저항값·전압·핀 라벨이 설계 사양과 맞는지 확인했습니다.</label>
    <label>확인 근거<textarea name="verification_note" required minlength="5" maxlength="1000" placeholder="예: UNO R3 표식과 LCD의 병렬 핀 라벨, 5V 정격을 데이터시트와 대조함"></textarea></label>
    <label><input name="accept_added_parts" type="checkbox"> 추가 부품의 규격과 수량을 확인하고 준비하겠습니다.</label></details>
    <label id="lcd-message-label">LCD에 표시할 새 문구<input name="message" value="Hello circuit!" maxlength="16" pattern="[A-Za-z0-9 .,!?_\\-]+" required></label>
    <button class="primary" ${stale||!recipes||!proposals.length?'disabled':''}>실물 검토 후 KiCad 프로젝트 생성 →</button></form>
    </div>`;
    const comparison=completionBody(buildDatasheet(state.data.graph,plan,state.data.integrated?.catalog||{},proposalData));
    const photoHost=document.createElement('div');host.querySelector('#system-model').before(photoHost);
    renderPhotoAppearance(photoHost,{scene:plan.photo_structure,api,endpoint:`${apiPrefix}/projects/${state.data.graph.project_id}/inventory/${plan.id}`,esc,stale});
    host.querySelector('#component-completion').innerHTML=proposalData?.functional_design?`<details class="compact-details"><summary>사진 분석과 선정 부품 비교</summary>${comparison}</details>`:comparison;
    const enclosureHost=document.createElement('div');host.querySelector('#component-completion').before(enclosureHost);
    renderEnclosureAnalysis(enclosureHost,{analysis:proposalData?.enclosure_analysis||plan.enclosure_analysis,implementation:proposalData?.functional_design,functionVersion:proposalData?.function_version,api,endpoint:`${apiPrefix}/projects/${state.data.graph.project_id}/inventory/${plan.id}`,esc,stale});
    renderVirtualSystem(host.querySelector('#system-model'),{data:proposalData,api,endpoint:`${apiPrefix}/projects/${state.data.graph.project_id}/inventory/${plan.id}`,esc,stale});
    if(proposalData){
      const endpoint=`${apiPrefix}/projects/${state.data.graph.project_id}/inventory/${plan.id}`;
      if(proposalData.prototype_design&&!stale){
        const url=prototypeEditorUrl(endpoint,proposalData.function_version);
        host.querySelector('#robot-circuit').innerHTML=`<section class="workbench-launch"><div class="workbench-lead"><div><span class="section-kicker">새 회로 · 코드 · 시뮬레이션</span><h3>선택한 기능의 편집기</h3><p>회로와 코드를 확인하고 입력을 바꿔 동작을 시험하세요.</p></div><a class="button primary" href="${esc(url)}" target="_blank" rel="noopener noreferrer">회로·시뮬레이터 열기 ↗</a></div></section>`;
      }
      if(!proposalData.robot_design&&!proposalData.prototype_design)renderPhysicalGuide(host.querySelector('#physical-guide'),{data:proposalData,endpoint,esc,stale});
      if(proposalData.robot_design&&!stale){
        const params=new URLSearchParams({project:state.data.graph.project_id,plan:plan.id,function_version:proposalData.function_version});
        const editor=(workspaceId?`/w/${workspaceId}/rover-editor.html`:'/rover-editor.html')+'?'+params;
        host.querySelector('#robot-circuit').innerHTML=`<section class="workbench-launch"><div class="workbench-lead"><div><span class="section-kicker">회로 · 시뮬레이션</span><h3>로봇 회로 편집</h3><p>편집기를 넓은 새 탭에서 열고, 편집기에서 운동 미리보기를 실행하세요.</p></div><a class="button primary" href="${esc(editor)}" target="_blank" rel="noopener noreferrer">회로 편집기 열기 ↗</a></div></section>`;
      }
    }

    renderFunctionIntent(host.querySelector('#function-intent'),{data:proposalData,api,endpoint:`${apiPrefix}/projects/${state.data.graph.project_id}/inventory/${plan.id}`,revision:plan.revision,esc,onChange:data=>{proposalData=data;render(host,plan,stale);ctx.renderVisuals();}});
    const hypothesisPreviews=proposalData?.hypothesis_previews||[],previewHost=host.querySelector('#hypothesis-preview');
    if(proposalData?.function?.status==='UNKNOWN'&&hypothesisPreviews.length&&!stale){
      const choice=selectHypothesisPreview(hypothesisPreviews,proposalData.recommended_hypothesis_id);
      const initialCopy=hypothesisPreviewCopy(choice.isRecommended);
      const content=`<div class="preview-heading"><h3 data-preview-heading>${initialCopy.heading}</h3><span class="tag">추정 · 원본 동작 미검증</span></div><p><span data-preview-description>${initialCopy.description}</span> 원본과 같은 동작인지는 아직 확인되지 않았습니다.</p><label>미리 볼 기능<select data-hypothesis-preview>${hypothesisPreviews.map((p,i)=>`<option value="${i}" ${i===choice.index?'selected':''}>${esc(p.title)}</option>`).join('')}</select></label><div data-hypothesis-circuit></div><p class="micro">원하는 기능이 맞으면 위 기능 후보를 선택해 시뮬레이터를 여세요. 추정만으로 실물 부품의 정격을 확정하지 않습니다.</p>`;
      previewHost.innerHTML=wrapHypothesisPreviews(content,choice.isRecommended);
      const drawPreview=()=>{const index=Number(previewHost.querySelector('[data-hypothesis-preview]').value);const item=hypothesisPreviews[index],copy=hypothesisPreviewCopy(item.candidate_id===proposalData.recommended_hypothesis_id);previewHost.querySelector('[data-preview-heading]').textContent=copy.heading;previewHost.querySelector('[data-preview-description]').textContent=copy.description;previewHost.querySelector('[data-hypothesis-circuit]').innerHTML=designPreview(item.proposal,esc,inv.parts);if(state.designProposal)state.designProposal.selectedCandidateId=choice.isRecommended||previewHost.querySelector('[data-other-previews]')?.open?item.candidate_id:null;};
      const otherDetails=previewHost.querySelector('[data-other-previews]');if(otherDetails)otherDetails.ontoggle=drawPreview;
      previewHost.querySelector('[data-hypothesis-preview]').onchange=drawPreview;drawPreview();
    }
    const select=host.querySelector('#design-recipe');
    function roles(){
      const suggestion=proposals.find(p=>p.recipe===select.value);if(state.designProposal)state.designProposal.selectedRecipe=suggestion?.recipe||null;host.querySelector('#design-proposal-preview').innerHTML=suggestion?designPreview(suggestion,esc,inv.parts):'';
      if(suggestion?.simulator_supported){
        const workbenchHost=document.createElement('div');host.querySelector('#design-proposal-preview').prepend(workbenchHost);
        initWorkbench(workbenchHost,{api,endpoint:`${apiPrefix}/projects/${state.data.graph.project_id}/inventory/${plan.id}`,recipe:suggestion.recipe,functionVersion:proposalData.function_version});
      }
      if(suggestion?.recipe==='arduino_voltage_divider'){
        const checks=document.createElement('details');checks.className='compact-details design-tests';checks.innerHTML='<summary>추가 동작 시험 <span>전압 계산·가상 MCU 실행</span></summary><div data-tests></div>';host.querySelector('#design-proposal-preview').append(checks);
        const simHost=document.createElement('div');checks.querySelector('[data-tests]').append(simHost);
        const simKey=key+':'+suggestion.recipe,base=`${apiPrefix}/projects/${state.data.graph.project_id}/inventory/${plan.id}`;
        const onRun=async analysis=>{const r=await api(base+'/simulate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({expected_revision:plan.revision,recipe:suggestion.recipe,analysis})});simulations.set(simKey,r);return r;};
        const emulatorHost=document.createElement('div');checks.querySelector('[data-tests]').append(emulatorHost);initEmulator(emulatorHost,{api,endpoint:base+'/emulator',revision:plan.revision,esc});
        const draw=result=>renderSimulation(simHost,{result,onRun,esc,proposal:true});draw(simulations.get(simKey));
        if(!simulations.has(simKey))api(base+'/simulation').then(r=>{if(simHost.isConnected&&r.simulation&&!simulations.has(simKey)){simulations.set(simKey,r.simulation);draw(r.simulation);}}).catch(e=>{if(simHost.isConnected)simHost.querySelector('[data-sim-error]').textContent='이전 계산을 불러오지 못했습니다: '+e.message;});
      }
      const r=recipes?.[select.value];if(!r){host.querySelector('#design-roles').innerHTML='<p>기능에 맞는 회로를 선택하세요.</p>';host.querySelector('#lcd-message-label').hidden=true;return;}
      host.querySelector('#lcd-message-label').hidden=true;
      host.querySelector('#design-roles').innerHTML=`${Object.entries(r.slots).map(([ref,slot])=>{
        // A photographed two-pin LDR must not be selected as a three-pin
        // module. The backend-approved sensor assignment is the only option.
        const parts=inv.parts.filter(p=>p.kind===slot.kind&&p.status!=='UNKNOWN'&&(!['board','sensor'].includes(slot.kind)||p.id===suggestion?.assignments[ref])),required=r.required_observed.includes(ref);
        return `<article class="assembly-step"><label>${esc(ref)} · ${esc(slot.name)} ${esc(slot.value||'')}<select data-design-slot="${esc(ref)}" required><option value="">선택하세요</option>${parts.map(p=>`<option value="${esc(p.id)}" ${suggestion?.assignments[ref]===p.id?'selected':''}>입력 부품 ${esc(p.id)} · ${esc(p.name)} (호환성 확인 필요)</option>`).join('')}${required?'':`<option value="__added__" ${suggestion?.assignments[ref]===null?'selected':''}>새로 준비할 추가 부품</option>`}</select></label><details class="compact-details"><summary>부품 사양·자료</summary><p>${esc(slot.note)}</p><a href="${esc(slot.source)}" target="_blank" rel="noopener noreferrer">설계 사양·핀 확인 자료 ↗</a></details></article>`;
      }).join('')}<p>브레드보드와 점퍼선은 조립용 준비물입니다. 선택하지 않은 관측 부품은 새 회로에 넣지 않습니다.</p>`;
    }
    if(recipes){roles();select.onchange=roles;}
    host.querySelector('#inventory-design').addEventListener('invalid',e=>{for(let d=e.target.closest('details');d;d=d.parentElement.closest('details'))d.open=true;},true);
    host.querySelector('#inventory-design').onsubmit=e=>{e.preventDefault();run(async()=>{
      const f=new FormData(e.target),assignments={};host.querySelectorAll('[data-design-slot]').forEach(s=>assignments[s.dataset.designSlot]=s.value==='__added__'?null:s.value);
      const result=await post(`/inventory/${plan.id}/design`,{recipe:select.value,function_version:proposalData.function_version,function_confirmed:f.has('function_confirmed'),assignments,parts_verified:f.has('parts_verified'),accept_added_parts:f.has('accept_added_parts'),verification_note:f.get('verification_note'),message:f.get('message')});
      state.assetId='image';state.selected=null;await accept(await api(`${apiPrefix}/projects/${result.project_id}`));
      document.querySelector('#user-step-4').scrollIntoView({block:'start'});
      message('새 회로·코드를 만들었습니다. 원본 입력은 보존했습니다. 아래 KiCad MCP 실행으로 회로도 연결과 ERC를 검사하세요.');
    });};
  }
  return {load,render,clearAuto:autoWorkbench.clear};
}
