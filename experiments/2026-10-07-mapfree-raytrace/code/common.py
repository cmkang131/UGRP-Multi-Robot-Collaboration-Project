import hashlib
import json
from pathlib import Path
import sys
EXP = Path(__file__).resolve().parents[1]
ROOT = EXP.parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'experiments/2026-10-07-mapfree-frontier-oracle/code')]
import run_frontier as prior
from harness.public_navigation_raytrace import RaytraceActor
from ray_world import RayOracleWorld

RAW = Path('/Users/changmin/projects/ugrp/outputs/mapfree-raytrace-v6')
PRIOR_RAW = Path('/Users/changmin/projects/ugrp/outputs/mapfree-frontier-oracle-v1')
SETTINGS = {**prior.SETTINGS, 'navigation': 'public_ros_v6',
            'obstacle_memory': 'camera_origin_bresenham_clear_then_mark_v1'}
CRITERIA = prior.CRITERIA


def read(p): return json.loads(p.read_text())
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p, value): prior.write(p, value)
def lines(p): return [json.loads(x) for x in p.read_text().splitlines()]


def hashes():
    out = prior.hashes()  # verifies every v5 source byte as well
    paths = [EXP/'README.md', EXP/'REFERENCES.md', ROOT/'harness/public_navigation_raytrace.py']
    paths += [EXP/'code'/name for name in ('common.py','ray_world.py','development.py','register_new.py','gate.py','run_raytrace.py')]
    for p in paths:
        out[str(p.relative_to(ROOT))] = sha(p)
    return out


def configure(manifest):
    prior.v5.old.RectangleOracleWorld = RayOracleWorld
    def factory(condition, static_grid=None, static_goal=None, *, navigation):
        assert navigation == 'public_ros_v5'
        return RaytraceActor(condition, static_grid, static_goal, navigation='public_ros_v6')
    prior.ResolutionActor = factory
    runner = prior.configure(manifest)
    runner.SETTINGS = SETTINGS
    return runner
