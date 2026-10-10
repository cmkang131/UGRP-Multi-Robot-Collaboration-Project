"""Opt-in convergence certification, independent of physical success or control.

Reuse the existing Nav2 all-particle convergence test and connected-bin modes.
Small weighted covariance alone cannot certify a multimodal global posterior.
No particle, weight, RNG, pose, command, or numerical threshold is changed.
This can refuse a false certificate; it cannot recover discarded hypotheses.
"""
import copy
import math

from harness.zone_solo_cyan_amcl_update import converged

OPTION = 'posterior_consensus_v1'


def certificate(report, particles):
    modes = (report.observation_quality or {}).get('diagnostics', {}).get('pose_estimate', {})
    count = modes.get('cluster_count')
    compact = bool(len(particles) and converged(particles))
    # Same .05 m / 5 degree limits as the S2 navigation check, not replay tuning.
    covariance_ok = bool(report.initialized and report.last_fix_t is not None
        and report.std_xy_m <= .05 and report.std_yaw_rad <= math.radians(5))
    return dict(option=OPTION, estimate_t=report.t_est, qualified=bool(
        covariance_ok and compact and count == 1), covariance_ok=covariance_ok,
        all_particles_compact=compact, connected_modes=count,
        gt_inputs=False, qualification='posterior certificate only; accuracy requires eval_only')


def attach(runtime, *, localization_certification='off'):
    if localization_certification == 'off':
        return runtime
    if localization_certification != OPTION:
        raise ValueError('unknown localization_certification')
    old_frames, old_record = runtime.on_frames, runtime.record
    audit = dict(option=OPTION, scope='reporting only; DEV control unchanged',
        distribution_changed=False, thresholds_changed=False, gt_inputs=False, rows=[])

    def frames(now, images):
        result = old_frames(now, images)
        row = certificate(runtime.last_report, runtime.pose.provider.loc._pf.px)
        row['released_t'] = now
        runtime.pose_log[-1]['convergence_certificate'] = copy.deepcopy(row)
        audit['rows'].append(row)
        return result

    def record():
        return {**old_record(), 'localization_certification': copy.deepcopy(audit)}

    runtime.on_frames, runtime.record = frames, record
    return runtime
