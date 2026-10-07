from pathlib import Path
import sys
EXP=Path(__file__).resolve().parents[1]
ROOT=EXP.parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'experiments/2026-10-07-mapfree-collision-monitor/code')]
import monitor_common as v8
read,write,sha,lines=v8.read,v8.write,v8.sha,v8.lines
RAW=Path('/Users/changmin/projects/ugrp/outputs/mapfree-v8-stop')
PRIOR=v8.RAW/'development'
CRITERIA=v8.CRITERIA
SETTINGS={**v8.SETTINGS,'stop_adapter':'v8_final_zero_velocity_bugfix',
    'observation_wait_controller_hz':10.}
CHANGED={'harness/public_navigation_monitor.py',
    'experiments/2026-10-07-mapfree-collision-monitor/code/integer_episode.py'}


def hashes():
    old=read(v8.EXP/'freeze.json')['hashes']
    current=v8.hashes()
    assert set(current)==set(old)
    assert {p for p in old if old[p]!=current[p]}==CHANGED
    paths=[EXP/'README.md',EXP/'REFERENCES.md',ROOT/'tests/test_navigation_stop.py']
    paths+=sorted((EXP/'code').glob('*.py'))
    paths+=sorted((EXP/'references').rglob('*'))
    return {**current,**{str(p.relative_to(ROOT)):sha(p) for p in paths if p.is_file()}}


def configure(manifest):
    runner=v8.configure(manifest)
    runner.SETTINGS=SETTINGS
    return runner
