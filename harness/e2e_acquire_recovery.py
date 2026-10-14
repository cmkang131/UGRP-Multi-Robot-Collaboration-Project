"""Default-off acquisition failure propagation and persistent Nav2 recovery.

References: experiments/2026-10-14-e2e18-approach-recovery/references.md.
Own camera/command pose only. Never converts a cancelled view into an observation.
"""
import math
import numpy as np

OPTIONS = ('cancel_v1', 'persistent_v1')
PARAMS = dict(failed_view_frames=3, explore_s=25., progress_s=10.,
              same_choice_limit=3, translation_m=.003, rotation_rad=.01)


def enabled(tr):
    option = getattr(tr, 'acquire_recovery', 'off')
    if option not in ('off', *OPTIONS):
        raise ValueError('UNKNOWN_ACQUIRE_RECOVERY')
    return option != 'off'


def failed_view(tr, rid, now, a, busy):
    """Count distinct accepted frames after the executor has stopped servicing a view."""
    if not enabled(tr) or a.get('view', -1) < 0:
        return False
    r = tr.robots[rid]
    if busy or now < getattr(r, 'camera_settle_until', -1.):
        return False
    matches = all(r.servo.get(k) == v for k, v in a.get('view_pose', {}).items())
    frame = (r.last_obs or {}).get('frame_id')
    if matches:
        a['view_failure_count'] = 0
        return False
    if frame is None or frame == a.get('view_failure_frame'):
        return False
    a['view_failure_frame'] = frame
    a['view_failure_count'] = a.get('view_failure_count', 0) + 1
    if a['view_failure_count'] < PARAMS['failed_view_frames']:
        return False
    tr.event(now, 'own_acquisition_view_rejected', robot_id=rid,
             view=a['view'], requested_pose=a['view_pose'], issued_pose=dict(r.servo),
             reason='executor_idle_posture_mismatch', observed=False)
    a['view_failure_count'] = 0
    return True


def resume(robot, now):
    """Keep failed goals/recovery cursor; a camera scan already covered the sector."""
    e = robot.goal.explorer
    n = e.navigator
    n.finished = False
    n.initial_scan_used = True
    # Do not reset an active goal or recovery. Re-plan from the newest own grid.
    e.plan = None
    e.last_plan_t = -math.inf
    n.next_frontier_ns = 0
    n.event(now, 'acquisition_navigation_continued', blacklist_size=len(n.blacklist),
            phase=getattr(n, 'phase', None))


def filter_choice(tr, rid, now, a, action):
    """Three unchanged own-pose choices fail the action, preserving its blacklist.

    The existing navigator supplies recovery candidates, calibrated pulses and
    collision admission on the next camera update; no unfiltered escape pulse.
    """
    r = tr.robots[rid]
    pose = np.asarray(r.goal.explorer.local_pose, float)
    signature = tuple(action.get(k, 0.) for k in ('forward', 'left', 'turn'))
    old = a.get('choice_watch')
    if old:
        delta = pose - np.asarray(old['pose'])
        changed = (np.linalg.norm(delta[:2]) >= PARAMS['translation_m'] or
                   abs(math.atan2(math.sin(delta[2]), math.cos(delta[2]))) >= PARAMS['rotation_rad'])
    else:
        changed = True
    count = old['count'] + 1 if old and not changed and old['signature'] == signature else 1
    a['choice_watch'] = dict(pose=pose.tolist(), signature=signature, count=count)
    if count < PARAMS['same_choice_limit']:
        return action
    n = r.goal.explorer.navigator
    tr.event(now, 'own_acquisition_choice_removed', robot_id=rid,
             choice=list(signature), unchanged_choices=count,
             source='own_RGB_command_odometry', next_candidate='navigator_recovery')
    a.pop('choice_watch', None)
    # Native action failure blacklists only the failed goal. Native recovery
    # then supplies backup/spin and later replans; never clear this blacklist.
    if getattr(n, 'phase', None):
        n.phase_result(now, False)
    else:
        n.action_failed(now, 'acquisition_unchanged_choice')
        n.begin_phase('backup', now)
    r.goal.explorer.plan = None
    r.goal.explorer.last_plan_t = -math.inf
    return dict(kind='hold')
