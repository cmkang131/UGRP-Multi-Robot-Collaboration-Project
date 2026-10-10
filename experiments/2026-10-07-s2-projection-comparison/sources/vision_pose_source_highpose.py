"""V94 OpenCV observations + existing P03 PF/clock and BeamEdgeTracker.

No v2/v88 measured values or segmentation checkpoint are instantiated. Static
camera calibration, own RGB, own commands and the public map are the inputs.
"""
import copy
import math
import numpy as np

from harness import vision_loc_protocol as vp
from harness import zone_pair_highpose_contract as contract
from harness import zone_pair_highpose as pose
from harness.vision_pose_source_pair_v3 import PairVisionPoseSource, pair_motion_module  # noqa: F401
from harness import zone_pair_highpose_motion_v102 as motion_v102
from harness.vision_pose_source_p03 import VisionPoseSource, FailClosedLoc
from harness.vision_pose_source_final import CalibrationError, measured_column_model
from harness.zone_final_pair_scan import install, resample
from harness.zone_pair_highpose_edge import HIGH_EDGE_INFORMATIVE, HighBeamEdgeTracker
from harness.opencv_wall_observation import OpenCVObserver, DETECTOR
from harness import zone_pair_highpose_pf_consistency as pf_consistency
from harness import zone_pair_highpose_pf_local_redraw as pf_redraw


# Augmented MCL (Thrun, Burgard & Fox 2005, Table 8.3; Nav2 AMCL pf.c): v98 ran with robust={} (off), so a filter that became over-confident
# had no way back. Trigger rates are the Nav2-documented example values (recovery_alpha_slow 0.001 / recovery_alpha_fast 0.1), cap 1 = Nav2.
# The random poses are drawn around the own estimate (uniform_share 0) with the expansion radii of Ueda et al. 2004 / emcl2 (0.1 m, 0.1 m, 0.2 rad),
# NOT uniformly over the map: replay showed uniform injection can move the estimate metres away for seconds (evidence/recovery_transient_cost.txt).
# The frozen vision_pf replaces a candidate that lands in a wall with a uniform draw over the whole map (independent review #363 P1-2: 101 of 2000 near a door, up to 4.2 m);
# harness/zone_pair_highpose_pf_local_redraw.py redraws such candidates from the same local Gaussian instead (frozen PF unchanged, no scale changed).
# DEV candidate: constants come from the sources, not tuned; not validated closed-loop.
PF_RECOVERY = {'alpha_slow': 0.001, 'alpha_fast': 0.1, 'max_fraction': 1.0, 'uniform_share': 0.0, 'local_std': [0.1, 0.1, 0.2]}

# Expansion resetting (Ueda, Arai & Sakamoto, IROS 2004; emcl2 defaults expansion_radius_position 0.1 m / expansion_radius_orientation 0.2 rad):
# an own arrival rejection says belief and view disagree, so keeping belief and sigma (what begin_relocalization does) repeats the rejected view.
# The belief is expanded ONLY when the arrival-rejection path arms it (zone_pair_highpose_arrival_confirm.request_belief_expansion); the DR
# checkpoint and every other relocalization keep their belief. Radii are the emcl2 defaults: DEV candidate, not tuned.
EXPANSION_RADIUS = (0.1, 0.1, 0.2)


class HighPoseSource(PairVisionPoseSource):
    provider_id = contract.PROVIDER_ID
    source_prefix = 'owncam_pf_opencv_final_pair_highpose_v98'

    def __init__(self, static_map, calibration, calibration_sha256, seed=0, *, worker=None):
        static, _, _ = contract.resolve(static_map['map_id'])
        if static != static_map:
            raise ValueError('provider requires exact final static map')
        self.calibration = cal = contract.student_calibration(
            contract.admitted_calibration(calibration, calibration_sha256, static['map_id']))
        self.cfg = {'sim_time_charge': {'charged': False, 'reason': 'fixed P03 delay is external'}}
        # Registered own-image gate values for floor_light_v1 (registry own_image_gates, pinned by sha256).
        self.gates = contract.own_image_gates()
        self.runtime_contract = {'provider_id': self.provider_id, 'calibration_sha256': calibration_sha256,
            'detector': DETECTOR, 'learned_segmentation': False, 'robot_model': 'masterpi_v3',
            'render_profile': 'floor_light_v1', 'qualification': 'unqualified OpenCV/HIGH candidate',
            'own_image_gates': {'path': self.gates['path'], 'sha256': self.gates['sha256']},
            'pf_consistency': pf_consistency.record(pf_consistency.CONFIG),
            'pf_recovery': copy.deepcopy(PF_RECOVERY),
            'pf_local_redraw': pf_redraw.record(pf_redraw.CONFIG),
            'pf_expansion': {'radius': list(EXPANSION_RADIUS), 'trigger': 'own arrival-view rejection only (one shot)'}}
        # These frozen modules supply only column geometry, likelihood and PF.
        # load_vis3 never imports seg_model/torch or opens a checkpoint.
        vl, vpf = vp.load_vis3()
        self.frozen = vp.check_frozen()
        selected = vp.selected_config()
        pf = vpf.make_robust_pf(motion_v102.motion_module(), copy.deepcopy(static), copy.deepcopy(cal['params']),
            selected.get('measurement', {}), {**selected.get('obs', {}), 'columns': DETECTOR['columns'],
            'strip_half_px': DETECTOR['strip_half_px']}, {}, seed, cal['pan_base_yaw'],
            {**selected.get('robust', {}), 'loaded_scale_reinit': False, 'recovery': copy.deepcopy(PF_RECOVERY)})

        def column_model_for(servo, columns=None):
            state = 'loaded' if pf.load.loaded else 'unloaded'
            record = contract.camera_record(cal, state, servo)
            yaw = vl.pan_yaw(cal['pan_base_yaw'], pf.load.loaded, servo)
            c, s = math.cos(yaw), math.sin(yaw)
            rz = np.array([[c, -s, 0.], [s, c, 0.], [0., 0., 1.]])
            shifted = {'origin_m': rz @ record['origin_m'], 'rotation': rz @ record['rotation']}
            return measured_column_model(vl.mp, shifted, pf.columns if columns is None else columns)

        pf.column_model_for = column_model_for
        self.high_since = None
        settled = pf.settled
        pf.settled = lambda now: settled(now) and (not pf.load.loaded or
            (pose.at_high(self.servo) and self.high_since is not None and now-self.high_since >= pose.HIGH_SETTLE_S))
        install(pf, vl)
        pf._normalize_and_resample = lambda: resample(pf)
        # R1 stays local next to walls: invalid random poses are redrawn around the own estimate, never over the whole map (review #363 P1-2).
        pf_redraw.install(pf, pf_redraw.CONFIG)
        # v98 consistency: one stationary view counts once; columns tempered (calibrated, see module).
        pf_consistency.install(pf, pf_consistency.CONFIG)
        self.loc = FailClosedLoc(pf, self.provider_id, on_command=self.on_command)
        self.seed = seed
        self.m1_calibration = {'path': str(calibration), 'file_sha256': calibration_sha256,
                               'robot_model': 'masterpi_v3', 'v2_inherited': False, 'v88_inherited': False}
        self.identity_sha256 = contract.base.digest(self.runtime_contract)
        self.source = f'{self.source_prefix}:{self.identity_sha256[:8]}'
        self.servo, self.prior, self.failure, self.last_obs = {}, None, None, None
        self.counts = {'frames': 0, 'worker_calls': 0, 'measured': 0, 'unsettled_or_uninitialized': 0,
                       'rejected_frames': 0, 'after_failure': 0}
        self.timing, self.lifecycle = [], []
        self._started, self._closed, self._last_frame_t = False, False, None
        self._expand_next = False
        pair = cal['pair_model']
        self.beam_edge = HighBeamEdgeTracker(float(pair['slope_to_yaw_ratio']))
        self.carry_yaw_fallback = {'pair': True, 'edge': HIGH_EDGE_INFORMATIVE,
            'b_full': float(cal['params']['motion_loaded']['yaw_bias_std_rad_s']),
            'b': copy.deepcopy(pair['b_rad_s']), 'level_frames': {}, 'pm_bad_until': -1.}
        self.worker = worker if worker is not None else OpenCVObserver(
            vl, lambda: pf.column_model_for(self.servo), self.gates['values'])

    def arm_expansion(self):
        """One shot: the next begin_relocalization also expands the belief. Only the arrival-rejection path arms it."""
        self._expand_next = True

    def disarm_expansion(self):
        self._expand_next = False

    def begin_relocalization(self, now, servo):
        expand, self._expand_next = self._expand_next, False
        super().begin_relocalization(now, servo)
        if expand:
            self._expand_belief()

    def _expand_belief(self):
        """Expansion resetting at the (already predicted) relocalization time: uniform +-radius per particle, weights reset."""
        pf = self.loc._pf
        pf.px = pf.px + pf.rng.uniform(-1., 1., size=pf.px.shape)*np.asarray(EXPANSION_RADIUS, float)
        pf.px[:, 2] = pf.wrap(pf.px[:, 2])
        pf.logw = np.zeros(pf.n)
        self.lifecycle[-1].update(expansion_radius=list(EXPANSION_RADIUS), belief_preserved=False,
                                  particles_sha256_after_expansion=contract.base.digest(pf.px.tolist()))

    def on_command(self, row):
        super().on_command(row)
        if not pose.at_high(self.servo):
            self.high_since = None
        elif self.high_since is None:
            self.high_since = float(row['t'])

    def on_frame(self, now, rgb):
        if (self.failure is None and now >= self.loc._pf.t
                and (self._last_frame_t is None or now > self._last_frame_t)):
            try:
                loaded = self.loc.load.loaded
                if self.loc._pf.settled(now):
                    contract.camera_record(self.calibration, 'loaded' if loaded else 'unloaded', self.servo)
                enabled = loaded and self.loc._pf.settled(now) and pose.at_high(self.servo)
                if HIGH_EDGE_INFORMATIVE:      # v98: the HIGH edge is the near-clip trace, not a beam edge (see zone_pair_highpose_edge)
                    dyaw = self.beam_edge.observe(now, rgb, self.servo, enabled)
                    if dyaw:
                        self.loc.apply_relative_yaw(now, dyaw)
                from harness.owncam_carry_v6e import update_availability
                update_availability(self, now)
            except CalibrationError as exc:
                self._fail(now, str(exc))
        try:
            return VisionPoseSource.on_frame(self, now, rgb)
        except CalibrationError as exc:
            self._fail(now, str(exc))
            return self.report(now)


def build_provider(static_map, calibration, calibration_sha256, seed=0, *, worker=None):
    from harness.zone_study_pose_delay_p03 import DelayedPoseSource
    provider = HighPoseSource(static_map, calibration, calibration_sha256, seed, worker=worker)
    try:
        return DelayedPoseSource(provider)
    except Exception:
        provider.close()
        raise
