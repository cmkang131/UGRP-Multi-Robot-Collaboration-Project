"""Nonphysical audit before refreshing static-view cache source fingerprint."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from harness import servo_camera_fk as current
from harness.active_camera import SEARCH, LOOK_AHEAD
from harness.e2e_speed5 import source_hashes, plan_views

BASE = 'efc484ad5ff59a3af3ccf58ebef5bf954c91e5af'
NAME = 'harness/servo_camera_fk.py'
raw = subprocess.check_output(['git', 'show', BASE + ':' + NAME], cwd=ROOT)
old = {'__file__': str(ROOT / NAME), '__name__': 'baseline_fk'}
exec(compile(raw, str(ROOT / NAME), 'exec'), old)
rng = np.random.default_rng(2026101711)
commands = [SEARCH, LOOK_AHEAD]
commands += [{**SEARCH, 1: grip} for grip in (500, 1500, 1600, 1601, 2500)]
commands += [{k: float(rng.integers(500, 2501)) for k in (1, 3, 4, 5, 6)}
             for _ in range(1000)]
checks = 0
for servo in commands:
    for mode in ('off', 'servo_fk_v1'):
        before, br = old['transform_from_commands'](servo, camera_pose=mode)
        after, ar = current.transform_from_commands(servo, camera_pose=mode)
        assert br == ar
        assert (before is None) == (after is None)
        if before is not None:
            for a, b in zip(before, after):
                assert a.dtype == b.dtype and a.shape == b.shape
                assert a.tobytes() == b.tobytes()
        checks += 1
cache = ROOT / 'configs/e2e18_static_views_v1.json'
record = json.loads(cache.read_text())
prior = json.loads(subprocess.check_output(['git', 'show', '18a78adb6:' + str(cache.relative_to(ROOT))], cwd=ROOT))
assert record['views'] == prior['views']
assert {k: v for k, v in record.items() if k != 'source_sha256'} == {
    k: v for k, v in prior.items() if k != 'source_sha256'}
assert record['source_sha256'] == source_hashes(ROOT)
assert len(plan_views()) == 85
print(json.dumps(dict(
    baseline_commit=BASE, baseline_fk_sha256=hashlib.sha256(raw).hexdigest(),
    current_fk_sha256=hashlib.sha256((ROOT / NAME).read_bytes()).hexdigest(),
    rng_seed=2026101711, commands=len(commands), mode_checks=checks,
    bitwise_equal=True, cached_views=85, views_and_counts_unchanged=True,
    cache_source_hashes_match=True, physics_steps=0, mujoco_render_calls=0), indent=2))
