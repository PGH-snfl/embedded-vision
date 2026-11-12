import {test} from 'node:test';
import assert from 'node:assert/strict';
import {catalogReference, catalogStatusMessage, renderCatalogReference} from '../frontend/inventory-catalog.js';

const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

test('older analyses and failed catalog loads are distinguishable', () => {
  assert.match(catalogStatusMessage(null), /이전 분석 결과/);
  assert.match(catalogStatusMessage({status:'unavailable', matches:[]}), /불러오지 못해/);
  assert.equal(renderCatalogReference(null, 'sensor', esc), '');
  assert.equal(renderCatalogReference({status:'unavailable', matches:[]}, 'sensor', esc), '');
});

test('renders candidates without suggesting observed identity or simulation guarantees', () => {
  const catalog = {status:'ready', matches:[{part_id:'sensor', candidates:[
    {id:'ldr', name:'광센서 <후보>', availability:'available'},
    {id:'board', name:'보드', availability:'unavailable'},
    {id:'other', name:'기타', availability:'unexpected'},
  ], note:'추가 검토 <필요>'}]};
  const html = renderCatalogReference(catalog, 'sensor', esc);
  assert.match(html, /사진 속 부품과의 일치 미확인/);
  assert.match(html, /목록에서 배치 가능 · 동작 확인 필요/);
  assert.match(html, /보드 · 추가 불가/);
  assert.match(html, /기타 · 지원 여부 미확인/);
  assert.match(html, /광센서 &lt;후보&gt;/);
  assert.match(html, /추가 검토 &lt;필요&gt;/);
  assert.doesNotMatch(html, /<후보>|<필요>/);
  assert.match(renderCatalogReference(catalog, 'other', esc), /후보를 확인하지 못했습니다/);
  assert.equal(catalogReference(catalog, 'sensor').candidates.length, 3);
});
