"""V3 measured cameras + pair motion, retaining P03's PF lifetime/delay.

Only fixed calibration and own inputs enter this provider. No world or labels.
The existing VIS3 image likelihood is reused; its old accuracy is not claimed.
"""
from __future__ import annotations

import copy
import math
from dataclasses import replace
from types import SimpleNamespace

import numpy as np

from harness import owncam_localizer as motion
from harness import vision_loc_protocol as vp
from harness import zone_final_pair_contract as contract
from harness.vision_motion_init import motion_module
from harness.vision_pose_source_p03 import VisionPoseSource, FailClosedLoc
from harness.vision_pose_source_final import CalibrationError, measured_column_model
from harness.vision_loc_client import VisionWorkerClient
from harness.zone_final_pair_binding import bind


def pair_motion_module():
    """Current registered pair plant, without constructing a tag catalogue."""
    from harness import visual_arm_v3
    load_command = bind(motion.LoadState.command, tool_pose=visual_arm_v3.tool_pose)

    class LoadStateV3(motion.LoadState):
        command = load_command

    class PairMotion(motion_module(motion).OwnCamLocalizer):
        def __init__(self, static_map, params=None, seed=0):
            super().__init__(static_map, params, seed)
            self.load = LoadStateV3()
            self.yaw_bias = self.yaw_extra = self.drift = None
            self.pair_plan = self.cmd_partner = None
            self.pair_matched = self.pair_unmatched = 0
            self.extra_std = 0.

        def _partner_of(self, t, cmd):
            raw = super()._partner_of(t, cmd)
            if raw is None:
                return None
            # Frozen prediction applies deadband to own commands but expects
            # the partner operand to be effective before multiplying gain.
            db = self.params['motion_loaded']['deadband']
            c0, u1 = (np.asarray(db[k], float) for k in ('c0', 'u1'))
            return raw*np.where(u1 > c0, np.clip((abs(raw)-c0)/np.maximum(u1-c0, 1e-9), 0., 1.), 1.)

    return SimpleNamespace(**{**vars(motion), 'OwnCamLocalizer': PairMotion})


class PairVisionPoseSource(VisionPoseSource):
    provider_id = contract.PROVIDER_ID
    source_prefix = 'owncam_pf_vision_zero_tag_final_pair_v88'

    def __init__(self, static_map, calibration, calibration_sha256, seed=0, *, worker=None, cfg=None):
        static, _, _ = contract.resolve(static_map['map_id'])
        if static != static_map:
            raise ValueError('provider requires exact final static map')
        self.calibration = cal = contract.measured_calibration(calibration, calibration_sha256, static['map_id'])
        self.cfg = vp.load_config() if cfg is None else cfg
        from harness.vision_loc_contract_p03 import provider_runtime_contract
        worker_contract = provider_runtime_contract(map_id='zone_wide_door_geometry_v2', cfg=self.cfg)
        self.runtime_contract = {'worker_model_contract': worker_contract,
                                 'provider_id': self.provider_id, 'calibration_sha256': calibration_sha256,
                                 'robot_model': 'masterpi_v3', 'render_profile': 'floor_light_v1',
                                 'qualification': 'physical acceptance pending; no v2 calibration inheritance'}
        vl, vpf = vp.load_vis3()
        self.frozen = vp.check_frozen()
        selected = vp.selected_config()
        pf = vpf.make_robust_pf(pair_motion_module(), copy.deepcopy(static), copy.deepcopy(cal['params']),
                                selected.get('measurement', {}), selected.get('obs', {}), {}, seed,
                                cal['pan_base_yaw'], {**selected.get('robust', {}), 'loaded_scale_reinit': False})

        def column_model_for(servo, columns=None):
            state = 'loaded' if pf.load.loaded else 'unloaded'
            record = contract.camera_record(cal, state, servo)
            yaw = vl.pan_yaw(cal['pan_base_yaw'], pf.load.loaded, servo)
            c, s = math.cos(yaw), math.sin(yaw)
            rz = np.array([[c, -s, 0.], [s, c, 0.], [0., 0., 1.]])
            shifted = {'origin_m': rz @ record['origin_m'], 'rotation': rz @ record['rotation']}
            return measured_column_model(vl.mp, shifted, pf.columns if columns is None else columns)

        pf.column_model_for = column_model_for
        from harness.zone_final_pair_scan import install, resample
        install(pf, vl)
        pf._normalize_and_resample = lambda: resample(pf)
        self.loc = FailClosedLoc(pf, self.provider_id, on_command=self.on_command)
        self.seed = seed
        self.m1_calibration = {'path': str(calibration), 'file_sha256': calibration_sha256,
                               'robot_model': 'masterpi_v3', 'v2_inherited': False}
        self.identity_sha256 = contract.base.digest(self.runtime_contract)
        self.source = f'{self.source_prefix}:{self.identity_sha256[:8]}'
        self.servo, self.prior, self.failure, self.last_obs = {}, None, None, None
        self.counts = {'frames': 0, 'worker_calls': 0, 'measured': 0, 'unsettled_or_uninitialized': 0,
                       'rejected_frames': 0, 'after_failure': 0}
        self.timing, self.lifecycle = [], []
        self._started, self._closed, self._last_frame_t = False, False, None
        from harness.own_beam_edge import BeamEdgeTracker
        pair = cal['pair_model']
        self.beam_edge = BeamEdgeTracker(float(pair['slope_to_yaw_ratio']))
        self.carry_yaw_fallback = {'pair': True, 'edge': True,
                                  'b_full': float(cal['params']['motion_loaded']['yaw_bias_std_rad_s']),
                                  'b': copy.deepcopy(pair['b_rad_s']), 'level_frames': {}, 'pm_bad_until': -1.}
        self.worker = worker if worker is not None else VisionWorkerClient(self.cfg)

    def on_frame(self, now, rgb):
        # Do not consume duplicate/late pixels in the relative-yaw tracker.
        if (self.failure is None and now >= self.loc._pf.t
                and (self._last_frame_t is None or now > self._last_frame_t)):
            try:
                if self.loc._pf.settled(now):
                    contract.camera_record(self.calibration, 'loaded' if self.loc.load.loaded else 'unloaded', self.servo)
                dyaw = self.beam_edge.observe(now, rgb, self.servo, self.loc.load.loaded)
                if dyaw:
                    self.loc.apply_relative_yaw(now, dyaw)
                from harness.owncam_carry_v6e import update_availability
                update_availability(self, now)
            except CalibrationError as error:
                self._fail(now, str(error))
        try:
            return super().on_frame(now, rgb)
        except CalibrationError as error:
            self._fail(now, str(error))
            return self.report(now)

    def begin_relocalization(self, now, servo):
        pf = self.loc._pf
        self.loc.predict_to(now)
        before = {'pf_id': id(pf), 'particles_sha256': contract.base.digest(pf.px.tolist()),
                  'std': self.loc.estimate().get('cov'), 'last_scan_t': pf.last_scan_t}
        super().begin_relocalization(now, servo)
        pf.v3_last_fix_quality = None
        self.lifecycle[-1].update(before=before, after={'pf_id': id(pf),
            'particles_sha256': contract.base.digest(pf.px.tolist()), 'last_scan_t': pf.last_scan_t})

    def report(self, now):
        report = super().report(now)
        quality = copy.deepcopy(self.loc._pf.v3_last_fix_quality)
        return replace(report, observation_quality={**(report.observation_quality or {}),
            'last_fix_quality': quality, 'informative': False if quality is None else quality['informative']})


def build_provider(static_map, calibration, calibration_sha256, seed=0, *, worker=None):
    from harness.zone_study_pose_delay_p03 import DelayedPoseSource
    provider = PairVisionPoseSource(static_map, calibration, calibration_sha256, seed, worker=worker)
    try:
        return DelayedPoseSource(provider)
    except Exception:
        provider.close()
        raise
