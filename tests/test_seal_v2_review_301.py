"""Independent PR #301 attacks: isolated programs, no physics or model calls.

A strict xfail is limited to SealAccepted: setup/runtime failures never count as
reproduced holes. The external digest is captured BEFORE the mutation. Boundary
cases explicitly distinguish missing declarations from import-analysis bugs.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

from harness.execution_dependency_contract import (
    ROOT, SPEC_SCHEMA, VERIFIER_SOURCES, build_contract, verify_contract, workflow_spec,
)


class SealAccepted(AssertionError):
    """The original externally anchored seal admitted a behavior-changing edit."""


def hole(reason):
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
    for name in VERIFIER_SOURCES:
        write(tmp_path, name, (ROOT / name).read_bytes())
    # Deliberately tiny package; never import the real robot harness in children.
    write(tmp_path, 'harness/__init__.py', '')
    return tmp_path


def spec(entry='entry.py', **overrides):
    return {'schema': SPEC_SCHEMA, 'entry_points': [entry], 'modules': [],
            'inputs': [], 'registries': [], 'dynamic_imports': {}, **overrides}


def run(root, entry='entry.py', **extra_env):
    env = {k: v for k, v in os.environ.items()
           if not k.endswith('_API_KEY') and k not in {
               'PYTHONPATH', 'PYTHONHOME', 'GOOGLE_APPLICATION_CREDENTIALS'}}
    env.update(PYTHONDONTWRITEBYTECODE='1', **extra_env)
    return subprocess.check_output(
        [sys.executable, '-B', entry], cwd=root, env=env, text=True, timeout=15,
    ).strip()


def seal(root, declaration):
    receipt = build_contract(declaration, root=root)
    # Persist and reload just as a registration would (also freezes JSON order).
    return json.loads(json.dumps(receipt)), receipt['sha256']


def must_reject(root, receipt, expected):
    try:
        verify_contract(receipt, expected_sha256=expected, root=root)
    except ValueError:
        return
    raise SealAccepted('unchanged external digest still verifies after runtime behavior changed')


@hole('R1 BLOCKER: star import omits package __all__ submodules')
def test_star_import_child_changes_command_without_invalidating_seal(sandbox):
    root = sandbox
    write(root, 'entry.py', 'from pkg import *\nprint(child.COMMAND)\n')
    write(root, 'pkg/__init__.py', '__all__ = ["child"]\n')
    write(root, 'pkg/child.py', 'COMMAND = "STOP"\n')
    receipt, expected = seal(root, spec())
    assert run(root) == 'STOP'
    write(root, 'pkg/child.py', 'COMMAND = "MOVE"\n')
    assert run(root) == 'MOVE'
    must_reject(root, receipt, expected)


@pytest.mark.parametrize('loader', [
    'import importlib\nload = importlib.import_module\nmod = load("plugin")',
    'import importlib\nmod = getattr(importlib, "import_module")("plugin")',
    'from builtins import __import__ as load\nmod = load("plugin")',
    'import builtins\nmod = builtins.__import__("plugin")',
], ids=['assigned-importlib-alias', 'getattr-string', 'builtin-alias', 'builtin-attribute'])
@hole('R2 BLOCKER: indirect/aliased dynamic loader is not tracked or refused')
def test_dynamic_loader_changes_command_without_invalidating_seal(sandbox, loader):
    root = sandbox
    write(root, 'entry.py', loader + '\nprint(mod.COMMAND)\n')
    write(root, 'plugin.py', 'COMMAND = "STOP"\n')
    receipt, expected = seal(root, spec())
    assert run(root) == 'STOP'
    write(root, 'plugin.py', 'COMMAND = "MOVE"\n')
    assert run(root) == 'MOVE'
    must_reject(root, receipt, expected)


@hole('R3 MAJOR: root-only resolution misses ordinary sibling imports in script entry points')
def test_script_directory_import_changes_command_without_invalidating_seal(sandbox):
    root = sandbox
    write(root, 'jobs/entry.py', 'import helper\nprint(helper.COMMAND)\n')
    write(root, 'jobs/helper.py', 'COMMAND = "STOP"\n')
    receipt, expected = seal(root, spec('jobs/entry.py'))
    assert run(root, 'jobs/entry.py') == 'STOP'
    write(root, 'jobs/helper.py', 'COMMAND = "MOVE"\n')
    assert run(root, 'jobs/entry.py') == 'MOVE'
    must_reject(root, receipt, expected)


@hole('R4 MAJOR: canonical object hashes discard order that Python JSON consumers can use')
def test_selected_entry_key_order_changes_first_command_without_invalidating_seal(sandbox):
    root = sandbox
    write(root, 'entry.py', 'import json\nfrom pathlib import Path\n'
          'row = json.loads(Path("registry.json").read_text())["policy"]\n'
          'print(next(iter(row["commands"])))\n')
    write(root, 'registry.json', '{"schema":"v1","policy":{"commands":{"STOP":0,"MOVE":1}}}')
    declaration = spec(registries=[{'path': 'registry.json', 'keys': ['policy']}])
    receipt, expected = seal(root, declaration)
    assert run(root) == 'STOP'
    write(root, 'registry.json', '{"schema":"v1","policy":{"commands":{"MOVE":1,"STOP":0}}}')
    assert run(root) == 'MOVE'
    must_reject(root, receipt, expected)


@hole('B1 declaration boundary: subprocess worker must be declared explicitly')
def test_undeclared_subprocess_worker_is_outside_seal(sandbox):
    root = sandbox
    write(root, 'entry.py', 'import subprocess, sys\n'
          'subprocess.run([sys.executable, "-B", "worker.py"], check=True)\n')
    write(root, 'worker.py', 'print("STOP")\n')
    receipt, expected = seal(root, spec())
    assert run(root) == 'STOP'
    write(root, 'worker.py', 'print("MOVE")\n')
    assert run(root) == 'MOVE'
    must_reject(root, receipt, expected)


@pytest.mark.parametrize('declared', [False, True], ids=['undeclared', 'declared'])
def test_runner_monkeypatch_is_pinned_when_runner_is_declared(sandbox, declared):
    root = sandbox
    write(root, 'entry.py', 'COMMAND = "STOP"\n')
    write(root, 'runner.py', 'import entry\nentry.COMMAND = "LEFT"\nprint(entry.COMMAND)\n')
    receipt, expected = seal(root, spec(entry_points=['entry.py', *(['runner.py'] if declared else [])]))
    assert run(root, 'runner.py') == 'LEFT'
    write(root, 'runner.py', 'import entry\nentry.COMMAND = "RIGHT"\nprint(entry.COMMAND)\n')
    assert run(root, 'runner.py') == 'RIGHT'
    if declared:
        must_reject(root, receipt, expected)
    else:
        # An intentionally incomplete spec is not proof of an import-closure bug.
        assert verify_contract(receipt, expected_sha256=expected, root=root)['sha256'] == expected


@pytest.mark.parametrize('name,reader,before,after', [
    ('config.json', 'json.loads(p.read_text())["command"]', '{"command":"STOP"}', '{"command":"MOVE"}'),
    ('map.json', 'json.loads(p.read_text())["command"]', '{"command":"STOP"}', '{"command":"MOVE"}'),
    ('scene.xml', 'ET.fromstring(p.read_text()).get("command")', '<mujoco command="STOP"/>', '<mujoco command="MOVE"/>'),
    ('scene.mjcf', 'ET.fromstring(p.read_text()).get("command")', '<mujoco command="STOP"/>', '<mujoco command="MOVE"/>'),
    ('render.yaml', 'p.read_text().split(":", 1)[1].strip()', 'command: STOP', 'command: MOVE'),
], ids=['json-config', 'json-map', 'xml', 'mjcf', 'yaml-scalar'])
@pytest.mark.parametrize('declared', [False, True], ids=['undeclared', 'declared'])
def test_runtime_data_boundary(sandbox, name, reader, before, after, declared):
    root = sandbox
    write(root, 'entry.py', 'import json\nimport xml.etree.ElementTree as ET\nfrom pathlib import Path\n'
          f'p = Path({name!r})\nprint({reader})\n')
    write(root, name, before)
    receipt, expected = seal(root, spec(inputs=[name] if declared else []))
    assert run(root) == 'STOP'
    write(root, name, after)
    assert run(root) == 'MOVE'
    if declared:
        must_reject(root, receipt, expected)
    else:
        assert verify_contract(receipt, expected_sha256=expected, root=root)['sha256'] == expected


@hole('B1 declaration boundary: pinning an MJCF parent does not pin include/mesh contents')
def test_mjcf_include_requires_transitive_asset_declaration(sandbox):
    root = sandbox
    write(root, 'scene.xml', '<mujoco><include file="assets/body.xml"/></mujoco>')
    write(root, 'assets/body.xml', '<body command="STOP"/>')
    write(root, 'entry.py', 'import xml.etree.ElementTree as ET\n'
          'child = ET.parse("scene.xml").find("include").get("file")\n'
          'print(ET.parse(child).getroot().get("command"))\n')
    receipt, expected = seal(root, spec(inputs=['scene.xml']))
    assert run(root) == 'STOP'
    write(root, 'assets/body.xml', '<body command="MOVE"/>')
    assert run(root) == 'MOVE'
    must_reject(root, receipt, expected)


@pytest.mark.parametrize('declared', [False, True], ids=['undeclared', 'declared'])
def test_npz_runtime_input_boundary(sandbox, declared):
    import numpy as np
    root = sandbox
    write(root, 'entry.py', 'import numpy as np\nprint(int(np.load("fit.npz")["gain"]))\n')
    np.savez(root / 'fit.npz', gain=1)
    receipt, expected = seal(root, spec(inputs=['fit.npz'] if declared else []))
    assert run(root) == '1'
    np.savez(root / 'fit.npz', gain=9)
    assert run(root) == '9'
    if declared:
        must_reject(root, receipt, expected)
    else:
        assert verify_contract(receipt, expected_sha256=expected, root=root)['sha256'] == expected


@hole('B1 declaration boundary: selecting a row does not pin defaults read outside it')
def test_registry_default_outside_selected_row_changes_command(sandbox):
    root = sandbox
    write(root, 'entry.py', 'import json\nfrom pathlib import Path\n'
          'c = json.loads(Path("registry.json").read_text())\n'
          'print(c["policy"].get("command", c["defaults"]["command"]))\n')
    write(root, 'registry.json', '{"schema":"v1","policy":{},"defaults":{"command":"STOP"}}')
    receipt, expected = seal(root, spec(registries=[{'path': 'registry.json', 'keys': ['policy']}]))
    assert run(root) == 'STOP'
    write(root, 'registry.json', '{"schema":"v1","policy":{},"defaults":{"command":"MOVE"}}')
    assert run(root) == 'MOVE'
    must_reject(root, receipt, expected)


@hole('B2 admission boundary: live environment variables are not dependency inputs')
def test_environment_changes_command_without_invalidating_seal(sandbox):
    root = sandbox
    write(root, 'entry.py', 'import os\nprint(os.environ.get("REVIEW_301_COMMAND", "STOP"))\n')
    receipt, expected = seal(root, spec())
    assert run(root, REVIEW_301_COMMAND='STOP') == 'STOP'
    assert run(root, REVIEW_301_COMMAND='MOVE') == 'MOVE'
    must_reject(root, receipt, expected)


@hole('B2 admission boundary: Python/NumPy/MuJoCo identities are recorded elsewhere, not in v2')
def test_runtime_environment_identity_changes_without_invalidating_seal(sandbox, monkeypatch):
    from sim import workflow_manager as manager
    root = sandbox
    write(root, 'entry.py', 'print("environment identity consumer")\n')
    receipt, expected = seal(root, spec())
    # Simulated upgrades, no package installation, MuJoCo import or physics.
    before = manager.environment_identity()
    original_version = manager.importlib.metadata.version
    monkeypatch.setattr(manager.platform, 'python_version', lambda: '99.0.301')
    monkeypatch.setattr(manager.importlib.metadata, 'version',
                        lambda name: '99.0.301' if name in {'numpy', 'mujoco'} else original_version(name))
    after = manager.environment_identity()
    assert before['python'] != after['python']
    assert before['packages']['numpy'] != after['packages']['numpy']
    assert before['packages']['mujoco'] != after['packages']['mujoco']
    must_reject(root, receipt, expected)


@pytest.mark.parametrize('changed', ['pkg/__init__.py', 'pkg/conditional.py'])
def test_initializer_side_effect_and_conditional_import_are_pinned(sandbox, changed):
    root = sandbox
    write(root, 'entry.py', 'from pkg import policy\nprint(policy.command())\n')
    write(root, 'pkg/__init__.py', 'import builtins\nbuiltins.REVIEW_301_BIAS = 1\n')
    write(root, 'pkg/policy.py', 'def command():\n import builtins\n if True:\n'
          '  from .conditional import VALUE\n return VALUE + builtins.REVIEW_301_BIAS\n')
    write(root, 'pkg/conditional.py', 'VALUE = 1\n')
    receipt, expected = seal(root, spec())
    assert run(root) == '2'
    write(root, changed, (root / changed).read_text().replace('= 1', '= 9'))
    assert run(root) == '10'
    must_reject(root, receipt, expected)


LEGACY = [
    'experiments/2026-09-28-zone-pair-v6/prereg_v6.json',
    'experiments/2026-09-28-zone-pair-v6b-boot/prereg_v6b.json',
    'experiments/2026-09-29-pair-v6c/prereg_v6c.json',
    'experiments/2026-09-29-pair-v6d-align/prereg_v6d.json',
    'experiments/2026-09-29-pair-v6e-carry/prereg_v6e.json',
]
PR_BASE = 'd17ca4345affef8cf027e121cf1f3197b36c23e0'


@pytest.mark.parametrize('path', LEGACY)
def test_real_old_registration_bytes_are_unchanged_and_v2_refuses_them(path):
    current = (ROOT / path).read_bytes()
    original = subprocess.check_output(['git', 'show', f'{PR_BASE}:{path}'], cwd=ROOT)
    assert current == original
    registration = json.loads(current)
    with pytest.raises(ValueError, match='legacy verifier'):
        verify_contract(registration['v6_contract'], expected_sha256='0' * 64)
    with pytest.raises(ValueError, match='explicit v2'):
        build_contract(registration)


def test_all_old_rgb_registry_blobs_and_legacy_verifiers_are_unchanged():
    paths = subprocess.check_output(
        ['git', 'ls-tree', '-r', '--name-only', PR_BASE, 'config/rgb_execution_bundles'],
        cwd=ROOT, text=True).splitlines()
    paths += ['harness/rgb_execution_bundle.py', 'harness/python_source_closure.py',
              'scripts/zone_pair_v6_contract.py', 'scripts/zone_pair_registered_source.py',
              'scripts/run_zone_pair_dev.py', 'scripts/run_zone_study_integration.py']
    assert paths
    for path in paths:
        assert (ROOT / path).read_bytes() == subprocess.check_output(
            ['git', 'show', f'{PR_BASE}:{path}'], cwd=ROOT), path


@pytest.mark.parametrize('change', ['missing-entry', 'duplicate-unused-id'])
@hole('R5 MAJOR: the real workflow consumer validates unselected rows outside the entry pin')
def test_unselected_workflow_row_can_disable_selected_workflow(sandbox, change):
    from sim import workflow_manager as manager
    root = sandbox
    rows = [dict(id=name, entry=f'{name}.py', runner=name, version='1', output_flag=None,
                 output_kind='directory', required_inputs=[], side_effect='offline_analysis')
            for name in ('used', 'unused')]
    for name in ('used', 'unused'):
        write(root, f'{name}.py', 'print("STOP")\n')
    write(root, 'sim/__init__.py', '')
    write(root, 'sim/workflow_manager.py', (ROOT / 'sim/workflow_manager.py').read_bytes())
    catalog = {'schema': 'ugrp.local_workflow_catalog.v1', 'workflows': rows}
    write(root, 'configs/simulation_workflows.json', json.dumps(catalog))
    declaration = workflow_spec('used', root=root, entry_points=['sim/workflow_manager.py'])
    receipt, expected = seal(root, declaration)
    assert manager._row(root, 'used')[0] == rows[0]
    if change == 'missing-entry':
        rows[1]['entry'] = 'missing.py'
        error = 'workflow entry missing'
    else:
        rows.append(dict(rows[1]))
        error = 'distinct workflows'
    write(root, 'configs/simulation_workflows.json', json.dumps(catalog))
    with pytest.raises(ValueError, match=error):
        manager._row(root, 'used')
    must_reject(root, receipt, expected)


@hole('R6 MAJOR: workflow_spec does not always include the standard workflow launcher')
def test_real_communication_workflow_omits_standard_launcher(sandbox):
    # Build from a real catalog row and its real transitive source graph.
    # Only construct a launch command; never execute that command.
    root = sandbox
    declaration = workflow_spec('communication')
    original = build_contract(declaration)
    for name in original['source_sha256']:
        write(root, name, (ROOT / name).read_bytes())
    write(root, 'configs/simulation_workflows.json', (ROOT / 'configs/simulation_workflows.json').read_bytes())
    write(root, 'sim/__init__.py', (ROOT / 'sim/__init__.py').read_bytes())
    write(root, 'sim/workflow_manager.py', (ROOT / 'sim/workflow_manager.py').read_bytes())
    write(root, 'probe.py', 'import json\nfrom pathlib import Path\n'
          'from sim.workflow_manager import _runner_command\n'
          'c = json.loads(Path("configs/simulation_workflows.json").read_text())\n'
          'row = next(r for r in c["workflows"] if r["id"] == "communication")\n'
          'cmd, _ = _runner_command(Path.cwd(), row, ["validate", "--manifest", "fixture.json"], record=None)\n'
          'print(cmd[2])\n')
    receipt, expected = seal(root, declaration)
    assert run(root, 'probe.py') == 'scripts.evaluate_rgb_communication'
    launcher = root / 'sim/workflow_manager.py'
    before = launcher.read_text()
    needle = 'return [sys.executable, "-m", runner, *argv], output'
    assert before.count(needle) == 1
    launcher.write_text(before.replace(needle, 'return [sys.executable, "-m", "alternate", *argv], output'))
    assert run(root, 'probe.py') == 'alternate'
    must_reject(root, receipt, expected)


def test_real_render_profile_code_change_is_pinned(sandbox):
    root = sandbox
    write(root, 'sim/__init__.py', '')
    write(root, 'sim/render_profile.py', (ROOT / 'sim/render_profile.py').read_bytes())
    write(root, 'entry.py', 'from sim.render_profile import apply_xml\n'
          'print(apply_xml("<mujoco><worldbody><light/></worldbody></mujoco>", "noshadow_v1"))\n')
    receipt, expected = seal(root, spec())
    assert 'castshadow="false"' in run(root)
    path = root / 'sim/render_profile.py'
    path.write_text(path.read_text().replace("'op': 'light_castshadow', 'value': 'false'",
                                             "'op': 'light_castshadow', 'value': 'true'"))
    assert 'castshadow="true"' in run(root)
    must_reject(root, receipt, expected)
