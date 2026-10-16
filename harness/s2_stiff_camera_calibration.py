"""Surveyed planar target PnP: fixed pitch/roll/height, no robot truth input.

OpenCV homography tutorial, Demo 1. K/D remain fixed; known target geometry
and detected RGB corners determine ground orientation and metric height.
Horizontal camera offset/yaw retain the existing fixed structural calibration.
"""
import copy
import math
import numpy as np
from harness import s2_extrinsic_targets as target
from harness.zone_final_pair_camera import floor_camera

OPTION = 'stiff_target_v1'


def fit(samples):
    rec, quality = target.fit(samples)
    camera = floor_camera(rec)
    r = np.asarray(camera['rotation'])
    return dict(ground_normal_optical=r[2].tolist(),
                pitch_deg=math.degrees(math.asin(r[2, 2])),
                height_m=camera['origin_m'][2], quality=quality)


def corrected_record(old, measured):
    camera = floor_camera(old)
    old_r = np.asarray(camera['rotation'])
    n = np.asarray(measured['ground_normal_optical'], float)
    if n.shape != (3,) or not np.isfinite(n).all() or not np.isclose(n @ n, 1., atol=1e-6) or n[1] >= 0:
        raise ValueError('invalid measured ground normal')
    height = float(measured['height_m'])
    if not .02 < height < .5:
        raise ValueError('invalid measured camera height')
    yaw = math.atan2(old_r[1, 2], old_r[0, 2])
    f = np.array([math.cos(yaw), math.sin(yaw)])
    side = np.array([math.sin(yaw), -math.cos(yaw)])
    h = math.sqrt(1 - n[2]**2)
    a = -n[0] * n[2] / h
    b = math.sqrt(max(0., 1 - n[0]**2 - a*a))
    forward = np.r_[h*f, n[2]]
    right = np.r_[a*f + b*side, n[0]]
    rotation = np.column_stack((right, np.cross(forward, right), forward))
    origin = list(camera['origin_m']); origin[2] = height
    # Coordinate encoding only; no claim of a live chassis tilt measurement.
    base = .0325
    return dict(frame='optical_to_actual_chassis',
                origin_m=[origin[0], origin[1], height-base], rotation=rotation.tolist(),
                chassis_to_floor=dict(origin_m=[0., 0., base], rotation=np.eye(3).tolist()))


def apply(source, table, *, camera_pitch='off', servo_stiffness='off'):
    if camera_pitch == 'off':
        return source
    if camera_pitch != OPTION or servo_stiffness != 'real_v1':
        raise ValueError('stiff target calibration requires explicit real_v1 plant')
    if (table.get('option') != OPTION or table.get('fit_uses_gt') is not False
            or table.get('servo_stiffness') != 'real_v1' or not table.get('complete')):
        raise ValueError('complete RGB target calibration required')
    cal = source.provider.calibration
    replacement = copy.deepcopy(cal['camera_models'])
    for state, poses in replacement.items():
        for key, rec in poses.items():
            if key not in table['poses']:
                raise ValueError('uncalibrated camera pose: '+key)
            poses[key] = corrected_record(rec, table['poses'][key])
    cal['camera_models'].clear(); cal['camera_models'].update(replacement)
    receipt = dict(option=OPTION, servo_stiffness='real_v1', runtime_gt=False,
                   unloaded_measured=True, loaded_measured=False,
                   loaded_assumption='rigid unloaded transform; requires separate loaded VO validation',
                   calibration_sha256=target.contract.old.hp.base.digest(table))
    cal['s2_stiff_camera'] = receipt
    source.provider.runtime_contract['s2_stiff_camera'] = receipt
    source.provider.identity_sha256 = target.contract.old.hp.base.digest(source.provider.runtime_contract)
    source.provider.source = 'owncam_pf_s2_stiff_target:'+source.provider.identity_sha256[:8]
    source.source = source.provider.source
    return source


def runtime_class(previous):
    class Runtime(previous):
        def __init__(self, *args, camera_pitch='off', stiff_camera_table=None,
                     servo_stiffness='off', **kwargs):
            if camera_pitch not in ('off', OPTION):
                raise ValueError('unknown camera_pitch')
            super().__init__(*args, **kwargs)
            try:
                apply(self.pose, stiff_camera_table or {}, camera_pitch=camera_pitch,
                      servo_stiffness=servo_stiffness)
            except Exception:
                self.close(); raise
            self.camera_pitch = camera_pitch

        def record(self):
            result = super().record()
            if self.camera_pitch != 'off':
                result['stiff_camera'] = copy.deepcopy(self.pose.provider.calibration['s2_stiff_camera'])
            return result
    return Runtime
