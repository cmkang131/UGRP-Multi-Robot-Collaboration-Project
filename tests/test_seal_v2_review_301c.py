"""Independent #301c review of cea627c5; run against its archived source.

No physics, network, host lock, or project worktree creation. Fixtures are tiny
read-only Python programs. Only a demonstrated wrong acceptance/rejection raises
the exception allowed by strict xfail; setup errors cannot masquerade as findings.
The directory-query cases preserve an explicitly documented scope boundary.
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


class SealAccepted(AssertionError):
    """A changed consumed input produced MOVE under the original STOP seal."""


class IrrelevantFileRejected(AssertionError):
    """A file never consumed by the program invalidated its runtime seal."""


class NormalScriptRejected(AssertionError):
    """A direct CPython control passed, but the canonical worker changed __main__."""


def gap(reason, exception=SealAccepted):
    return pytest.mark.xfail(strict=True, raises=exception, reason=reason)


def write(root, name, text):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


@pytest.fixture
def root(tmp_path):
    for name in VERIFIER_SOURCES:
        dest = tmp_path / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, dest)
    return tmp_path


def static_contract(root, *, registries=()):
    return build_contract({
        'schema': SPEC_SCHEMA, 'entry_points': ['entry.py'], 'modules': [],
        'inputs': [], 'registries': list(registries), 'dynamic_imports': {},
    }, root=root)


def run(root, value):
    return runtime.run_sealed(value, expected_sha256=value['sha256'], root=root)


def seal(root, *, registries=(), env_names=()):
    static = static_contract(root, registries=registries)
    value = runtime.trace_contract(
        static, expected_static_sha256=static['sha256'], root=root,
        cases=[{'entry': 'entry.py', 'args': []}], env_names=list(env_names),
    )
    value = json.loads(json.dumps(value))
    result = run(root, value)
    assert result['status'] == 'OK', result
    assert result['events']['review301c.command.STOP'] == 1
    return value


def require_rejection(result):
    if result['status'] == 'OK':
        # Demonstrate changed behavior, not merely an unexpectedly green API.
        assert result['events']['review301c.command.MOVE'] == 1, result
        raise SealAccepted('original digest accepted STOP -> MOVE')
    assert result['status'] == 'HOST_ERROR', result
    assert result['reason'] == 'seal-violation', result


READERS = {
    'open': 'command = open("alias/../payload.txt").read()\n',
    'pathlib': 'from pathlib import Path\ncommand = Path("alias/../payload.txt").read_text()\n',
    'os_open': 'import os\nfd = os.open("alias/../payload.txt", os.O_RDONLY)\n'
               'try:\n command = os.read(fd, 32).decode()\nfinally:\n os.close(fd)\n',
}


def dotdot_fixture(root, reader='open'):
    (root / 'deep/sub').mkdir(parents=True)
    (root / 'other/sub').mkdir(parents=True)
    (root / 'alias').symlink_to('deep/sub', target_is_directory=True)
    write(root, 'payload.txt', 'UNUSED')
    write(root, 'deep/payload.txt', 'STOP')
    write(root, 'other/payload.txt', 'MOVE')
    write(root, 'entry.py', 'import sys\n' + READERS[reader]
          + 'sys.audit("review301c.command." + command)\n')
    # POSIX resolution follows alias before traversing ..; abspath does not.
    assert (root / 'alias/../payload.txt').read_text() == 'STOP'
    assert (root / 'alias/../payload.txt').resolve() == root / 'deep/payload.txt'
    return seal(root)


@gap('C1/P1: abspath collapses symlink/.. before the audited open resolves it')
@pytest.mark.parametrize('reader', READERS)
def test_symlink_dotdot_consumed_file_drift(root, reader):
    value = dotdot_fixture(root, reader)
    write(root, 'deep/payload.txt', 'MOVE')
    require_rejection(run(root, value))


@gap('C1/P1: the traversed symlink binding is erased by abspath')
def test_symlink_dotdot_binding_drift(root):
    value = dotdot_fixture(root)
    (root / 'alias').unlink()
    (root / 'alias').symlink_to('other/sub', target_is_directory=True)
    assert (root / 'alias/../payload.txt').read_text() == 'MOVE'
    require_rejection(run(root, value))


@gap('C1/P2: normalization pins an unrelated sibling that the program never opens',
     IrrelevantFileRejected)
def test_symlink_dotdot_irrelevant_file_must_not_block(root):
    value = dotdot_fixture(root)
    write(root, 'payload.txt', 'STILL UNUSED')
    assert (root / 'alias/../payload.txt').read_text() == 'STOP'
    result = run(root, value)
    if result['status'] == 'HOST_ERROR':
        assert result['reason'] == 'seal-violation', result
        assert result['detail'] == 'sealed file drift: ' + str(root / 'payload.txt'), result
        raise IrrelevantFileRejected('unused root/payload.txt invalidated the seal')
    assert result['status'] == 'OK', result
    assert result['events']['review301c.command.STOP'] == 1


MAIN_PROGRAMS = [
    pytest.param('COMMAND = "STOP"\nimport __main__\n'
                 'assert __main__.COMMAND == COMMAND\n', 'AttributeError', id='main-globals'),
    pytest.param('import pickle\nclass Command:\n pass\n'
                 'assert isinstance(pickle.loads(pickle.dumps(Command())), Command)\n',
                 'PicklingError', id='pickle-main-class'),
]


@gap('C2/P2: exec in an anonymous dict leaves __main__ bound to the audit worker',
     NormalScriptRejected)
@pytest.mark.parametrize('source,error', MAIN_PROGRAMS)
def test_normal_script_main_module_semantics(root, source, error):
    write(root, 'entry.py', 'import __main__, sys\n'
          'sys.audit("review301c.main." + '
          '("ENTRY" if __main__.__dict__ is globals() else "WORKER"))\n'
          + source + 'import sys\nsys.audit("review301c.command.STOP")\n'
          'print("DIRECT_SCRIPT_OK")\n')
    # Identical isolation flags, interpreter, cwd, empty environment; no loader tricks.
    control = subprocess.run(
        [sys.executable, '-I', '-S', '-B', str(root / 'entry.py')],
        cwd=root, env={}, capture_output=True, text=True, timeout=10,
    )
    assert control.returncode == 0, control.stderr
    assert control.stdout.strip() == 'DIRECT_SCRIPT_OK'
    try:
        value = seal(root)
    except runtime.TraceFailure as exc:
        assert exc.report['status'] == 'HOST_ERROR', exc.report
        assert exc.report['reason'] == 'canonical-case-failed', exc.report
        assert exc.report['detail'] == error, exc.report
        assert exc.report['events']['review301c.main.WORKER'] == 1, exc.report
        raise NormalScriptRejected(f'direct CPython passes; worker raises {error}') from exc
    assert value['traces'][0]['events']['review301c.main.ENTRY'] == 1


@pytest.mark.parametrize('query', [
    'os.listdir("settings")', 'list(Path("settings").glob("*.cfg"))',
], ids=['listdir', 'glob-scandir'])
@gap('B1 documented directory/metadata boundary: names-only reads are not sealed')
def test_documented_directory_query_boundary(root, query):
    (root / 'settings').mkdir()
    write(root, 'entry.py', 'import os, sys\nfrom pathlib import Path\n'
          f'command = "MOVE" if {query} else "STOP"\n'
          'sys.audit("review301c.command." + command)\n')
    value = seal(root)
    write(root, 'settings/move.cfg', '')
    require_rejection(run(root, value))


def assert_preflight_rejects(root, value, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('a known changed dependency reached canonical process startup')
    monkeypatch.setattr(runtime, '_child', forbidden)
    result = run(root, value)
    assert result['status'] == 'HOST_ERROR', result
    assert result['reason'] == 'seal-violation', result


def test_two_hop_reexport_is_observed_and_checked_before_start(root, monkeypatch):
    write(root, 'entry.py', 'from facade import load\nimport sys\n'
          'sys.audit("review301c.command." + load("plugin").COMMAND)\n')
    write(root, 'facade.py', 'from middle import load\n')
    write(root, 'middle.py', 'from importlib import import_module as load\n')
    write(root, 'plugin.py', 'COMMAND = "STOP"\n')
    value = seal(root)
    assert 'plugin.py' not in value['static']['source_sha256']
    assert str(root / 'plugin.py') in value['traces'][0]['observed_files']
    write(root, 'plugin.py', 'COMMAND = "MOVE"\n')
    assert_preflight_rejects(root, value, monkeypatch)


def test_failed_open_absence_is_checked_before_start(root, monkeypatch):
    write(root, 'entry.py', 'import sys\ntry:\n command = open("optional.txt").read()\n'
          'except FileNotFoundError:\n command = "STOP"\n'
          'sys.audit("review301c.command." + command)\n')
    value = seal(root)
    assert value['files'][str(root / 'optional.txt')]['sha256'] is None
    write(root, 'optional.txt', 'MOVE')
    assert_preflight_rejects(root, value, monkeypatch)


def test_unrelated_unread_file_edit_does_not_block(root):
    write(root, 'entry.py', 'import sys\nsys.audit("review301c.command.STOP")\n')
    write(root, 'unrelated.md', 'before')
    value = seal(root)
    assert str(root / 'unrelated.md') not in value['files']
    write(root, 'unrelated.md', 'after')
    result = run(root, value)
    assert result['status'] == 'OK', result
    assert result['events']['review301c.command.STOP'] == 1


def test_declared_but_unread_setting_edit_does_not_block(root, monkeypatch):
    write(root, 'entry.py', 'import sys\nsys.audit("review301c.command.STOP")\n')
    monkeypatch.setenv('REVIEW_UNUSED_SETTING', 'before')
    value = seal(root, env_names=['REVIEW_UNUSED_SETTING'])
    assert 'REVIEW_UNUSED_SETTING' not in value['environment']
    monkeypatch.setenv('REVIEW_UNUSED_SETTING', 'after')
    assert run(root, value)['status'] == 'OK'


def test_whole_json_read_intentionally_pins_unselected_row(root, monkeypatch):
    write(root, 'entry.py', 'import json, sys\nfrom pathlib import Path\n'
          'data = json.loads(Path("catalog.json").read_text())\n'
          'sys.audit("review301c.command." + data["used"])\n')
    write(root, 'catalog.json', '{"used":"STOP","unused":1}')
    value = seal(root, registries=[{'path': 'catalog.json', 'keys': ['used']}])
    assert str(root / 'catalog.json') in value['files']
    write(root, 'catalog.json', '{"used":"STOP","unused":2}')
    assert_preflight_rejects(root, value, monkeypatch)
