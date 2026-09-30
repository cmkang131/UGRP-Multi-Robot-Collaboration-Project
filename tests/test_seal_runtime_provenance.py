"""Actual isolated Python runs of #301/#301b counterexamples; no physics/network.

The static analyser is unchanged. Each test saves the external digest before a
mutation, then requires HOST_ERROR from the opt-in runtime path. No xfails.
"""
import copy
import json
from pathlib import Path
import shutil

import pytest

from harness.execution_dependency_contract import ROOT, SPEC_SCHEMA, VERIFIER_SOURCES, build_contract
from harness.runtime_provenance import digest, run_sealed, trace_contract
from scripts.trace_execution_dependencies import main


def write(root, name, text):
    p = root / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


@pytest.fixture
def root(tmp_path):
    for name in VERIFIER_SOURCES:
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, tmp_path / name)
    return tmp_path


def seal(root, *, entry='entry.py', inputs=(), registries=(), cases=None, env=(), policy=None):
    spec = {'schema': SPEC_SCHEMA, 'entry_points': [entry], 'modules': [],
            'inputs': list(inputs), 'registries': list(registries), 'dynamic_imports': {}}
    static = build_contract(spec, root=root)
    value = trace_contract(static, expected_static_sha256=static['sha256'], root=root,
                           cases=cases or [{'entry': entry, 'args': []}],
                           env_names=list(env), policy=policy)
    value = json.loads(json.dumps(value))
    assert run_sealed(value, expected_sha256=value['sha256'], root=root)['status'] == 'OK'
    return value


def rejects(root, value, detail=None):
    result = run_sealed(value, expected_sha256=value['sha256'], root=root)
    assert result['status'] == 'HOST_ERROR', result
    assert result['reason'] == 'seal-violation', result
    if detail:
        assert detail in result['detail'], result
    return result


LOADERS = [
    ('R2-alias', '', 'import importlib\nload = importlib.import_module\nmod = load("plugin")'),
    ('R2-getattr', '', 'import importlib\nmod = getattr(importlib, "import_module")("plugin")'),
    ('R2-builtin-alias', '', 'from builtins import __import__ as load\nmod = load("plugin")'),
    ('R2-builtin-attr', '', 'import builtins\nmod = builtins.__import__("plugin")'),
    ('N1-function', 'from importlib import import_module as load', 'from bridge import load\nmod = load("plugin")'),
    ('N1-builtin', 'from builtins import __import__ as load', 'import bridge\nmod = bridge.load("plugin")'),
    ('N1-module', 'import importlib as il', 'from bridge import il\nmod = il.import_module("plugin")'),
    ('N1-wildcard', 'from importlib import import_module as load\n__all__ = ["load"]',
     'from bridge import *\nmod = load("plugin")'),
    ('N4-from', '', 'from importlib import __import__ as load\nmod = load("plugin")'),
    ('N4-attr', '', 'import importlib\nmod = importlib.__import__("plugin")'),
]


@pytest.mark.parametrize('name,bridge,entry', LOADERS, ids=[r[0] for r in LOADERS])
def test_review_loader_reads(root, name, bridge, entry):
    write(root, 'bridge.py', bridge + '\n')
    write(root, 'entry.py', entry + '\nassert mod.COMMAND == "STOP"\n')
    write(root, 'plugin.py', 'COMMAND = "STOP"\n')
    value = seal(root)
    assert str(root / 'plugin.py') in value['files']
    if name.startswith(('N1', 'N4')):
        assert 'plugin.py' not in value['static']['source_sha256']
    write(root, 'plugin.py', 'COMMAND = "MOVE"\n')
    rejects(root, value)


@pytest.mark.parametrize('symlink', [False, True], ids=['R1', 'N6'])
def test_review_wildcard(root, symlink):
    write(root, 'entry.py', 'from pkg import *\nassert child.COMMAND == "STOP"\n')
    write(root, 'pkg/__init__.py', '__all__ = ["child"]\n')
    name = 'child_impl/__init__.py' if symlink else 'pkg/child.py'
    write(root, name, 'COMMAND = "STOP"\n')
    if symlink:
        (root / 'pkg/child').symlink_to('../child_impl', target_is_directory=True)
    value = seal(root)
    write(root, name, 'COMMAND = "MOVE"\n')
    rejects(root, value)


@pytest.mark.parametrize('symlink', [False, True], ids=['R3', 'N7'])
def test_review_script_folder(root, symlink):
    write(root, 'jobs/start.py', 'import helper\nassert helper.COMMAND == "STOP"\n')
    write(root, 'jobs/helper.py', 'COMMAND = "STOP"\n')
    if symlink:
        (root / 'entry.py').symlink_to('jobs/start.py')
    value = seal(root, entry='entry.py' if symlink else 'jobs/start.py')
    write(root, 'jobs/helper.py', 'COMMAND = "MOVE"\n')
    rejects(root, value)


@pytest.mark.parametrize('before,after,consumer', [
    ('{"schema":"v1","policy":{"commands":{"STOP":0,"MOVE":1}}}',
     '{"schema":"v1","policy":{"commands":{"MOVE":1,"STOP":0}}}',
     'assert next(iter(data["policy"]["commands"])) == "STOP"'),
    ('{"schema":"v1","policy":{"gain":9007199254740992.0}}',
     '{"schema":"v1","policy":{"gain":9007199254740993.0}}',
     'assert data["policy"]["gain"] == Decimal("9007199254740992")'),
    ('{"policy":{"command":"STOP"}}', '{"schema":null,"policy":{"command":"STOP"}}',
     'assert data.get("schema", "legacy") == "legacy"'),
    ('{"policy":{"preset":"safe"},"presets":{"safe":{"command":"STOP"}}}',
     '{"policy":{"preset":"safe"},"presets":{"safe":{"command":"MOVE"}}}',
     'assert data["presets"][data["policy"]["preset"]]["command"] == "STOP"'),
], ids=['R4-order', 'N2-decimal', 'N5-schema-presence', 'B1-reference-chain'])
def test_review_registry_bytes(root, before, after, consumer):
    write(root, 'entry.py', 'import json\nfrom decimal import Decimal\nfrom pathlib import Path\n'
          'data = json.loads(Path("registry.json").read_text(), parse_float=Decimal)\n' + consumer + '\n')
    write(root, 'registry.json', before)
    value = seal(root, registries=[{'path': 'registry.json', 'keys': ['policy']}])
    assert 'registry.json' not in value['static']['source_sha256']
    assert str(root / 'registry.json') in value['files']
    write(root, 'registry.json', after)
    rejects(root, value)


def test_N3_same_bytes_source_symlink_target(root):
    source = 'from pathlib import Path\nassert Path(__file__).resolve().parent.name == "stop"\n'
    for folder in ('stop', 'move'):
        write(root, folder + '/main.py', source)
    (root / 'entry.py').symlink_to('stop/main.py')
    value = seal(root, inputs=['stop/main.py', 'move/main.py'])
    (root / 'entry.py').unlink()
    (root / 'entry.py').symlink_to('move/main.py')
    rejects(root, value, 'sealed file drift')


def test_N3_declared_xml_link_selects_other_declared_asset(root):
    write(root, 'entry.py', 'from pathlib import Path\nimport xml.etree.ElementTree as ET\n'
          'scene = Path("scene.xml").resolve()\nchild = ET.parse(scene).find("include").get("file")\n'
          'assert ET.parse(scene.parent / child).getroot().get("command") == "STOP"\n')
    for folder, command in [('a', 'STOP'), ('b', 'MOVE')]:
        write(root, folder + '/scene.xml', '<mujoco><include file="body.xml"/></mujoco>')
        write(root, folder + '/body.xml', f'<body command="{command}"/>')
    (root / 'scene.xml').symlink_to('a/scene.xml')
    value = seal(root, inputs=['scene.xml', 'a/scene.xml', 'b/scene.xml', 'a/body.xml', 'b/body.xml'])
    (root / 'scene.xml').unlink()
    (root / 'scene.xml').symlink_to('b/scene.xml')
    rejects(root, value, 'sealed file drift')


@pytest.mark.parametrize('name', ['map.json', 'calibration.yaml', 'scene.xml', 'mesh.obj', 'fit.npz'])
def test_undeclared_asset_bytes(root, name):
    write(root, 'entry.py', f'from pathlib import Path\nassert Path({name!r}).read_bytes() == b"STOP"\n')
    write(root, name, 'STOP')
    value = seal(root)
    write(root, name, 'MOVE')
    rejects(root, value)


@pytest.mark.parametrize('binary', [False, True])
@pytest.mark.parametrize('action', ['abort', 'warn'])
def test_environment_runtime_comparison(root, monkeypatch, action, binary):
    expr = 'os.environb.get(b"SEAL_MODE")' if binary else 'os.getenv("SEAL_MODE")'
    write(root, 'entry.py', f'import os\nvalue = {expr}\n')
    monkeypatch.setenv('SEAL_MODE', 'STOP')
    value = seal(root, env=['SEAL_MODE'], policy={
        'environment': action, 'identity': 'abort', 'reason': 'reviewed diagnostic' if action == 'warn' else ''})
    assert value['environment']['SEAL_MODE']['present']
    assert 'STOP' not in json.dumps(value['environment'])
    monkeypatch.setenv('SEAL_MODE', 'MOVE')
    if action == 'abort':
        rejects(root, value, 'environment drift')
    else:
        result = run_sealed(value, expected_sha256=value['sha256'], root=root)
        assert result['status'] == 'OK'
        assert any('environment drift: SEAL_MODE' in w for w in result['warnings'])


@pytest.mark.parametrize('operation', [
    'open(path).read()',
    '__import__("pathlib").Path(path).read_text()',
    'fd = os.open(path, os.O_RDONLY)\nos.read(fd, 10)',
    'exec(compile(open(path).read(), path, "exec"))',
])
def test_unseen_read_aborts_before_consumer_even_if_exception_caught(root, monkeypatch, operation):
    write(root, 'entry.py', 'import os\npath = os.getenv("SEAL_PATH")\n'
          'if path:\n try:\n  ' + operation.replace('\n', '\n  ') + '\n except BaseException:\n  pass\n')
    monkeypatch.delenv('SEAL_PATH', raising=False)
    value = seal(root, env=['SEAL_PATH'], policy={
        'environment': 'warn', 'identity': 'abort', 'reason': 'exercise unseen branch'})
    write(root, 'new.py', 'raise RuntimeError("MUST NEVER EXECUTE")')
    monkeypatch.setenv('SEAL_PATH', 'new.py')
    rejects(root, value, 'unsealed or changed file read')


@pytest.mark.parametrize('source,event', [
    ('import subprocess\nsubprocess.run(["/bin/true"])', 'subprocess.Popen'),
    ('import os\nos.system("true")', 'os.system'),
    ('import os\nos.fork()', 'os.fork'),
    ('import ctypes', 'native package'),
    ('import socket\nsocket.socket().connect(("127.0.0.1", 9))', 'socket.'),
    ('open("output", "w").write("x")', 'read-only'),
])
def test_unsupported_canonical_run_never_creates_seal(root, source, event):
    write(root, 'entry.py', source + '\n')
    with pytest.raises(ValueError, match=event):
        seal(root)
    assert not (root / 'output').exists()


def test_static_unobserved_union_and_multiple_cases(root):
    write(root, 'entry.py', 'import sys\nfrom pathlib import Path\nPath(sys.argv[1]).read_text()\n')
    for name in ('a.txt', 'b.txt', 'never-read.txt'):
        write(root, name, 'fixed')
    value = seal(root, inputs=['never-read.txt'], cases=[
        {'entry': 'entry.py', 'args': ['a.txt']}, {'entry': 'entry.py', 'args': ['b.txt']}])
    assert all(str(root / name) in value['files'] for name in ('a.txt', 'b.txt', 'never-read.txt'))
    assert run_sealed(value, expected_sha256=value['sha256'], root=root, case_index=1)['status'] == 'OK'
    write(root, 'never-read.txt', 'changed')
    rejects(root, value)


def test_external_digest_and_legacy_rejected(root):
    write(root, 'entry.py', 'pass\n')
    value = seal(root)
    changed = copy.deepcopy(value)
    changed['files'].pop(str(root / 'entry.py'))
    changed['sha256'] = digest({k: v for k, v in changed.items() if k != 'sha256'})
    assert run_sealed(changed, expected_sha256=value['sha256'], root=root)['status'] == 'HOST_ERROR'
    assert run_sealed(value['static'], expected_sha256=value['static']['sha256'], root=root)['status'] == 'HOST_ERROR'


def test_identity_abort_or_warn(root, monkeypatch):
    from harness import runtime_provenance as rp
    write(root, 'entry.py', 'pass\n')
    abort = seal(root)
    warn = seal(root, policy={'environment': 'abort', 'identity': 'warn', 'reason': 'version probe'})
    original = rp.identity
    monkeypatch.setattr(rp, 'identity', lambda: {**original(), 'packages': [['fake', 'changed']]})
    rejects(root, abort, 'identity drift')
    result = run_sealed(warn, expected_sha256=warn['sha256'], root=root)
    assert result['status'] == 'OK'
    assert result['warnings'] == ['interpreter/library identity drift: version probe']


def test_cli_no_overwrite_or_implicit_upgrade(root, tmp_path):
    output = tmp_path / 'old-seal.json'
    output.write_text('original bytes\n')
    with pytest.raises(SystemExit):
        main(['--root', str(root), 'trace', '--static-contract', 'missing',
              '--expected-static-sha256', '0' * 64, '--cases', 'missing', '--output', str(output)])
    assert output.read_text() == 'original bytes\n'


def test_credentials_not_inherited_or_saved(root, monkeypatch):
    write(root, 'entry.py', 'import os\nassert os.getenv("PRIVATE_TOKEN") is None\n')
    monkeypatch.setenv('PRIVATE_TOKEN', 'DO-NOT-SAVE-ME')
    value = seal(root)
    assert 'DO-NOT-SAVE-ME' not in json.dumps(value)
    with pytest.raises(ValueError, match='credential'):
        seal(root, env=['PRIVATE_TOKEN'])


@pytest.mark.parametrize('change', ['missing-entry', 'duplicate-id', 'launcher'],
                         ids=['R5-missing', 'R5-duplicate', 'R6-launcher'])
def test_review_standard_workflow_consumer(root, change):
    write(root, 'sim/__init__.py', '')
    write(root, 'entry.py', 'from pathlib import Path\n'
          'from sim.workflow_manager import _row, _runner_command\n'
          'row, _ = _row(Path.cwd(), "used")\n'
          'assert _runner_command(Path.cwd(), row, [], record=None)[0][2] == "entry"\n')
    write(root, 'unused.py', 'pass\n')
    rows = [dict(id=name, entry=f'{entry}.py', runner=entry, version='1', output_flag=None,
                 output_kind='directory', required_inputs=[], side_effect='offline_analysis')
            for name, entry in [('used', 'entry'), ('unused', 'unused')]]
    catalog = {'schema': 'ugrp.local_workflow_catalog.v1', 'workflows': rows}
    write(root, 'configs/simulation_workflows.json', json.dumps(catalog))
    value = seal(root, registries=[{'path': 'configs/simulation_workflows.json',
                                    'keys': ['workflows', {'id': 'used'}]}])
    if change == 'launcher':
        path = root / 'sim/workflow_manager.py'
        text = path.read_text()
        needle = 'return [sys.executable, "-m", runner, *argv], output'
        assert text.count(needle) == 1
        path.write_text(text.replace(needle, 'return [sys.executable, "-m", "alternate", *argv], output'))
    else:
        if change == 'missing-entry':
            rows[1]['entry'] = 'missing.py'
        else:
            rows.append(dict(rows[1]))
        write(root, 'configs/simulation_workflows.json', json.dumps(catalog))
    rejects(root, value)


def test_xml_include_is_observed_without_declaring_child(root):
    write(root, 'entry.py', 'import xml.etree.ElementTree as ET\n'
          'child = ET.parse("scene.xml").find("include").get("file")\n'
          'assert ET.parse(child).getroot().get("command") == "STOP"\n')
    write(root, 'scene.xml', '<mujoco><include file="assets/body.xml"/></mujoco>')
    write(root, 'assets/body.xml', '<body command="STOP"/>')
    value = seal(root, inputs=['scene.xml'])
    assert 'assets/body.xml' not in value['static']['source_sha256']
    write(root, 'assets/body.xml', '<body command="MOVE"/>')
    rejects(root, value)


def test_unknown_environment_name_is_never_covered_by_warn(root, monkeypatch):
    write(root, 'entry.py', 'import os\nif os.getenv("SEAL_BRANCH"):\n os.getenv("NEW_SETTING")\n')
    monkeypatch.delenv('SEAL_BRANCH', raising=False)
    value = seal(root, env=['SEAL_BRANCH'], policy={
        'environment': 'warn', 'identity': 'abort', 'reason': 'new branch probe'})
    monkeypatch.setenv('SEAL_BRANCH', 'yes')
    rejects(root, value, 'unsealed environment read: NEW_SETTING')


def test_failed_later_case_has_no_partial_seal_and_cli_saves_failure(root):
    write(root, 'entry.py', 'import sys\nassert len(sys.argv) == 1\n')
    static = build_contract({'schema': SPEC_SCHEMA, 'entry_points': ['entry.py'], 'modules': [],
                             'inputs': [], 'registries': [], 'dynamic_imports': {}}, root=root)
    write(root, 'static.json', json.dumps(static))
    write(root, 'cases.json', json.dumps([{'entry': 'entry.py', 'args': []},
                                         {'entry': 'entry.py', 'args': ['fail']}]))
    output = root / 'runtime.json'
    assert main(['--root', str(root), 'trace', '--static-contract', str(root / 'static.json'),
                 '--expected-static-sha256', static['sha256'], '--cases', str(root / 'cases.json'),
                 '--output', str(output)]) == 86
    assert not output.exists()
    failed = json.loads((root / 'runtime.json.failed.json').read_text())
    assert failed['status'] == 'HOST_ERROR'
    assert failed['reason'] == 'canonical-case-failed'
    assert failed['case']['args'] == ['fail']


def test_cli_round_trip(root, capsys):
    write(root, 'entry.py', 'from pathlib import Path\nassert Path("data.txt").read_text() == "STOP"\n')
    write(root, 'data.txt', 'STOP')
    static = build_contract({'schema': SPEC_SCHEMA, 'entry_points': ['entry.py'], 'modules': [],
                             'inputs': [], 'registries': [], 'dynamic_imports': {}}, root=root)
    write(root, 'static.json', json.dumps(static))
    write(root, 'cases.json', '[{"entry":"entry.py","args":[]}]')
    output = root / 'runtime.json'
    assert main(['--root', str(root), 'trace', '--static-contract', str(root / 'static.json'),
                 '--expected-static-sha256', static['sha256'], '--cases', str(root / 'cases.json'),
                 '--output', str(output)]) == 0
    value = json.loads(output.read_text())
    command = ['--root', str(root), 'run', '--seal', str(output), '--expected-sha256', value['sha256']]
    assert main(command) == 0
    write(root, 'data.txt', 'MOVE')
    assert main(command) == 86
    assert json.loads(capsys.readouterr().out.splitlines()[-1])['reason'] == 'seal-violation'


def test_shutdown_callback_reads_are_traced_and_guarded(root, monkeypatch):
    write(root, 'entry.py', 'import atexit, os\nfrom pathlib import Path\n'
          'path = os.getenv("SEAL_PATH", "data.txt")\n'
          'atexit.register(lambda: Path(path).read_text())\n')
    write(root, 'data.txt', 'STOP')
    monkeypatch.delenv('SEAL_PATH', raising=False)
    value = seal(root, env=['SEAL_PATH'], policy={
        'environment': 'warn', 'identity': 'abort', 'reason': 'shutdown branch probe'})
    assert str(root / 'data.txt') in value['traces'][0]['observed_files']
    write(root, 'other.txt', 'MOVE')
    monkeypatch.setenv('SEAL_PATH', 'other.txt')
    rejects(root, value, 'unsealed or changed file read')


def test_thread_read_is_guarded(root, monkeypatch):
    write(root, 'entry.py', 'import threading, os\nfrom pathlib import Path\n'
          'path = os.getenv("SEAL_PATH", "data.txt")\n'
          'thread = threading.Thread(target=lambda: Path(path).read_text())\n'
          'thread.start()\nthread.join()\n')
    write(root, 'data.txt', 'STOP')
    monkeypatch.delenv('SEAL_PATH', raising=False)
    value = seal(root, env=['SEAL_PATH'], policy={
        'environment': 'warn', 'identity': 'abort', 'reason': 'thread branch probe'})
    write(root, 'other.txt', 'MOVE')
    monkeypatch.setenv('SEAL_PATH', 'other.txt')
    rejects(root, value, 'unsealed or changed file read')


@pytest.mark.parametrize('name', ['PYTHONPATH', 'LD_PRELOAD', 'DYLD_INSERT_LIBRARIES'])
def test_startup_environment_cannot_run_before_hook(root, name):
    write(root, 'entry.py', 'pass\n')
    with pytest.raises(ValueError, match='startup environment'):
        seal(root, env=[name])
