import { test } from 'node:test';
import assert from 'node:assert/strict';

globalThis.location = { pathname: '/', origin: 'http://127.0.0.1:8897' };
const { workbenchUrl } = await import('../frontend/workbench.js');

test('the exported simulator project retains the current analysis origin without mutating input', () => {
  const project = { format: 'velxio-project', embeddedVision: { recipe: 'arduino_light_led' }, components: [], wires: [] };
  const href = workbenchUrl(project);
  const params = new URLSearchParams(new URL(href).hash.slice(1));
  const payload = JSON.parse(Buffer.from(params.get('project'), 'base64').toString('utf8'));
  assert.equal(payload.embeddedVision.analysis_origin, 'http://127.0.0.1:8897');
  assert.equal(payload.embeddedVision.recipe, 'arduino_light_led');
  assert.equal(project.embeddedVision.analysis_origin, undefined);
});

test('a configured local editor port is retained in the editor link', () => {
  globalThis.EMBEDDED_VISION_EDITOR_PORT=18968;
  try {
    assert.equal(new URL(workbenchUrl({components:[],wires:[]})).port,'18968');
  } finally {delete globalThis.EMBEDDED_VISION_EDITOR_PORT;}
});
