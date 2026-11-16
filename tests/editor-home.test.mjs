import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import vm from 'node:vm';
import {webcrypto} from 'node:crypto';
import test from 'node:test';
const require=createRequire(import.meta.url);
const {JSDOM}=require('jsdom');
const code=readFileSync(new URL('../services/editor/web/home.js',import.meta.url),'utf8');
const html=readFileSync(new URL('../services/editor/web/index.html',import.meta.url),'utf8');

test('standalone examples and imported projects open the editor without contacting the analyzer',async()=>{
 const dom=new JSDOM(html),requests=[],opened=[],saved=[];
 const project={format:'velxio-project',name:'edited',boards:[{id:'U1'}],components:[{id:'R1'}],wires:[{id:'wire'}],fileGroups:{main:[{name:'sketch.ino',content:'user code'}]}};
 const before=JSON.stringify(project);
 await vm.runInNewContext('(async()=>{'+code+'})()',{
  document:dom.window.document,location:{assign:url=>opened.push(url)},crypto:webcrypto,TextEncoder,
  btoa:text=>Buffer.from(text,'binary').toString('base64'),
  fetch:async (url,options)=>{requests.push(url);if(url==='/api/editor/lessons')return{ok:true,json:async()=>[{id:'uno-led-blink',title:'LED 깜빡이기',level:'입문',summary:'따라 하기'}]};if(url==='/api/editor/projects'){saved.push(JSON.parse(options.body));return{ok:true,json:async()=>({editor_url:'/editor?embedded=1&standalone=1&editor_project='+String(saved.length).padStart(32,'0')})}}return{ok:true,json:async()=>url==='/api/editor/examples'?[{id:'arduino-uno',name:'<script>unsafe</script>',runtime:'local'}]:structuredClone(project)}}
 });
 assert.equal(dom.window.document.querySelectorAll('script').length,1);
 await dom.window.document.querySelector('#new-project').onclick();
 assert.equal(dom.window.document.querySelectorAll('#lessons article').length,1);
 await dom.window.document.querySelector('#lessons button').onclick();
 assert.equal(opened.length,2);
 assert.match(opened[0],/^\/editor\?embedded=1&standalone=1&editor_project=/);
 const target={files:[{size:100,text:async()=>before}],value:'picked'};
 await dom.window.document.querySelector('#project-file').onchange({target});
 assert.equal(opened.length,3);
 const imported=saved.at(-1);
 for(const key of ['boards','components','wires','fileGroups'])assert.deepEqual(imported[key],project[key]);
 assert.equal(target.value,'');assert.equal(JSON.stringify(project),before);
 assert.ok(requests.every(url=>url.startsWith('/api/editor/')));
 dom.window.close();
});
