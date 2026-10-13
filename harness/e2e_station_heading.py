"""Opt-in terminal yaw shim for the own-RGB pregrasp station.

Nav2 Rotation Shim reacquires control inside XY goal tolerance. Here that
handoff uses the existing single-axis pulse selector and own station memory;
it never marks the arm ready or changes the final grasp envelope.
"""
import math

OPTIONS = ('station10_v1', 'station20_v1')
VERSIONS = dict(zip(OPTIONS, (265, 266)))
RADII = dict(zip(OPTIONS, (.10, .20)))
PARAMS = dict(yaw_tolerance_rad=.06, exit_multiplier=1.25,
              maximum_turn_s=20., settle_s=.45, fresh_grasp_required=True)


def parameters(option):
    return dict(PARAMS, station_radius_m=RADII[option])


def control(tr, rid, now, state, diag):
    mode = getattr(tr, 'station_heading', 'off')
    if mode == 'off':
        return None
    if mode not in OPTIONS:
        raise ValueError('UNKNOWN_STATION_HEADING')
    from harness.e2e_approach_commit import retained
    from harness.e2e_capture_pose import radius as capture_radius
    radius = capture_radius(tr, RADII[mode])
    attempt = state.get('station_heading_attempt')
    if not retained(tr, now, state) or diag['distance_m'] > radius*(PARAMS['exit_multiplier'] if attempt or state.get('station_handoff') else 1.):
        state.pop('station_heading_attempt', None)
        state.pop('station_handoff', None)
        return None
    from harness.e2e_station_handoff import active as handoff_active
    if handoff_active(tr, rid, now, state, diag):
        return 'observe'
    error = abs(diag['heading_error_rad'])
    if error <= PARAMS['yaw_tolerance_rad']:
        if attempt and not attempt.get('finished'):
            attempt['finished'] = now
            state.pop('progress_watch', None)
            tr.event(now, 'own_station_heading_complete', robot_id=rid,
                     heading_error_rad=diag['heading_error_rad'])
        if attempt and now-state.get('motion_until', -math.inf) < PARAMS['settle_s']:
            return 'settle'
        return None
    if attempt is None:
        attempt = state['station_heading_attempt'] = dict(started=now)
        tr.event(now, 'own_station_heading_begin', robot_id=rid,
                 distance_m=diag['distance_m'], heading_error_rad=diag['heading_error_rad'],
                 source='own_rgb_station_and_own_command_odometry', option=mode)
    if now-attempt['started'] > PARAMS['maximum_turn_s']:
        if not attempt.get('exhausted'):
            attempt['exhausted'] = True
            tr.event(now, 'own_station_heading_budget', robot_id=rid)
        return None
    return 'rotate'


def compose(bundle, option):
    if option == 'off':
        return ()
    if option not in OPTIONS or bundle['execution_bundle_id'] != 'e2e18-v264':
        raise ValueError('STATION_HEADING_REQUIRES_V264')
    v = VERSIONS[option]
    bundle['e2e_options']['station_heading'] = option
    bundle['station_heading_parameters'] = parameters(option)
    bundle.update(schema=f'ugrp.e2e_ownmap_live.v{v}', execution_bundle_id=f'e2e18-v{v}',
                  workflow_version=f'7.{v-107}.0')
    return (f'configs/simulation_workflows.d/e2e18_v{v}.json',)
