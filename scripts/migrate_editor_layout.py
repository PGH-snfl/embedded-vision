"""Adopt existing ignored editor installations without deleting user changes."""
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[1]


def migrate(root=ROOT):
    pairs=[('third_party/velxio','services/editor/vendor/velxio'),
           ('.tools/avr','services/editor/.tools/avr'),
           ('.tools/npm','services/editor/.tools/npm')]
    for old_name,new_name in pairs:
        old,new=root/old_name,root/new_name
        if old.is_symlink():continue
        if old.exists():
            if new.exists():
                print(f'두 설치본을 모두 보존합니다: {old_name}, {new_name}')
                continue
            new.parent.mkdir(parents=True,exist_ok=True)
            shutil.move(str(old),str(new))
            print(f'기존 설치 보존·이동: {old_name} → {new_name}')
        if new.exists() and not old.exists():
            import os
            old.parent.mkdir(parents=True,exist_ok=True)
            old.symlink_to(os.path.relpath(new,old.parent),target_is_directory=True)


if __name__=='__main__':migrate()
