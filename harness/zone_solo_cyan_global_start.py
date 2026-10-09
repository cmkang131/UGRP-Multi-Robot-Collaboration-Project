"""Default-off S2 global start: Nav2 free-space prior, modes and bounded Spin.

Algorithm sources: navigation2 235fc5ce, amcl_node.cpp uniformPoseGenerator /
globalLocalizationCallback / getMaxWeightHyp, pf_kdtree.c, pf.c (LGPL-2.1+).
Adapters: existing fixed-N RGB PF, clearance-expanded static free space,
calibrated command odometry instead of wheel odometry, bounded REAL pulses.
This is not Fox's entropy-optimal action selection or a ROS Spin server.
No seed-to-dock mapping, setup poses, simulator state, or evaluation inputs.
"""
import copy
import itertools
import math
from dataclasses import replace

import numpy as np

from harness.zone_solo_cyan_slip_detect import Runtime as Previous
from harness.zone_solo_cyan_amcl_update import converged
from harness.zone_solo_cyan_pulse_cal import action_of, profile_key
from harness.zone_own_guards import OwnPose

OPTION = 'amcl_global_active_v1'
PARAMS = dict(particles=2000, sampling='uniform free map and uniform [-pi,pi) yaw',
    cluster_bin_xy_m=.5, cluster_bin_yaw_rad=math.pi/18,
    spin_distance_rad=1.57, max_spin_sectors=4, spin_time_allowance_s=60,
    active_global_budget_s=120, turn_profile='0:turn:0.35:0.10',
    observe_after_horizon_s=.6)


def cluster_labels(px):
    """Nav2's floor bins and 27-neighbor connected components, no yaw wrap."""
    keys = [tuple(k) for k in np.floor(px / [.5, .5, math.pi/18]).astype(int)]
    bins = dict.fromkeys(keys, -1)
    offsets = tuple(itertools.product((-1, 0, 1), repeat=3))
    label = 0
    for key in bins:
        if bins[key] != -1:
            continue
        bins[key] = label
        queue = [key]
        while queue:
            node = queue.pop()
            for delta in offsets:
                near = tuple(a+b for a, b in zip(node, delta))
                if bins.get(near) == -1:
                    bins[near] = label
                    queue.append(near)
        label += 1
    return np.array([bins[k] for k in keys])


def maximum_mode(px, weights, labels):
    """Same maximum cluster mass / linear moments / circular yaw as pf.c."""
    mass = np.bincount(labels, weights=weights)
    selected = labels == int(np.argmax(mass))
    w = weights[selected]
    p = px[selected]
    xy = w @ p[:, :2] / w.sum()
    cs = w @ np.cos(p[:, 2]); sn = w @ np.sin(p[:, 2])
    mean = np.r_[xy, math.atan2(sn, cs)]
    cov = np.zeros((3, 3))
    delta = p[:, :2] - xy
    cov[:2, :2] = (w[:, None] * delta).T @ delta / w.sum()
    # Nav2 uses the unnormalised cluster circular moment here.
    cov[2, 2] = max(0., -2 * math.log(max(math.hypot(cs, sn), 1e-300)))
    return mean, cov, dict(cluster_count=len(mass), maximum_cluster_weight=float(mass.max()))


def initialize(pf):
    if pf.t != 0 or pf.n != PARAMS['particles']:
        raise ValueError('global start requires untouched fixed-2000-particle S2 provider')
    # Existing helper is rejection sampling over the static free map, not a
    # local Gaussian or a dock row list. Plant nuisance draws are independent.
    pf.px = pf._uniform_free(pf.n)
    pf.logw = np.zeros(pf.n)
    pf.initialized = True
    pf.last_scan_t = None
    pf.stats['resets'] = pf.stats.get('resets', 0) + 1
    audit = dict(option=OPTION, parameters=copy.deepcopy(PARAMS), gt_inputs=False,
        known_own_dock=False, initialization='uniform free map / uniform yaw',
        rows=[], settled_spin_observations_verified=False)
    estimate = pf.estimate
    cache = dict(resamples=-1, labels=None)

    def reported():
        out = estimate()
        if cache['resamples'] != pf.stats['resamples']:
            cache.update(resamples=pf.stats['resamples'], labels=cluster_labels(pf.px))
        mean, cov, modes = maximum_mode(pf.px, pf._weights(), cache['labels'])
        modes.update(global_std_xy_m=out['std_xy_m'], all_particles_converged=converged(pf.px))
        yaw = mean[2] + out.get('pan_yaw_offset', 0.)
        out.update(x=float(mean[0]), y=float(mean[1]), yaw=math.atan2(math.sin(yaw), math.cos(yaw)),
            cov=cov.tolist(), std_xy_m=float(np.sqrt(max(np.trace(cov[:2, :2]), 0.))),
            std_yaw_rad=float(np.sqrt(cov[2, 2])), global_modes=modes)
        return out

    pf.estimate = reported
    return audit


class Runtime(Previous):
    def __init__(self, *args, start_localization='off', **kwargs):
        if start_localization not in ('off', OPTION):
            raise ValueError('unknown start_localization')
        if start_localization != 'off' and (kwargs.get('pulse_motion_model') != 'v7_pulse_cal_v1'
                or kwargs.get('amcl_update') != 'ros_motion_v1'):
            raise ValueError('global start requires existing S2 pulse odometry and AMCL')
        self.start_localization = start_localization
        super().__init__(*args, **kwargs)
        if start_localization == 'off':
            return
        inner = self.pose.provider
        self.global_start = initialize(inner.loc._pf)
        inner.prior = dict(source='Nav2 uniform free-space global localization; no own dock',
            option=OPTION, setup_only=False, known_own_dock=False, applied_sim_s=0.)
        self.global_done = False
        self.global_started = None
        self.global_sector_t = None
        self.global_sector = 0
        self.global_angle = 0.
        self.global_wait_until = 0.
        from harness.zone_solo_cyan_v106 import hp
        inner.runtime_contract['s2_start_localization'] = copy.deepcopy(inner.prior)
        inner.identity_sha256 = hp.base.digest(inner.runtime_contract)
        inner.source = 'owncam_pf_s2_global_start:' + inner.identity_sha256[:8]
        self.pose.source = inner.source

    def on_command(self, rid, now, action):
        super().on_command(rid, now, action)
        if (self.start_localization != 'off' and self.state == 'global_start_spin'
                and action['kind'] == 'mecanum' and action.get('turn')):
            p = self.pulse_profiles[profile_key(action, False)]
            self.global_angle += abs(p['mean_delta'][2])
            self.global_start['rows'].append(dict(t=now, event='issued_spin_pulse',
                command=copy.deepcopy(action), command_odom_angle=self.global_angle,
                actual_rotation_known=False))

    def _control(self, now, idle):
        if self.start_localization == 'off' or self.global_done:
            return super()._control(now, idle)
        if self.state == 'search_move' and idle:
            self.set_state('global_start_spin', now)
            self.global_started = self.global_sector_t = now
        if self.state != 'global_start_spin':
            return super()._control(now, idle)
        if self.terminal or self.pose.provider.failure:
            return super()._control(now, idle)
        if not idle or now < self.global_wait_until:
            return [dict(kind='hold')]
        pf = self.pose.provider.loc._pf
        ready = pf.last_scan_t is not None and converged(pf.px)
        expired = now-self.global_started >= PARAMS['active_global_budget_s']
        if self.global_angle >= PARAMS['spin_distance_rad'] or now-self.global_sector_t >= PARAMS['spin_time_allowance_s']:
            self.global_sector += 1
            self.global_sector_t = now
            self.global_angle = 0.
        if ready or expired or self.global_sector >= PARAMS['max_spin_sectors']:
            self.global_done = True
            if not ready:
                self.soft('GLOBAL_START_UNRESOLVED', now)
            self.global_start['rows'].append(dict(t=now, event='active_scan_finished',
                resolved=ready, sectors=self.global_sector, budget_expired=expired))
            self.set_state('search_move', now)
            return [dict(kind='hold')]
        p = self.pulse_profiles[PARAMS['turn_profile']]
        pose = OwnPose.from_report(self.last_report)
        clear = pose is not None and all(self.guard._clear(self.servo,
            replace(pose, yaw=pose.yaw+float(a)), False)
            for a in np.linspace(0, p['mean_delta'][2], 5))
        if not clear:
            self.soft('GLOBAL_START_COLLISION_GUARD', now)  # DEV logs conservative guard.
        self.global_wait_until = now+p['times'][-1]+PARAMS['observe_after_horizon_s']
        return [action_of(p)]

    def record(self):
        out = super().record()
        if self.start_localization != 'off':
            out['start_localization'] = copy.deepcopy(self.global_start)
        return out
