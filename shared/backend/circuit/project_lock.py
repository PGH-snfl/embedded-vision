"""Cross-process project locks for requests and background jobs."""
import fcntl
import os
import re
from contextlib import contextmanager


class ProjectBusy(Exception):
    pass


@contextmanager
def project_lock(root, project, *, exclusive=False, wait=False):
    if not re.fullmatch(r'[a-f0-9]{32}', project):
        raise ValueError('Invalid project ID')
    folder = root / '.project-locks'
    folder.mkdir(mode=0o700, exist_ok=True)
    fd = os.open(folder / project, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, (fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH) | (0 if wait else fcntl.LOCK_NB))
        except BlockingIOError:
            raise ProjectBusy('프로젝트 작업이 진행 중입니다. 완료 후 다시 시도하세요.') from None
        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)
