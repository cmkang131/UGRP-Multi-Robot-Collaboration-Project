"""Static executor boundary and frozen inherited-hook audit; no physics/model imports."""
import ast
import hashlib
import json
from pathlib import Path
import re

import pytest

ROOT = Path(__file__).resolve().parents[1]
ALLOW = json.loads((ROOT / 'tests/fixtures/pose_provider_v5c/allowlist.json').read_text())
PATTERN = re.compile(r'(^|[^a-z])tags?([^a-z]|$)|Tag|TAG')


def marker_refs(source):
    refs = []
    for n in ast.walk(ast.parse(source)):
        values = []
        if isinstance(n, ast.Name): values = [n.id]
        elif isinstance(n, ast.Attribute): values = [n.attr]
        elif isinstance(n, ast.Constant) and isinstance(n.value, str): values = [n.value]
        elif isinstance(n, ast.alias): values = [n.name, n.asname or '']
        elif isinstance(n, ast.ImportFrom): values = [n.module or '']
        elif isinstance(n, ast.keyword): values = [n.arg or '']
        if any(PATTERN.search(v) for v in values):
            refs.append((n.lineno, values))
    return refs


def test_all_current_pair_own_executors_have_no_marker_references():
    files = {*ROOT.glob('harness/zone_pair*.py'), *ROOT.glob('harness/zone_own*.py'),
             ROOT / 'harness/owncam_time.py'}
    assert len(files) >= 25
    assert not set(str(p.relative_to(ROOT)) for p in files) & set(ALLOW['providers'])
    failures = {str(p.relative_to(ROOT)): marker_refs(p.read_text()) for p in sorted(files)}
    assert not {k: v for k, v in failures.items() if v}


@pytest.mark.parametrize('source', ['report.since_tag_s', 'loc.last_tag_t', "est['tag_gap']",
                                   'accepted_tag_checks(r)', 'from harness.wall_tags import TagDetector',
                                   "report.get('n_tags')", 'f(last_tag_t=0)'])
def test_static_check_catches_direct_control_and_dynamic_key_access(source):
    assert marker_refs(source)


def test_only_explicit_providers_evaluators_and_hash_frozen_paths_are_exempt():
    assert set(ALLOW) == {'providers', 'evaluation', 'historical_frozen'}
    for key in ('providers', 'evaluation'):
        assert all((ROOT / p).is_file() for p in ALLOW[key])
    for path, digest in ALLOW['historical_frozen'].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest, path
    # Avoid merely whitelisting a historical method that is still active.
    from harness.zone_own_driver import GuardedDriver
    from harness.zone_pair_guards import GuardedPairApproach
    for cls, hooks in ((GuardedDriver, ('_needs_look',)),
                       (GuardedPairApproach, ('_look_step', '_event', '_relocalize', '_needs_look', 'observe'))):
        for hook in hooks:
            assert getattr(cls, hook).__module__ in ('harness.zone_own_driver', 'harness.zone_pair_guards')


def test_new_interface_modules_have_no_truth_or_model_inference_dependencies():
    files = ['harness/pose_provider.py', 'harness/owncam_time.py', 'harness/zone_pair_align.py',
             'harness/zone_pair_grasp.py', 'harness/zone_pair_guards.py', 'harness/zone_own_driver.py']
    forbidden = {'mujoco', 'MjData', 'xpos', 'xquat', 'qpos', 'qvel', 'eval_only', 'GtStubPoseSource',
                 'cctv_top', 'nav_cam', 'torch'}
    for file in files:
        tree = ast.parse((ROOT / file).read_text())
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        names |= {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        imports = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        imports |= {n.name for n in ast.walk(tree) if isinstance(n, ast.alias)}
        assert not names & forbidden, file
        assert not any(i and i.split('.')[0] in forbidden for i in imports), file
