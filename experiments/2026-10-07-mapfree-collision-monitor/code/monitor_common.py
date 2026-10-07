from pathlib import Path
import sys
EXP=Path(__file__).resolve().parents[1]
ROOT=EXP.parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'experiments/2026-10-07-mapfree-unknown-footprint/code')]
import unknown_common as v7
from harness.public_navigation_monitor import MonitorActor,PARAMETERS
from integer_episode import episode
read,write,sha,lines=v7.read,v7.write,v7.sha,v7.lines
RAW=Path('/Users/changmin/projects/ugrp/outputs/mapfree-monitor-v8')
CRITERIA=v7.CRITERIA
SETTINGS={**v7.SETTINGS,'navigation':'public_ros_v8','monitor':PARAMETERS,
    'frontier_potential':3.,'frontier_gain':1.,'frontier_min_m':.75,'frontier_frequency_hz':.33,
    'footprint_update_hz':5.,'logical_clock':'integer_100ms_v1'}


def hashes():
    old=v7.hashes()
    assert old==read(v7.EXP/'freeze.json')['hashes'],'V7_FROZEN_BYTES_CHANGED'
    paths=[EXP/'README.md',EXP/'REFERENCES.md',ROOT/'harness/public_navigation_monitor.py',ROOT/'harness/public_navigation_monitor.cpp']
    paths+=sorted((EXP/'code').glob('*.py'))
    paths+=sorted((ROOT/'third_party/mapfree_navigation_monitor').rglob('*'))
    return {**old,**{str(p.relative_to(ROOT)):sha(p) for p in paths if p.is_file()}}


def configure(manifest):
    v7.v6.prior.v5.old.RectangleOracleWorld=v7.v6.RayOracleWorld
    def factory(condition,static_grid=None,static_goal=None,*,navigation):
        assert navigation=='public_ros_v5'
        return MonitorActor(condition,static_grid,static_goal,navigation='public_ros_v8')
    v7.v6.prior.ResolutionActor=factory
    runner=v7.v6.prior.configure(manifest)
    runner.SETTINGS=SETTINGS
    return runner
