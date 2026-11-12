import {test} from 'node:test';
import assert from 'node:assert/strict';
import {canDeleteInput, deleteInputProject, inputDeletePrompt} from '../frontend/delete-input.js';

function fixture({mode='photo',accept=true,fail=false,saved='a'.repeat(32),apiPrefix='/api'}={}){
 const graph={project_id:'a'.repeat(32),title:'검증 사진',mode,revision:3}, calls=[];
 let selection=saved,reloaded=false,shown='';
 return {graph,calls,get selection(){return selection},get reloaded(){return reloaded},get shown(){return shown},
  args:{graph,apiPrefix,storageKey:'active',storage:{getItem:()=>selection,removeItem:()=>{selection=null;}},
   confirmDelete:text=>{shown=text;return accept},reload:()=>{reloaded=true},
   api:async (...args)=>{calls.push(args);if(fail)throw new Error('진행 중인 작업이 있습니다.');return {deleted_project:graph.project_id}}}};
}

test('asks the user and leaves everything unchanged when cancelled',async()=>{
 const f=fixture({accept:false});assert.equal(await deleteInputProject(f.args),false);
 assert.equal(f.calls.length,0);assert.equal(f.selection,f.graph.project_id);assert.equal(f.reloaded,false);
 assert.match(f.shown,/입력, 분석 결과·이력/);assert.match(f.shown,/되돌릴 수 없습니다/);
 assert.match(f.shown,/브라우저에 저장된 시뮬레이터 초안은 남습니다/);
});

test('deletes photo or video in the correct workspace and refreshes only on success',async()=>{
 const f=fixture({mode:'video',apiPrefix:'/api/w/'+'b'.repeat(32)});
 assert.equal(await deleteInputProject(f.args),true);
 assert.deepEqual(f.calls,[[`/api/w/${'b'.repeat(32)}/projects/${f.graph.project_id}?expected_revision=3`,{method:'DELETE'}]]);
 assert.equal(f.selection,null);assert.equal(f.reloaded,true);assert.match(f.shown,/영상·추출 프레임·추가 사진/);
});

test('preserves another tab selection and leaves the page on server error',async()=>{
 const other=fixture({saved:'other'});await deleteInputProject(other.args);assert.equal(other.selection,'other');assert.equal(other.reloaded,true);
 const f=fixture({fail:true});await assert.rejects(deleteInputProject(f.args),/진행 중인 작업/);
 assert.equal(f.selection,f.graph.project_id);assert.equal(f.reloaded,false);
});

test('does not offer deletion of examples or derived circuits',async()=>{
 for(const mode of ['reference_design','synthetic_demo']){
  const f=fixture({mode});assert.equal(canDeleteInput(f.graph),false);
  await assert.rejects(deleteInputProject(f.args),/사진·영상 입력 프로젝트만/);assert.equal(f.calls.length,0);
 }
 assert.equal(canDeleteInput(null),false);assert.match(inputDeletePrompt({mode:'photo'}),/현재 프로젝트/);
});

test('warns about remaining server files and refreshes after a partial cleanup',async()=>{
 const f=fixture();let warning='';f.args.notify=value=>{warning=value;};f.args.api=async()=>({deleted_project:f.graph.project_id,cleanup_pending:true});
 await deleteInputProject(f.args);
 assert.match(warning,/프로젝트는 삭제됐지만 서버 파일 정리 또는 삭제 기록을 확인해야 합니다/);
 assert.equal(f.selection,null);assert.equal(f.reloaded,true);
});
