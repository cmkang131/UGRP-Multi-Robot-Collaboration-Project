"""Measured-calibration consumer for v84; P03 lifecycle and delay are reused.

No v2 kinematic/sag fallback: each observed posture must have an offline v3
camera calibration. This module receives no world, peer, or eval-only handle.
"""
from __future__ import annotations

import copy
import math
import numpy as np

from harness import vision_loc_protocol as vp
from harness import zone_final_environment as env
from harness.vision_pose_source_p03 import VisionPoseSource, FailClosedLoc
from harness.vision_loc_client import VisionWorkerClient


class CalibrationError(ValueError):
    pass


def camera_key(servo):
    return ','.join(str(int(servo[k])) for k in (3, 4, 5, 6))


def measured_column_model(mp, record, columns):
    """Same column projection as VIS3, with fixed measured v3 extrinsics.

    The saved camera pose is a static calibration product. It is never read
    from the running world. Do not patch the frozen VIS3 module's globals.
    """
    o, rot = np.asarray(record['origin_m'], float), np.asarray(record['rotation'], float)
    if (o.shape != (3,) or rot.shape != (3, 3) or not np.isfinite(o).all()
            or not np.isfinite(rot).all() or o[2] <= 0
            or not np.allclose(rot.T @ rot, np.eye(3), atol=1e-5)
            or not np.isclose(np.linalg.det(rot), 1., atol=1e-5)):
        raise CalibrationError('invalid measured v3 camera transform')
    cm = mp.ColumnModel.__new__(mp.ColumnModel)
    cm.columns, cm.origin, cm._rot = np.asarray(columns), o, rot
    u = cm.columns.astype(float)
    a = rot @ (mp.K_INV @ np.stack([u, np.zeros_like(u), np.ones_like(u)]))
    b = rot @ (mp.K_INV @ np.array([0., 1., 0.]))
    if abs(b[2]) < 1e-12:
        raise CalibrationError('camera calibration has no floor trace')
    bottom = mp.HEIGHT - 1.
    far = np.minimum(bottom - 1., -a[2] / b[2] + 25.)
    points = []
    for v in (np.full_like(u, bottom), far):
        ray = a + v[None, :] * b[:, None]
        if np.any(ray[2] >= 0):
            raise CalibrationError('bottom image row does not see the floor')
        points.append(o[:, None] + ray * (-o[2] / ray[2]))
    q0, q1 = points
    d = q1 - q0
    d /= np.linalg.norm(d[:2], axis=0, keepdims=True)
    cm.q0, cm.d = q0[:2].T, d[:2].T
    cm.alpha = (rot.T @ (q0 - o[:, None])).T
    cm.beta = (rot.T @ np.vstack([d[:2], np.zeros(len(u))])).T
    cm.gamma, cm._traces = rot.T @ np.array([0., 0., 1.]), {}
    return cm


class FinalVisionPoseSource(VisionPoseSource):
    provider_id = env.PROVIDER_ID
    source_prefix = 'owncam_pf_vision_zero_tag_final_v3_p03'

    def __init__(self, static_map, params, seed=0, *, calibration, calibration_sha256, worker=None, cfg=None):
        static, row, _ = env.resolve(static_map['map_id'])
        if static_map != static:
            raise ValueError('final provider requires the exact registered static map')
        cal = env.measured_calibration(calibration, calibration_sha256, static['map_id'])
        if params != cal['params']:
            raise ValueError('params differ from measured v3 motion calibration')
        if not isinstance(seed, int) or isinstance(seed, bool):
            raise TypeError('seed must be an int')
        self.cfg = vp.load_config() if cfg is None else cfg
        # Validate the existing worker/model/frozen source contract against its
        # own v2 registration, then separately bind the new map + calibration.
        # No old accuracy or camera qualification is inherited.
        from harness.vision_loc_contract_p03 import provider_runtime_contract
        worker_contract = provider_runtime_contract(map_id='zone_wide_door_geometry_v2', cfg=self.cfg)
        self.runtime_contract = {'provider': env.provider_spec(static['map_id']),
                                 'worker_model_contract': worker_contract,
                                 'calibration_sha256': calibration_sha256,
                                 'calibration_source_sha': cal['source_sha'],
                                 'qualification': 'DRAFT; physical acceptance pending'}
        vl, vpf = vp.load_vis3()
        self.frozen = vp.check_frozen()
        from harness.vision_motion_init import motion_module
        sel = vp.selected_config()
        pf = vpf.make_robust_pf(motion_module(vl.mp.load_m1_localizer()), copy.deepcopy(static),
                                copy.deepcopy(params), sel.get('measurement', {}), sel.get('obs', {}),
                                {}, seed, cal['pan_base_yaw'], sel.get('robust', {}))
        camera_models = copy.deepcopy(cal['camera_models'])

        def column_model_for(pose, columns=None):
            state, key = ('loaded' if pf.load.loaded else 'unloaded'), camera_key(pose)
            if key not in camera_models[state]:
                raise CalibrationError(f'UNMEASURED_V3_CAMERA_POSTURE: {state}:{key}')
            # Extrinsics are measured in the actual chassis frame; the PF
            # represents nominal yaw and adds the measured pan-induced yaw.
            # Apply that same static offset to the camera model, as VIS3 does.
            yaw = vl.pan_yaw(cal['pan_base_yaw'], pf.load.loaded, pose)
            c, s = math.cos(yaw), math.sin(yaw)
            rz = np.array([[c, -s, 0.], [s, c, 0.], [0., 0., 1.]])
            record = camera_models[state][key]
            shifted = {'origin_m': rz @ np.asarray(record['origin_m']),
                       'rotation': rz @ np.asarray(record['rotation'])}
            return measured_column_model(vl.mp, shifted,
                                         pf.columns if columns is None else columns)

        pf.column_model_for = column_model_for
        self.loc = FailClosedLoc(pf, self.provider_id, on_command=self.on_command)
        self.seed = seed
        self.m1_calibration = {'path': str(calibration), 'file_sha256': calibration_sha256,
                               'robot_model': 'masterpi_v3', 'v2_inherited': False}
        self.identity_sha256 = env.digest({'provider': self.provider_id, 'map': row['static_map_sha256'],
                                          'contract': self.runtime_contract, 'frozen': self.frozen})
        self.source = f'{self.source_prefix}:{self.identity_sha256[:8]}'
        self.servo, self.prior, self.failure, self.last_obs = {}, None, None, None
        self.counts = {'frames': 0, 'worker_calls': 0, 'measured': 0, 'unsettled_or_uninitialized': 0,
                       'rejected_frames': 0, 'after_failure': 0}
        self.timing, self.lifecycle = [], []
        self._started, self._closed, self._last_frame_t = False, False, None
        self.worker = worker if worker is not None else VisionWorkerClient(self.cfg)

    def on_frame(self, now, rgb):
        try:
            return super().on_frame(now, rgb)
        except CalibrationError as error:
            # An unmeasured posture cannot leave a usable stale posterior.
            self._fail(now, str(error))
            return self.report(now)


def build_provider(static_map, params, seed, *, calibration, calibration_sha256, worker=None):
    """Exactly one P03 delay wrapper; dispose a worker if wrapping fails."""
    from harness.zone_study_pose_delay_p03 import DelayedPoseSource
    provider = FinalVisionPoseSource(static_map, params, seed, calibration=calibration,
                                     calibration_sha256=calibration_sha256, worker=worker)
    try:
        return DelayedPoseSource(provider)
    except Exception:
        provider.close()
        raise
