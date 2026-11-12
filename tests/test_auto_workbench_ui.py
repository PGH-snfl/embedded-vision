"""A fresh upload opens the supported simulator once; old projects remain stable."""
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
NODE=Path('/home/snowflower/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node')


def test_auto_navigation_selection_and_lifecycle(tmp_path):
    output=tmp_path/'auto.cjs'
    entry=tmp_path/'entry.js'
    entry.write_text(f"export * from '{ROOT}/frontend/auto-workbench.js';\nexport * from '{ROOT}/frontend/auto-navigation.js?v=photo-auto-nav-2';\n")
    esbuild=ROOT/'third_party/velxio/frontend/node_modules/.bin/esbuild'
    subprocess.run([str(esbuild),str(entry),'--bundle','--platform=node',
                    '--format=cjs','--target=node18',f'--outfile={output}'],check=True,capture_output=True)
    script=r'''
const assert=require('node:assert/strict');
const {JSDOM}=require(process.argv[2]);
const dom=new JSDOM('<section id="auto" hidden></section>',{url:'http://localhost:8901/'});
global.window=dom.window;global.document=dom.window.document;global.location=dom.window.location;
const {createAutoWorkbench,autoTarget,withAutorun,markAutoLaunch,cancelAutoLaunch}=require(process.argv[1]);
const host=document.querySelector('#auto');let calls=0;const navigations=[];
const data={format:'velxio-project',components:[],boards:[],embeddedVision:{}};
const api=async(url)=>{calls++;return url.includes('/prototype?')?{workbench:data}:url.includes('/robot-design/workbench?')?{project:data}:data;};
const control=createAutoWorkbench({host,api,navigate:url=>navigations.push(url)});
const project='a'.repeat(32),plan='b'.repeat(32),version='c'.repeat(64);
const opts={project,plan,revision:1,stale:false,endpoint:'/api/projects/'+project+'/inventory/'+plan};
const proto={function_version:version,prototype_design:{kind:'watering'},selection_origin:'automatic'};
(async()=>{
 assert.equal(autoTarget({function_version:version,proposals:[]}),null);
 assert.equal(new URL(withAutorun('http://localhost/edit?x=1#abc','http://localhost')).hash,'#abc');
 assert.equal(markAutoLaunch(project),true);
 await control.update({...opts,data:proto});
 assert.equal(navigations.length,1);assert.equal(new URL(navigations[0]).pathname,'/editor');
 assert.equal(new URL(navigations[0]).searchParams.get('autorun'),'1');
 assert.equal(host.hidden,false);assert.equal(host.querySelector('iframe'),null);
 await control.update({...opts,data:proto});assert.equal(navigations.length,1);
 control.clear();await control.update({...opts,data:proto});assert.equal(navigations.length,1);
 assert.equal(new URL(host.querySelector('a').href).pathname,'/editor');
 assert.equal(markAutoLaunch(project),true);cancelAutoLaunch();control.clear();
 await control.update({...opts,data:proto});assert.equal(navigations.length,1);
 const robot={function_version:version,robot_design:{id:'raspberry_pi_2wd_robot'},selection_origin:'user'};
 await control.update({...opts,data:robot});assert.equal(navigations.length,1);
 assert.equal(new URL(host.querySelector('a').href).pathname,'/rover-editor.html');assert.match(host.textContent,/수동 조작/);
 const recipe={function_version:version,recommended:'arduino_led_output',selection_origin:'automatic',proposals:[{recipe:'arduino_led_output',simulator_supported:true}]};
 assert.equal(markAutoLaunch(project),true);
 let release;const slow=createAutoWorkbench({host,api:url=>url.includes('/prototype?')?Promise.resolve({workbench:data}):new Promise(r=>{release=r;}),navigate:url=>navigations.push(url)});
 const pending=slow.update({...opts,data:recipe});await slow.update({...opts,data:proto});
 assert.equal(navigations.length,2);release(data);await pending;assert.equal(navigations.length,2);
 slow.clear();await slow.update({...opts,data:{function_version:version,proposals:[]}});assert.equal(host.hidden,true);
 const broken={setItem(){throw Error('blocked');}};assert.equal(markAutoLaunch(project,broken),false);
 await slow.update({...opts,data:proto});assert.equal(navigations.length,2);assert.equal(host.querySelector('a').hidden,false);
})().catch(error=>{console.error(error);process.exit(1)});
'''
    node=str(NODE) if NODE.exists() else 'node'
    jsdom=ROOT/'third_party/velxio/frontend/node_modules/jsdom'
    result=subprocess.run([node,'-e',script,str(output),str(jsdom)],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
