"""Close-range beam-loss recovery toggles (all default off).

* beam_lost_standoff_v1: a beam last seen within a short distance of the own
  odometry pose is probably lost because it left the camera field of view, not
  because it is far away. Back off with calibrated reverse pulses (own command
  history + own odometry only), then face the remembered side and scan as before.
* arm_clearance_align_skip_v1: stop repeating backup/turn/verify clearance cycles
  next to the own pregrasp station or at an already-visited spot.
* acquire_scan_fast_v1: shorter view period / turn cap in the existing scan cycle.

Remembered geometry only proposes where to look; the existing own-RGB alignment
and grasp gates are unchanged. No simulator truth, contact or joint state is read.
"""
import copy
import math
import numpy as np

STANDOFF = 'v1'
SKIP = 'v1'
FAST = 'v1'
# (standoff, align_skip, scan_fast) -> bundle number. Parent must be e2e18-v273.
VERSIONS = {(STANDOFF, 'off', 'off'): 295, (STANDOFF, SKIP, FAST): 296}
PARENT = 'e2e18-v273'
PAN_VERSIONS = {(STANDOFF, SKIP, FAST): 297, (STANDOFF, 'off', 'off'): 300}
RELOOK_PARENT = 'e2e18-v276'   # relook_search=view5_pan_v1 on v273
BEAM_HALF_M = .30            # known beam size, as in the existing station model
STANDOFF_PARAMS = dict(near_m=.35, front_rad=math.pi/2, backup_m=.30, reverse_u=-.35,
                       pulse_s=.1, max_pulses=12, cap_s=10., memory_s=120.,
                       once_per_loss=True, own_command_and_odometry_only=True)
SKIP_PARAMS = dict(station_radius_m=.5, repeat_cap=2, log_period_s=5.)
FAST_PARAMS = dict(view_period_s=1.2, turn_cap_s=2.)
DEFAULT_SCAN = dict(view_period_s=2., turn_cap_s=3.)


def scan_timing(tr):
    p = FAST_PARAMS if getattr(tr, 'acquire_scan_fast', 'off') == FAST else DEFAULT_SCAN
    return p['view_period_s'], p['turn_cap_s']


def segment_distance(pose_xy, beam_pose):
    """Distance and nearest point from own pose to the remembered beam segment."""
    c = np.asarray(beam_pose[:2], float)
    u = np.array([math.cos(beam_pose[2]), math.sin(beam_pose[2])])
    p = np.asarray(pose_xy, float)
    s = min(BEAM_HALF_M, max(-BEAM_HALF_M, float((p-c)@u)))
    q = c+s*u
    return float(np.linalg.norm(p-q)), q


def advance(tr, rid, now, a, last, age, pose):
    """Phase hook called by acquire(); returns a command result or None."""
    if getattr(tr, 'beam_lost_standoff', 'off') != STANDOFF or last is None:
        return None
    r = tr.robots[rid]
    if a['phase'] == 'standoff':
        return _step(tr, rid, r, now, a, pose)
    P = STANDOFF_PARAMS
    if a['phase'] != 'turn' or not 0 <= age <= P['memory_s']:
        return None
    if a.get('standoff_for') == last['rgb']['t_sim']:
        return None
    dist, q = segment_distance(pose[:2], last['pose_own_m'])
    bearing = math.atan2(q[1]-pose[1], q[0]-pose[0])-float(pose[2])
    bearing = math.atan2(math.sin(bearing), math.cos(bearing))
    if dist > P['near_m'] or abs(bearing) > P['front_rad']:
        return None
    a.update(phase='standoff', started=now, standoff_for=last['rgb']['t_sim'],
             standoff=dict(pose=np.asarray(pose, float).copy(), pulses=0, gate=_gate(),
                           point=list(last['pose_own_m'][:2])))
    tr.event(now, 'own_beam_lost_standoff_begin', robot_id=rid, distance_m=dist,
             bearing_rad=bearing, age_s=age, rgb=last['rgb'], parameters=copy.deepcopy(P),
             execution_phase=tr.state)
    return _step(tr, rid, r, now, a, pose)


def _gate():
    from harness.zone_s3_settled_servo import SettleGate
    return SettleGate()


def _finish(tr, rid, now, a, pose, reason):
    s = a['standoff']
    point = np.asarray(s['point'], float)
    yaw = math.atan2(point[1]-pose[1], point[0]-pose[0])
    a.update(phase='turn', started=now, yaw=float(yaw))
    tr.event(now, 'own_beam_lost_standoff_end', robot_id=rid, reason=reason, pulses=s['pulses'],
             own_odom_displacement_m=float(np.linalg.norm(np.asarray(pose[:2])-s['pose'][:2])))
    return False, [dict(kind='hold')]


def _step(tr, rid, r, now, a, pose):
    P = STANDOFF_PARAMS
    s = a['standoff']
    r.carrier_approach = dict(t=now, status='acquire_standoff', pulses=s['pulses'])
    moved = float(np.linalg.norm(np.asarray(pose[:2])-s['pose'][:2]))
    if moved >= P['backup_m']:
        return _finish(tr, rid, now, a, pose, 'distance')
    if s['pulses'] >= P['max_pulses']:
        return _finish(tr, rid, now, a, pose, 'pulse_cap')
    if now-a['started'] >= P['cap_s']:
        return _finish(tr, rid, now, a, pose, 'time_cap')
    if not s['gate'].ready(now, r.last_obs):
        return False, [dict(kind='hold')]
    from harness.zone_solo_cyan_pulse_cal import action_of
    profile = next((p for p in tr.profiles.values() if not p['loaded'] and p['axis'] == 'forward'
                    and p['u'] == P['reverse_u'] and p['duration_s'] == P['pulse_s']), None)
    if profile is None:
        return _finish(tr, rid, now, a, pose, 'no_reverse_profile')
    command = action_of(profile)
    from harness.active_wall_mapping import compose
    from harness.public_navigation_unknown import from_observed_grid
    from harness.public_navigation.follower import projected_clear
    from harness.public_navigation_recovery import issued_twist
    ex = r.goal.explorer
    mp = compose(ex.map_to_odom, ex.local_pose)
    clear = projected_clear(from_observed_grid(ex.grid, mp, ex.latest, set()), mp, issued_twist(command))
    if not clear:
        tr.event(now, 'would_stop_standoff_collision_guard', robot_id=rid, dev_light=tr.dev_light)
        if not tr.dev_light:
            return _finish(tr, rid, now, a, pose, 'collision_guard')
    s['pulses'] += 1
    s['gate'].issued(now, profile, r.last_obs)
    tr.approach.setdefault(rid, {})['motion_until'] = now+command['duration_s']
    return False, [command]


def skip_reason(tr, rid, pose, excluded, option):
    """Reason to skip an arm-clearance deferral during align, else None."""
    if option != SKIP or tr.state != 'align':
        return None
    station = tr.approach.get(rid, {}).get('station')
    if station is not None and float(np.linalg.norm(np.asarray(station)[:2]-np.asarray(pose)[:2])) < SKIP_PARAMS['station_radius_m']:
        return 'near_own_station'
    from harness.e2e_arm_clearance import PARAMS
    revisits = sum(1 for p in excluded if np.linalg.norm(np.asarray(pose)[:2]-p) < PARAMS['repeat_radius_m'])
    if revisits >= SKIP_PARAMS['repeat_cap']:
        return 'repeat_location_cap'
    return None


def parameters(standoff, skip, fast):
    out = {}
    if standoff != 'off':
        out['beam_lost_standoff_parameters'] = copy.deepcopy(STANDOFF_PARAMS)
    if skip != 'off':
        out['arm_clearance_align_skip_parameters'] = copy.deepcopy(SKIP_PARAMS)
    if fast != 'off':
        out['acquire_scan_fast_parameters'] = copy.deepcopy(FAST_PARAMS)
    return out


def compose(bundle, standoff='off', skip='off', fast='off'):
    if (standoff, skip, fast) == ('off', 'off', 'off'):
        return ()
    key = (standoff, skip, fast)
    if bundle['execution_bundle_id'] == RELOOK_PARENT and key in PAN_VERSIONS \
            and bundle['e2e_options'].get('relook_search') == 'view5_pan_v1':
        # v297/v300 = v296/v295 toggles on top of the v276 own-view pan relook search.
        version = PAN_VERSIONS[key]
        bundle['standoff_relook_parent'] = RELOOK_PARENT
    elif key not in VERSIONS or bundle['execution_bundle_id'] != PARENT:
        raise ValueError('ACQUIRE_STANDOFF_REQUIRES_V273_AND_REGISTERED_COMBINATION')
    else:
        version = VERSIONS[key]
    bundle['e2e_options'].update(beam_lost_standoff=standoff, arm_clearance_align_skip=skip,
                                 acquire_scan_fast=fast)
    bundle.update(parameters(*key))
    bundle.update(schema=f'ugrp.e2e_ownmap_live.v{version}', execution_bundle_id=f'e2e18-v{version}',
                  workflow_version=f'7.{version-107}.0')
    return (f'configs/simulation_workflows.d/e2e18_v{version}.json',)


def install(tr, standoff='off', skip='off', fast='off'):
    tr.beam_lost_standoff = standoff
    tr.acquire_scan_fast = fast
    if getattr(tr, 'arm_clearance', None) is not None:
        tr.arm_clearance.align_skip = skip
    return tr
