"""Remove an uploaded photo/video project under an exclusive project lock."""
import json
import re
import shutil
import uuid
from contextvars import ContextVar
from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from .project_lock import ProjectBusy, project_lock

ACTIVE = {'queued', 'running', 'sol', 'components', 'component_review', 'coverage', 'function', 'completion', 'datasheet', 'routing', 'astra', 'validation'}
PROJECT_PATH = re.compile(r'^/api/projects/([a-f0-9]{32})(?:/|$)')
terminal_queue_jobs = ContextVar('terminal_queue_jobs', default=frozenset())


def _project_paths(root: Path, project: str):
    # Project identifiers are validated before this function. No glob input is
    # supplied by a client, and only this project's own names are included.
    result = [p for p in root.iterdir()
              if p.name.startswith(project + '.') or p.name.startswith(project + '-')]
    for category in ('artifacts', 'planner', 'function_targets', 'proposal_simulations',
                     'emulations', 'designs'):
        if (root / category).is_symlink(): raise OSError('Project storage directory is a symlink')
        path = root / category / project
        if path.exists() or path.is_symlink(): result.append(path)
    if (root / 'auto_jobs').is_symlink(): raise OSError('Project storage directory is a symlink')
    for suffix in ('.json', '.tmp'):
        path = root / 'auto_jobs' / (project + suffix)
        if path.exists() or path.is_symlink(): result.append(path)
    return result


def _valid_relative(project: str, value: str):
    path = Path(value)
    if path.is_absolute() or '..' in path.parts:
        return False
    if len(path.parts) == 1:
        return path.name.startswith(project + '.') or path.name.startswith(project + '-')
    return len(path.parts) == 2 and (
        (path.parts[0] in {'artifacts','planner','function_targets','proposal_simulations','emulations','designs'} and path.parts[1] == project)
        or (path.parts[0] == 'auto_jobs' and path.parts[1] in {project+'.json', project+'.tmp'}))


def recover_project_deletions(store):
    """Recover interrupted renames without interfering with a live deletion."""
    trash = store.root / '.project-trash'
    if not trash.is_dir() or trash.is_symlink(): return
    for staged in trash.iterdir():
        if not staged.is_dir() or staged.is_symlink(): continue
        manifest = staged / 'manifest.json'
        try:
            record = json.loads(manifest.read_text())
            project, paths = record['project'], record['paths']
            if (not re.fullmatch(r'[a-f0-9]{32}', project) or not isinstance(paths, list)
                    or not all(isinstance(p,str) and _valid_relative(project,p) for p in paths)):
                continue
            with project_lock(store.root, project, exclusive=True):
                try: store.get(project); exists = True
                except KeyError: exists = False
                if exists:
                    for index, relative in enumerate(paths):
                        original = store.root / relative
                        target = staged / str(index)
                        if target.exists() or target.is_symlink():
                            if original.parent != store.root and original.parent.is_symlink():
                                raise OSError('Project storage directory is a symlink')
                            if original.exists() or original.is_symlink():
                                raise OSError('Project restore target already exists')
                            original.parent.mkdir(parents=True,exist_ok=True)
                            target.rename(original)
                    manifest.unlink(); staged.rmdir()
                else:
                    shutil.rmtree(staged)
        except (ProjectBusy, OSError, ValueError, KeyError, TypeError):
            # Leave recoverable data untouched for the next startup/admin.
            continue


def install_project_deletion(app, store, get, *, saas=False):
    recover_project_deletions(store)
    @app.middleware('http')
    async def project_mutation_guard(request: Request, call_next):
        match = PROJECT_PATH.match(request.url.path)
        if request.method in {'GET', 'HEAD', 'OPTIONS'} or not match:
            return await call_next(request)
        is_delete = request.method == 'DELETE' and request.url.path == '/api/projects/' + match[1]
        try:
            with project_lock(store.root, match[1], exclusive=is_delete):
                return await call_next(request)
        except ProjectBusy as exc:
            return JSONResponse({'detail': str(exc)}, status_code=409)

    @app.delete('/api/projects/{project}')
    def delete_project(project: str, expected_revision: int):
        graph = get(project)
        if graph.mode not in {'photo', 'video'}:
            raise HTTPException(422, '사진·영상 프로젝트만 이 메뉴에서 삭제할 수 있습니다.')
        if graph.revision != expected_revision:
            raise HTTPException(409, '프로젝트가 변경되었습니다. 새로고침 후 다시 시도하세요.')
        job_file = store.root / 'auto_jobs' / (project + '.json')
        if job_file.exists():
            try:
                job = json.loads(job_file.read_text())
                if job.get('status') in ACTIVE and job.get('queue_id') not in terminal_queue_jobs.get():
                    raise HTTPException(409, '사진 분석이 진행 중입니다. 완료 후 삭제하세요.')
            except (OSError, ValueError):
                raise HTTPException(409, '분석 상태를 확인할 수 없습니다. 삭제하지 않았습니다.')
        if any(j.get('project_id') == project and j.get('status') in ACTIVE
               for j in getattr(app.state, 'vision_jobs', {}).values()):
            raise HTTPException(409, '사진 분석이 진행 중입니다. 완료 후 삭제하세요.')

        # Stage by atomic renames; restore on an error before database commit.
        # Separate newly created circuit projects and browser/download copies
        # are deliberately not included.
        trash_root = store.root / '.project-trash'
        if trash_root.is_symlink():
            raise HTTPException(500, '서버 파일 정리 경로를 확인할 수 없습니다.')
        trash_root.mkdir(mode=0o700, exist_ok=True)
        staged = trash_root / (project + '-' + uuid.uuid4().hex)
        staged.mkdir(mode=0o700)
        moves = []
        marker = None; marker_created = False
        try:
            paths = _project_paths(store.root, project)
            manifest = staged / 'manifest.json'
            manifest.write_text(json.dumps({'project':project,'paths':[str(p.relative_to(store.root)) for p in paths]}))
            for index, path in enumerate(paths):
                target = staged / str(index)
                path.rename(target); moves.append((path, target))
            if saas:
                markers = store.root / '.project-deletion-commits'
                if markers.is_symlink(): raise OSError('Invalid deletion marker directory')
                markers.mkdir(mode=0o700,exist_ok=True)
                marker = markers / project
                # The marker is written before the project DB commit. A
                # different process reconciles only after checking that the
                # project is actually absent and obtaining the project lock.
                with marker.open('x') as out:
                    marker_created = True
                    out.write('deletion-requested\n'); out.flush()
                    import os
                    os.fsync(out.fileno())
            with store.connect() as conn:
                conn.execute('BEGIN IMMEDIATE')
                current = conn.execute('SELECT MAX(revision) FROM revisions WHERE project=?', (project,)).fetchone()[0]
                if current != expected_revision:
                    raise HTTPException(409, '프로젝트가 변경되었습니다. 새로고침 후 다시 시도하세요.')
                conn.execute('DELETE FROM rover_structures WHERE project=?', (project,))
                conn.execute('DELETE FROM rover_circuits WHERE project=?', (project,))
                conn.execute('DELETE FROM revisions WHERE project=?', (project,))
        except BaseException:
            for original, target in reversed(moves):
                if target.exists() or target.is_symlink(): target.rename(original)
            if marker_created: marker.unlink(missing_ok=True)
            (staged / 'manifest.json').unlink(missing_ok=True)
            staged.rmdir()
            raise
        jobs = getattr(app.state, 'vision_jobs', {})
        for jid in [jid for jid, job in list(jobs.items()) if job.get('project_id') == project]:
            jobs.pop(jid, None)
        try:
            shutil.rmtree(staged)
        except OSError:
            # Tell the user the visible project is gone but files remain in the
            # protected recovery area; startup retries their removal.
            return {'deleted_project': project, 'cleanup_pending': True}
        return {'deleted_project': project, 'cleanup_pending': False}
