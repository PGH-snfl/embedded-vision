"""Edits must persist in order without stale tabs overwriting one another."""
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def test_rover_frontend_serializes_pending_saves_and_surfaces_conflicts(tmp_path):
    output=tmp_path/'rover-storage.cjs'
    build=ROOT/'third_party/velxio/frontend/node_modules/.bin/esbuild'
    subprocess.run([str(build),str(ROOT/'frontend/rover-storage.js'),'--bundle','--platform=node',
                    '--format=cjs','--target=node12',f'--outfile={output}'],check=True,capture_output=True)
    script=r'''
const assert=require('assert');
const {createRoverStorage}=require(process.argv[1]);
(async()=>{
 let revision=0,stored=null,requests=[];const messages=[];
 const pause=()=>new Promise(r=>setTimeout(r,15));
 const api=async(url,opts)=>{
   if(!opts)return {revision,structure:stored};
   const b=JSON.parse(opts.body);requests.push(b);await pause();
   if(b.expected_revision!==revision)throw Error('다른 화면에서 구조를 변경했습니다.');
   stored=b.structure;return {revision:++revision,structure:stored};
 };
 const store=createRoverStorage(api,'/test','a'.repeat(64));
 assert.equal(await store.load(),null);
 store.update({version:1,objects:[{id:'one'}]},m=>messages.push(m));
 store.update({version:1,objects:[{id:'two'}]},m=>messages.push(m));
 await pause();await pause();await pause();
 assert.equal(requests.length,2);assert.equal(requests[0].expected_revision,0);assert.equal(requests[1].expected_revision,1);
 assert.equal(stored.objects[0].id,'two');assert.equal(messages[messages.length-1],'구조 저장됨');
 revision=3;store.update({version:1,objects:[{id:'three'}]},m=>messages.push(m));await pause();await pause();
 assert(messages[messages.length-1].includes('저장 실패'));assert.equal(store.snapshot().objects[0].id,'three');
 store.update({version:1,objects:[{id:'four'}]},m=>messages.push(m));assert(messages[messages.length-1].includes('저장 실패'));
})().catch(e=>{console.error(e);process.exit(1);});
'''
    subprocess.run(['node','-e',script,str(output)],check=True,capture_output=True,text=True)
