"""Bounded visual docking reset using own RGB and calibrated reverse pulses.

A clipped band is a reason to regain field of view, never a grasp measurement.
Keep the existing projection guard and require a new settled image per pulse.
"""
import math

OPTIONS = ('back3_v1', 'back6_v1')
COUNTS = dict(zip(OPTIONS, (3, 6)))
PARENTS = {('back3_v1', 'e2e18-v264'): 267,
           ('back3_v1', 'e2e18-v266'): 268,
           ('back6_v1', 'e2e18-v266'): 269}
PARAMS = dict(station_radius_m=.25, observation_age_s=.45,
              forward_min_m=.10, forward_max_m=.32, lateral_max_m=.12,
              axis_max_rad=.75, band_min_m=.015, band_max_m=.06,
              reverse_u=-.35, pulse_s=.1, fresh_grasp_required=True)


def parameters(option):
    return dict(PARAMS, maximum_pulses=COUNTS[option])


def step(tr, rid, now, state, diag):
    mode = getattr(tr, 'clip_recovery', 'off')
    if mode == 'off':
        return None
    if mode not in OPTIONS:
        raise ValueError('UNKNOWN_CLIP_RECOVERY')
    r = tr.robots[rid]
    obs = getattr(r, 'beam_observation', None)
    if not obs or not 0 <= now-obs['rgb']['t_sim'] <= PARAMS['observation_age_s']:
        return None
    b = obs['result']
    attempt = state.get('clip_recovery_attempt')
    if attempt and not attempt['gate'].ready(now, r.last_obs):
        diag['status'] = 'clip_recovery_settle'
        return False, [dict(kind='hold')]
    if b.get('end_visible'):
        if attempt:
            tr.event(now, 'own_clip_recovered', robot_id=rid, pulses=attempt['count'],
                     rgb=obs['rgb'], aligned_receipt=False)
            state.pop('clip_recovery_attempt')
        return None
    from harness.owncam_pair_beam_v2 import pose_of
    inspect = pose_of('inspect')
    if (r.servo.get(1, 0) < 1900 or any(r.servo.get(k) != inspect[k] for k in (3, 4, 5))
            or diag['distance_m'] > PARAMS['station_radius_m']):
        return None
    band = b.get('band') or {}
    xy = b.get('near_end_base_m') or [math.inf, math.inf]
    if not (b.get('visible') and b.get('reason') == 'BAND_CLIPPED'
            and band.get('touches_invalid_border')
            and PARAMS['band_min_m'] <= band.get('length_m', -1) <= PARAMS['band_max_m']
            and PARAMS['forward_min_m'] < xy[0] < PARAMS['forward_max_m']
            and abs(xy[1]) < PARAMS['lateral_max_m']
            and abs(b.get('axis_heading_rad', math.inf)) < PARAMS['axis_max_rad']):
        return None
    from harness.zone_s3_settled_servo import SettleGate
    if attempt is None:
        attempt = state['clip_recovery_attempt'] = dict(count=0, gate=SettleGate())
    if attempt['count'] >= COUNTS[mode]:
        if not attempt.get('exhausted'):
            attempt['exhausted'] = True
            tr.event(now, 'own_clip_recovery_budget', robot_id=rid, pulses=attempt['count'])
        return None
    from harness.zone_solo_cyan_pulse_cal import action_of
    profile = next(p for p in tr.profiles.values() if not p['loaded']
                   and p['axis'] == 'forward' and p['u'] == PARAMS['reverse_u']
                   and p['duration_s'] == PARAMS['pulse_s'])
    command = action_of(profile)
    from harness.active_wall_mapping import compose
    from harness.public_navigation_unknown import from_observed_grid
    from harness.public_navigation.follower import projected_clear
    from harness.public_navigation_recovery import issued_twist
    ex = r.goal.explorer
    pose = compose(ex.map_to_odom, ex.local_pose)
    costmap = from_observed_grid(ex.grid, pose, ex.latest, set())
    clear = projected_clear(costmap, pose, issued_twist(command))
    if not clear:
        tr.event(now, 'would_stop_clip_recovery_collision_guard', robot_id=rid, dev_light=tr.dev_light)
        if not tr.dev_light:
            return False, [dict(kind='hold')]
    attempt['count'] += 1
    attempt['gate'].issued(now, profile, r.last_obs)
    state['motion_until'] = now+command['duration_s']
    state.pop('progress_watch', None)
    diag.update(status='clip_recovery_backup', clip_pulses=attempt['count'], projected_clear=bool(clear))
    tr.event(now, 'own_clip_recovery_pulse', robot_id=rid, option=mode,
             pulse=attempt['count'], rgb=obs['rgb'], reason=b['reason'],
             band_length_m=band['length_m'], action=command, aligned_receipt=False)
    return False, [command]


def compose(bundle, option):
    if option == 'off':
        return ()
    key = (option, bundle['execution_bundle_id'])
    if key not in PARENTS:
        raise ValueError('CLIP_RECOVERY_REQUIRES_V264_OR_V266')
    version = PARENTS[key]
    bundle['e2e_options']['clip_recovery'] = option
    bundle['clip_recovery_parameters'] = parameters(option)
    bundle.update(schema=f'ugrp.e2e_ownmap_live.v{version}', execution_bundle_id=f'e2e18-v{version}',
                  workflow_version=f'7.{version-107}.0')
    return (f'configs/simulation_workflows.d/e2e18_v{version}.json',)
