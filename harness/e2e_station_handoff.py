"""Own-station yaw to bounded perception handoff, separate from XY pursuit.

Nav2 docking rotates, then stays in its perception controller. Do not restart
the staging path while acquiring the fresh image needed by the grasp servo.
"""
OPTIONS = ('hold_v1', 'pan_v1')
VERSIONS = dict(zip(OPTIONS, (270, 271)))
PARAMS = dict(enter_yaw_rad=.06, release_yaw_rad=.15, perception_budget_s=12.,
              pan_period_s=2.4, pan_pulses=[1500, 1250, 1750],
              fresh_grasp_required=True)


def active(tr, rid, now, state, diag):
    mode = getattr(tr, 'station_handoff', 'off')
    if mode == 'off':
        return False
    if mode not in OPTIONS:
        raise ValueError('UNKNOWN_STATION_HANDOFF')
    handoff = state.get('station_handoff')
    error = abs(diag['heading_error_rad'])
    if handoff and error > PARAMS['release_yaw_rad']:
        state.pop('station_handoff')
        return False
    if handoff is None:
        if error > PARAMS['enter_yaw_rad'] or state['last_seen'] <= state.get('handoff_blocked_seen', -1.):
            return False
        handoff = state['station_handoff'] = dict(started=now)
        state.pop('progress_watch', None)
        tr.event(now, 'own_station_perception_handoff', robot_id=rid, option=mode,
                 heading_error_rad=diag['heading_error_rad'], distance_m=diag['distance_m'],
                 aligned_receipt=False)
    if now-handoff['started'] > PARAMS['perception_budget_s']:
        state['handoff_blocked_seen'] = state['last_seen']
        state.pop('station_handoff')
        tr.event(now, 'own_station_perception_budget', robot_id=rid, option=mode)
        return False
    return True


def observe(tr, rid, now, state, diag):
    mode = tr.station_handoff
    diag['status'] = 'station_perception_'+mode
    if mode == 'pan_v1':
        handoff = state['station_handoff']
        step = int((now-handoff['started'])//PARAMS['pan_period_s'])
        if handoff.get('view_step') != step:
            handoff['view_step'] = step
            pan = PARAMS['pan_pulses'][step % len(PARAMS['pan_pulses'])]
            if tr.robots[rid].servo[6] != pan:
                tr._poses(rid, now, [({6: pan}, .3, .6)])
            tr.event(now, 'own_station_perception_view', robot_id=rid, pan_pulse=pan)
    return False, [dict(kind='hold')]


def compose(bundle, option):
    if option == 'off':
        return ()
    if option not in OPTIONS or bundle['execution_bundle_id'] != 'e2e18-v268':
        raise ValueError('STATION_HANDOFF_REQUIRES_V268')
    version = VERSIONS[option]
    bundle['e2e_options']['station_handoff'] = option
    bundle['station_handoff_parameters'] = dict(PARAMS)
    bundle.update(schema=f'ugrp.e2e_ownmap_live.v{version}', execution_bundle_id=f'e2e18-v{version}',
                  workflow_version=f'7.{version-107}.0')
    return (f'configs/simulation_workflows.d/e2e18_v{version}.json',)
