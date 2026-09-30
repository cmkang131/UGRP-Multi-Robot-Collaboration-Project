"""I-330-1 regression from independent review e24cb9ce (PR #330 only).

Run against the working checkout, including uncommitted fixes, with no archive,
physics or network. The original case body/assertion is retained; xfail is
removed so normal CI must pass. PR #335 belongs to its separate change.
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
