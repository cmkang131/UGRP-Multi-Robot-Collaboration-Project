"""S2 v133 full + existing Augmented/KLD initialization; default off.

The opt-in constructor replaces, rather than clears after use, v106's dock
prior. Its remaining initialization is copied from the frozen v106 constructor
so historical sources/bundles remain byte-identical. No spawn-layout import,
Gaussian prior, row identity, evaluator or simulator input exists on this path.
"""
import copy
from dataclasses import asdict
from types import SimpleNamespace

import numpy as np

from harness import zone_solo_cyan_v106 as legacy
from harness.zone_solo_cyan_kld_start import Runtime as KLD, OPTION as KLD_OPTION
from harness.zone_solo_cyan_augmented_start import OPTION as GLOBAL_OPTION
from harness.zone_solo_cyan_look_ahead import Runtime as Carry

OPTION = 'none_v1'


class _NoDockInitialization(legacy.Runtime):
    def __init__(self, static, calibration, calibration_sha, *, seed=911, robot_id='r3',
                 pickup_slot='P1-2', destination='B', passage_id='door_1', dev_light=True,
                 provider_factory=legacy.build_provider, vision_factory=legacy.CyanVision,
                 model_runtime=None, start_prior='off'):
        self.start_prior = start_prior
        if start_prior == 'off':
            super().__init__(static, calibration, calibration_sha, seed=seed, robot_id=robot_id,
                pickup_slot=pickup_slot, destination=destination, passage_id=passage_id,
                dev_light=dev_light, provider_factory=provider_factory,
                vision_factory=vision_factory, model_runtime=model_runtime)
            return
        if start_prior != OPTION:
            raise ValueError('unknown start_prior')
        if dev_light is not True:
            raise ValueError('SOLO_CYAN_DEV_ONLY: loaded motion/camera and grasp qualification pending')
        if robot_id not in ('r1', 'r2', 'r3') or static['map_id'] != 'zone_wide_door_geometry_v3':
            raise ValueError('solo v106 robot/map outside DEV scope')
        self.route = legacy.passage_route(static, passage_id, destination)
        self.slot = legacy.pickup_slots(static)[pickup_slot]
        self.map, self.robot_id, self.pickup_slot, self.destination = static, robot_id, pickup_slot, destination
        self.pose = provider_factory(static, calibration, calibration_sha, seed, model_runtime=model_runtime)
        try:
            inner = self.pose.provider
            pf = inner.loc._pf
            if pf.t != 0 or pf.initialized or inner.prior is not None:
                raise ValueError('untouched uninitialized provider required; no prior may be supplied')
            pf.px = pf._uniform_free(pf.n)
            pf.logw = np.zeros(pf.n)
            pf.initialized = True
            pf.last_scan_t = None
            pf.stats['resets'] = pf.stats.get('resets', 0) + 1
            inner.prior = dict(option=OPTION, source='uniform static free space and full yaw',
                known_own_dock=False, setup_only=False, applied_sim_s=0.)
            self.vision = vision_factory(inner.calibration)
            self.guard = legacy.SweepGuardV3(static)
        except Exception:
            self.pose.close()
            raise
        # Frozen v106's remaining non-prior state initialization, unchanged.
        self.servo, self.last_obs, self.last_report = {}, None, None
        self.state, self.state_t, self.started_at = 'init', 0., None
        self.events, self.pose_log, self.commands = [], [], []
        self.failure, self.receipt = None, False
        self.sink, self.arm = legacy.CommandSink(), None
        self.blind = legacy.BlindCyan()
        self.target = None
        self.target_t = None
        self.next_control = 0.
        self.path, self.path_goal = [], None
        self.route_i, self.search_i = 0, 0
        self.scan_queue, self.scan_after = [], None
        self.align_streak, self.last_align_frame = 0, None
        self.align_view = None
        self.last_visual_state = None
        self.soft_counts = {}
        self.relooked = set()
        self.regrasp = False
        self.relook_index, self.relook_started = None, None
        self.controller = self.own = self
        self.policy = SimpleNamespace(own_image_ob=False)
        self.own_load_occlusion = legacy.occlusion.OwnLoadOcclusion(self)


class Runtime(KLD, Carry, _NoDockInitialization):
    """Cooperative MRO reuses the existing KLD/augmented/loaded-stack methods.

Global scan and first-motion 2000-particle handoff retain their old constants.
The outer v133 best-cluster/AMCL sensor/landmark adapters are installed last.
"""
    def __init__(self, *args, start_prior='off', **kwargs):
        if start_prior not in ('off', OPTION):
            raise ValueError('unknown start_prior')
        global_mode = kwargs.get('global_localization', 'off')
        sampling = kwargs.get('particle_sampling', 'off')
        if start_prior == OPTION:
            if (global_mode != GLOBAL_OPTION or sampling != KLD_OPTION or
                    kwargs.get('start_localization', 'off') != 'off'):
                raise ValueError('none_v1 requires existing augmented_active_v1 + kld_global_v1')
        elif global_mode != 'off' or sampling != 'off':
            raise ValueError('global full path requires explicit start_prior=none_v1')
        super().__init__(*args, start_prior=start_prior, **kwargs)
        if start_prior == 'off':
            return
        self.global_full_decisions = []
        inner = self.pose.provider
        inner.runtime_contract['s2_start_prior'] = dict(option=OPTION, dock_prior_calls=0,
            startup_pose_information=False, sampling='static free space and uniform [-pi,pi) yaw',
            full_carry=True, parameters_changed=False, runtime_gt=False)
        inner.identity_sha256 = legacy.hp.base.digest(inner.runtime_contract)
        inner.source = 'owncam_pf_s2_unknown_start:' + inner.identity_sha256[:8]
        self.pose.source = inner.source

    def drive(self, xy, now, **kwargs):
        if self.start_prior == 'off':
            return super().drive(xy, now, **kwargs)
        # Reporting only: the exact released own estimate and actual warning,
        # including early-return branches that issued no motion pulse.
        report = copy.deepcopy(asdict(self.last_report))
        before = self.soft_counts.get('POSE_UNCERTAIN', 0)
        state = self.state
        result = super().drive(xy, now, **kwargs)
        self.global_full_decisions.append(dict(t=float(now), state=state, report=report,
            pose_uncertain=self.soft_counts.get('POSE_UNCERTAIN', 0) > before))
        return result

    def record(self):
        out = super().record()
        if self.start_prior != 'off':
            out['start_prior'] = copy.deepcopy(self.pose.provider.runtime_contract['s2_start_prior'])
            out['global_full_decisions'] = copy.deepcopy(self.global_full_decisions)
        return out
