import hashlib
import json
from pathlib import Path
import sys
EXP = Path(__file__).resolve().parents[1]
ROOT = EXP.parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'experiments/2026-10-07-mapfree-raytrace/code')]
import common as v6
from harness.public_navigation_unknown import UnknownActor
RAW = Path('/Users/changmin/projects/ugrp/outputs/mapfree-unknown-v7')
SETTINGS = {**v6.SETTINGS, 'navigation':'public_ros_v7', 'footprint_clearing_enabled':True,
            'allow_unknown':True, 'track_unknown_space':True,
            'frontier_goal':'upstream_centroid', 'footprint_update_hz':10.}
CRITERIA = v6.CRITERIA
read,sha,write,lines = v6.read,v6.sha,v6.write,v6.lines


def hashes():
    out = v6.hashes()
    paths = [EXP/'README.md',EXP/'REFERENCES.md',ROOT/'harness/public_navigation_unknown.py',
             ROOT/'harness/public_navigation_unknown.cpp']
    paths += sorted((EXP/'code').glob('*.py'))
    paths += sorted((ROOT/'third_party/mapfree_navigation_unknown').rglob('*'))
    for p in paths:
        if p.is_file():out[str(p.relative_to(ROOT))] = sha(p)
    return out


def configure(manifest):
    v6.prior.v5.old.RectangleOracleWorld = v6.RayOracleWorld
    def factory(condition,static_grid=None,static_goal=None,*,navigation):
        assert navigation == 'public_ros_v5'
        return UnknownActor(condition,static_grid,static_goal,navigation='public_ros_v7')
    v6.prior.ResolutionActor = factory
    runner = v6.prior.configure(manifest)
    runner.SETTINGS = SETTINGS
    return runner
