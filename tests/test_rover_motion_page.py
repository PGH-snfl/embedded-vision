"""The independent motion tab only uses a verified saved circuit revision."""
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ESBUILD = ROOT / 'third_party/velxio/frontend/node_modules/.bin/esbuild'


def test_motion_page_validates_context_and_checks_every_drive(tmp_path):
    target=tmp_path/'motion-page.cjs'
    subprocess.run([str(ESBUILD),str(ROOT/'frontend/rover-motion-page.js'),
        '--bundle','--platform=node','--format=cjs','--target=node12',f'--outfile={target}'],
        check=True,capture_output=True,text=True)
    script=r'''
const assert=require('assert');
global.location={pathname:'/',origin:'http://localhost:8766'};
const {parseMotionQuery,createMotionSession}=require(process.argv[1]);
const project='a'.repeat(32),plan='b'.repeat(32),version='c'.repeat(64);
const search=`?project=${project}&plan=${plan}&function_version=${version}&revision=7`;
assert.deepStrictEqual(parseMotionQuery(search),{project,plan,version,revision:7});
for(const s of [search+'&revision=8',search+'&extra=x',search.replace('revision=7','revision=-1'),
  search.replace('revision=7','revision=01'),search.replace('revision=7','revision=9007199254740992'),
  search.replace(project,'../x'),search.replace(version,'bad')])assert.throws(()=>parseMotionQuery(s));
let revision=7, checks=0, allowed=true, calls=[];
const api=async (url,opts={})=>{
 calls.push([url,opts.method||'GET']);
 if(url.endsWith('/proposals'))return {inventory_plan:plan,function_version:version,robot_design:{id:'test'}};
 if(url.includes('/circuit?'))return {revision,circuit:{version:1,components:[],connections:[]}};
 if(url.endsWith('/circuit/validate')){
  checks++;const b=JSON.parse(opts.body);assert.equal(b.expected_revision,7);
  if(b.expected_revision!==revision)throw Error('다른 화면에서 회로가 변경되었습니다.');
  return {revision,allowed,errors:allowed?[]:['연결 오류']};
 }
 if(url.includes('/structure?'))return {revision:0,structure:null};
 if(url.endsWith('/structure'))return {revision:1,structure:JSON.parse(opts.body).structure};
 throw Error('unexpected '+url);
};
(async()=>{
 const s=createMotionSession({api,project,plan,version,revision:7,prefix:'/api/w/'+('d'.repeat(32))});
 const initial=await s.load();assert.equal(initial.proposal.robot_design.id,'test');assert.equal(initial.structure,null);
 assert.equal(checks,1);await s.check();await s.check();assert.equal(checks,3);
 assert(calls.every(([url])=>url.startsWith('/api/w/'+('d'.repeat(32))+'/projects/'+project+'/inventory/'+plan)));
 allowed=false;await assert.rejects(s.check(),/연결 오류/);allowed=true;revision=8;
 await assert.rejects(s.check(),/다른 화면/);
 const stale=createMotionSession({api,project,plan,version,revision:7,prefix:'/api'});
 await assert.rejects(stale.load(),/회로가 변경/);
 const wrong=createMotionSession({api:async u=>u.endsWith('/proposals')?{inventory_plan:plan,function_version:'0'.repeat(64),robot_design:{}}:{revision:7,circuit:{}},project,plan,version,revision:7,prefix:'/api'});
 await assert.rejects(wrong.load(),/변경/);
})().catch(e=>{console.error(e);process.exit(1)});
'''
    subprocess.run(['node','-e',script,str(target)],check=True,capture_output=True,text=True)
