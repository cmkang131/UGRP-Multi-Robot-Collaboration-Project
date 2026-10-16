"""Explicit carry FK adapters; bind dependencies locally, preserve legacy globals.

Only own PWM + fixed geometry/K/D/RGB. No load detector or sag correction.
The finger envelopes still use the actual issued grip PWM for occlusion.
"""
from functools import lru_cache
import numpy as np
from harness.servo_camera_fk import transform_from_commands, CARRY_OPTION
from harness.active_camera import bind


@lru_cache(maxsize=2)
def adapters(camera_pose='off'):
    from harness import e2e_rgb_vo as vo
    from harness import mapbuild_rbpf as rb
    if camera_pose=='off':return vo.ground_pair,rb.virtual_scan
    if camera_pose!=CARRY_OPTION:raise ValueError('UNKNOWN_MAPBUILD_CAMERA')
    from harness.floor_goal_self_mask import body_envelopes,project_envelopes
    def camera(servo):
        value,reason=transform_from_commands(servo,camera_pose=camera_pose)
        if value is None:raise ValueError(reason)
        return value
    @lru_cache(maxsize=16)
    def cached(items):return camera(dict(items))
    def mask(servo,profile,width,height):
        if profile!='camera_v3':raise ValueError('V3_ONLY')
        origin,rotation=camera(servo)
        return project_envelopes(body_envelopes(servo,profile),origin,rotation.T,width,height)
    ground=bind(vo.ground,_camera=cached)
    floor_mask=lru_cache(maxsize=16)(bind(vo.floor_mask.__wrapped__,ground=ground,self_body_mask=mask))
    image_mask=bind(vo.image_mask,floor_mask=floor_mask)
    covariance=bind(vo.rigid_fit_covariance,ground=ground)
    pair=bind(vo.ground_pair,ground=ground,image_mask=image_mask,rigid_fit_covariance=covariance)
    # virtual_scan imports its dependencies inside its body; give it explicit
    # keyword parameters rather than mutating another module's globals.
    def scan(rgb,servo,state):return rb.virtual_scan(rgb,servo,state,camera_pose=camera_pose)
    return pair,scan
