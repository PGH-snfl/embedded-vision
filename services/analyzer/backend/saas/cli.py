"""Explicit account provisioning. Passwords are read through getpass, never argv/logs."""
import argparse
import getpass
from .repository import Repository
from .settings import Settings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command",choices=["init"])
    parser.add_argument("--email",required=True)
    parser.add_argument("--workspace",required=True)
    args = parser.parse_args()
    password = getpass.getpass("새 비밀번호 (12자 이상): ")
    if password != getpass.getpass("비밀번호 확인: "):
        raise SystemExit("비밀번호가 다릅니다.")
    repo = Repository(Settings.from_env())
    try:
        _, wid = repo.provision(args.email,password,args.workspace)
    except (ValueError, __import__('sqlite3').IntegrityError) as exc:
        raise SystemExit("계정을 만들지 못했습니다. 이메일 중복 또는 입력 조건을 확인하세요.") from exc
    print("계정·작업공간 생성 완료:",wid)


if __name__ == "__main__":
    main()
