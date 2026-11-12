"""Owner-only worker secret file, parsed as data (never sourced as shell code)."""
import argparse
import getpass
import os
from pathlib import Path
import stat
import sys
import tempfile
from .settings import ROOT


def worker_env_path():
    return Path(os.getenv("EV_SAAS_WORKER_ENV", str(ROOT / ".runtime/saas-worker.env")))


def read_key(path):
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return ""
    except OSError:
        raise ValueError("키 환경변수 파일을 열 수 없습니다.") from None
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
            raise ValueError("키 환경변수 파일은 소유자만 읽을 수 있는 일반 파일(권한 600)이어야 합니다.")
        raw = stream.read(8193)
    if len(raw) > 8192:
        raise ValueError("키 환경변수 파일이 너무 큽니다.")
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeError:
        raise ValueError("키 환경변수 파일은 UTF-8 텍스트여야 합니다.") from None
    value, seen = "", False
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, sep, entry = line.partition("=")
        if name.strip() != "OPENAI_API_KEY" or not sep or seen:
            raise ValueError("키 파일에는 OPENAI_API_KEY 항목 하나만 입력하세요.")
        seen = True
        value = entry.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if any(c.isspace() or ord(c) < 32 or ord(c) > 126 for c in value):
            raise ValueError("API 키에 공백이나 제어 문자를 넣을 수 없습니다.")
    return value


class WorkerEnvironment:
    def __init__(self, path=None):
        self.path = path or worker_env_path()
        self.external = bool(os.getenv("OPENAI_API_KEY", "").strip())

    def refresh(self):
        # Deployment-provided environment variables retain precedence.
        if self.external:
            return bool(os.getenv("OPENAI_API_KEY", "").strip())
        try:
            key = read_key(self.path)
        except ValueError:
            os.environ.pop("OPENAI_API_KEY", None)
            raise
        if key:
            os.environ["OPENAI_API_KEY"] = key
        else:
            os.environ.pop("OPENAI_API_KEY", None)
        return bool(key)


def configure(path):
    key = getpass.getpass("OpenAI API 키를 붙여넣고 Enter (화면에 표시되지 않음): ").strip()
    if not key or len(key) > 4096 or any(c.isspace() or ord(c) < 32 or ord(c) > 126 for c in key):
        raise ValueError("빈 키나 공백이 포함된 키는 저장하지 않았습니다.")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink():
        raise ValueError("심볼릭 링크에는 키를 저장하지 않습니다.")
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="w",encoding="utf-8",dir=path.parent,prefix=".worker-env-",delete=False) as stream:
            temp_path = Path(stream.name)
            os.chmod(temp_path, 0o600)
            stream.write("OPENAI_API_KEY="+key+"\n")
        os.replace(temp_path,path)
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink()
    print("API 키를 비공개 환경변수 파일에 저장했습니다.")
    print("파일:",path)
    print("실행 중인 SaaS worker가 다음 대기 주기에 자동 반영합니다.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command",choices=["configure","check"])
    args = parser.parse_args()
    try:
        if args.command == "configure":
            if not sys.stdin.isatty():
                raise ValueError("키 입력은 터미널에서 bash configure_saas_openai.sh를 직접 실행하세요.")
            configure(worker_env_path())
        else:
            ready = WorkerEnvironment().refresh()
            print("OPENAI_API_KEY 설정됨" if ready else "OPENAI_API_KEY 미설정")
            print("키 값은 출력하지 않았으며 API 요청은 보내지 않았습니다.")
    except ValueError as exc:
        raise SystemExit(str(exc)) from None


if __name__ == "__main__":
    main()
