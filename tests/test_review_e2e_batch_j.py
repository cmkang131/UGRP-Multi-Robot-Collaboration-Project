"""Batch J mutation counterexamples for PR #336; no physics or network.

Default: archive the reviewed SHA into a self-cleaning temporary directory.
To review a fix, set UGRP_REVIEW_J_CRATE_REF to its locally fetched Git ref.
UGRP_REVIEW_J_CRATE_TREE can instead point to an existing extracted PR tree.
The strict xfails describe missing regression coverage, NOT failures of the
unmodified controller. The passing cases show what the two lost guards protect.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

import pytest


ROOT = Path(__file__).resolve().parents[1]
SHA = "98ff3a1e3f3ecf7df18b339ae2e476327ac63ddd"
SOURCE = "harness/zone_crate_skill.py"
SUITE = "tests/test_zone_own_executor_crate.py"
MUTATIONS = {
    "peer_holding": "if not self._peer_holding(now):",
    "missed_go": "if self.status.grant and now > self.status.grant[1] + EPS:",
}


class MutationSurvived(AssertionError):
    """Only this precise coverage failure is expected, not infrastructure errors."""


def child_env(tree):
    env = dict(os.environ, PYTHONPATH=str(tree), PYTHONDONTWRITEBYTECODE="1")
    for key in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "PYTEST_ADDOPTS"):
        env.pop(key, None)
    return env


@pytest.fixture(scope="module")
def crate_tree():
    supplied = os.environ.get("UGRP_REVIEW_J_CRATE_TREE")
    if supplied:
        tree = Path(supplied).resolve()
        assert (tree / SOURCE).is_file() and (tree / SUITE).is_file()
        yield tree
        return
    ref = os.environ.get("UGRP_REVIEW_J_CRATE_REF", SHA)
    # No worktree/checkout/index/config writes. The archive is always removed.
    with tempfile.TemporaryDirectory(prefix="review-e2e-j-counterexample-") as temp:
        tree = Path(temp)
        with subprocess.Popen(["git", "archive", ref], cwd=ROOT, env=child_env(ROOT),
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE) as archive:
            unpack = subprocess.run(["tar", "-x", "-C", str(tree)], stdin=archive.stdout,
                                    capture_output=True, text=True, timeout=120)
            archive.stdout.close()
            error = archive.stderr.read().decode()
            assert archive.wait(timeout=120) == 0, error
            assert unpack.returncode == 0, unpack.stderr
        assert (tree / SOURCE).is_file() and (tree / SUITE).is_file()
        yield tree


# Load only the target module as an in-memory mutant. Its file and the sealed
# source bytes stay unchanged. Each child has fresh imports and status state.
LOAD = r'''
import hashlib, json, pathlib, socket, sys, types
for name in ('mujoco', 'torch', 'torchvision', 'google.genai', 'openai'):
    sys.modules[name] = None
def forbidden(*args, **kwargs):
    raise RuntimeError('Batch J forbids network/physics/provider execution')
socket.socket.connect = socket.socket.connect_ex = forbidden
import harness
path = pathlib.Path('harness/zone_crate_skill.py').resolve()
original = path.read_bytes()
source = original.decode()
needle = sys.argv[1]
if needle:
    assert source.count(needle) == 1, 'mutation anchor changed; review the new source'
    source = source.replace(needle, 'if False:')
module = types.ModuleType('harness.zone_crate_skill')
module.__file__ = str(path)
sys.modules[module.__name__] = module
harness.zone_crate_skill = module
exec(compile(source, str(path), 'exec'), module.__dict__)
'''

SCENARIO = r'''
from tests.test_zone_own_executor_crate import Rig, fixture_frame
rig = Rig()
if sys.argv[2] == 'peer_holding':
    rig.until(lambda: all(s.phase == 'carry' for s in rig.skills.values()))
    own, peer = rig.skills['r1'], rig.skills['r2']
    now = round(rig.t + .05, 8)
    # A fresh delivered not_ready is alive, but supplies no holding evidence.
    peer.status.latched = None
    peer.status.tick('not_ready', now, force=True)
    assert rig.bus.partner_view('r1', now)['r2']['alive']
    intent = own.step(now, fixture_frame(own, now, overrides={'at_destination': 'no'}))
else:
    for _ in range(6):
        rig.tick()
    rig.tick(omit=('r2',))  # r1 closes at .30; r2 misses GO consumption.
    own = rig.skills['r1']
    assert rig.t == .3 and rig.trace[-1]['kind'] == 'close_lug'
    rig.tick(omit=('r2',))  # .35 is before the .15-second heartbeat timeout.
    assert rig.bus.partner_view('r1', rig.t)['r2']['alive']
    intent = rig.trace[-1]
assert path.read_bytes() == original
print(json.dumps({'kind': intent['kind'], 'failure': own.failure, 'terminal': own.terminal}))
'''


def run_scenario(tree, name, *, mutant):
    proc = subprocess.run([sys.executable, "-c", LOAD + SCENARIO,
                           MUTATIONS[name] if mutant else "", name],
                          cwd=tree, env=child_env(tree), capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return json.loads(proc.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize("name,reason", [
    ("peer_holding", "PARTNER_HOLDING_UNCONFIRMED"),
    ("missed_go", "PARTNER_MISSED_GO"),
])
def test_original_guard_blocks_the_counterexample(crate_tree, name, reason):
    assert run_scenario(crate_tree, name, mutant=False) == {
        "kind": "hold", "failure": reason, "terminal": True,
    }


@pytest.mark.parametrize("name,kind", [("peer_holding", "carry_to_zone"), ("missed_go", "hold")])
def test_removed_guard_changes_the_safety_decision(crate_tree, name, kind):
    assert run_scenario(crate_tree, name, mutant=True) == {
        "kind": kind, "failure": None, "terminal": False,
    }


@pytest.mark.parametrize("name", MUTATIONS)
@pytest.mark.xfail(strict=True, raises=MutationSurvived,
                   reason="J1: PR336's 55 tests miss peer-holding and peer-GO guard removal")
def test_pr_suite_must_detect_removed_safety_logic(crate_tree, tmp_path, name):
    xml = tmp_path / (name + ".xml")
    code = LOAD + r'''
import pytest
result = pytest.main(['-q', '-p', 'no:cacheprovider',
                     'tests/test_zone_own_executor_crate.py', '--junitxml=' + sys.argv[2]])
assert path.read_bytes() == original
raise SystemExit(result)
'''
    proc = subprocess.run([sys.executable, "-c", code, MUTATIONS[name], str(xml)],
                          cwd=crate_tree, env=child_env(crate_tree), capture_output=True,
                          text=True, timeout=180)
    (tmp_path / (name + ".log")).write_text(proc.stdout + proc.stderr)
    assert xml.is_file(), proc.stdout + proc.stderr
    suites = list(ET.parse(xml).getroot().iter("testsuite"))
    counts = {key: sum(int(s.get(key, 0)) for s in suites)
              for key in ("tests", "failures", "errors", "skipped")}
    assert counts["tests"] >= 55 and counts["errors"] == counts["skipped"] == 0, counts
    assert proc.returncode in (0, 1), proc.stdout + proc.stderr
    if counts["failures"] == 0:
        assert proc.returncode == 0
        raise MutationSurvived(f"{name}: all {counts['tests']} PR tests still pass")
    assert proc.returncode == 1
