"""Offline v106 extension for #403; no execution admission or physics changes.

The frozen v106 runner/bundle stay byte-identical. A future camera+drive bundle
must explicitly select this Runtime and bind the renderer before execution.
"""
from __future__ import annotations

import copy
import numpy as np

from harness import zone_solo_cyan_v106 as legacy
from sim import masterpi_camera_profile as archived
from sim import masterpi_camera_review_v3 as camera
from sim.masterpi_camera_review_v1 import quat_matrix

PROFILE = 'solo-cyan-v106-camera-v3-setdown-option-offline-v1'
SCENE_PROFILE = 'solo-cyan-v106-camera-v3-scene-check-offline-v1'


def option_record(setdown_relook='on', camera_profile=None, grasp_check='off'):
    if setdown_relook not in ('on', 'off'):
        raise ValueError('setdown_relook must be on or off')
    if camera_profile not in (None, camera.PROFILE_ID):
        raise ValueError('unsupported camera profile')
    if setdown_relook == 'off' and camera_profile != camera.PROFILE_ID:
        raise ValueError('off requires explicit camera v3 profile')
    if grasp_check not in ('off', 'pickup_site_v1'):
        raise ValueError('grasp_check must be off or pickup_site_v1')
    if grasp_check != 'off' and camera_profile != camera.PROFILE_ID:
        raise ValueError('pickup-site check requires explicit camera v3 profile')
    record = {'profile': PROFILE, 'setdown_relook': setdown_relook,
            'camera_profile': camera_profile, 'runtime_admitted': False,
            'execution_bundle_id': None, 'pending_drive_issue': 404,
            'motion_proxy': legacy.MOTION_PROXY,
            'localization': 'own issued commands predict; visible wall RGB corrects',
            'physical_success': None}
    if grasp_check != 'off':
        record['grasp_check'] = grasp_check
        record['profile'] = SCENE_PROFILE
    return record


def camera_calibration(calibration):
    """Compose rigid transforms only; no new measurement or tuned fit.

    Camera records map OpenCV optical axes into the actual chassis. Strip the
    old gripper-to-camera transform, then apply v3. K/D, arm poses, floor/loaded
    chassis transforms and the command motion model remain inherited.
    """
    out = copy.deepcopy(calibration)
    optical = np.diag([1., -1., -1.])  # MuJoCo right/up/back -> right/down/forward
    old_r = quat_matrix(archived.CAMERA_LOCAL_QUAT_WXYZ) @ optical
    new_r = quat_matrix(camera.QUAT_WXYZ) @ optical
    delta_p = np.asarray(camera.POSITION_M)-archived.CAMERA_LOCAL_POS_M
    for table in out['camera_models'].values():
        for rec in table.values():
            if rec['frame'] != 'optical_to_actual_chassis':
                raise ValueError('unsupported camera calibration frame')
            gripper_r = np.asarray(rec['rotation']) @ old_r.T
            rec['origin_m'] = (np.asarray(rec['origin_m'])+gripper_r @ delta_p).tolist()
            rec['rotation'] = (gripper_r @ new_r).tolist()
    out['camera_v3_derivation'] = {
        'profile': camera.PROFILE_ID, 'status': 'RIGID_COMPOSITION_UNQUALIFIED',
        'source_camera_models_sha256': legacy.hp.base.digest(calibration['camera_models']),
        'derived_camera_models_sha256': legacy.hp.base.digest(out['camera_models']),
        'new_measurements': False, 'intrinsics_changed': False,
        'inherited_arm_and_chassis_calibration': True}
    return out


def build_provider(*args, **kwargs):
    source = legacy.build_provider(*args, **kwargs)
    try:
        inner = source.provider
        derived = camera_calibration(inner.calibration)
        # The PF column-model closure and CyanVision share this instance-local
        # dictionary. Updating it preserves that binding; no module globals move.
        inner.calibration.update(derived)
        inner.runtime_contract.update(camera_v3=derived['camera_v3_derivation'],
                                      qualification='OFFLINE_ONLY_PENDING_404_AND_CAMERA_BINDING')
        inner.identity_sha256 = legacy.hp.base.digest(inner.runtime_contract)
        inner.source = 'owncam_pf_'+PROFILE+':'+inner.identity_sha256[:8]
        source.source = inner.source
        inner.m1_calibration['camera_v3_derivation'] = derived['camera_v3_derivation']
        return source
    except Exception:
        source.close()
        raise


build_provider.controller_geometry_id = legacy.CONTROLLER_GEOMETRY_ID
build_provider.uses_landmark_tags = False


class Runtime(legacy.Runtime):
    def __init__(self, *args, setdown_relook='on', camera_profile=None,
                 grasp_check='off', provider_factory=None, **kwargs):
        self.option = option_record(setdown_relook, camera_profile, grasp_check)
        self.skipped_relooks = []
        factory = provider_factory or (build_provider if camera_profile else legacy.build_provider)
        super().__init__(*args, provider_factory=factory, **kwargs)
        self.scene_check = None
        if grasp_check != 'off':
            from harness.zone_solo_cyan_scene_runtime import SceneCheck
            self.scene_check = SceneCheck()

    def _control(self, now, idle):
        if self.scene_check is None:
            return super()._control(now, idle)
        return self.scene_check.control(self, now, idle, super()._control)

    def on_frames(self, now, frames):
        super().on_frames(now, frames)
        if self.scene_check is not None and not self.failure:
            self.scene_check.observe_carry(self, now)

    def drain_notifications(self):
        """Host-readable notices; no robot command or external message is sent."""
        if self.scene_check is None:
            return []
        notices, self.scene_check.pending_notifications = self.scene_check.pending_notifications, []
        return notices

    @property
    def visual_grasp_confirmed(self):
        return bool(self.receipt and self.scene_check is not None and
                    self.scene_check.visual_status == 'confirmed_by_site_disappearance')

    def setdown_relook(self, now, index):
        if self.option['setdown_relook'] == 'on':
            return super().setdown_relook(now, index)
        self.skipped_relooks.append(index)
        self.event('cyan_setdown_relook_disabled', now, index=index,
                   last_fix_t=self.last_report.last_fix_t, physical_success=None)
        # The parent carry state calls here and returns immediately. Advance
        # exactly once without opening the gripper or inventing a fresh fix.
        self.route_i += 1
        if self.route_i == len(self.route):
            for p, duration, settle in legacy.high.lower_path():
                self.queue({**p, 1: 1500}, now, duration=duration, settle=settle)
            self.set_state('lower', now)  # ordinary final release, never regrasp
        else:
            self.arm.until = now+legacy.high.HIGH_SETTLE_S

    def record(self):
        out = super().record()
        # Default extension is behaviour/record-equivalent to frozen v106.
        if self.option['camera_profile'] is None:
            return out
        out['profile'] = self.option['profile']
        out['offline_option'] = copy.deepcopy(self.option)
        out['setdown_relook'].update(enabled=self.option['setdown_relook'] == 'on',
                                    skipped_indexes=list(self.skipped_relooks))
        if self.scene_check is not None:
            out['scene_grasp_check'] = self.scene_check.record()
            out['visual_grasp_confirmed'] = self.visual_grasp_confirmed
            out['in_run_visual_drop_notifications'] = 'suspected_only_log_only'
        return out


def main(argv=None):
    """Print an offline plan only: intentionally no --execute or backend import."""
    import argparse
    import json
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--setdown-relook', choices=('on', 'off'), default='on')
    parser.add_argument('--camera-profile', choices=(camera.PROFILE_ID,))
    parser.add_argument('--grasp-check', choices=('off', 'pickup_site_v1'), default='off')
    args = parser.parse_args(argv)
    try:
        record = option_record(args.setdown_relook, args.camera_profile, args.grasp_check)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(record, indent=2))


if __name__ == '__main__':
    main()
