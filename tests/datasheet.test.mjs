import {test} from 'node:test';
import assert from 'node:assert/strict';
import {buildDatasheet,datasheetBody,datasheetDocument,safeSource} from '../frontend/datasheet.js';
const graph={project_id:'a'.repeat(32),title:'사진 분석',revision:1,components:[]};
const part={id:'board',kind:'board',name:'제어 보드',quantity:1,status:'INFERRED',model_candidates:['UNO R3'],markings:['UNO'],regions:[{asset_id:'image'}],evidence:'표식 확인',checks_needed:['정격 확인']};
const catalog={arduino_uno_r3_interface:{name:'UNO R3',kind:'board',source:'https://docs.arduino.cc/resources/pinouts/A000066-full-pinout.pdf',pins:{D5:'DIGITAL 5'},note:'모델 확인 필요'}};
test('keeps an internal hypothesis separate and hides it on stale reports',()=>{
 const study={summary:'내부 구성 추정',enclosures:[]};
 const plan={revision:1,inventory:{parts:[part]},component_datasheet:{enclosure_analysis:study}};
 assert.deepEqual(buildDatasheet(graph,plan,catalog).enclosureAnalysis,study);
 assert.equal(buildDatasheet({...graph,revision:2},plan,catalog).enclosureAnalysis,null);
});
test('exports concrete selected specifications, connections and escaped code',()=>{
 const design={functional_design:{title:'제어기',behavior:'입력 제어',parts:[{id:'R1',name:'저항',quantity:1,parameters:{value:'220'},purpose:'전류 제한',selection_reason:'LED 구동'}],structures:[],connections:[{source:'U1.5',target:'R1.1'}],firmware:{source:'if(a<b){} // <script>bad</script>'}}};
 const r=buildDatasheet(graph,{revision:1,inventory:{parts:[part]}},catalog,design);
 const html=datasheetDocument(r);assert.match(html,/부품 선정 완료/);assert.match(html,/value=220/);assert.match(html,/U1.5 → R1.1/);assert.ok(!html.includes('<script>'));
});
test('inventory report preserves candidates and unknown physical specifications without mutating input',()=>{
 const plan={id:'plan',revision:1,inventory:{parts:[part],summary:'보드 관측',unknowns:['전압 미확인']}};
 const before=JSON.stringify([graph,plan,catalog]);const report=buildDatasheet(graph,plan,catalog);
 assert.equal(report.parts[0].value,null);assert.deepEqual(report.parts[0].pins,[]);assert.equal(report.parts[0].status,'INFERRED');assert.equal(report.parts[0].references[0].basis,'모델 후보와 일치 · 실물 모델 미확인');assert.equal(report.stale,false);assert.equal(JSON.stringify([graph,plan,catalog]),before);
 assert.match(datasheetBody(report),/기록된 핀 매핑/);assert.match(datasheetBody(report),/미확인/);
});
test('does not attach a reference to a vague board label, and flags old analysis',()=>{
 const report=buildDatasheet({...graph,revision:2},{revision:1,inventory:{parts:[{...part,model_candidates:['Arduino UNO']}]}},catalog);
 assert.equal(report.stale,true);assert.deepEqual(report.parts[0].references,[]);assert.match(datasheetBody(report),/이전 버전/);
});
test('download escapes observation text and rejects script sources',()=>{
 assert.equal(safeSource('javascript:alert(1)'),null);assert.equal(safeSource('data:text/html,hi'),null);
 const report=buildDatasheet({...graph,title:'<script>alert(1)</script>'},{revision:1,inventory:{parts:[{...part,name:'<img onerror=alert(1)>',evidence:'<script>bad</script>'}]}},catalog);
 const html=datasheetDocument(report);assert.ok(!html.includes('<script>'));assert.ok(!html.includes('<img onerror'));assert.ok(html.includes('&lt;script&gt;'));assert.ok(html.includes('rel="noopener noreferrer"'));
});
test('graph fallback displays only confirmed physical pin mappings',()=>{
 const c={id:'U1',kind:'board',label:{value:'UNO R3',status:'CONFIRMED',reason:'사용자 확인'},catalog_id:'arduino_uno_r3_interface',value:{value:null,status:'UNKNOWN'},asset_id:'image',terminals:[{name:{value:'D5'},pin_mapping:{value:'DIGITAL 5',status:'CONFIRMED'}},{name:{value:'D6'},pin_mapping:{value:'invented',status:'INFERRED'}}]};
 const report=buildDatasheet({...graph,components:[c]},null,catalog);const body=datasheetBody(report);assert.match(body,/D5 → DIGITAL 5/);assert.ok(!body.includes('invented'));assert.equal(report.parts[0].references.length,1);
});

test('does not confuse a text match with a different component category',()=>{const r=buildDatasheet(graph,{revision:1,inventory:{parts:[{...part,kind:'led'}]}},catalog);assert.deepEqual(r.parts[0].references,[]);});

test('falls back to recorded parts when an inventory result has no detected parts',()=>{
 const c={id:'D1',kind:'led',label:{value:'LED',status:'INFERRED',reason:'관찰'},value:{value:null,status:'UNKNOWN'},asset_id:'image',terminals:[]};
 const report=buildDatasheet({...graph,components:[c]},{revision:1,inventory:{parts:[],summary:'없음'}},catalog);
 assert.equal(report.parts.length,1);assert.equal(report.parts[0].name,'LED');assert.equal(report.analysis,'회로 그래프에 기록된 부품');
});
test('confirmed schematic port labels remain labeled mappings requiring physical verification',()=>{
 const c={id:'U1',kind:'board',label:{value:'UNO R3',status:'CONFIRMED',reason:'사양'},value:{value:null,status:'UNKNOWN'},asset_id:'image',terminals:[{name:{value:'D5'},pin_mapping:{value:'5',status:'CONFIRMED'}}]};
 const body=datasheetBody(buildDatasheet({...graph,mode:'reference_design',components:[c]},null,catalog));
 assert.match(body,/기록된 핀 매핑/);assert.match(body,/실물 핀과 대조 필요/);assert.doesNotMatch(body,/<dt>물리 핀 배치<\/dt>/);
});

test('function-first report compares new design parts with photo candidates without certifying them',()=>{
 const sensor={...part,id:'s1',kind:'sensor',name:'원판형 소자',status:'UNKNOWN',model_candidates:['광저항']};
 const plan={id:'plan',revision:1,inventory:{parts:[sensor],summary:'미확인 소자',unknowns:[]}};
 const proposal={recipe:'arduino_light_led',behavior:'어두울 때 LED 켜기',function:{status:'INFERRED'},
  specifications:{S1:{name:'가상 조도 모듈',value:null,note:'3핀 모듈',source:'https://docs.wokwi.com/parts/wokwi-photoresistor-sensor'},R1:{name:'저항',value:'220',note:'새 설계값',source:'javascript:alert(1)'}},
  assignments:{S1:null,R1:null},replacements:[{reference:'S1',candidate_ids:['s1'],reason:'2핀 후보와 3핀 모듈은 다릅니다.'}]};
 const report=buildDatasheet(graph,plan,{}, {hypothesis_previews:[{title:'조도 제어',proposal}]});
 assert.equal(report.designs[0].parts[0].observed,null);
 assert.equal(report.designs[0].parts[0].related[0].status,'UNKNOWN');
 const html=datasheetBody(report);
 assert.match(html,/기능에 필요한 새 부품/);assert.match(html,/새로 준비 · 사진의 후보와 다른 구성/);
 assert.match(html,/원판형 소자 · 미확인/);assert.match(html,/사진 속 부품의 측정 결과가 아닙니다/);
 assert.doesNotMatch(html,/href="javascript:/);
 const stale=buildDatasheet({...graph,revision:2},plan,{}, {hypothesis_previews:[{title:'조도 제어',proposal}]});
 assert.deepEqual(stale.designs,[]);
});

test('distinguishes manufacturer datasheets, simulation references and unknown sources',()=>{
 const p={...part,kind:'sensor',name:'가상 조도 센서',model_candidates:['sim_module']};
 const refs={sim_module:{name:'sim_module',kind:'sensor',source:'https://docs.wokwi.com/parts/wokwi-photoresistor-sensor',source_type:'simulation_reference',pins:{VCC:'VCC'},note:'가상 모델'},
   unknown:{name:'가상 조도 센서',kind:'sensor',source:'https://example.org/part',pins:{},note:''}};
 const report=buildDatasheet(graph,{revision:1,inventory:{parts:[p]}},refs);
 assert.equal(report.parts[0].references.find(r=>r.id==='sim_module').kind,'시뮬레이터 참고자료');
 assert.equal(report.parts[0].references.find(r=>r.id==='unknown').kind,'출처 유형 미확인 참고자료');
 const html=datasheetBody(report);
 assert.match(html,/시뮬레이터 참고자료/);assert.match(html,/사진 부품과의 일치는 자동 검증되지 않았습니다/);
 assert.doesNotMatch(html,/제조사 원본 데이터시트 열기/);
 const manufacturer={...catalog,arduino_uno_r3_interface:{...catalog.arduino_uno_r3_interface,source_type:'manufacturer_pinout'}};
 assert.match(datasheetBody(buildDatasheet(graph,{revision:1,inventory:{parts:[part]}},manufacturer)),/제조사 핀 배치 자료/);
});

test('observed components precede system reasoning and inferred additions remain separate',()=>{
 const addition={id:'ADD_DRIVER',name:'펌프 구동 회로 <script>',kind:'other',quantity:1,
  status:'INFERRED',photo_presence:'UNKNOWN',purpose:'펌프 제어',reason:'사진에서 구동부 미확인',
  basis_part_ids:['board'],hypothesis_ids:['watering'],model_candidates:[],checks_needed:['전류와 정격 확인'],
  references:[{url:'javascript:alert(1)',name:'bad'}]};
 const plan={id:'plan',revision:1,analysis_complete:true,inventory:{parts:[part],summary:'보드',unknowns:[]},
  component_datasheet:{inferred_parts:[addition],function_hypotheses:[{title:'급수',rationale:'구성품 근거',input_behavior:'건조',output_behavior:'급수'}]}};
 const before=JSON.stringify(plan),report=buildDatasheet(graph,plan,catalog);
 assert.equal(report.parts.length,1);assert.equal(report.inferredParts.length,1);
 assert.equal(report.inferredParts[0].photo_presence,'UNKNOWN');
 const html=datasheetBody(report);
 assert.ok(html.indexOf('1. 사진에서 확인한 구성품')<html.indexOf('2. 구성품으로 추론한 기능'));
 assert.ok(html.indexOf('2. 구성품으로 추론한 기능')<html.indexOf('3. 부족한 부품 보완'));
 assert.match(html,/추정 보완 · 사진 내 존재 미확인/);assert.doesNotMatch(html,/<script>|href="javascript:/);
 assert.equal(JSON.stringify(plan),before);
 const selected=buildDatasheet(graph,plan,catalog,{selected_hypothesis_id:'other'});
 assert.equal(selected.inferredParts.length,0);
 const stale=buildDatasheet({...graph,revision:2},plan,catalog);
 assert.equal(stale.inferredParts.length,0);
});

test('prototype report shows its actual selected simulation parts separately from photo evidence',()=>{
 const plan={revision:1,inventory:{parts:[part],summary:'보드 후보',unknowns:[]}};
 const design={prototype_details:{id:'distance_indicator',title:'거리 표시',
  simulator:{behavior:'거리값을 LCD에 표시'},components:[{id:'LCD1',name:'16×2 LCD'},{id:'R1',name:'220Ω 저항'}]}};
 const report=buildDatasheet(graph,plan,{},design);
 assert.equal(report.parts.length,1);assert.equal(report.designs[0].parts.length,2);
 assert.equal(report.designs[0].parts[0].observed,null);
 assert.match(datasheetBody(report),/16×2 LCD/);
 assert.match(datasheetBody(report),/사진 속 부품의 측정 결과가 아닙니다/);
});
