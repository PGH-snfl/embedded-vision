/** Delete an uploaded photo/video project only after an explicit confirmation. */
export function canDeleteInput(graph) {
  return Boolean(graph && ['photo', 'video'].includes(graph.mode));
}

export function inputDeletePrompt(graph) {
  const input = graph.mode === 'video' ? '영상·추출 프레임·추가 사진' : '입력된 사진과 추가 사진';
  return `‘${graph.title || '현재 프로젝트'}’의 ${input} 및 분석 프로젝트를 삭제할까요?\n\n서버의 입력, 분석 결과·이력과 이 프로젝트에 저장된 회로 초안이 삭제됩니다.\n별도로 생성한 회로 프로젝트, 다운로드 파일, 브라우저에 저장된 시뮬레이터 초안은 남습니다.\n\n이 작업은 되돌릴 수 없습니다.`;
}

export async function deleteInputProject({graph, api, apiPrefix, storage, storageKey, confirmDelete, notify, reload}) {
  if (!canDeleteInput(graph)) throw new Error('사진·영상 입력 프로젝트만 삭제할 수 있습니다.');
  if (!confirmDelete(inputDeletePrompt(graph))) return false;
  const project = graph.project_id;
  const result = await api(`${apiPrefix}/projects/${encodeURIComponent(project)}?expected_revision=${encodeURIComponent(graph.revision)}`, {method:'DELETE'});
  // Clear only the deleted selection. Another tab may already have selected a
  // different project, and blocked storage must not prevent the UI refresh.
  try { if (storage.getItem(storageKey) === project) storage.removeItem(storageKey); } catch { /* storage unavailable */ }
  if (result?.cleanup_pending && notify) notify('프로젝트는 삭제됐지만 서버 파일 정리 또는 삭제 기록을 확인해야 합니다. 관리자 확인이 필요합니다.');
  reload();
  return true;
}
