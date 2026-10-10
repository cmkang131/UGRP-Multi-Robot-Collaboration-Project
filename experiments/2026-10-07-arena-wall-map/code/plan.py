"""Compile authored waypoints to sealed v122 pulses, without any scene/GT input."""
from pathlib import Path
import copy
import json
import math
import sys
import numpy as np
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from harness.self_pulse_odom import command_odometry,wrap
from scripts.run_wall_parallax_strafe import PULSES,write
EXP=Path(__file__).resolve().parents[1]
# Own-start frame: x initially west, y initially south. These are authored goals.
POINTS=[[0,0],[0,3.35],[3.55,3.35],[3.55,.10],[1.95,.10],
        [1.95,3.35],[-1.35,3.35],[-1.35,0],[0,0]]
HEADINGS=[0,math.pi/2,0,-math.pi/2,-math.pi,math.pi/2,-math.pi,-math.pi/2]


def compile_route(reverse=False):
    points=list(reversed(POINTS)) if reverse else POINTS
    headings=list(reversed(HEADINGS)) if reverse else HEADINGS
    odom=command_odometry(motion_model='s2_pulse_v122')
    odom.command(dict(t=0,kind='initial_servo_command',pulses=PULSES))
    t=2.
    commands=[]
    milestones=[]
    path=[[0.,0.,0.,0.]]
    for leg,(target,heading) in enumerate(zip(points[1:],headings)):
        for _ in range(500):
            odom.advance(t)
            p=np.array(odom.pose)
            error=abs(wrap(heading-p[2]))
            if np.linalg.norm(p[:2]-target)<=.10 and error<=math.radians(3):
                break
            axes=('turn',) if error>math.radians(3) else ('left','forward')
            candidates=[]
            for axis in axes:
                for sign in (-1,1):
                    action=dict(kind='mecanum',forward=0.,left=0.,turn=0.,duration_s=.65 if axis=='left' else .10)
                    action[axis]=sign*(.65 if axis=='left' else .35)
                    step=.8 if axis=='left' else .2
                    q=copy.deepcopy(odom)
                    q.command(dict(t=t,**action))
                    q.advance(round(t+step,8))
                    new=np.array(q.pose)
                    cost=abs(wrap(heading-new[2])) if axis=='turn' else np.linalg.norm(new[:2]-target)
                    candidates.append((cost,action,q,step))
            _,action,odom,step=min(candidates,key=lambda x:x[0])
            commands.append(dict(t=round(t,8),leg=leg,**action))
            t=round(t+step,8)
            path.append([t,*odom.pose])
        else:raise ValueError('COMMAND_COMPILER_STUCK')
        milestones.append(dict(leg=leg,target_own_m=target,heading_own_rad=heading,t=t,predicted_pose=odom.pose))
        t+=1. # observe/settle at each authored corner
    assert t<=180.,('COMMAND_BUDGET_EXCEEDED',t)
    return dict(schema='ugrp.authored_pulse_route.v1',frame='own start SE2; no runtime map or truth',
        case='reverse' if reverse else 'forward',seed=20102 if reverse else 20101,
        spawn_setup_only=[3.25,.75,math.pi],cap_s=180.,capture_s=.1,
        end_command_s=t,commands=commands,milestones=milestones,predicted_path=path)


if __name__=='__main__':
    for reverse in (False,True):
        plan=compile_route(reverse)
        write(EXP/(plan['case']+'-plan.json'),plan)
        print(plan['case'],len(plan['commands']),plan['end_command_s'])
