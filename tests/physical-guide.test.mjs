import {test} from 'node:test';
import assert from 'node:assert/strict';
import {matchesReviewedLayout,physicalGuideHTML} from '../frontend/physical-guide.js';

const fixture=()=>({
 id:'raspberry_pi_4b_button_led',title:'가상 시험',behavior:'버튼',
 board:{model:'Raspberry Pi 4 Model B (40핀 헤더)',gpio_voltage:'3.3 V',pins:[{name:'3V3',physical:1,bcm:null},{name:'GND',physical:6,bcm:null},{name:'GPIO17',physical:11,bcm:17},{name:'GPIO27',physical:13,bcm:27}]},
 breadboard:{rows:30,columns:'ABCDEFGHIJ',groups:['A-E','F-J']},
 parts:[{id:'R1',model:'1 kΩ, 허용오차 5% 이내, 0.25 W 이상, 축형',holes:[{terminal:'1',hole:'B1'},{terminal:'2',hole:'B5'}]},{id:'D1',model:'Kingbright WP7113ID',holes:[{terminal:'A',hole:'A5'},{terminal:'K',hole:'A6'}]},{id:'SW1',model:'Adafruit STEMMA Wired Tactile Push-Button #4431',holes:[{terminal:'signal_white',hole:'A14'},{terminal:'gnd_black',hole:'A16'},{terminal:'power_red',hole:'A18'}]}],
 connections:[{id:'W1',from:'U1.P11',to:'A1'},{id:'W2',from:'U1.P6',to:'B6'},{id:'W3',from:'U1.P13',to:'B14'},{id:'W4',from:'B16',to:'C6'},{id:'W5',from:'U1.P1',to:'B18'}],steps:[],sources:[],warnings:[],code:{source:'print(1)',filename:'file.py'}});

test('verified layout matches pins, parts, holes and wires',()=>{
 assert.equal(matchesReviewedLayout(fixture()),true);
 for(const mutate of [x=>x.board.pins[0].physical=2,x=>x.parts[0].holes[0].hole='B3',x=>x.parts[2].model='다른 버튼',x=>x.connections[0].to='A2',x=>x.parts[1].holes.push({terminal:'extra',hole:'A7'})]) {
  const bad=fixture();mutate(bad);assert.equal(matchesReviewedLayout(bad),false);
 }
});
test('unsupported functions do not expose a physical design',()=>{
 assert.match(physicalGuideHTML({physical_design:null},'/demo',String),/다른 기능/);
});
