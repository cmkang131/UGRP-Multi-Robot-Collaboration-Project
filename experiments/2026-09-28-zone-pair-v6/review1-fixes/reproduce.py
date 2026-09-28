"""Before/after counterexamples from git blobs; analytical RGB, no physical step."""
import json
import subprocess
import sys
import types
from dataclasses import replace
from pathlib import Path

from harness.zone_pair_guards import PairCommandGuard
from harness.zone_pair_global import GlobalEnvelope
from harness.zone_pair_relative import RelativeBeamTrack
from harness.zone_pair_v6_policy import pair_policy
from harness.zone_own_guards import OwnPose
from tests.test_zone_pair_grasp import real_pair
from tests.test_zone_pair_v6 import good
from tests.test_zone_pair_v6_review1 import image_at

BASE = '837a110ae15e46a45291100f161b3a33c83eb3d9'

def previous(path):
    name = 'review1_previous_'+Path(path).stem
    mod = types.ModuleType(name); sys.modules[name] = mod
    code = subprocess.check_output(['git','show',f'{BASE}:{path}'],text=True)
    exec(compile(code, f'{BASE}:{path}', 'exec'), mod.__dict__)
    return mod


def move(cls):
    _, _, eps = real_pair(); ep = eps['r1']; ep.policy = pair_policy('a+b')
    ep.controller.state = 'approach'
    ep.own.last_report = replace(good(), x_m=1.83, y_m=-1.8)
    guard = cls(ep)
    pose = OwnPose(1.83,-1.8,0.,.06,.01)
    guard.global_envelope.pose = lambda *args: pose
    command = dict(kind='mecanum',forward=.12,left=0.,turn=0.,duration_s=.15)
    gap = guard.sweep_guard().certificate(ep.own.servo,pose)['clearance_m']
    return {'clearance_m':gap, 'commands':guard.check(0.,[command]), 'aborted':ep.terminal}


def yaw(cls):
    import math
    env=cls(); env.pose(good(),0.)
    result=env.pose(replace(good(1.),yaw_rad=math.pi/2),1.)
    return {'fix_t':env.fix_t,'anchor_yaw_rad':env.anchor.yaw,
            'returned_std_yaw_rad':None if result is None else result.std_yaw}


def relative(cls):
    track=cls(); first,servo=image_at(.33)
    rows=[]
    def read(o,s):
        result=track.observe(o,s,0,now=o['sim_time'])
        rows.append({'t':o['sim_time'],'ready':result.ready(o['sim_time']),
                     'bound_m':None if result.std_xy_m is None else result.std_xy_m+result.bias_bound_m,
                     'grip_base_m':result.grip_base_m,'reasons':result.reasons})
    read(first,servo)
    track.command(dict(kind='mecanum',t=0.,forward=.08,left=0.,turn=0.,duration_s=.3),servo)
    after,_=image_at(.306,fid=2,t=.3);read(after,servo)
    frame,view=image_at(.306,'p45',fid=3,t=1.)
    for sid,pulse in view.items():
        if servo.get(sid)!=pulse:
            track.command(dict(kind='arm',t=.3,servo_id=sid,pulse=pulse),servo)
    read(frame,view)
    return rows

result={'base_sha':BASE,'scope':'counterfactual source/geometry regression, not episode replay or physics',
        'approach':{'before':move(previous('harness/zone_pair_guards.py').PairCommandGuard),'after':move(PairCommandGuard)},
        'yaw':{'before':yaw(previous('harness/zone_pair_global.py').GlobalEnvelope),'after':yaw(GlobalEnvelope)},
        'relative':{'before':relative(previous('harness/zone_pair_relative.py').RelativeBeamTrack),'after':relative(RelativeBeamTrack)}}
Path(__file__).with_name('counterexamples.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(result,ensure_ascii=False,indent=2))
