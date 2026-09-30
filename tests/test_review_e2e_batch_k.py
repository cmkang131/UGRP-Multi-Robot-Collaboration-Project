"""Independent batch K counterexamples; offline only, no physics or inference.

Run against git-archive trees with REVIEW_E2E_K_PR338_ROOT and
REVIEW_E2E_K_PR339_ROOT. Missing candidate modules skip on the notes branch.
The strict xfails describe desired behavior, so a fix produces XPASS until
the reviewer removes its marker. Do not weaken the frozen source tests.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
BASE_SHA = "55609ed1be4e770019e0640f47c7a2f7f0403f37"
PREREG = "experiments/2026-09-29-pair-v6e-carry/prereg_v6e.json"


def candidate(number):
    root = Path(os.environ.get(f"REVIEW_E2E_K_PR{number}_ROOT", ROOT)).resolve()
    module = {338: "harness/zone_final_environment.py",
              339: "harness/zone_target_executor.py"}[number]
    if not (root / module).is_file():
        pytest.skip(f"PR #{number} tree not provided")
    return root


def python_in(root, source):
    # Do not export GIT_DIR/GIT_WORK_TREE: candidate tests can create their own
    # temporary repositories. Imports resolve only within the selected tree.
    env = {k: v for k, v in os.environ.items()
           if k not in {"GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "PYTEST_ADDOPTS"}}
    env.update(PYTHONPATH=str(root), PYTHONDONTWRITEBYTECODE="1")
    guard = "import sys\nfor m in ('mujoco', 'torch', 'torchvision', 'sim.multi_masterpi_production'):\n sys.modules[m] = None\n"
    result = subprocess.run([sys.executable, "-B", "-c", guard + source],
                            cwd=root, env=env, text=True, capture_output=True, timeout=90)
    if result.returncode:
        pytest.fail(result.stdout + result.stderr)
    return json.loads(result.stdout)


@pytest.mark.xfail(strict=True, raises=AssertionError,
                   reason="K1: #338 new test name breaks the existing CI collection assertion")
def test_pr338_preserves_existing_ci_collection_check():
    result = python_in(candidate(338), """
import json
from tests.test_zone_final_env import test_ci_collects_this_file
try:
    test_ci_collects_this_file()
except AssertionError as error:
    print(json.dumps({'passed': False, 'error': str(error)}))
else:
    print(json.dumps({'passed': True}))
""")
    assert result["passed"], result


SCHEDULER_REPRO = """
import json
from types import SimpleNamespace
from tests.test_zone_own_executor import make
from tests.test_zone_own_executor_target import catalogue, specific, saved_observation
from harness.zone_target_executor import TargetOwnExecutor
from harness.zone_own_team_host import _RobotSlot
from scripts.zone_target_host import TargetStudyHost

def run(delta):
    inner = make()
    inner.orders = {'order-cyan': specific()}
    # Only pose estimation is faked. Real saved own RGB goes through the new
    # recognizer, TargetRecoveryJobs, and the actual native host scheduler.
    inner.on_frame = lambda now, obs, rgb: SimpleNamespace(initialized=False)
    executor = TargetOwnExecutor(inner, visual_catalogue=catalogue(),
                                 cancel_scheduled=lambda *args: None)
    host = TargetStudyHost.__new__(TargetStudyHost)  # never construct a World
    host.pairs = None
    slot = _RobotSlot('r1', None, executor)
    host.robots = {'r1': slot}
    holds = []
    host._hold = lambda rid, now: holds.append((rid, now))
    sequence = 0

    def capture(rid, now):
        nonlocal sequence
        sequence += 1
        obs = saved_observation()
        obs.update(frame_id=sequence, sim_time=now)
        return executor.on_frame(now, obs, None)

    host._capture_raw = capture  # replace only camera acquisition/eval I/O
    host._capture('r1', 1.)     # periodic capture just completed
    slot.timeline = [(1. + delta, [])]
    slot.capture_after = True
    host._run_timeline('r1', 1. + delta)  # real macro completion capture
    return {'delta_s': delta, 'captures': sequence, 'dead': slot.dead,
            'stopped': executor.stopped,
            'error': None if slot.exception is None else slot.exception['message']}

print(json.dumps({'progressed': run(.2), 'same_tick': run(0.)}))
"""


@pytest.fixture(scope="module")
def scheduler_cases():
    return python_in(candidate(339), SCHEDULER_REPRO)


def test_pr339_later_macro_capture_is_accepted(scheduler_cases):
    positive = scheduler_cases["progressed"]
    assert positive["captures"] == 2
    assert positive["dead"] is False and positive["stopped"] is None
    assert positive["error"] is None


@pytest.mark.xfail(strict=True, raises=AssertionError,
                   reason="K2: #339 periodic and macro captures at the same SIM time kill the robot")
def test_pr339_same_tick_macro_capture_does_not_permanently_stop_robot(scheduler_cases):
    # Two distinct frame IDs at the same time are a normal host scheduling
    # case. Deduplicate/defer capture; do not relax stale identity evidence.
    assert scheduler_cases["same_tick"]["dead"] is False, scheduler_cases["same_tick"]


@pytest.mark.xfail(strict=True, raises=AssertionError,
                   reason="K3: #339 rewrites the existing v6e workflow pin")
def test_pr339_preserves_existing_preregistration_bytes():
    root = candidate(339)
    baseline = subprocess.run(["git", "show", f"{BASE_SHA}:{PREREG}"], cwd=ROOT,
                              capture_output=True, check=True).stdout
    assert (root / PREREG).read_bytes() == baseline


@pytest.mark.xfail(strict=True, raises=AssertionError,
                   reason="K4: #339 T13 SIM candidate explicitly selects v2, not the TASKS final v3 environment")
def test_pr339_t13_handoff_uses_required_final_environment():
    root = candidate(339)
    cfg = json.loads((root / "configs/t13_target_checks.json").read_text())
    assert cfg["robot_model"] == "masterpi_v3", cfg["scope"]
    maps = list((root / "maps").rglob(cfg["map_id"] + ".json"))
    assert len(maps) == 1
    static = json.loads(maps[0].read_text())
    assert static["wall_profile"]["id"] == "walls_v3"
    assert static["wall_profile"]["height_m"] == .4
