"""Execute upstream PythonRobotics pursuit; adapt body twist to own M1 commands.

Only the upstream target/steering functions are run, never its simulation/main.
Nav2 RPP rotate-to-heading + projected footprint collision structure is ported.
"""
from functools import lru_cache
import importlib.util
import math
from types import SimpleNamespace
import sys

import numpy as np

from harness.self_odom_grid import motion_profiles
from .native import ROOT,VENDOR


def wrap(x):
    return (x+math.pi)%(2*math.pi)-math.pi


@lru_cache(maxsize=1)
def pursuit():
    # Existing optional plot dependency, not a new venv/install. No figures are created.
    deps = ROOT/'outputs/self-map-plot-deps'
    if deps.exists():
        sys.path.insert(0,str(deps))
    base = VENDOR/'PythonRobotics'
    sys.path.insert(0,str(base))
    spec = importlib.util.spec_from_file_location('ugrp_upstream_pursuit',base/'PathTracking/pure_pursuit/pure_pursuit.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.show_animation = False
    module.WB = .24
    module.Lfc = .20
    module.k = .1
    return module


def follow_twist(path,pose,goal_heading=None):
    path,pose = np.asarray(path,float).reshape(-1,2),np.asarray(pose,float)
    remaining = np.linalg.norm(path[-1]-pose[:2]) if len(path) else 0.
    if remaining <= .05:
        error = wrap((goal_heading if goal_heading is not None else pose[2])-pose[2])
        return np.array([0.,0.,float(np.clip(error/.1,-.5,.5))])
    module = pursuit()
    # Bicycle rear axle is aligned with our commanded body origin, not displaced .12 m.
    state = SimpleNamespace(rear_x=pose[0],rear_y=pose[1],yaw=pose[2],v=.12,direction=1)
    state.calc_distance = lambda x,y: math.hypot(pose[0]-x,pose[1]-y)
    # Fresh course after own-DR pruning; no call to upstream vehicle.update/dynamics.
    course = module.TargetCourse(path[:,0].tolist(),path[:,1].tolist())
    delta,index = module.pure_pursuit_steer_control(state,course,0)
    angle = wrap(math.atan2(path[index,1]-pose[1],path[index,0]-pose[0])-pose[2])
    if abs(angle)>math.pi/4:
        return np.array([0.,0.,math.copysign(.5,angle)])
    velocity = min(.12,remaining)
    return np.array([velocity,0.,velocity/module.WB*math.tan(delta)])


def command_from_twist(twist,t,duration=.1):
    requested = np.linalg.solve(np.asarray(motion_profiles()['motion']['gain']),twist)
    requested /= max(1.,abs(requested[0])/.25,abs(requested[1])/.25,abs(requested[2])/.5)
    return dict(t=float(t),kind='mecanum',forward=float(requested[0]),left=float(requested[1]),
                turn=float(requested[2]),duration_s=float(duration))


def projected_clear(costmap,pose,twist,horizon=1.):
    # Nav2 RPP finite collision projection. Rectangle interior + boundary, not a point robot.
    predicted = np.array(pose,float)
    for _ in range(math.ceil(horizon/.05)):
        c,s = math.cos(predicted[2]),math.sin(predicted[2])
        predicted += np.array([c*twist[0]-s*twist[1],s*twist[0]+c*twist[1],twist[2]])*.05
        if not costmap.pose_clear(predicted):
            return False
    return True
