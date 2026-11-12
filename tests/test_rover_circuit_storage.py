"""Motion is gated by the saved drawing, including concurrent edits."""
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def test_saved_revision_and_concurrent_edit_gate(tmp_path):
    output=tmp_path/'circuit-store.cjs'
    build=ROOT/'third_party/velxio/frontend/node_modules/.bin/esbuild'
    subprocess.run([str(build),str(ROOT/'frontend/rover-circuit-storage.js'),'--bundle','--platform=node',
                    '--format=cjs','--target=node12',f'--outfile={output}'],check=True,capture_output=True)
    script=r'''
const assert=require('assert');const {createRoverCircuitStorage}=require(process.argv[1]);
const pause=()=>new Promise(r=>setTimeout(r,10));
(async()=>{
 let revision=0,server={version:1,components:[],connections:[]},checks=0;
 const api=async(url,opts)=>{
  if(!opts)return {revision,circuit:server};
  const body=JSON.parse(opts.body);await pause();
  if(body.expected_revision!==revision)throw Error('다른 화면에서 회로가 변경되었습니다.');
  if(url.endsWith('/validate')){checks++;return {revision,allowed:server.connections.length>0,errors:[]};}
  server=body.circuit;return {revision:++revision,circuit:server};
 };
 const store=createRoverCircuitStorage(api,'/project','a'.repeat(64));await store.load();
 const graph={version:1,components:[],connections:[{id:'a'}]};store.update(graph,()=>{});
 assert((await store.validate()).allowed);assert.equal(revision,1);
 const p=store.validate();await pause();store.update({...graph,connections:[]},()=>{});
 await assert.rejects(p,/검사 중 회로가 변경/);
 assert(!(await store.validate()).allowed);assert.equal(checks,3);
 revision++;await assert.rejects(store.validate(),/다른 화면/);
})().catch(e=>{console.error(e);process.exit(1)});
'''
    subprocess.run(['node','-e',script,str(output)],check=True,capture_output=True,text=True)
