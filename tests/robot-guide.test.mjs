import {test} from 'node:test';
import assert from 'node:assert/strict';
import {matchesRobotWiring,robotWiringDiagram,robotGuideHTML} from '../frontend/robot-guide.js';

function fixture(){return {
 id:'raspberry_pi_2wd_robot',title:'테스트',behavior:'전진·정지',board:{model:'Raspberry Pi 4 Model B'},
 parts:[{id:'HAT1',model:'Adafruit DC & Stepper Motor HAT #2348'},
  {id:'MOTOR_L',model:'#2939에 포함된 #2941'},{id:'MOTOR_R',model:'#2939에 포함된 #2941'},
  {id:'BAT1',model:'별도 5V 정전압 DC 전원, 3A 이상, 차단 스위치'}],
 connections:[['U1.GPIO40','HAT1.GPIO40'],['U1.USB_C','PS1.USB_C'],['MOTOR_L.black','HAT1.M1.left'],
  ['MOTOR_L.red','HAT1.M1.right'],['MOTOR_R.black','HAT1.M2.left'],['MOTOR_R.red','HAT1.M2.right'],
  ['BAT1.red','HAT1.PWR.positive'],['BAT1.black','HAT1.PWR.negative']].map(([from,to],i)=>({id:`C${i+1}`,from,to,description:'test'})),
 steps:[],warnings:[],sources:[],code:{source:'test',filename:'rover.py'}};}
test('a mismatched pin, part, or board hides the physical diagram',()=>{
 const good=fixture();assert.equal(matchesRobotWiring(good),true);assert.match(robotWiringDiagram(good,[],String),/M1/);
 for(const mutate of [x=>x.connections[2].to='HAT1.M2.left',x=>x.parts[0].model='other',x=>x.board.model='Pico']){
  const bad=fixture();mutate(bad);assert.equal(matchesRobotWiring(bad),false);assert.match(robotWiringDiagram(bad,[],String),/숨겼습니다/);
 }
});
test('guide only appears for supplied reviewed design',()=>{
 assert.equal(robotGuideHTML({robot_design:null},'/test',String),'');
 assert.match(robotGuideHTML({robot_design:fixture(),function_version:'abc'},'/test',String),/robot-design\/python\?function_version=abc/);
});
