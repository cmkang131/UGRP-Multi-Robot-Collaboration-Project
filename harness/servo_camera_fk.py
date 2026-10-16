"""Default-off v3 camera TF chain from OWN commanded PWM, never actual joint GT.

robot_state_publisher convention: fixed parent->joint transform, joint rotation,
then child transform. Uses stored structural geometry only, no simulator/ROS.
Commanded joint targets do not measure gravity sag or chassis roll/pitch.
"""
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from harness.visual_arm import PULSE_PER_DEGREE, SERVO_DEVIATION

OPTION='servo_fk_v1'
MODEL=Path(__file__).with_name('data')/'servo_camera_v3_chain.json'
MODEL_SHA256='0cced72fd129556cb1e1ecbeef63155129426e669f77b6d5a70244d3d9b269be'


@lru_cache(maxsize=1)
def model():
    raw=MODEL.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=MODEL_SHA256:
        raise ValueError('SERVO_CAMERA_GEOMETRY_CHANGED')
    return json.loads(raw)


def axis_rotation(axis,angle):
    axis=np.asarray(axis,float)
    axis=axis/np.linalg.norm(axis)
    x,y,z=axis
    k=np.array([[0,-z,y],[z,0,-x],[-y,x,0]])
    return np.eye(3)+math.sin(angle)*k+(1-math.cos(angle))*(k@k)


def fixed_transform(record):
    w,x,y,z=record['quaternion_wxyz']
    q=np.asarray([w,x,y,z],float)
    if not np.isclose(np.linalg.norm(q),1.,atol=1e-9):
        raise ValueError('INVALID_FIXED_CAMERA_QUATERNION')
    t=np.eye(4)
    t[:3,3]=record['translation_m']
    t[:3,:3]=np.array([[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],
        [2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],
        [2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]])
    return t


def commanded_joints(servo):
    """Reuse the v7 driver's fixed PWM->target convention, not live joint state."""
    if not isinstance(servo,dict):
        raise ValueError('OWN_SERVO_COMMANDS_REQUIRED')
    pose={int(k):float(v) for k,v in servo.items()}
    if set(pose)-{1,3,4,5,6} or not {1,3,4,5,6}<=set(pose):
        raise ValueError('OWN_SERVO_COMMAND_SCHEMA')
    if not all(math.isfinite(v) and 500<=v<=2500 for v in pose.values()):
        raise ValueError('INVALID_SERVO_COMMAND')
    nominal=lambda k:pose[k]-SERVO_DEVIATION[k]
    return pose, {6:math.radians((pose[6]-1500.)/PULSE_PER_DEGREE),
        5:math.radians(90.-(nominal(5)-1500.)/PULSE_PER_DEGREE),
        4:math.radians(-(nominal(4)-1500.)/PULSE_PER_DEGREE),
        3:math.radians((nominal(3)-1500.)/PULSE_PER_DEGREE)}


def transform_from_commands(servo, *, camera_pose='off'):
    if camera_pose=='off':
        return None,'off'
    if camera_pose!=OPTION:
        raise ValueError('UNKNOWN_CAMERA_POSE')
    pose,joints=commanded_joints(servo)
    # Preserve egomap9's unloaded comparison domain. A closed gripper command
    # does not reveal actual load, and loaded sag is unmeasured by this model.
    if pose[1]<=1600:
        return None,'loaded_or_unknown_load_not_qualified'
    spec=model()
    t=np.eye(4)
    t[:3,3]=spec['floor_to_chassis_translation_m']
    for link in spec['chain']:
        t=t@fixed_transform(link)
        if 'servo' in link:
            angle=joints[link['servo']]
            lo,hi=link['range_rad']
            if not lo<=angle<=hi:
                return None,'command_target_outside_joint_range'
            joint=np.eye(4)
            joint[:3,:3]=axis_rotation(link['joint_axis'],angle)
            t=t@joint
    t=t@fixed_transform(spec['camera'])
    # MuJoCo fixed camera mount convention -> OpenCV right/down/forward.
    rot=t[:3,:3]@np.diag([1.,-1.,-1.])
    return (t[:3,3].copy(),rot),'servo_fk_nominal_unloaded'


def camera_output(legacy, *, camera_pose='off', servo=None):
    """Identity passthrough when off; requires explicit own-command opt-in."""
    if camera_pose=='off':
        return legacy
    return transform_from_commands(servo,camera_pose=camera_pose)
