import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import test from 'node:test';
const require=createRequire(new URL('../third_party/velxio/frontend/package.json',import.meta.url));
const {JSDOM}=require('jsdom');
const html=readFileSync(new URL('../tutorial.html',import.meta.url),'utf8');

test('every command reveals its exact text and copies without executing',async()=>{
 let copied=[];
 const dom=new JSDOM(html,{runScripts:'dangerously',url:'https://tutorial.example/',beforeParse(w){
  Object.defineProperty(w,'isSecureContext',{value:true});
  Object.defineProperty(w.navigator,'clipboard',{value:{writeText:async text=>copied.push(text)}});
 }});
 const doc=dom.window.document;
 for(const button of doc.querySelectorAll('[data-action=reveal]')){
  const code=doc.getElementById(button.getAttribute('aria-controls'));
  assert.ok(code.hidden);button.click();assert.equal(code.hidden,false);
  assert.equal(button.getAttribute('aria-expanded'),'true');
  doc.querySelector(`[data-source="${code.id}"]`).click();
  await new Promise(resolve=>setTimeout(resolve,0));
  assert.equal(copied.at(-1),code.textContent);
  button.click();assert.ok(code.hidden);
 }
 assert.ok(copied.length>=8);
 for(const a of doc.querySelectorAll('a[href^="#"]'))assert.ok(doc.querySelector(a.getAttribute('href')));
 const theme=doc.querySelector('[data-action=theme]');theme.click();
 assert.equal(doc.documentElement.dataset.theme,'dark');
 assert.equal(dom.window.localStorage.getItem('ev-tutorial-theme'),'dark');
 dom.window.close();
});

test('file protocol clipboard fallback works',async()=>{
 let text;
 const dom=new JSDOM(html,{runScripts:'dangerously',url:'file:///tmp/tutorial.html',beforeParse(w){
  w.document.execCommand=cmd=>{assert.equal(cmd,'copy');text=w.document.querySelector('textarea').value;return true;};
 }});
 dom.window.document.querySelector('[data-action=copy]').click();
 await new Promise(resolve=>setTimeout(resolve,0));
 assert.match(text,/raw\.githubusercontent\.com\/PGH-snfl\/embedded-vision\/main\/install\.sh/);
 assert.equal(dom.window.document.querySelector('textarea'),null);
 dom.window.close();
});
