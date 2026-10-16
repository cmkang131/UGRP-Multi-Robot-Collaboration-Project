"""Independent #301 e25d7509 re-review: temporary Python/data files only.

No fixture subprocesses, network, sys.path/sys.modules/environment changes,
permission changes, bytecode fabrication, physics or model calls. Import cases
use CPython PathFinder with explicit search paths and inspect literal constants;
JSON/XML/path consumers run as small pure functions in private namespaces. This
is source-resolution evidence, not a full controller or worker execution.

The old receipt and EXTERNAL digest are captured before each edit. Only the
specific SealAccepted exception is xfailed; setup/observation errors fail hard.
B1 is a documented exclusion, not a newly introduced import-analysis defect.
"""
from __future__ import annotations

import ast
import importlib
from importlib.machinery import PathFinder
import json
from pathlib import Path

import pytest

from harness.execution_dependency_contract import (
    ROOT, SPEC_SCHEMA, VERIFIER_SOURCES, WORKFLOW_SOURCES,
    build_contract, verify_contract,
)


class SealAccepted(AssertionError):
    """The unchanged external digest accepted a behavior-changing fixture edit."""


def gap(reason):
    return pytest.mark.xfail(strict=True, raises=SealAccepted, reason=reason)


def write(root, name, content):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content)


@pytest.fixture
def sandbox(tmp_path):
    for name in (*VERIFIER_SOURCES, *WORKFLOW_SOURCES):
        write(tmp_path, name, (ROOT / name).read_bytes())
    write(tmp_path, 'harness/__init__.py', '')
    return tmp_path


def spec(entry='entry.py', **overrides):
    return {'schema': SPEC_SCHEMA, 'entry_points': [entry], 'modules': [],
            'inputs': [], 'registries': [], 'dynamic_imports': {}, **overrides}


def seal(root, declaration):
    receipt = build_contract(declaration, root=root)
    expected = receipt['sha256']
    assert verify_contract(receipt, expected_sha256=expected, root=root)['sha256'] == expected
    return json.loads(json.dumps(receipt)), expected


def must_reject(root, receipt, expected):
    try:
        verify_contract(receipt, expected_sha256=expected, root=root)
    except ValueError:
        return
    raise SealAccepted('old external digest accepted the edited dependency')


def resolve_source(root, module, *, search=None):
    """Ask the real CPython finder; do not import modules or alter global paths."""
    paths = [str(p) for p in (search if search is not None else [root])]
    parts = module.split('.')
    for index in range(1, len(parts) + 1):
        found = PathFinder.find_spec('.'.join(parts[:index]), paths)
        assert found is not None, module
        paths = found.submodule_search_locations
    assert found.origin is not None, module
    source = Path(found.origin)
    assert source.resolve().is_relative_to(root.resolve())
    return source


def literal(path, name='COMMAND'):
    nodes = ast.parse(path.read_bytes()).body
    return next(ast.literal_eval(node.value) for node in nodes
                if isinstance(node, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == name for t in node.targets))


def pure_command(root):
    """Execute only the known tiny stdlib file/data consumer, with private globals."""
    path = root / 'entry.py'
    namespace = {'__file__': str(path), '__name__': '__review_fixture__'}
    exec(compile(path.read_bytes(), str(path), 'exec'), namespace)
    return namespace['command']()


@pytest.mark.parametrize('declared', [
    pytest.param(False, marks=gap('N6/R1: wildcard glob skips a repository-internal symlinked child package')),
    True,
], ids=['wildcard-symlink-gap', 'explicit-module-control'])
def test_wildcard_symlinked_child_package_drift(sandbox, declared):
    write(sandbox, 'entry.py', 'from pkg import *\nprint(child.COMMAND)\n')
    write(sandbox, 'pkg/__init__.py', '__all__ = ["child"]\n')
    write(sandbox, 'child_impl/__init__.py', 'COMMAND = "STOP"\n')
    (sandbox / 'pkg/child').symlink_to('../child_impl', target_is_directory=True)
    receipt, expected = seal(sandbox, spec(modules=['pkg.child'] if declared else []))
    assert literal(sandbox / 'pkg/__init__.py', '__all__') == ['child']
    source = resolve_source(sandbox, 'pkg.child')
    assert literal(source) == 'STOP'
    write(sandbox, 'child_impl/__init__.py', 'COMMAND = "MOVE"\n')
    assert literal(resolve_source(sandbox, 'pkg.child')) == 'MOVE'
    must_reject(sandbox, receipt, expected)


@pytest.mark.parametrize('target_declared', [
    pytest.param(False, marks=gap('N7/R3: symlink script target directory is absent from import search roots')),
    True,
], ids=['script-symlink-gap', 'declared-target-control'])
def test_symlinked_script_sibling_import_drift(sandbox, target_declared):
    write(sandbox, 'jobs/start.py', 'import helper\nprint(helper.COMMAND)\n')
    write(sandbox, 'jobs/helper.py', 'COMMAND = "STOP"\n')
    (sandbox / 'entry.py').symlink_to('jobs/start.py')
    points = ['entry.py', *(['jobs/start.py'] if target_declared else [])]
    receipt, expected = seal(sandbox, spec(entry_points=points))
    # File-mode Python uses the resolved script directory. Query that resolution
    # explicitly, without launching a process or changing this process's sys.path.
    search = [(sandbox / 'entry.py').resolve().parent]
    assert literal(resolve_source(sandbox, 'helper', search=search)) == 'STOP'
    write(sandbox, 'jobs/helper.py', 'COMMAND = "MOVE"\n')
    assert literal(resolve_source(sandbox, 'helper', search=search)) == 'MOVE'
    must_reject(sandbox, receipt, expected)


@pytest.mark.parametrize('declared', [
    pytest.param(False, marks=gap('N1/R2: per-file loader bindings miss normal cross-module re-exports')),
    True,
], ids=['automatic-closure-gap', 'explicit-module-control'])
@pytest.mark.parametrize('bridge,entry,export', [
    ('from importlib import import_module as load\n',
     'from bridge import load\nmod = load("plugin")\n', 'function'),
    ('from builtins import __import__ as load\n',
     'import bridge\nmod = bridge.load("plugin")\n', 'builtin'),
    ('import importlib as il\n',
     'from bridge import il\nmod = il.import_module("plugin")\n', 'module'),
    ('from importlib import import_module as load\n__all__ = ["load"]\n',
     'from bridge import *\nmod = load("plugin")\n', 'wildcard'),
], ids=['function-reexport', 'builtin-reexport', 'module-reexport', 'wildcard-reexport'])
def test_reexported_loader_drift(sandbox, bridge, entry, export, declared):
    write(sandbox, 'bridge.py', bridge)
    write(sandbox, 'entry.py', entry + 'print(mod.COMMAND)\n')
    write(sandbox, 'plugin.py', 'COMMAND = "STOP"\n')
    receipt, expected = seal(sandbox, spec(modules=['plugin'] if declared else []))
    assert 'bridge.py' in receipt['source_sha256']
    namespace = {}
    exec(compile(bridge, str(sandbox / 'bridge.py'), 'exec'), namespace)
    if export == 'module':
        assert namespace['il'].import_module is importlib.import_module
    elif export == 'builtin':
        assert namespace['load'] is __import__
    else:
        assert namespace['load'] is importlib.import_module
    if export == 'wildcard':
        assert namespace['__all__'] == ['load']
    assert literal(resolve_source(sandbox, 'plugin')) == 'STOP'
    write(sandbox, 'plugin.py', 'COMMAND = "MOVE"\n')
    assert literal(resolve_source(sandbox, 'plugin')) == 'MOVE'
    must_reject(sandbox, receipt, expected)


@pytest.mark.parametrize('whole_file', [
    pytest.param(False, marks=gap('N2/R4: selected JSON parsing merges distinct Decimal values')),
    True,
], ids=['entry-pin-gap', 'whole-file-control'])
def test_selected_json_decimal_precision_drift(sandbox, whole_file):
    write(sandbox, 'entry.py', 'import json\nfrom decimal import Decimal\nfrom pathlib import Path\n'
          'def command():\n'
          ' gain = json.loads(Path(__file__).with_name("registry.json").read_text(), '
          'parse_float=Decimal)["policy"]["gain"]\n'
          ' return "STOP" if gain == Decimal("9007199254740992") else "MOVE"\n')
    write(sandbox, 'registry.json', '{"schema":"v1","policy":{"gain":9007199254740992.0}}')
    declaration = spec(inputs=['registry.json']) if whole_file else spec(
        registries=[{'path': 'registry.json', 'keys': ['policy']}])
    receipt, expected = seal(sandbox, declaration)
    assert pure_command(sandbox) == 'STOP'
    write(sandbox, 'registry.json', '{"schema":"v1","policy":{"gain":9007199254740993.0}}')
    assert pure_command(sandbox) == 'MOVE'
    must_reject(sandbox, receipt, expected)


@gap('N3: identical source bytes do not pin a declared symlink target or __file__.resolve()')
def test_declared_source_symlink_target_drift(sandbox):
    program = 'from pathlib import Path\ndef command():\n return Path(__file__).resolve().parent.name.upper()\n'
    for directory in ('stop', 'move'):
        write(sandbox, directory + '/main.py', program)
    link = sandbox / 'entry.py'
    link.symlink_to('stop/main.py')
    receipt, expected = seal(sandbox, spec(
        entry_points=['entry.py', 'stop/main.py', 'move/main.py']))
    assert pure_command(sandbox) == 'STOP'
    link.unlink()
    link.symlink_to('move/main.py')
    assert pure_command(sandbox) == 'MOVE'
    must_reject(sandbox, receipt, expected)


@gap('N3/B1: every XML asset is declared but the top-level symlink target is not pinned')
def test_declared_xml_symlink_selects_different_declared_child(sandbox):
    write(sandbox, 'entry.py', 'from pathlib import Path\nimport xml.etree.ElementTree as ET\n'
          'def command():\n'
          ' scene = Path(__file__).with_name("scene.xml").resolve()\n'
          ' child = ET.parse(scene).find("include").get("file")\n'
          ' return ET.parse(scene.parent / child).getroot().get("command")\n')
    for directory, command in [('a', 'STOP'), ('b', 'MOVE')]:
        write(sandbox, directory + '/scene.xml', '<mujoco><include file="body.xml"/></mujoco>')
        write(sandbox, directory + '/body.xml', f'<body command="{command}"/>')
    link = sandbox / 'scene.xml'
    link.symlink_to('a/scene.xml')
    receipt, expected = seal(sandbox, spec(inputs=[
        'scene.xml', 'a/scene.xml', 'b/scene.xml', 'a/body.xml', 'b/body.xml']))
    assert pure_command(sandbox) == 'STOP'
    link.unlink()
    link.symlink_to('b/scene.xml')
    assert pure_command(sandbox) == 'MOVE'
    must_reject(sandbox, receipt, expected)


@pytest.mark.parametrize('declared', [
    pytest.param(False, marks=gap('N4/R2: importlib.__import__ is neither followed nor rejected')),
    True,
], ids=['stdlib-loader-gap', 'explicit-module-control'])
@pytest.mark.parametrize('prefix,call', [
    ('from importlib import __import__ as load\n', 'load'),
    ('import importlib\n', 'importlib.__import__'),
], ids=['from-import', 'module-attribute'])
def test_importlib_builtin_loader_drift(sandbox, declared, prefix, call):
    write(sandbox, 'entry.py', prefix + f'print({call}("plugin").COMMAND)\n')
    write(sandbox, 'plugin.py', 'COMMAND = "STOP"\n')
    receipt, expected = seal(sandbox, spec(modules=['plugin'] if declared else []))
    namespace = {}
    exec(compile(prefix, '<stdlib import only>', 'exec'), namespace)
    loader = namespace['load'] if call == 'load' else namespace['importlib'].__import__
    assert loader is importlib.__import__
    assert loader('json') is json  # Harmless already-loaded stdlib control.
    assert literal(resolve_source(sandbox, 'plugin')) == 'STOP'
    write(sandbox, 'plugin.py', 'COMMAND = "MOVE"\n')
    assert literal(resolve_source(sandbox, 'plugin')) == 'MOVE'
    must_reject(sandbox, receipt, expected)


@pytest.mark.parametrize('whole_file', [
    pytest.param(False, marks=gap('N5: automatically pinned catalog schema collapses missing and null')),
    True,
], ids=['schema-presence-gap', 'whole-file-control'])
def test_catalog_schema_presence_drift(sandbox, whole_file):
    write(sandbox, 'entry.py', 'import json\nfrom pathlib import Path\n'
          'def command():\n'
          ' r = json.loads(Path(__file__).with_name("registry.json").read_text())\n'
          ' return "STOP" if r.get("schema", "legacy") == "legacy" else "MOVE"\n')
    write(sandbox, 'registry.json', '{"policy":{"command":"STOP"}}')
    declaration = spec(inputs=['registry.json']) if whole_file else spec(
        registries=[{'path': 'registry.json', 'keys': ['policy']}])
    receipt, expected = seal(sandbox, declaration)
    assert pure_command(sandbox) == 'STOP'
    write(sandbox, 'registry.json', '{"schema":null,"policy":{"command":"STOP"}}')
    assert pure_command(sandbox) == 'MOVE'
    must_reject(sandbox, receipt, expected)


@pytest.mark.parametrize('defaults_declared', [
    pytest.param(False, marks=gap('B1 documented exclusion: a transitive registry reference has no exclusion receipt')),
    True,
], ids=['excluded-reference', 'declared-reference-control'])
def test_registry_reference_chain_boundary(sandbox, defaults_declared):
    write(sandbox, 'entry.py', 'import json\nfrom pathlib import Path\n'
          'def command():\n'
          ' r = json.loads(Path(__file__).with_name("registry.json").read_text())\n'
          ' return r["presets"][r["policy"]["preset"]]["command"]\n')
    write(sandbox, 'registry.json', '{"schema":"v1","policy":{"preset":"safe"},'
          '"presets":{"safe":{"command":"STOP"}}}')
    selectors = [{'path': 'registry.json', 'keys': ['policy']}]
    if defaults_declared:
        selectors.append({'path': 'registry.json', 'keys': ['presets', 'safe']})
    receipt, expected = seal(sandbox, spec(registries=selectors))
    assert pure_command(sandbox) == 'STOP'
    write(sandbox, 'registry.json', '{"schema":"v1","policy":{"preset":"safe"},'
          '"presets":{"safe":{"command":"MOVE"}}}')
    assert pure_command(sandbox) == 'MOVE'
    must_reject(sandbox, receipt, expected)


def test_v2_receipt_has_no_environment_or_exclusion_admission_fields(sandbox):
    write(sandbox, 'entry.py', 'COMMAND = "STOP"\n')
    write(sandbox, 'expected-env.json', '{"controller_profile":"STOP"}')
    receipt, expected = seal(sandbox, spec(inputs=['expected-env.json']))
    assert set(receipt) == {'schema', 'declaration', 'source_sha256', 'registry_entries', 'sha256'}
    assert set(receipt['declaration']) == {
        'schema', 'entry_points', 'modules', 'inputs', 'registries', 'dynamic_imports'}
    assert 'expected-env.json' in receipt['source_sha256']
    assert verify_contract(receipt, expected_sha256=expected, root=sandbox)['sha256'] == expected
    for field in ('environment', 'exclusions', 'admission'):
        with pytest.raises(ValueError, match='explicit v2 dependency spec'):
            build_contract(spec(**{field: {}}), root=sandbox)


def test_nested_json_key_order_fix_generalizes(sandbox):
    write(sandbox, 'entry.py', 'import json\nfrom pathlib import Path\n'
          'def command():\n'
          ' p = json.loads(Path(__file__).with_name("registry.json").read_text())["policy"]\n'
          ' return next(iter(p["nested"][0]["commands"]))\n')
    write(sandbox, 'registry.json', '{"policy":{"nested":[{"commands":{"STOP":0,"MOVE":1}}]}}')
    receipt, expected = seal(sandbox, spec(
        registries=[{'path': 'registry.json', 'keys': ['policy']}]))
    assert pure_command(sandbox) == 'STOP'
    write(sandbox, 'registry.json', '{"policy":{"nested":[{"commands":{"MOVE":1,"STOP":0}}]}}')
    assert pure_command(sandbox) == 'MOVE'
    must_reject(sandbox, receipt, expected)


def test_script_relative_wildcard_fix_generalizes(sandbox):
    write(sandbox, 'jobs/entry.py', 'from pkg import facade\nprint(facade.child.COMMAND)\n')
    write(sandbox, 'jobs/pkg/__init__.py', '')
    write(sandbox, 'jobs/pkg/facade.py', 'from .children import *\n')
    write(sandbox, 'jobs/pkg/children/__init__.py', '__all__ = ["ch" + "ild"]\n')
    write(sandbox, 'jobs/pkg/children/child.py', 'COMMAND = "STOP"\n')
    receipt, expected = seal(sandbox, spec('jobs/entry.py'))
    assert 'jobs/pkg/children/child.py' in receipt['source_sha256']
    search = [sandbox / 'jobs']
    assert literal(resolve_source(sandbox, 'pkg.children.child', search=search)) == 'STOP'
    write(sandbox, 'jobs/pkg/children/child.py', 'COMMAND = "MOVE"\n')
    assert literal(resolve_source(sandbox, 'pkg.children.child', search=search)) == 'MOVE'
    must_reject(sandbox, receipt, expected)
