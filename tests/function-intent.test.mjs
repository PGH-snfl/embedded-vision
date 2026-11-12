import {test} from 'node:test';
import assert from 'node:assert/strict';

globalThis.location = {pathname:'/'};
const {candidateCanSimulate,offeredCandidateCanSimulate,recommendedCandidate,renderRecommendation} = await import('../frontend/function-intent.js');
const esc = v => String(v ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

test('a text LCD can open the simulator only after its message is known', () => {
  assert.equal(candidateCanSimulate({kind:'lcd_text', display_text:'Javalab.org'}), true);
  assert.equal(candidateCanSimulate({kind:'lcd_text', display_text:null}), false);
  assert.equal(candidateCanSimulate({kind:'lcd_text', display_text:''}), false);
  assert.equal(candidateCanSimulate({kind:'lcd_text', display_text:'안녕하세요'}), false);
  assert.equal(candidateCanSimulate({kind:'lcd_text', display_text:'01234567890123456'}), false);
});

test('recommended visual follows server ranking, not simulator support', () => {
  const a={id:'sensor',title:'온도 감지 <후보>',kind:'unsupported',plausibility:'medium',rationale:'추정',input_behavior:'온도 변화',output_behavior:'온도 표시',evidence:[],assumptions:[]};
  const b={id:'led',title:'LED',kind:'led_blink',plausibility:'low',input_behavior:'전원 켜기',output_behavior:'LED 점멸'};
  const data={function:{status:'UNKNOWN'},function_hypotheses:[b,a],recommended_hypothesis_id:'sensor',hypothesis_previews:[{candidate_id:'led',proposal:{simulator_supported:true}}]};
  assert.equal(recommendedCandidate(data),a);
  const html=renderRecommendation(data,esc);
  assert.match(html,/온도 감지 &lt;후보&gt;/);
  assert.match(html,/1 · 입력/);assert.match(html,/2 · 처리/);assert.match(html,/3 · 출력/);
  assert.match(html,/현재 바로 실행할 수 없습니다/);
  assert.doesNotMatch(html,/시뮬레이션하기/);
  assert.match(html,/수치 확률이나 원본 동작의 확인 결과는 아닙니다/);
});

test('runnable recommendation opens only its own supported candidate', () => {
  const a={id:'blink',title:'깜빡임',kind:'led_blink',plausibility:'medium',rationale:'LED',input_behavior:'전원',output_behavior:'깜빡임'};
  const data={function:{status:'UNKNOWN'},function_hypotheses:[a],recommended_hypothesis_id:'blink',hypothesis_previews:[{candidate_id:'blink',proposal:{simulator_supported:true}}]};
  assert.match(renderRecommendation(data,esc),/data-candidate="blink"/);
  assert.match(renderRecommendation(data,esc),/이 기능으로 시뮬레이션/);
});

test('missing LCD text is explained and unknown behaviors are not invented', () => {
  const candidate={id:'lcd',title:'LCD',kind:'lcd_text',display_text:'안녕',input_behavior:'전원',output_behavior:'문자 표시'};
  assert.match(renderRecommendation({function:{status:'UNKNOWN'},function_hypotheses:[candidate],recommended_hypothesis_id:'lcd',hypothesis_previews:[]},esc),/LCD 표시 문구 확인이 필요합니다/);
  assert.equal(renderRecommendation({function:{status:'UNKNOWN'},function_hypotheses:[],recommended_hypothesis_id:null},esc),'');
});

test('older inferred plans can open an already supported proposal', () => {
  const intent={status:'INFERRED',kind:'led_blink',summary:'깜빡임',input_behavior:'전원',output_behavior:'점멸'};
  const data={function:intent,function_hypotheses:[],recommended:'arduino_led_blink',proposals:[{recipe:'arduino_led_blink',simulator_supported:true}]};
  assert.match(renderRecommendation(data,esc),/data-open-inferred/);
});

test('unsupported behavior is never presented as a runnable recipe', () => {
  assert.equal(candidateCanSimulate({kind:'unsupported'}), false);
  assert.equal(candidateCanSimulate({kind:'led_brightness'}), true);
});

test('a simulator is offered only if the observed parts match a supported recipe', () => {
  const candidate={id:'display_message',kind:'lcd_text',display_text:'Javalab.org'};
  assert.equal(offeredCandidateCanSimulate({hypothesis_previews:[]},candidate),false);
  assert.equal(offeredCandidateCanSimulate({hypothesis_previews:[{candidate_id:candidate.id,proposal:{simulator_supported:true}}]},candidate),true);
  assert.equal(offeredCandidateCanSimulate({hypothesis_previews:[{candidate_id:candidate.id,proposal:{simulator_supported:false}}]},candidate),false);
});

test('the estimated function and actual proposed simulation behavior are distinct', () => {
  const candidate={id:'light',title:'조도에 따른 제어',kind:'light_led',input_behavior:'빛',output_behavior:'밝기에 따라 LED가 변하나 방향은 모름'};
  const data={function:{status:'UNKNOWN'},function_hypotheses:[candidate],recommended_hypothesis_id:'light',hypothesis_previews:[{candidate_id:'light',proposal:{simulator_supported:true,simulation_behavior:'어두우면 LED를 켜고 밝으면 끕니다. <기본값>'}}]};
  const html=renderRecommendation(data,esc);
  assert.match(html,/방향은 모름/);
  assert.match(html,/새 시뮬레이션에서 실행할 동작/);
  assert.match(html,/어두우면 LED를 켜고 밝으면 끕니다\. &lt;기본값&gt;/);
  assert.match(html,/새 설계의 기본값/);
  assert.doesNotMatch(html,/<기본값>/);
});

test('different LCD text and disabled own preview cannot inherit an existing target', () => {
  const candidate={id:'lcd-a',kind:'lcd_text',display_text:'A'};
  const data={function:{kind:'lcd_text',display_text:'B'},recommended:'arduino_lcd',proposals:[{recipe:'arduino_lcd',simulator_supported:true}]};
  assert.equal(offeredCandidateCanSimulate(data,candidate),false);
  assert.equal(offeredCandidateCanSimulate({...data,function:{kind:'lcd_text',display_text:'A'},hypothesis_previews:[{candidate_id:'lcd-a',proposal:{simulator_supported:false}}]},candidate),false);
});
