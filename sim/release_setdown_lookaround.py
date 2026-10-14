"""Default-off unloaded panoramic recovery, without a global-pose prerequisite.

The release runner already lowers/opens via PairReleaseCode before any sweep.
After one unsuccessful extra panorama, retrace part of that robot's issued
backoff, then look behind it as well. Map *hypotheses* check static clearance;
none is accepted as a pose here. No new grasp path or simulator input.
"""
from __future__ import annotations

import math
import numpy as np

from sim.global_landmark_localization import PARAMS, rotation, wrap
from sim.lookaround_localization import LOOK_ARM, LOOK_ARM_V2, look_servo, rotate_plan
from sim.release_global_observation import BACKSTEP_M, MARGIN_M

OPTION = 'setdown_lookaround_v1'


def script(localizer, teacher, now, release_command_pose):
    """One bounded attempt; fresh RGB is consumed by the normal localizer.

The .10 m forward leg reverses a subset of the initial .15 m backoff. This
avoids backing farther toward an unseen wall. Every retained map hypothesis
must clear the *unchanged* .18 m body + .15 m uncertainty halo for the whole
leg, and the own-command released beam must clear the turning body + .04 m.
Unknown clearance fails closed. Rotation always happens with the arm folded.
"""
    entry = dict(action='setdown_lookaround_unavailable', t=now)

    def reject(reason):
        return [], dict(entry, reason=reason)

    if teacher.holding or teacher.pwm[1] < 1900:
        return reject('cargo_not_set_down')
    if release_command_pose is None:
        return reject('release_command_trace_missing')
    start = np.asarray(release_command_pose, float)
    current = np.asarray(localizer.command_own.x, float)
    displacement = rotation(-start[2])@(current[:2]-start[:2])
    # Do not turn a nominal retrace into a new approach path after a body turn
    # or a sideways leg. The anchor is reset only by the actual open sequence.
    if (not np.isfinite(np.r_[start, current]).all() or
            abs(float(wrap(current[2]-start[2]))) > .02 or
            abs(displacement[1]) > .01 or displacement[0] > -BACKSTEP_M-.01):
        return reject('not_on_issued_backoff_trace')
    band = teacher.belief.get('released_band', now)
    if band is None:
        return reject('release_command_memory_missing')
    end, outward, _ = teacher.end_and_outward(now)
    end = np.asarray(end); other = end-.60*np.asarray(outward)
    v = other-end
    for forward in np.linspace(0., BACKSTEP_M, 11):
        center = np.array([forward, 0.])
        closest = end+np.clip((center-end)@v/(v@v), 0., 1.)*v
        if np.linalg.norm(center-closest) < PARAMS['robot_clearance_m']+MARGIN_M:
            return reject('released_beam_turn_clearance')
    decision = localizer.decision or {}
    candidates = decision.get('credible_hypotheses', decision.get('alternatives', []))
    poses = np.array([h['pose'] for h in candidates], float).reshape(-1, 3)
    if not len(poses) or not np.isfinite(poses).all():
        return reject('map_clearance_unknown')
    for forward in np.linspace(0., BACKSTEP_M, 11):
        q = poses.copy()
        q[:, :2] += forward*np.c_[np.cos(q[:, 2]), np.sin(q[:, 2])]
        if not localizer.global_matcher.free(q, extra_clearance=.15).all():
            return reject('map_clearance_unsafe')
    restore = {k: teacher.pwm[k] for k in (3, 4, 5, 6)}
    steps = [dict(servo=look_servo(0., LOOK_ARM_V2), wait=1., capture=False, label='setdown_fold'),
             dict(wheels=teacher.shift_plan(BACKSTEP_M, 1.), wait=.3, capture=False,
                  label='setdown_retrace_backoff_0.10m')]
    yaw = 0.
    # Two half-panoramas cover the rear blind sector. All 12 views fit inside
    # the existing 18-view estimator window; no acceptance/window change.
    for heading in (-90., 90.):
        steps.append(dict(servo=look_servo(0., LOOK_ARM_V2), wait=1., capture=False,
                          label='setdown_fold_before_turn'))
        steps.append(dict(wheels=rotate_plan(math.radians(heading-yaw)), wait=.3,
                          capture=False, label=f'setdown_turn_{heading:+.0f}'))
        yaw = heading
        for arm, name in ((LOOK_ARM_V2, 'surroundings'), (LOOK_ARM, 'floor')):
            for pan in (-60., 0., 60.):
                steps.append(dict(servo=look_servo(pan, arm), wait=1., capture=True,
                                  label=f'setdown_view_{heading:+.0f}_{name}_{pan:+.0f}'))
    steps.extend([
        dict(servo=look_servo(0., LOOK_ARM_V2), wait=1., capture=False, label='setdown_fold_before_return'),
        dict(wheels=rotate_plan(math.radians(-yaw)), wait=.3, capture=False, label='setdown_turn_return'),
        dict(servo=restore, wait=1., capture=False, label='restore_arm')])
    return steps, dict(entry, action=OPTION, retrace_m=BACKSTEP_M, body_headings_deg=[-90., 90.],
                       capture_count=12, hypothesis_count=len(poses), all_retained_hypotheses_clear=True,
                       released_beam_clearance_m=PARAMS['robot_clearance_m']+MARGIN_M,
                       source='own RGB map hypotheses + own issued backoff/release commands')
