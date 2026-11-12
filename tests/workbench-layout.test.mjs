import {test} from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';
import {fullBreadboardProject} from '../frontend/workbench-layout.js';
const fixture=JSON.parse(fs.readFileSync(new URL('./fixtures/mini-workbench.json',import.meta.url),'utf8'));
test('enlarges freshly generated mini layouts while preserving code and wire identities',()=>{
 const before=JSON.stringify(fixture),out=fullBreadboardProject(fixture);
 assert.equal(out.components.find(c=>c.id==='BB1').metadataId,'breadboard');
 assert.equal(out.wires.find(w=>w.id==='J1').end.pinName,'23t.a');
 assert.equal(out.wires.find(w=>w.id==='J1').end.x,400+6+14.56+22*9.6);
 assert.equal(out.wires.find(w=>w.id==='J1').end.y,115+6+48);
 assert.deepEqual(out.fileGroups,fixture.fileGroups);assert.equal(JSON.stringify(fixture),before);
 assert.deepEqual(out.wires.map(w=>[w.id,w.color,w.bb]),fixture.wires.map(w=>[w.id,w.color,w.bb]));
 assert.equal(out.embeddedVision.assembly.steps[0].to,'BB1.23t.a');
 assert.equal(fullBreadboardProject(out),out);
});
test('does not reinterpret arbitrary projects or malformed breadboard hole names',()=>{
 const ordinary={...fixture,embeddedVision:{}};assert.equal(fullBreadboardProject(ordinary),ordinary);
 const bad=structuredClone(fixture);bad.wires[0].end.pinName='hidden';assert.equal(fullBreadboardProject(bad),bad);
});
