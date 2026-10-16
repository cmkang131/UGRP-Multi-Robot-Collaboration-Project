"""Own-input loader, without evaluation imports or simulator execution."""
import hashlib
import json
from pathlib import Path
import sys

EXP=Path(__file__).resolve().parents[1]
ROOT=EXP.parents[1]
OUT=Path('/Users/changmin/projects/ugrp/outputs/wall-parallax-v1')
sys.path[:0]=[str(ROOT),str(ROOT/'experiments/2026-10-05-ego-wall-map-probe/code')]
import v3_confidence_replay as old
from harness.self_map_prob import V7CommandOdometry

EPISODES={**old.EPISODES,
    's1050':Path('/Users/changmin/projects/ugrp/outputs/s2-realism-97fcb5d2-s1050-P1-2-place'),
    's1051':Path('/Users/changmin/projects/ugrp/outputs/s2-realism-c26e9afd-s1051-P1-2-place')}


def read(path):return json.loads(Path(path).read_text())
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def dump(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,indent=2,ensure_ascii=False,allow_nan=False)+'\n')


def stream(case):
    fs,cs=old.own_inputs(EPISODES[case],'r3')
    odom=V7CommandOdometry(fs[0]['sim_time'])
    odom.command(dict(t=fs[0]['sim_time'],kind='initial_servo_command',pulses=fs[0]['commanded_servo']))
    cursor=0
    for i,f in enumerate(fs):
        t=f['sim_time']
        while cursor<len(cs) and cs[cursor]['t']<t-1e-8:
            odom.command(cs[cursor])
            cursor+=1
        odom.advance(t)
        if i%2:continue
        cm=None
        if t-odom.servo_since+1e-8 < (.25,2.25)[int(odom.loaded)]:reason='unsettled'
        else:
            servo={int(k):int(v) for k,v in f['commanded_servo'].items()}
            cm,_,reason=old.geometry(servo,'v3_unloaded_extrinsic_v1')
        yield f,cm,reason,odom.pose,odom.covariance.copy()
