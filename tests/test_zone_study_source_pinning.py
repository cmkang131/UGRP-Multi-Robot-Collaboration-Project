"""PR #229 provenance regressions. No simulator, network, or model calls."""
from pathlib import Path

import pytest

from harness.python_source_closure import source_closure
from scripts import run_zone_study_integration as runner

ROOT = Path(__file__).resolve().parents[1]
PREREG = ROOT / 'configs/zone_study_integration/pair_dev_DRAFT.json'


def test_closure_follows_nested_relative_imports_initializers_and_config_roots(tmp_path):
    files = {
        'entry.py': 'from pkg import child\ndef later():\n from pkg.sub import leaf\n',
        'pkg/__init__.py': 'from . import init_dependency\n',
        'pkg/init_dependency.py': '',
        'pkg/child.py': 'from .sub import leaf\n',
        'pkg/sub/__init__.py': '',
        'pkg/sub/leaf.py': 'from .. import child\n',  # import cycle
        'selected.py': 'import selected_dependency\n',
        'selected_dependency.py': '',
        'unrelated.py': 'raise AssertionError("never execute sources")\n',
    }
    for name, content in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    assert set(source_closure(tmp_path, ['entry.py'], modules=['selected'])) == set(files) - {'unrelated.py'}
    with pytest.raises(ValueError, match='missing local module'):
        source_closure(tmp_path, ['entry.py'], modules=['absent'])


@pytest.mark.parametrize('changed', ['harness/visual_arm.py', 'harness/llm_completion.py',
                                     'sim/session_scenes.py', 'harness/wrist_zone_skill_v9.py',
                                     'harness/owncam_pose_source.py'])
def test_dependency_mutation_changes_the_actual_run_bundle(monkeypatch, changed):
    pre = runner.load_prereg(PREREG)
    original = runner.run_bundle(pre, pre['episodes'][0])[0]
    assert changed in original['runtime_files_sha256']
    file_sha = runner.zi.file_sha256
    monkeypatch.setattr(runner.zi, 'file_sha256', lambda p: 'f' * 64 if Path(p) == ROOT / changed else file_sha(p))
    mutated = runner.run_bundle(pre, pre['episodes'][0])[0]
    assert mutated['runtime_files_sha256'][changed] == 'f' * 64
    assert runner.digest(original) != runner.digest(mutated)
    assert original['execution_bundle_id'] == 'zone-study-integration-v64-source-closure'


HEAD = '1' * 40
OTHER = '2' * 40
BUNDLE = '3' * 64


def fake_git(*args):
    if args[:2] == ('rev-parse', '--verify'):
        if args[2] in ('HEAD^{commit}', HEAD + '^{commit}', HEAD[:8] + '^{commit}'):
            return HEAD
        if args[2] == OTHER + '^{commit}':
            return OTHER
        return ''
    if args[0] == 'status':
        return ''
    pytest.fail(f'unexpected git command: {args}')


@pytest.mark.parametrize('pin', [HEAD, HEAD[:8]])
def test_matching_resolvable_source_pin(monkeypatch, pin):
    monkeypatch.setattr(runner, 'git', fake_git)
    assert runner.check_run_source({'source_sha': pin, 'bundle_sha256': BUNDLE}, BUNDLE)['sha'] == HEAD
    assert runner.check_run_source({'bundle_sha256': BUNDLE}, BUNDLE, expected_source_sha=pin)['sha'] == HEAD


@pytest.mark.parametrize('pin', [None, '', OTHER, 'a' * 40, 'HEAD', '--all'])
def test_same_bundle_does_not_admit_missing_wrong_or_unresolved_source(monkeypatch, pin):
    monkeypatch.setattr(runner, 'git', fake_git)
    with pytest.raises(SystemExit, match='[Ss][Hh][Aa]|source_sha'):
        runner.check_run_source({'source_sha': pin, 'bundle_sha256': BUNDLE}, BUNDLE)


def test_cli_pin_cannot_override_prereg_pin_even_in_dev(monkeypatch):
    monkeypatch.setattr(runner, 'git', fake_git)
    for dev in (False, True):
        with pytest.raises(SystemExit, match='differs from expected source SHA'):
            runner.check_run_source({'source_sha': OTHER, 'bundle_sha256': BUNDLE}, BUNDLE,
                                    expected_source_sha=HEAD, dev=dev)


def test_bundle_and_dirty_source_checks_are_retained(monkeypatch):
    monkeypatch.setattr(runner, 'git', fake_git)
    with pytest.raises(SystemExit, match='run bundle'):
        runner.check_run_source({'source_sha': HEAD, 'bundle_sha256': 'old'}, BUNDLE)
    monkeypatch.setattr(runner, 'git', lambda *a: ' M harness/visual_arm.py' if a[0] == 'status' else fake_git(*a))
    with pytest.raises(SystemExit, match='source is dirty'):
        runner.check_run_source({'source_sha': HEAD, 'bundle_sha256': BUNDLE}, BUNDLE)


def test_source_mismatch_stops_before_physics_import_host_or_output(monkeypatch, tmp_path):
    import sys
    monkeypatch.setitem(sys.modules, 'mujoco', None)
    monkeypatch.setattr(runner, 'git', fake_git)
    monkeypatch.setattr(runner, 'StudyTeamHost', lambda *a, **k: pytest.fail('host construction forbidden'))
    pre = runner.load_prereg(PREREG)
    pre['source_sha'] = OTHER
    pre['bundle_sha256'] = runner.digest(runner.run_bundle(pre, pre['episodes'][0])[0])
    output = tmp_path / 'must-not-be-created'
    with pytest.raises(SystemExit, match='differs from expected source SHA'):
        runner.run_trial(pre, pre['episodes'][0], 'no_comm', output, horizon_s=1.)
    assert not output.exists()
