import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';

globalThis.location={pathname:'/'};
const {USER_STEP_IDS}=await import('../frontend/io.js');
test('components-first display order preserves stable section IDs',()=>{
 const html=fs.readFileSync(new URL('../frontend/index.html',import.meta.url),'utf8');
 const ordered=[...html.matchAll(/<section id="user-step-(\d)"/g)].map(m=>m[1]);
 assert.deepEqual(ordered,['1','2','3','4']);
 assert.deepEqual(USER_STEP_IDS,ordered);
 assert.match(html,/<section id="user-step-2"[^]*?<span class="user-step-number">2<\/span>[^]*?구성품/);
 assert.match(html,/<section id="user-step-3"[^]*?<span class="user-step-number">3<\/span>[^]*?기능 추론·부품 보완·데이터시트/);
 assert.ok(html.indexOf('id="auto-analysis-panel"')<html.indexOf('id="assistant-panel"'));
});
