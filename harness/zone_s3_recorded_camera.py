"""Default-off rigid camera remapping for the archived S3 input replay only.

s14201 omitted S2's persistent v3 render binding. Its renderer used the old
centered mount. Strip the calibrated v3 mount and compose the recorded mount;
retain measured arm/floor transforms, K/D, noise and all filter thresholds.
No fit, GT input, image synthesis or camera placement change is performed.
"""
import copy
import numpy as np

from sim import masterpi_camera_profile as legacy
from sim import masterpi_camera_review_v3 as v3
from sim.masterpi_camera_review_v1 import quat_matrix

OPTION = 'legacy_centered_replay_v1'


def calibration_for_recorded_mount(calibration):
    out = copy.deepcopy(calibration)
    optical = np.diag([1., -1., -1.])
    old_r = quat_matrix(v3.QUAT_WXYZ) @ optical
    recorded_r = quat_matrix(legacy.CAMERA_LOCAL_QUAT_WXYZ) @ optical
    delta = np.asarray(legacy.CAMERA_LOCAL_POS_M)-v3.POSITION_M
    for poses in out['camera_models'].values():
        for rec in poses.values():
            if rec['frame'] != 'optical_to_actual_chassis':
                raise ValueError('unsupported camera calibration frame')
            gripper = np.asarray(rec['rotation']) @ old_r.T
            rec['origin_m'] = (np.asarray(rec['origin_m'])+gripper@delta).tolist()
            rec['rotation'] = (gripper@recorded_r).tolist()
    return out


def attach(runtime, *, recorded_camera_mount='off'):
    if recorded_camera_mount == 'off':
        return runtime
    if recorded_camera_mount != OPTION:
        raise ValueError('unknown recorded_camera_mount')
    inner = runtime.pose.provider
    revised = calibration_for_recorded_mount(inner.calibration)
    inner.calibration['camera_models'].clear()
    inner.calibration['camera_models'].update(revised['camera_models'])
    old_record = runtime.record
    audit = dict(option=OPTION, scope='archived input replay only; not the next v3 physical configuration',
        gt_inputs=False, fit=False, thresholds_changed=False, images_changed=False,
        runtime_mount='centered structural legacy', calibration_mount_before=v3.PROFILE_ID)
    inner.runtime_contract['s3_recorded_camera'] = copy.deepcopy(audit)
    from harness.zone_solo_cyan_v106 import hp
    inner.identity_sha256 = hp.base.digest(inner.runtime_contract)
    inner.source = 'owncam_pf_s3_recorded_mount:'+inner.identity_sha256[:8]
    runtime.pose.source = inner.source
    runtime.record = lambda: {**old_record(), 'recorded_camera_mount': copy.deepcopy(audit)}
    return runtime
