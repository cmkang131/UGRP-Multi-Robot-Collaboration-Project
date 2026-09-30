"""Independent delta review of #301 at b7f53d34; run in its git archive.

Only read-only Python fixtures, dummy child interpreters, and temporary files.
The three original counterexamples now require ordinary passing assertions.
"""
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from harness.execution_dependency_contract import (
    ROOT, SPEC_SCHEMA, VERIFIER_SOURCES, build_contract,
)
from harness import runtime_provenance as runtime
from scripts.trace_execution_dependencies import main as cli


class ReceiptInvalidatedBySaving(AssertionError):
    """The successful trace's own new output blocks its first unchanged run."""


class EnvironmentCopyRejected(AssertionError):
    """A normal read-only environment copy works directly but fails in tracing."""


def write(root, name, source):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source)


@pytest.fixture
def root(tmp_path):
    result = (tmp_path / 'source').resolve()
    for name in VERIFIER_SOURCES:
        path = result / name
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, path)
    return result


def static(root):
    return build_contract({
        'schema': SPEC_SCHEMA, 'entry_points': ['entry.py'], 'modules': [],
        'inputs': [], 'registries': [], 'dynamic_imports': {},
    }, root=root)


def trace(root, *, env=(), policy=None):
    declaration = static(root)
    value = runtime.trace_contract(
        declaration, expected_static_sha256=declaration['sha256'], root=root,
        cases=[{'entry': 'entry.py', 'args': []}], env_names=list(env), policy=policy,
    )
    return json.loads(json.dumps(value))


def run(root, value):
    return runtime.run_sealed(value, expected_sha256=value['sha256'], root=root)


def assert_stop(result):
    assert result['status'] == 'OK', result
    assert result['events']['review301d.command.STOP'] == 1


def reject_before_child(root, value, monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail('changed known dependency reached child startup')
    monkeypatch.setattr(runtime, '_child', unexpected)
    result = run(root, value)
    assert result['status'] == 'HOST_ERROR', result
    assert result['reason'] == 'seal-violation', result


@pytest.mark.parametrize('change', ['bytes', 'intermediate-link'])
def test_absolute_link_target_with_nested_relative_dotdot(root, monkeypatch, change):
    (root / 'transit').mkdir()
    (root / 'real/leaf').mkdir(parents=True)
    (root / 'jump').symlink_to('transit/../real', target_is_directory=True)
    (root / 'view').symlink_to(root / 'jump/leaf', target_is_directory=True)
    write(root, 'real/payload.txt', 'STOP')
    write(root, 'entry.py', 'import sys\n'
          'sys.audit("review301d.command." + open("view/../payload.txt").read())\n')
    value = trace(root)
    assert_stop(run(root, value))
    state = value['files'][str(root / 'view/../payload.txt')]
    assert state['realpath'] == str(root / 'real/payload.txt')
    assert state['links'][str(root / 'view')] == str(root / 'jump/leaf')
    assert state['links'][str(root / 'jump')] == 'transit/../real'
    if change == 'bytes':
        write(root, 'real/payload.txt', 'MOVE')
    else:
        (root / 'jump').unlink()
        (root / 'jump').symlink_to('real', target_is_directory=True)
        assert (root / 'view/../payload.txt').read_text() == 'STOP'
    reject_before_child(root, value, monkeypatch)


def test_new_symlink_spelling_is_not_accepted_as_plain_equivalent_path(root, monkeypatch):
    write(root, 'payload.txt', 'STOP')
    (root / 'alias').symlink_to('payload.txt')
    write(root, 'entry.py', 'import os, sys\n'
          'sys.audit("review301d.command." + open(os.getenv("REVIEW_PATH")).read())\n')
    monkeypatch.setenv('REVIEW_PATH', 'payload.txt')
    value = trace(root, env=['REVIEW_PATH'], policy={
        'environment': 'warn', 'identity': 'abort', 'reason': 'alternate path probe',
    })
    assert_stop(run(root, value))
    monkeypatch.setenv('REVIEW_PATH', 'alias')
    result = run(root, value)
    assert result['status'] == 'HOST_ERROR', result
    assert 'unsealed or changed file read' in result['detail'], result
    assert 'review301d.command.STOP' not in result['events']


def test_directory_query_uses_same_link_dotdot_identity(root, monkeypatch):
    (root / 'real/leaf').mkdir(parents=True)
    (root / 'view').symlink_to('real/leaf', target_is_directory=True)
    (root / 'real/settings').mkdir()
    write(root, 'entry.py', 'import os, sys\n'
          'names = os.listdir("view/../settings")\n'
          'sys.audit("review301d.command." + ("MOVE" if names else "STOP"))\n')
    value = trace(root)
    assert_stop(run(root, value))
    assert value['directories'][str(root / 'view/../settings')]['realpath'] == str(root / 'real/settings')
    write(root, 'real/settings/new.cfg', '')
    reject_before_child(root, value, monkeypatch)


def test_main_dataclass_pickle_and_globals_survive_exit_callbacks(root):
    source = ('import atexit, pickle, sys\nfrom dataclasses import dataclass\n'
              '@dataclass\nclass Command:\n value: str = "STOP"\n'
              'def finish():\n import __main__\n'
              ' assert __main__.__dict__ is globals()\n'
              ' restored = pickle.loads(pickle.dumps(Command()))\n'
              ' assert isinstance(restored, Command) and restored.value == "STOP"\n'
              ' sys.audit("review301d.command." + restored.value)\n'
              ' print("DIRECT_OK")\natexit.register(finish)\n')
    write(root, 'entry.py', source)
    direct = subprocess.run([sys.executable, '-I', '-S', '-B', str(root / 'entry.py')],
                            cwd=root, env={}, capture_output=True, text=True, timeout=10)
    assert direct.returncode == 0, direct.stderr
    assert direct.stdout.strip() == 'DIRECT_OK'
    value = trace(root)
    assert value['traces'][0]['events']['review301d.command.STOP'] == 1
    assert_stop(run(root, value))


@pytest.mark.parametrize('inside', [
    pytest.param(True, id='output-inside-root'),
    pytest.param(False, id='output-outside-root-control'),
])
def test_cli_receipt_save_and_first_run(root, tmp_path, inside):
    write(root, 'helper.py', 'COMMAND = "STOP"\n')
    write(root, 'entry.py', 'import helper, sys\n'
          'sys.audit("review301d.command." + helper.COMMAND)\n')
    declaration = static(root)
    write(root, 'static.json', json.dumps(declaration))
    write(root, 'cases.json', '[{"entry":"entry.py","args":[]}]')
    output = (root if inside else tmp_path) / 'runtime-seal.json'
    assert cli(['--root', str(root), 'trace', '--static-contract', str(root / 'static.json'),
                '--expected-static-sha256', declaration['sha256'],
                '--cases', str(root / 'cases.json'), '--output', str(output)]) == 0
    value = json.loads(output.read_text())
    assert value['traces'][0]['events']['review301d.command.STOP'] == 1
    assert str(root) in value['directories']
    assert output.name not in [row[0] for row in value['directories'][str(root)]['entries']]
    result = run(root, value)
    if inside and result['status'] == 'HOST_ERROR':
        assert result['reason'] == 'seal-violation', result
        assert result['detail'] == 'sealed directory drift: ' + str(root), result
        # Same seal/digest and all consumed inputs work after moving only the
        # newly created receipt out of the staged input tree.
        output.rename(tmp_path / 'moved-runtime-seal.json')
        assert_stop(run(root, value))
        raise ReceiptInvalidatedBySaving('trace succeeds; its own output blocks first run')
    assert_stop(result)


@pytest.mark.parametrize('binary', [False, True], ids=['environ', 'environb'])
def test_readonly_environment_copy_keeps_python_semantics(root, monkeypatch, binary):
    expression = 'os.environb.copy()[b"REVIEW_MODE"].decode()' if binary else 'os.environ.copy()["REVIEW_MODE"]'
    write(root, 'entry.py', 'import os, sys\n'
          f'command = {expression}\n'
          'sys.audit("review301d.command." + command)\nprint(command)\n')
    monkeypatch.setenv('REVIEW_MODE', 'STOP')
    direct = subprocess.run([sys.executable, '-I', '-S', '-B', str(root / 'entry.py')],
                            cwd=root, env={'REVIEW_MODE': 'STOP'},
                            capture_output=True, text=True, timeout=10)
    assert direct.returncode == 0, direct.stderr
    assert direct.stdout.strip() == 'STOP'
    try:
        value = trace(root, env=['REVIEW_MODE'])
    except runtime.TraceFailure as exc:
        assert exc.report['reason'] == 'canonical-case-failed', exc.report
        assert exc.report['detail'] == 'AttributeError', exc.report
        assert not hasattr(runtime._Environment(None, {}), 'copy')
        raise EnvironmentCopyRejected('direct Python succeeds; adapter has no copy()') from exc
    assert_stop(run(root, value))
    assert value['environment']['REVIEW_MODE']['present']
    monkeypatch.setenv('REVIEW_MODE', 'MOVE')
    result = run(root, value)
    assert result['status'] == 'HOST_ERROR', result
    assert result['reason'] == 'seal-violation', result


def test_readonly_environment_dict_copy_control_tracks_drift(root, monkeypatch):
    write(root, 'entry.py', 'import os, sys\n'
          'sys.audit("review301d.command." + dict(os.environ)["REVIEW_MODE"])\n')
    monkeypatch.setenv('REVIEW_MODE', 'STOP')
    value = trace(root, env=['REVIEW_MODE'])
    assert_stop(run(root, value))
    monkeypatch.setenv('REVIEW_MODE', 'MOVE')
    result = run(root, value)
    assert result['status'] == 'HOST_ERROR', result
    assert 'environment drift: REVIEW_MODE' in result['detail'], result
