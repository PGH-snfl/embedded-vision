import os
from pathlib import Path
import pytest
from backend.saas.envfile import WorkerEnvironment,read_key,configure


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','')


def private_file(tmp_path,body):
    path=tmp_path/'worker.env';path.write_text(body);path.chmod(0o600);return path


def test_private_file_populates_and_refreshes_environment(tmp_path):
    path=private_file(tmp_path,'# private worker config\nOPENAI_API_KEY="unit-test-token-one"\n')
    loader=WorkerEnvironment(path)
    assert loader.refresh() and os.environ['OPENAI_API_KEY']=='unit-test-token-one'
    path.write_text('OPENAI_API_KEY=unit-test-token-two\n')
    assert loader.refresh() and os.environ['OPENAI_API_KEY']=='unit-test-token-two'
    path.write_text('OPENAI_API_KEY=\n')
    assert loader.refresh() is False and 'OPENAI_API_KEY' not in os.environ


def test_deployment_environment_has_precedence(tmp_path,monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','deployment-test-token')
    loader=WorkerEnvironment(private_file(tmp_path,'OPENAI_API_KEY=file-test-token\n'))
    assert loader.refresh() and os.environ['OPENAI_API_KEY']=='deployment-test-token'


def test_key_file_is_never_executed_as_shell(tmp_path):
    marker=tmp_path/'not-created'
    path=private_file(tmp_path,f'OPENAI_API_KEY=$(touch${{IFS}}{marker})\n')
    assert read_key(path).startswith('$(touch')
    assert not marker.exists()
    path.write_text('PATH=/untrusted\nOPENAI_API_KEY=unit-test-token\n')
    with pytest.raises(ValueError):read_key(path)


def test_invalid_rotation_removes_old_key_and_hides_content(tmp_path):
    path=private_file(tmp_path,'OPENAI_API_KEY=unit-test-token\n');loader=WorkerEnvironment(path)
    loader.refresh();path.chmod(0o644)
    with pytest.raises(ValueError) as error:loader.refresh()
    assert 'unit-test-token' not in str(error.value)
    assert 'OPENAI_API_KEY' not in os.environ


def test_symlink_and_duplicate_entries_are_rejected(tmp_path):
    path=private_file(tmp_path,'OPENAI_API_KEY=one\nOPENAI_API_KEY=two\n')
    with pytest.raises(ValueError):read_key(path)
    link=tmp_path/'link.env';link.symlink_to(path)
    with pytest.raises(ValueError):read_key(link)


def test_configuration_is_atomic_private_and_never_prints_key(tmp_path,monkeypatch,capsys):
    token='configuration-unit-test-token'
    monkeypatch.setattr('backend.saas.envfile.getpass.getpass',lambda _:token)
    path=tmp_path/'secrets'/'worker.env';configure(path)
    assert read_key(path)==token and path.stat().st_mode&0o777==0o600
    assert token not in capsys.readouterr().out
    assert not list(path.parent.glob('.worker-env-*'))


def test_bad_input_does_not_overwrite_existing_file(tmp_path,monkeypatch):
    path=private_file(tmp_path,'OPENAI_API_KEY=previous-test-token\n')
    monkeypatch.setattr('backend.saas.envfile.getpass.getpass',lambda _:'bad token')
    with pytest.raises(ValueError):configure(path)
    assert read_key(path)=='previous-test-token'


def test_cli_requires_terminal_for_secret_entry(tmp_path):
    import subprocess,sys
    path=private_file(tmp_path,'OPENAI_API_KEY=previous-test-token\n')
    result=subprocess.run([sys.executable,'-m','backend.saas.envfile','configure'],
        input='not-a-real-key\n',text=True,capture_output=True,
        env={**os.environ,'EV_SAAS_WORKER_ENV':str(path)},timeout=10)
    assert result.returncode != 0 and '터미널' in result.stderr
    assert 'not-a-real-key' not in result.stdout+result.stderr
    assert read_key(path)=='previous-test-token'
