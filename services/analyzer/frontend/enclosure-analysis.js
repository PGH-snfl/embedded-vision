import {workbenchUrl} from './workbench.js?v=photo-autorun-1';
export function renderEnclosureAnalysis(host,{analysis,implementation,api,endpoint,esc,stale=false,functionVersion}){
 if(!host)return;
 if(stale||(!analysis?.enclosures?.length&&!implementation)){host.replaceChildren();return;}
 const cases=analysis?.enclosures||[],roles={controller:'제어부',power:'전원부',driver:'구동부',sensor:'센서부',interface:'통신·인터페이스',protection:'보호부',passive:'수동소자',connector:'연결부',mechanical:'기구부'};
 const row=(node,nodes,seen=new Set())=>{
  if(seen.has(node.id))return '';const next=new Set(seen);next.add(node.id);
  return `<li><strong>${esc(node.name)}</strong> <span class="part-status">${esc(roles[node.role]||node.role)} · 내부 추정</span><p>${esc(node.purpose)}</p><details class="compact-details"><summary>부품 후보·추론 근거</summary><p>${(node.candidate_parts||[]).map(esc).join(' / ')||'정확한 모델 미확인'}</p><p>${esc(node.rationale)}</p><p>다른 가능성: ${(node.alternatives||[]).map(esc).join(' / ')||'추가 확인 필요'}</p><p>확신도: ${esc(({low:'낮음',medium:'중간',high:'높음'})[node.confidence]||'미확인')} · 실제 존재 여부 미확인</p></details>${nodes.some(n=>n.parent_id===node.id)?`<ul>${nodes.filter(n=>n.parent_id===node.id).map(n=>row(n,nodes,next)).join('')}</ul>`:''}</li>`;
 };
 const runtime=implementation?.runtime;
 const boardStatus=runtime?`<p><strong>선정 보드: ${esc(runtime.board_kind)} · ${esc(runtime.language)}</strong></p><details class="compact-details"><summary>보드 실행 상태 · ${runtime.availability==='local'?'로컬 실행 지원':'전용 실행 서비스 필요'}</summary><p>${esc(runtime.notice)}</p><p>회로·코드 생성과 실제 실행 시험은 별개입니다. 실행 검사 결과는 편집기에 표시합니다.</p></details>`:'';
 const implementationBody=implementation?`<p>${esc(implementation.behavior)}</p>${boardStatus}<p><strong>부품 ${implementation.parts.length}개 · 배선 ${implementation.connections.length}개 · 실행 코드 포함</strong></p><details class="compact-details"><summary>선정 부품·값·구조 확인</summary><ul>${implementation.parts.map(p=>`<li><strong>${esc(p.id)} · ${esc(p.name)}</strong> × ${esc(p.quantity)}${Object.keys(p.parameters||{}).length?` · ${esc(Object.entries(p.parameters).map(([k,v])=>`${k}=${v}`).join(', '))}`:''}<p>${esc(p.purpose)} · ${esc(p.selection_reason)}</p></li>`).join('')}</ul>${(implementation.structures||[]).map(s=>`<p>${esc(s.label)} · ${esc(s.size_mm?.join(' × '))} mm · ${esc(s.purpose)}</p>`).join('')}<p>${(implementation.design_choices||[]).map(esc).join(' / ')}</p></details>${implementation.not_implemented?.length?`<p>이번 실행에 포함하지 않은 기능: ${implementation.not_implemented.map(esc).join(' / ')}</p>`:''}`:`<p>${esc(analysis?.summary)}</p>`;
 const observations=cases.map(c=>`<details class="compact-details"><summary>사진 분석 비교 · ${esc(c.name)}</summary><p>${esc(c.rationale)}</p><ul class="enclosure-module-tree">${c.modules.filter(m=>!m.parent_id).map(m=>row(m,c.modules)).join('')}</ul><p>가정: ${c.assumptions.map(esc).join(' / ')}</p><p>원본 확인 항목: ${c.unknowns.map(esc).join(' / ')}</p></details>`).join('');
 host.innerHTML=`<section class="enclosure-analysis"><div class="panel-heading"><div><span class="section-kicker">${implementation?'부품·배선·코드 선정 완료':'외장 안의 구성 분석'}</span><h3>${implementation?'기능 구현 설계':'가상 분해 분석'}</h3></div><button type="button" class="primary" data-enclosure-open>${implementation?'완성 설계·시뮬레이터 열기 ↗':'내부 추정·3D 분해도 ↗'}</button></div>${implementationBody}${observations}<p role="status" data-enclosure-status></p></section>`;
 const status=host.querySelector('[data-enclosure-status]');
 host.querySelector('[data-enclosure-open]').onclick=async()=>{
  const win=window.open('about:blank','_blank');if(win)win.opener=null;
  try{const result=await api(implementation?endpoint+'/functional-workbench'+(functionVersion?'?'+new URLSearchParams({function_version:functionVersion}):''):endpoint+'/enclosure-study');
   const project=implementation?result:result.workbench;if(!project||(!implementation&&!result.available))throw Error('저장된 내부 추론이 없습니다. 사진 분석을 다시 실행하세요.');
   const url=new URL(workbenchUrl(project));if(implementation)url.searchParams.set('autorun','1');if(win)win.location=url.href;else{const a=document.createElement('a');a.href=url.href;a.target='_blank';a.rel='noopener';a.textContent='설계 편집기 열기';status.replaceChildren(a);return;}
   status.textContent=implementation?'선정한 부품·배선·코드와 시뮬레이터를 열었습니다.':'새 탭에서 외장·내부 추정·분해 보기를 전환할 수 있습니다.';
  }catch(e){if(win)win.close();status.textContent=e.message;}
 };
}
