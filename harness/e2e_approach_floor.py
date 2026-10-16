"""Own-RGB approach distance floor (default off): do not drive closer to the beam.

Diagnosis (e2e18 v273 r52 r2, 207-226 SIM s): the own camera saw a clipped beam band
(BAND_CLIPPED, end not visible) with the nearest visible point 0.33 m ahead, yet the
navigate_pregrasp controller kept driving forward from the remembered station to
0.08 m, where the beam fills and leaves the image; the later turn/scan/explore
re-acquisition cost hundreds of SIM s. Recovery after the loss (v295/v302 standoff)
did not help. This toggle keeps the target in view instead.

Standard references: field-of-view keeping in visual servoing and a docking staging
pose at a distance from the target (Chaumette & Hutchinson, IEEE RAM 2006; Nav2
opennav_docking) -- the specific rule here is ours (citations not re-verified).

Rule (fresh own RGB only; own odometry/commands only, no truth, contact or joints):
while the freshest beam observation is clipped (end not visible) and its nearest
visible point is closer than `floor_m`, forward motion is removed from the planned
command. If the point is also `retreat_below_m` closer than the floor, up to
`max_reverse_pulses` calibrated reverse pulses (one per new settled frame) restore
the view. After `release_s` SIM s of continuous blocking the filter lets the
planned command through again and records it (DEV-light never stops the run).
"""
import copy
import math

OPTIONS = {'v1': .30, 'v2': .22}
PARENT = 'e2e18-v303'
VERSIONS = {'v1': 310, 'v2': 311}
PARAMS = dict(retreat_below_m=.04, max_reverse_pulses=8, release_s=20., observation_age_s=.45,
              reverse_u=-.35, pulse_s=.1, own_rgb_and_odometry_only=True)


def parameters(option):
    return dict(PARAMS, floor_m=OPTIONS[option])


def compose(bundle, option):
    if option == 'off':
        return ()
    if option not in OPTIONS or bundle['execution_bundle_id'] != PARENT:
        raise ValueError('APPROACH_FLOOR_REQUIRES_V303')
    version = VERSIONS[option]
    bundle['approach_floor_parent'] = PARENT
    bundle['e2e_options']['approach_floor'] = option
    bundle['approach_floor_parameters'] = parameters(option)
    bundle.update(schema=f'ugrp.e2e_ownmap_live.v{version}', execution_bundle_id=f'e2e18-v{version}',
                  workflow_version=f'7.{version-107}.0')
    return (f'configs/simulation_workflows.d/e2e18_v{version}.json',)


def parent_for_validation(bundle):
    option = bundle['e2e_options'].get('approach_floor')
    if (option not in OPTIONS or bundle.get('approach_floor_parent') != PARENT
            or bundle['execution_bundle_id'] != f'e2e18-v{VERSIONS[option]}'
            or bundle.get('approach_floor_parameters') != parameters(option)):
        raise ValueError('REGISTERED_APPROACH_FLOOR_REQUIRED')
    old = copy.deepcopy(bundle)
    old['execution_bundle_id'] = PARENT
    old['e2e_options'].pop('approach_floor')
    old.pop('approach_floor_parent')
    old.pop('approach_floor_parameters')
    return old


def install(tr, option='off'):
    tr.approach_floor = option
    return tr


def _clipped_near_x(tr, r, now):
    obs = getattr(r, 'beam_observation', None)
    if not obs or not 0 <= now-obs['rgb']['t_sim'] <= PARAMS['observation_age_s']:
        return None, None
    b = obs['result']
    if b.get('end_visible'):
        return None, obs
    band = b.get('band') or {}
    if not (b.get('visible') and (b.get('reason') == 'BAND_CLIPPED' or band.get('touches_invalid_border'))):
        return None, obs
    xy = b.get('near_end_base_m')
    return (float(xy[0]) if xy else None), obs


def apply(tr, rid, now, state, command, diag):
    """Return the (possibly replaced) command for the planned navigate step."""
    mode = getattr(tr, 'approach_floor', 'off')
    if mode == 'off':
        return command
    floor = OPTIONS[mode]
    r = tr.robots[rid]
    st = state.setdefault('approach_floor', dict(pulses=0, blocked_since=None, gate=None))
    x, obs = _clipped_near_x(tr, r, now)
    if x is None:
        if obs is not None and obs['result'].get('end_visible'):
            st.update(pulses=0, blocked_since=None)
        return command
    if x >= floor or command.get('kind') != 'mecanum' or command.get('forward', 0.) <= 0.:
        st['blocked_since'] = None if x >= floor else st['blocked_since']
        return command
    if st['gate'] is not None and not st['gate'].ready(now, r.last_obs):
        diag['status'] = 'approach_floor_settle'
        return dict(kind='hold')
    if st['blocked_since'] is None:
        st['blocked_since'] = now
    if now-st['blocked_since'] > PARAMS['release_s']:
        tr.event(now, 'approach_floor_released', robot_id=rid, near_end_x_m=x, floor_m=floor,
                 rgb=obs['rgb'], dev_light=tr.dev_light)
        st['blocked_since'] = now
        return command
    diag.update(status='approach_floor_hold', approach_floor_near_end_x_m=x)
    out = dict(kind='hold')
    action = 'hold'
    if x < floor-PARAMS['retreat_below_m'] and st['pulses'] < PARAMS['max_reverse_pulses']:
        from harness.zone_s3_settled_servo import SettleGate
        from harness.zone_solo_cyan_pulse_cal import action_of
        profile = next(p for p in tr.profiles.values() if not p['loaded'] and p['axis'] == 'forward'
                       and p['u'] == PARAMS['reverse_u'] and p['duration_s'] == PARAMS['pulse_s'])
        out = action_of(profile)
        if st['gate'] is None:
            st['gate'] = SettleGate()
        st['gate'].issued(now, profile, r.last_obs)
        st['pulses'] += 1
        diag['status'] = 'approach_floor_backup'
        action = 'reverse'
    tr.event(now, 'own_approach_floor', robot_id=rid, option=mode, near_end_x_m=x, floor_m=floor,
             action=action, pulses=st['pulses'], rgb=obs['rgb'], aligned_receipt=False)
    return out
