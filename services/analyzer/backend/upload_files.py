"""Own new upload files until their project revision is committed.

Existing files are never overwritten or removed. This matters for failed
multi-frame uploads and for a concurrent image upload that loses a revision
race after it has created its own file.
"""
from pathlib import Path


class PendingUploadFiles:
    def __init__(self):
        self._created: list[Path] = []
        self._committed = False

    def __enter__(self):
        return self

    def write(self, path: Path, data: bytes):
        # Exclusive creation prevents a UUID collision from overwriting (or
        # subsequently deleting) an existing project's file.
        with path.open('xb') as output:
            self._created.append(path)
            output.write(data)

    def commit(self):
        self._committed = True

    def __exit__(self, exc_type, exc, tb):
        if not self._committed:
            errors = []
            for path in reversed(self._created):
                try:
                    path.unlink(missing_ok=True)
                except OSError as error:
                    errors.append(error)
            if errors:
                raise RuntimeError('실패한 업로드 파일을 정리하지 못했습니다.') from errors[0]
        return False
