import {test} from 'node:test';
import assert from 'node:assert/strict';
import {designRequirements,designPreview} from '../frontend/design-preview.js';

const observed=[{id:'board1',name:'UNO 계열',status:'INFERRED'},
 {id:'sensor1',name:'2핀 광저항 후보',status:'UNKNOWN'}];
const proposal={recipe:'arduino_light_led',behavior:'어두울 때 LED를 켭니다.',
 specifications:{U1:{name:'Arduino UNO',value:null},S1:{name:'3핀 조도 모듈',value:null}},
 assignments:{U1:'board1',S1:null},added_parts:['S1'],
 replacements:[{reference:'S1',candidate_ids:['sensor1'],reason:'사진 후보와 다릅니다. 3핀 모듈을 준비하세요.'}],
 remaining_parts:[],connections:[{from:'U1.A0',to:'S1.AO'}],
 firmware:{source:'analogRead(A0)',execution:'가상 보드'}};
const esc=v=>String(v??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));

test('new requirements distinguish observed candidate, replacement and unknowns',()=>{
 const rows=designRequirements(proposal,observed);
 assert.equal(rows[0].basis,'candidate');assert.equal(rows[0].observedId,'board1');
 assert.equal(rows[1].basis,'replacement');assert.equal(rows[1].observedId,null);
 assert.deepEqual(rows[1].candidates,['2핀 광저항 후보']);
 const html=designPreview(proposal,esc,observed);
 assert.match(html,/사진 후보: UNO 계열 · 실물 모델과 사양 대조 필요/);
 assert.match(html,/새로 준비·대체 검토 · 사진 후보: 2핀 광저항 후보/);
 assert.match(html,/3핀 모듈을 준비하세요/);
 assert.doesNotMatch(html,/사진 후보: 3핀 조도 모듈/);
});

test('a missing role is clearly marked as a new required part',()=>{
 const p={...proposal,replacements:[]};
 assert.equal(designRequirements(p,observed)[1].basis,'added');
 assert.match(designPreview(p,esc,observed),/사진에서 사용 가능한 부품을 확인하지 못해 새로 준비/);
});
