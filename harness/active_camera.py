"""Command-only look-ahead camera, fixed v3 mount/K/D. Default identity."""
import math
from functools import lru_cache
from types import FunctionType
from harness.servo_camera_fk import transform_from_commands

SEARCH = {1:2000,3:740,4:2320,5:1320,6:1500}
LOOK_AHEAD = {**SEARCH,3:858}  # nominal -7.46 deg, 0.09 deg/PWM rounding


def servo_output(legacy, *, camera_pose='off'):
    if camera_pose == 'off':
        return legacy
    if camera_pose != 'look_ahead_v1':
        raise ValueError('UNKNOWN_ACTIVE_CAMERA')
    return {**legacy,3:858}


def transform(servo):
    result, reason = transform_from_commands(servo,camera_pose='servo_fk_v1')
    if result is None:
        raise ValueError(reason)
    return result


def pitch(servo):
    return math.degrees(math.asin(float(transform(servo)[1][2,2])))


def goal_camera(servo, profile):
    if profile != 'camera_v3':
        raise ValueError('ACTIVE_CAMERA_REQUIRES_V3')
    origin, rotation = transform(servo)
    return origin, rotation.T


def bind(fn, **injected):
    """Dependency injection without mutating frozen function/module globals."""
    cloned=FunctionType(fn.__code__,{**fn.__globals__,**injected},fn.__name__,fn.__defaults__,fn.__closure__)
    cloned.__kwdefaults__=fn.__kwdefaults__
    return cloned


@lru_cache(maxsize=1)
def goal_detector():
    from harness import floor_goal_v2 as v2, floor_goal_v3 as v3, floor_goal_self_mask as mask
    @lru_cache(maxsize=4)
    def own_mask(items, profile, w, h):
        servo=dict(items)
        origin,axes=goal_camera(servo,profile)
        return mask.project_envelopes(mask.body_envelopes(servo,profile),origin,axes,w,h)
    def self_mask(servo,profile,w,h):
        return own_mask(tuple(sorted(servo.items())),profile,w,h)
    return bind(v3.detect_floor_v3, commanded_camera=goal_camera,self_body_mask=self_mask,
                detect_floor_v2=bind(v2.detect_floor_v2,commanded_camera=goal_camera))
