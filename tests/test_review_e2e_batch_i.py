"""Batch I counterexamples promoted from strict xfail to live regressions.

Source: codex/review-e2e-batch-i, e24cb9ce3c10236efe03a1b66c9ec7671ece71b9.
Retain main's I-335-1 static sweep and PR #330's I-330-1 delayed capture case.
Run against the current tree, including uncommitted fixes, without old-source
extraction or physics. Both original case bodies and assertions are unchanged.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
OFFLINE = """
import importlib.abc, sys
class OfflineOnly(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'mujoco', 'glfw', 'torch', 'openai', 'anthropic'}:
            raise RuntimeError('review forbids physics/model import: ' + fullname)
sys.meta_path.insert(0, OfflineOnly())
def offline_audit(event, args):
    if event in {'socket.connect', 'socket.getaddrinfo'}:
        raise RuntimeError('review forbids network')
sys.addaudithook(offline_audit)
"""


def probe(tree, code):
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "OMP_NUM_THREADS": "1",
           "OPENBLAS_NUM_THREADS": "1"}
    result = subprocess.run([sys.executable, "-c", OFFLINE + code], cwd=tree, env=env,
                            text=True, capture_output=True, timeout=60, check=True)
    return json.loads(result.stdout)


def test_t04_issued_arm_increment_passes_the_same_static_sweep():
    import copy
    import numpy as np
    from tests.test_zone_own_executor_can import MAP, FakeOwnPose, observation, pose, decide
    from harness.zone_can_skill import CanSkill, VIEWS
    from harness.zone_own_guards import OwnPose
    initial = {1:2000, 3:1164, 4:2321, 5:2080, 6:1174}
    static = copy.deepcopy(MAP)
    # Authored static geometry, not a simulator state or a physical collision claim.
    static['obstacles'].append(dict(id='review_static_post',
        center_m=[.27446602791450786, -.11115416383666454],
        half_extents_m=[.0001, .0001], height_m=.025))
    skill = CanSkill('r1', static, destination_zone='C', pose_source=FakeOwnPose())
    skill.on_command(dict(robot_id='r1', t=0., kind='initial_servo_command', pulses=initial))
    own = OwnPose(0., 0., 0., .002, .002)
    out = decide(skill, 1., observation(np.full((480,640,3),80,np.uint8)), pose(1.,xy=(0.,0.)))
    issued = dict(initial)
    for cmd in out['commands']:
        if cmd['kind'] == 'arm':
            issued[cmd['servo_id']] = cmd['pulse']
    def clearance(target):
        return min(skill.guard.arm_clearance(p, own, loaded=False)[0]
                   for p in skill.guard.transition_samples(initial, target))
    result = dict(phase=out['phase'], issued=issued,
        start_clearance_m=skill.guard.arm_clearance(initial,own,loaded=False)[0],
        chassis_clearance_m=skill.guard.chassis_clearance(own)[0],
        checked_clearance_m=clearance(VIEWS[0]), issued_clearance_m=clearance(issued))
    # Fixture validity is separate from the expected failing safety assertion.
    if min(result["start_clearance_m"], result["chassis_clearance_m"]) <= 0:
        raise RuntimeError(f"counterexample no longer starts clear: {result}")
    assert result["issued_clearance_m"] >= 0, result


def test_t09b_delayed_own_capture_cannot_issue_a_new_drive():
    result = probe(ROOT, """
import dataclasses, json
from tests.test_zone_own_executor_observed_reroute import make, tick, rr, PIXELS
c = make()
tick(c, 0, now=0.)
# This camera packet was captured at t=.01 and queued, not yet consumed.
# Sequence 1 is genuinely newer than sequence 0; no sequence replay is needed.
kwargs = dict(robot_id='r1', sequence=1, rgb=PIXELS['clear'])
if 'captured_at_s' in {f.name for f in dataclasses.fields(rr.OwnFrame)}:
    kwargs['captured_at_s'] = .01
queued_frame = rr.OwnFrame(**kwargs)
before = len(c.navigation.calls)
d = c.tick(queued_frame, now_s=1.)  # 990 ms old; no new camera evidence
print(json.dumps(dict(state=d.state, new_drive_calls=len(c.navigation.calls)-before,
                      stop_calls=c.navigation.cancelled)))
""")
    assert result["new_drive_calls"] == 0 and result["stop_calls"] >= 1, result
