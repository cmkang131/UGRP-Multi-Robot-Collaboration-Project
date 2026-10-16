"""Default-off bounded own-RGB target memory and gaze, never grasp evidence.

Stationary-track prediction: fixed own-odom mean, monotonically increasing
uncertainty between RGB detections. Noise bounds are DEV assumptions, not a
calibrated posterior. Fresh RGB alone still enters the existing fine servo.
"""
import copy
import math
import numpy as np
from harness.active_wall_mapping import wrap
from harness.self_odom_grid import transform

OPTIONS = ('regulated_v1', 'gaze_v1', 'track_gaze_v1')
VERSIONS = dict(zip(OPTIONS, (384, 385, 386)))
PARAMS = dict(max_age_s=120., initial_sigma_m=.03, sigma_limit_m=.18,
              drift_m_per_s=.0005, drift_m_per_m=.06, drift_m_per_rad=.01,
              gaze_deadband_deg=12., pan_limit_deg=60., fresh_alignment_required=True)


def mode(tr):
    return getattr(tr, 'grasp_once', 'off')


def install(tr, option='off'):
    if option not in ('off', *OPTIONS): raise ValueError('UNKNOWN_GRASP_ONCE')
    tr.grasp_once = option
    for r in tr.robots.values(): r.grasp_once = option


def observe(r, now):
    """Called after own perception; no simulator or peer state is available."""
    if getattr(r, 'grasp_once', 'off') not in OPTIONS[1:]: return
    pose = np.asarray(r.goal.explorer.local_pose, float)
    track = getattr(r, 'grasp_track', None)
    if track:
        dt = max(0., now-track['updated'])
        delta = pose-np.asarray(track['pose'])
        track['sigma_m'] += (PARAMS['drift_m_per_s']*dt
            + PARAMS['drift_m_per_m']*float(np.linalg.norm(delta[:2]))
            + PARAMS['drift_m_per_rad']*abs(wrap(delta[2])))
        track.update(updated=now, pose=pose.tolist())
    b = r.beam
    if b is None or not 0 <= now-b['rgb']['t_sim'] <= .45: return
    if track and track['rgb'] == b['rgb']: return  # never refresh age on replay
    band = transform([b['grip_base_m']], pose)[0]
    r.grasp_track = dict(beam=copy.deepcopy(b), band=band.tolist(),
        rgb=copy.deepcopy(b['rgb']), seen=float(b['rgb']['t_sim']), updated=now,
        pose=pose.tolist(), sigma_m=PARAMS['initial_sigma_m'])


def valid(r, now):
    track = getattr(r, 'grasp_track', None)
    return bool(track and 0 <= now-track['seen'] <= PARAMS['max_age_s']
                and math.isfinite(track['sigma_m'])
                and track['sigma_m'] <= PARAMS['sigma_limit_m'])


def seed_station(tr, rid, now, state, target):
    if mode(tr) != 'track_gaze_v1' or 'station' in state or target is None: return
    r = tr.robots[rid]
    if not valid(r, now): return
    from harness.e2e_carrier_axes import station
    t = r.grasp_track
    end, grip, basis = station(t['beam'], target['center_m'], rid)
    state.update(station=end, grip=grip, basis=basis, last_seen=t['seen'])
    tr.event(now, 'own_track_staging_hypothesis', robot_id=rid,
             rgb=t['rgb'], age_s=now-t['seen'], sigma_m=t['sigma_m'])


def retained(tr, rid, now, state):
    return (mode(tr) == 'track_gaze_v1' and 'station' in state
            and valid(tr.robots[rid], now)
            and state.get('basis', {}).get('rgb') == tr.robots[rid].grasp_track['rgb'])


def gaze_target(tr, rid, now):
    r = tr.robots[rid]
    if mode(tr) not in OPTIONS[1:] or not valid(r, now): return None
    return np.asarray(r.grasp_track['band'])


def pan_target(tr, rid, grip):
    """One absolute pan command instead of repeated 80-PWM gaze/settle cycles.

    No FOV or mount change. Unreachable bearing is reported, not claimed visible.
    The normal queue/settle/clearance gates still dispatch the look command.
    """
    if mode(tr) not in OPTIONS[1:]: return None
    from harness.e2e_pregrasp_gaze import bearing
    from harness.visual_arm import PULSE_PER_DEGREE
    r = tr.robots[rid]
    error = math.degrees(wrap(bearing(r.goal.explorer.local_pose, grip)
                              - r.goal.explorer.local_pose[2]))
    clipped = max(-PARAMS['pan_limit_deg'], min(PARAMS['pan_limit_deg'], error))
    if getattr(r, 'carrier_approach', None) is not None:
        r.carrier_approach.update(gaze_bearing_deg=error,
            gaze_pan_reachable=abs(error)<=PARAMS['pan_limit_deg'],
            gaze_source='own_rgb_track', track_sigma_m=r.grasp_track['sigma_m']
            if getattr(r, 'grasp_track', None) else None)
    return int(round(1500+clipped*PULSE_PER_DEGREE))


def compose(bundle, option='off'):
    if option == 'off': return ()
    if option not in OPTIONS or bundle['execution_bundle_id'] != 'e2e18-v375':
        raise ValueError('GRASP_ONCE_REQUIRES_V375')
    from harness.e2e_approach_efficiency import PARAMS as efficiency
    v = VERSIONS[option]
    bundle.update(grasp_once_parent='e2e18-v375',
                  grasp_once_parameters=copy.deepcopy(PARAMS),
                  grasp_once_efficiency_parameters=copy.deepcopy(efficiency),
                  execution_bundle_id=f'e2e18-v{v}', schema=f'ugrp.e2e_ownmap_live.v{v}',
                  workflow_version=f'7.{v-107}.0')
    bundle['e2e_options']['grasp_once'] = option
    return ('harness/e2e_grasp_once.py', f'configs/simulation_workflows.d/e2e18_v{v}.json')


def parent_for_validation(bundle):
    from harness.e2e_approach_efficiency import PARAMS as efficiency
    old = copy.deepcopy(bundle)
    v = VERSIONS.get(old['e2e_options'].get('grasp_once'))
    if (v is None or old['execution_bundle_id'] != f'e2e18-v{v}'
            or old.get('grasp_once_parent') != 'e2e18-v375'
            or old.get('grasp_once_parameters') != PARAMS
            or old.get('grasp_once_efficiency_parameters') != efficiency):
        raise ValueError('REGISTERED_GRASP_ONCE_REQUIRED')
    old['execution_bundle_id'] = old.pop('grasp_once_parent')
    old.pop('grasp_once_parameters'); old.pop('grasp_once_efficiency_parameters')
    old['e2e_options'].pop('grasp_once')
    return old
