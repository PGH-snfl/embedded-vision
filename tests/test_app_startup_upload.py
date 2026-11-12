"""Boot the complete production page; mock HTTP only, never initIntegrated."""
import io
import json
from pathlib import Path
import subprocess

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from backend.application import create_app

ROOT=Path(__file__).resolve().parents[1]
NODE='/home/snowflower/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node'


@pytest.mark.parametrize('workspace',[False,True])
def test_complete_page_starts_and_uploads_photo_then_video(tmp_path,monkeypatch,workspace):
    monkeypatch.setenv('EMBEDDED_VISION_AUTO_ANALYSIS','0')
    photo=io.BytesIO();Image.new('RGB',(64,64),'white').save(photo,format='PNG')
    with TestClient(create_app(tmp_path/'api')) as client:
        uploaded=client.post('/api/projects',files={'image':('input.png',photo.getvalue(),'image/png')}).json()
        recipes=client.get('/api/design/recipes').json()
    fixture=tmp_path/'response.json';fixture.write_text(json.dumps({'uploaded':uploaded,'recipes':recipes}))
    output=tmp_path/'app.mjs'
    subprocess.run([NODE,str(ROOT/'third_party/velxio/frontend/node_modules/esbuild/bin/esbuild'),str(ROOT/'frontend/app.js'),
                    '--bundle','--platform=browser','--format=esm','--external:https:*',f'--outfile={output}'],check=True,capture_output=True)
    script=r'''
const fs=require('node:fs'),assert=require('node:assert/strict'),{pathToFileURL}=require('node:url');
const {JSDOM}=require(process.argv[2]);
const hosted=process.argv[5]==='true',wid='a'.repeat(32),prefix=hosted?'/api/w/'+wid:'/api';
const dom=new JSDOM(fs.readFileSync(process.argv[3],'utf8'),{url:'http://localhost'+(hosted?'/w/'+wid+'/':'/')});
for(const key of ['window','document','location','localStorage','sessionStorage','CustomEvent','Event','Node','HTMLElement','FormData','File'])global[key]=dom.window[key];
global.requestAnimationFrame=()=>1;global.cancelAnimationFrame=()=>{};
dom.window.HTMLElement.prototype.scrollIntoView=function(){this.dataset.scrolled='true'};
const {uploaded,recipes}=JSON.parse(fs.readFileSync(process.argv[4],'utf8'));let hasProject=false,calls=[];
const json=value=>new Response(JSON.stringify(value),{headers:{'Content-Type':'application/json'}});
global.fetch=async(url,options={})=>{
 const method=options.method||'GET';calls.push({method,url:String(url),body:options.body});
 const path=String(url).replace(prefix,'/api'),pid=uploaded.graph.project_id;
 if(path==='/api/saas/me')return json({workspaces:[{id:wid,name:'Test workspace'}],email:'unit test',auth_enabled:false});
 if(path==='/api/projects'&&method==='GET')return json(hasProject?[{project_id:pid,title:'Test input',revision:1}]:[]);
 if(['/api/projects','/api/projects/video'].includes(path)&&method==='POST'){
  assert.equal(options.body.get('analysis_model'),'gpt-6-astra');hasProject=true;
  if(path.endsWith('/video'))uploaded.graph.mode='video';return json(uploaded);
 }
 if(path==='/api/planner/status')return json({configured:false,primary:'gpt-6.1-sol',specialist:'gpt-6-astra',note:'Unit test'});
 if(path==='/api/design/recipes')return json(recipes);
 if(path===`/api/projects/${pid}/planner`)return json({plan:null});
 if(path===`/api/projects/${pid}/new-design`)return json({design:null});
 if(path===`/api/projects/${pid}/auto-analysis`)return json({job:{...uploaded.auto_analysis,analysis_model:'gpt-6-astra'},configured:false});
 if(path===`/api/projects/${pid}/vision/jobs`||path===`/api/projects/${pid}/vision`)return json({jobs:[]});
 if(path==='/api/vision/status')return json({ready:false});
 throw Error('Unexpected request '+method+' '+path);
};
const pause=()=>new Promise(resolve=>setImmediate(resolve));
async function settle(){for(let i=0;i<8;i++)await pause();assert.equal(document.body.hasAttribute('aria-busy'),false);}
(async()=>{
 await import(pathToFileURL(process.argv[1]).href);await settle();
 assert.equal(document.querySelector('#video-upload').onchange instanceof Function,true,'video handler initialized');
 document.querySelector('[data-analysis-model="gpt-6-astra"]').click();
 const photo=document.querySelector('#upload');Object.defineProperty(photo,'files',{value:[new File(['test'],'photo.png',{type:'image/png'})]});
 await photo.onchange();await settle();
 assert.equal(document.querySelector('#workspace').hidden,false);
 assert.equal(document.querySelector('#message').classList.contains('error'),false,document.querySelector('#message').textContent);
 assert.match(document.querySelector('#auto-analysis-panel .tag').textContent,/Astra/);
 assert.equal(document.querySelector('#user-step-2').dataset.scrolled,'true');
 const video=document.querySelector('#video-upload');Object.defineProperty(video,'files',{value:[new File(['test'],'video.mp4',{type:'video/mp4'})]});
 await video.onchange();await settle();
 assert.equal(document.querySelector('#message').classList.contains('error'),false,document.querySelector('#message').textContent);
 assert.equal(calls.filter(c=>c.method==='POST').length,2,'one upload per input; no analysis resubmission');
 assert.equal(calls.filter(c=>c.method==='POST'&&c.url.endsWith('/auto-analysis')).length,0);
 assert.match(document.querySelector('#auto-analysis-panel .tag').textContent,/Astra/);
 console.log('Complete application startup, photo upload, video upload, selected model and analysis refresh passed: '+(hosted?'SaaS':'local'));
})().catch(e=>{console.error(e);process.exit(1)});
'''
    result=subprocess.run([NODE,'-e',script,str(output),str(ROOT/'third_party/velxio/frontend/node_modules/jsdom'),str(ROOT/'frontend/index.html'),str(fixture),str(workspace).lower()],capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stderr
