"""Measured heading pulses for the pair's unloaded approach, default off.

Reuse the shared RPP-style selector. Keep the original own-camera planner and
arrival state machine, but replace its continuous mecanum proposal BEFORE issue.
Pulse completion, calibrated coast and delayed own feedback precede the next
controller tick. No mixed-axis pulse is admitted by weakening the PF contract.
"""
import copy
import math

from harness.zone_solo_cyan_path_heading import select_waypoint, command_reason
from harness.zone_solo_cyan_pulse_cal import action_of, profile_key

OPTION = 'pair_heading_pulse_v1'


def moving(action):
    return action['kind'] in ('mecanum', 'drive') and any(action.get(k, 0.) for k in ('forward','left','turn'))


def validate_pulse(action, profiles, *, loaded, goal_distance, alignment):
    if not moving(action):
        return
    key = profile_key(action, loaded)
    if key not in profiles:
        raise ValueError('uncalibrated pair heading pulse '+key)
    if action.get('left', 0.) and (not alignment or goal_distance > .10):
        raise ValueError('lateral pair motion outside final 0.10 m alignment')
    reason = command_reason(action)
    if reason is not None:
        raise ValueError('shared heading contract: '+reason)


def approach_proposal(profiles, pose, waypoint, goal, goal_yaw):
    profile, score = select_waypoint(profiles, False, pose, waypoint, goal, goal_yaw=goal_yaw)
    action = dict(kind='hold') if profile is None else action_of(profile)
    validate_pulse(action, profiles, loaded=False, goal_distance=math.dist(pose[:2], goal), alignment=True)
    return action, profile, score


def attach_driver(driver, localizer, *, pair_heading='off'):
    if pair_heading == 'off':
        return driver
    if pair_heading != OPTION:
        raise ValueError('unknown pair heading option')
    original = driver.tick
    audit = []
    until = None
    settled = -math.inf
    def tick(now):
        nonlocal until, settled
        if driver.outcome:
            return original(now)
        if until is not None:
            if now < until-1e-8:
                return []
            until = None
            return [dict(kind='hold')]
        if now < settled-1e-8 or localizer.last_report.t_est < settled-1e-8:
            return []
        rows = original(now)
        if not any(moving(row) for row in rows):
            return rows
        estimate = driver.loc.estimate()
        pose = (estimate['x'], estimate['y'], estimate['yaw'])
        waypoint = driver.path[0] if driver.path else driver.goal
        action, profile, score = approach_proposal(localizer.pulse_profiles, pose,
            waypoint, driver.goal, driver.goal_yaw)
        audit.append(dict(t=now, original=copy.deepcopy(rows), issued=copy.deepcopy(action),
            goal=list(driver.goal), waypoint=list(waypoint), **score))
        result = [row for row in rows if not moving(row) and row['kind'] != 'hold']+[action]
        if profile is not None:
            until = now+profile['duration_s']
            settled = now+profile['times'][-1]
        return result
    driver.tick = tick
    driver.s3_heading_audit = audit
    return driver


def attach_pair(pair, *, pair_heading='off'):
    if pair_heading == 'off':
        return pair
    if pair_heading != OPTION:
        raise ValueError('unknown pair heading option')
    from harness.zone_s3_coupled_motion import attach_prediction, HEADING_EXCEPTIONS
    for own in pair.actors.values():
        attach_prediction(own.pose.localizer, pair.team.params)
    start = pair.team.start
    def submit(*args, **kwargs):
        result = start(*args, **kwargs)
        for session in pair.team.sessions:
            for ep in session['endpoints'].values():
                if not hasattr(ep.controller.driver, 's3_heading_audit'):
                    attach_driver(ep.controller.driver, ep.own.pose.localizer, pair_heading=pair_heading)
                    from harness.zone_s3_pair_alignment import attach
                    attach(ep)
        return result
    pair.team.start = submit
    record = pair.record
    def recorded():
        return {**record(), 'pair_heading': dict(option=pair_heading,
            scope='heading for solo/approach; coupled beam carry preserves legacy schedule',
            exceptions=copy.deepcopy(HEADING_EXCEPTIONS),
            prediction={r:copy.deepcopy(a.pose.localizer.s3_coupled_motion) for r,a in pair.actors.items()},
            decisions={ep.own.robot_id: copy.deepcopy(ep.controller.driver.s3_heading_audit)
                for session in pair.team.sessions for ep in session['endpoints'].values()},
            alignment={ep.own.robot_id:copy.deepcopy(ep.s3_alignment_audit)
                for session in pair.team.sessions for ep in session['endpoints'].values()})}
    pair.record = recorded
    return pair
