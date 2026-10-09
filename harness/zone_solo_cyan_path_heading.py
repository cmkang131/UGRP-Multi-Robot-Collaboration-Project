"""Opt-in path-heading pursuit using the unchanged calibrated pulse vocabulary.

Nav2 RPP rotateToHeading / path carrot bearing, adapted to MasterPi's minimum
PWM: full measured pulse + coast + fresh feedback replaces continuous ramps.
The mixin sits immediately before PulseRuntime in the cooperative MRO, so
unknown-start reporting, slip recovery, frames and active sensing remain live.
"""
import copy
import math

import numpy as np

from harness.zone_solo_cyan_pulse_cal import Runtime as PulseRuntime
from harness.zone_solo_cyan_pulse_cal import action_of, profile_key, select_pulse
from harness.zone_solo_cyan_v106 import ENVELOPE

OPTION = 'path_tangent_v1'
PARAMS = dict(final_alignment_m=.10, heading_tolerance_rad=.06,
              turn_raw_limit=.35, turn_duration_s=.10,
              lateral_raw_limit=.35, lateral_duration_s=.06,
              angular_dynamics='unchanged measured pulse, coast and delayed feedback',
              active_observation_actual_limit_deg=90., gt_inputs=False)


def wrap(angle):
    return math.atan2(math.sin(angle), math.cos(angle))


def select(profiles, loaded, body_error, yaw, goal_distance):
    """Rotate on the spot, then positive body-forward; trim only near FINAL goal.

    Distance to an intermediate waypoint never enables strafe. Finite turn
    resolution is the existing .06 rad threshold, not a fitted new motor law.
    """
    error = np.asarray(body_error, float)
    final = goal_distance <= PARAMS['final_alignment_m']
    bearing = math.atan2(error[1], error[0])
    heading_error = wrap(-yaw if final else bearing)
    pool = {k: p for k, p in profiles.items() if p['loaded'] == loaded}
    turns = {k: p for k, p in pool.items() if p['axis'] == 'turn'
             and abs(p['u']) <= PARAMS['turn_raw_limit']
             and p['duration_s'] == PARAMS['turn_duration_s']}
    # Final task orientation is east (existing grasp/door/place contract).
    # Finish that turn before lateral/fore-aft fine positioning.
    if abs(heading_error) > PARAMS['heading_tolerance_rad']:
        candidates = [p for p in turns.values() if p['mean_delta'][2]*heading_error > 0
                      if abs(wrap(heading_error-p['mean_delta'][2])) < abs(heading_error)]
        p = min(candidates, key=lambda p: abs(wrap(heading_error-p['mean_delta'][2]))) if candidates else None
        return p, dict(phase='rotate_goal' if final else 'rotate_path',
                       heading_error_rad=heading_error, goal_distance_m=goal_distance,
                       before=heading_error**2,
                       after=heading_error**2 if p is None else wrap(heading_error-p['mean_delta'][2])**2)
    if final:
        pool = {k: p for k, p in pool.items()
                if (p['axis'] == 'left' and abs(p['u']) <= PARAMS['lateral_raw_limit']
                    and p['duration_s'] == PARAMS['lateral_duration_s'])
                or (p['axis'] == 'forward' and p['duration_s'] == .10)}
    else:
        pool = {k: p for k, p in pool.items()
                if p['axis'] == 'forward' and p['u'] > 0 and p['duration_s'] == .10}
    p, score = select_pulse(pool, loaded, error, 0.)
    score.update(phase='final_alignment' if final else 'forward_path',
                 heading_error_rad=heading_error, goal_distance_m=goal_distance)
    return p, score


class _HeadingPulse(PulseRuntime):
    def drive(self, xy, now, *, tolerance=.03):
        if getattr(self, 'heading_mode', 'off') == 'off':
            return super().drive(xy, now, tolerance=tolerance)
        from harness.map_goto import plan_path
        r = self.last_report
        if not r.initialized or not all(math.isfinite(v) for v in (r.x_m, r.y_m, r.yaw_rad)):
            return self.fail('POSE_NOT_INITIALIZED', now), False
        if r.std_xy_m > .05 or r.std_yaw_rad > math.radians(5) or r.last_fix_t is None:
            self.soft('POSE_UNCERTAIN', now)
        here = (r.x_m, r.y_m)
        distance, yaw = math.dist(here, xy), wrap(r.yaw_rad)
        if distance <= tolerance and abs(yaw) <= PARAMS['heading_tolerance_rad']:
            self.path, self.path_goal = [], None
            return [dict(kind='hold')], True
        if self.path_goal != tuple(xy):
            plan = plan_path(self.map, here, xy, ENVELOPE, escape_start_m=.10)
            if plan is None:
                self.soft('PATH_COLLISION_GUARD', now)
                self.path = [list(xy)]
            else:
                self.path = plan['waypoints_m'][1:] or [list(xy)]
                self.event('path', now, plan=plan)
            self.path_goal = tuple(xy)
        while len(self.path) > 1 and math.dist(here, self.path[0]) < .035:
            self.path.pop(0)
        c, s = math.cos(yaw), math.sin(yaw)
        error = np.array([[c, s], [-s, c]]) @ (np.array(self.path[0])-here)
        loaded = self.pose.provider.loc._pf.load.loaded
        p, score = select(self.pulse_profiles, loaded, error, yaw, distance)
        self.heading_rows.append(dict(t=now, state=self.state, goal=list(xy),
                                     waypoint=list(self.path[0]), **copy.deepcopy(score)))
        if p is None:
            self.soft('PULSE_RESOLUTION_LIMIT', now)
            return [dict(kind='hold')], False
        action = action_of(p)
        self.cal_rows.append(dict(t=now, state=self.state, waypoint=list(self.path[0]),
            issued=action, profile_key=profile_key(action, loaded), predicted_delta=p['mean_delta'],
            prediction_variance=p['prediction_variance'], transfer=p['transfer'], score=score))
        return [action], False


def runtime_class(previous):
    class Runtime(previous, _HeadingPulse):
        def __init__(self, *args, heading_mode='off', **kwargs):
            if heading_mode not in ('off', OPTION):
                raise ValueError('unknown heading_mode')
            if heading_mode != 'off' and kwargs.get('pulse_motion_model') != 'v7_pulse_cal_v1':
                raise ValueError('path heading requires measured pulse motion')
            super().__init__(*args, **kwargs)
            # Default off does not even add instance state or change records.
            if heading_mode != 'off':
                self.heading_mode, self.heading_rows = heading_mode, []
                self.heading_align_until = None
                self.heading_align_settled = -math.inf

        def drive(self, xy, now, **kwargs):
            if getattr(self, 'heading_mode', 'off') == 'off':
                return super().drive(xy, now, **kwargs)
            # Slip BackUp may otherwise select a lateral inverse. Outside the
            # final 10 cm offer it only its existing forward/backward vocabulary.
            r = self.last_report
            original = self.pulse_profiles
            if math.dist((r.x_m, r.y_m), xy) > PARAMS['final_alignment_m']:
                self.pulse_profiles = {k:p for k,p in original.items() if p['axis'] != 'left'}
            try:
                return super().drive(xy, now, **kwargs)
            finally:
                self.pulse_profiles = original

        def step(self, now):
            if getattr(self, 'heading_mode', 'off') == 'off' or self.terminal:
                return super().step(now)
            if self.heading_align_until is not None:
                if now < self.heading_align_until-1e-8:
                    return []
                self.heading_align_until = None
                return [(self.robot_id, dict(kind='hold'))]
            if now < self.heading_align_settled or self.last_report.t_est < self.heading_align_settled-1e-8:
                return []
            rows = super().step(now)
            if self.state != 'align' or self.target is None:
                return rows
            from harness.zone_final_pair_vision import GRASP_RADIUS_M
            error = np.array(self.target)-[GRASP_RADIUS_M, 0.]
            distance = float(np.linalg.norm(error))
            if distance <= PARAMS['final_alignment_m']:
                return rows
            result = []
            for rid, action in rows:
                if action['kind'] != 'mecanum' or not any(action.get(k,0) for k in ('forward','left','turn')):
                    result.append((rid, action)); continue
                # Preserve the visual detector/view state machine; replace only
                # its far approach proposal BEFORE the host issues any command.
                p, score = select(self.pulse_profiles, self.pose.provider.loc._pf.load.loaded,
                                  error, self.last_report.yaw_rad, distance)
                issued = dict(kind='hold') if p is None else action_of(p)
                self.heading_rows.append(dict(t=now, state='align', target_base_m=list(self.target),
                    replaced_proposal=copy.deepcopy(action), issued=issued, **score))
                if self.fine_rows and self.fine_rows[-1]['t'] == now:
                    self.fine_rows[-1]['heading_replaced_before_issue'] = True
                self.fine_until = None
                if p is not None:
                    self.heading_align_until = now+p['duration_s']
                    self.heading_align_settled = now+p['times'][-1]
                    self.fine_observe_after = self.heading_align_settled
                result.append((rid, issued))
            return result

        def record(self):
            out = super().record()
            if getattr(self, 'heading_mode', 'off') != 'off':
                out['heading_mode'] = dict(option=OPTION, parameters=copy.deepcopy(PARAMS),
                                           decisions=copy.deepcopy(self.heading_rows))
            return out
    return Runtime
