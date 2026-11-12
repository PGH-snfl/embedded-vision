import {test} from 'node:test';
import assert from 'node:assert/strict';
import {selectHypothesisPreview,hypothesisPreviewCopy,wrapHypothesisPreviews} from '../frontend/design-preview.js';

test('recommendation selects its own preview even if other previews appear first',()=>{
  const previews=[{candidate_id:'led'},{candidate_id:'lcd'}];
  assert.deepEqual(selectHypothesisPreview(previews,'lcd'),{index:1,isRecommended:true});
  assert.equal(hypothesisPreviewCopy(true).heading,'추천 기능 회로 미리보기');
  assert.match(wrapHypothesisPreviews('<p>추천 회로</p>',true),/^<section/);
});

test('unsupported recommendation never presents another function as its own',()=>{
  const previews=[{candidate_id:'led'}];
  assert.deepEqual(selectHypothesisPreview(previews,'parking'),{index:0,isRecommended:false});
  assert.equal(hypothesisPreviewCopy(false).heading,'다른 기능의 회로 미리보기');
  const html=wrapHypothesisPreviews('<p>LED 회로</p>',false);
  assert.match(html,/^<details /);
  assert.match(html,/<summary>다른 기능의 회로 미리보기<\/summary>/);
  assert.doesNotMatch(html,/<details[^>]*\sopen(?:\s|>)/);
});
