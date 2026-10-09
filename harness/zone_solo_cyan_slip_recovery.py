"""S2-only default-off Nav2 progress timeout -> inverse BackUp -> replan.

Nav2 235fc5ce SimpleProgressChecker (0.5 m, 10 s), default BT (six
retries, BackUp 0.30 m / 0.15 m/s) and BackUp port timeout (10 s).
Own complete RGB slip measurements replace odometry for progress checking.
Mecanum inverse-direction fine pulses are an explicit actuator adaptation.
No simulator/GT input; no change to the grasp, detector or PF implementation.
"""
import copy
import math
import numpy as np

from harness.zone_solo_cyan_slip_detect import Runtime as Previous, OPTION as SLIP
from harness.zone_solo_cyan_flow_fusion import compose, rot
from harness.zone_solo_cyan_pulse_cal import action_of, profile_key
from harness.zone_solo_cyan_v106 import ENVELOPE
from harness.map_goto import plan_path, rect

OPTION = 'slip_recovery_v1'
PARAMS = dict(required_movement_radius_m=.5, movement_time_allowance_s=10.,
              backup_distance_m=.30, backup_speed_limit_m_s=.15,
              backup_time_allowance_s=10., loaded_wheel_magnitude=.35,
              max_recovery_attempts=6)


def direction(action):
    v = np.array([action.get('forward', 0.), action.get('left', 0.)], float)
    return None if np.linalg.norm(v) == 0 else v / np.linalg.norm(v)


class SlipProgress:
    """Nav2 time/radius checker restricted to consecutive confirmed slip.

    There is no invented Nav2 count threshold. N is an audit output only.
    Unknown, normal travel, turns and unmeasured fine commands break evidence.
    """
    def __init__(self):
        self.reset()

    def reset(self):
        self.start = None
        self.delta = np.zeros(3)
        self.axis = None
        self.n = 0

    def issued(self, action, profiles):
        if action['kind'] == 'hold':
            return
        d = direction(action)
        p = profiles.get(profile_key(action, True)) if d is not None else None
        if (p is None or np.linalg.norm(p['mean_delta'][:2]) < .05 or
                (self.axis is not None and np.dot(d, self.axis) < .95)):
            self.reset()

    def observe(self, row):
        if row.get('status') != 'slip_replaced' or not row.get('complete_visual'):
            self.reset()
            return None
        d = np.array(row['direction'], float)
        d /= np.linalg.norm(d)
        if self.axis is not None and np.dot(d, self.axis) < .95:
            self.reset()
        if self.start is None:
            self.start, self.axis = float(row['t']), d
        self.delta = compose(self.delta, np.array(row['visual_delta']))
        self.n += 1
        if np.linalg.norm(self.delta[:2]) > PARAMS['required_movement_radius_m']:
            self.start, self.delta, self.n = float(row['end']), np.zeros(3), 0
        if row['end'] - self.start > PARAMS['movement_time_allowance_s']:
            return dict(t=row['end'], since=self.start, n=self.n,
                        visual_delta=self.delta.tolist(), direction=d.tolist())
        return None


def inverse_profile(profiles, blocked_world, yaw):
    """Existing loaded fine vocabulary; never invent an uncalibrated pulse."""
    choices = []
    for p in profiles.values():
        if not p['loaded'] or p['axis'] not in ('forward', 'left'):
            continue
        if abs(p['u']) != PARAMS['loaded_wheel_magnitude']:
            continue
        if np.linalg.norm(p['mean_delta'][:2]) / p['duration_s'] > PARAMS['backup_speed_limit_m_s']:
            continue
        a = action_of(p)
        alignment = float((rot(yaw) @ direction(a)) @ blocked_world)
        if alignment < -.5:
            choices.append((alignment, p['duration_s'], p))
    return None if not choices else min(choices, key=lambda x: x[:2])[2]


class Runtime(Previous):
    def __init__(self, *args, slip_recovery='off', **kwargs):
        if slip_recovery not in ('off', OPTION):
            raise ValueError('unknown slip_recovery')
        if slip_recovery != 'off' and (kwargs.get('slip_detection') != SLIP or
                                      kwargs.get('stall_recovery', 'off') != 'off'):
            raise ValueError('slip recovery requires slip detector and no rejected recovery')
        super().__init__(*args, **kwargs)
        self.slip_recovery = slip_recovery
        if slip_recovery != 'off':
            self.slip_progress = SlipProgress()
            self.slip_cursor = 0
            self.slip_backup = None
            self.slip_blocks = []
            self.slip_attempts = 0
            self.slip_recovery_rows = []
            self.slip_replan = False
            self.slip_exhausted_logged = False

    def _slip_event(self, now, event, **kw):
        self.slip_recovery_rows.append(dict(t=float(now), event=event, **kw))

    def _consume_slip(self, now):
        r = self.last_report
        for row in self.flow.audit['rows'][self.slip_cursor:]:
            if self.slip_backup is not None:
                b = self.slip_backup
                # A completed inverse pulse only; unknown never means progress.
                if (row.get('complete_visual') and row['t'] >= b['started'] and
                        np.dot(np.array(row.get('direction', [0, 0])), b['body_direction']) < 0):
                    b['delta'] = compose(b['delta'], np.array(row['visual_delta']))
                continue
            trigger = self.slip_progress.observe(row)
            if trigger is not None:
                if self.slip_attempts >= PARAMS['max_recovery_attempts']:
                    if not self.slip_exhausted_logged:
                        self.soft('SLIP_RECOVERY_EXHAUSTED', now)
                        self.slip_exhausted_logged = True
                    self.slip_progress.reset()
                    continue
                world = rot(r.yaw_rad) @ np.array(trigger['direction'])
                block = dict(xy=[r.x_m, r.y_m], direction=world.tolist())
                self.slip_blocks.append(block)
                self.slip_attempts += 1
                self.slip_backup = dict(started=now, delta=np.zeros(3),
                    body_direction=np.array(trigger['direction']), world_direction=world,
                    start_yaw=r.yaw_rad, pulses=0)
                self.flow.measure_small = True
                self.slip_progress.reset()
                self._slip_event(now, 'progress_failed_stop', trigger=trigger, block=block)
        self.slip_cursor = len(self.flow.audit['rows'])

    def _forbidden(self, action):
        d = direction(action)
        if d is None:
            return False
        r = self.last_report
        world = rot(r.yaw_rad) @ d
        # Temporary inhibition is cleared on the post-recovery retry, or is
        # irrelevant outside this local radius. The static map is untouched.
        return any(math.dist([r.x_m, r.y_m], b['xy']) < .5 and
                   np.dot(world, b['direction']) > .95 for b in self.slip_blocks)

    def _replan_slip(self, xy, now):
        if self.slip_replan:
            # Nav2 clear/retry semantics: an expired local failure receipt
            # must not veto the only progress command after BackUp. This does
            # not assert that the wall disappeared or that BackUp succeeded.
            self._slip_event(now, 'clear_direction_blocks', count=len(self.slip_blocks),
                             attempts=self.slip_attempts, fresh_slip_required=True)
            self.slip_blocks.clear()
            self.slip_progress.reset()
            self.path, self.path_goal = [], None
        r = self.last_report
        keep = [rect('slip_failed_target_' + str(i),
                     np.array(b['xy']) + .1 * np.array(b['direction']), [.04, .04],
                     'own_rgb_progress_failure_not_wall_truth')
                for i, b in enumerate(self.slip_blocks)]
        plan = plan_path(self.map, (r.x_m, r.y_m), xy, ENVELOPE,
                         point_keepouts=keep, escape_start_m=.10)
        self.path = (plan['waypoints_m'][1:] or [list(xy)]) if plan else [list(xy)]
        self.path_goal = tuple(xy)
        if plan is None:
            self.soft('SLIP_REPLAN_COLLISION_GUARD', now)
        self._slip_event(now, 'replan', found=plan is not None, keepouts=keep, path=self.path)
        self.slip_replan = False

    def drive(self, xy, now, *, tolerance=.03):
        if self.slip_recovery == 'off' or self.state != 'carry':
            return super().drive(xy, now, tolerance=tolerance)
        # Existing real-carry _control retains grip/arm state, timeout and
        # provider checks before dispatching here. No arm actions are generated.
        was_active = self.slip_backup is not None
        self._consume_slip(now)
        if not was_active and self.slip_backup is not None:
            return [dict(kind='hold')], False
        if self.slip_backup is not None:
            b, r = self.slip_backup, self.last_report
            progress = max(0., float(-b['delta'][:2] @ b['body_direction']))
            timeout = now - b['started'] > PARAMS['backup_time_allowance_s']
            if progress >= PARAMS['backup_distance_m'] or timeout:
                self._slip_event(now, 'backup_end', progress_m=progress, timeout=timeout,
                                 measured_success=not timeout, pulses=b['pulses'])
                self.slip_backup = None
                self.flow.measure_small = False
                self.slip_replan = True
            else:
                p = inverse_profile(self.pulse_profiles, b['world_direction'], r.yaw_rad)
                if p is None:
                    self._slip_event(now, 'backup_no_calibrated_inverse')
                    self.slip_backup = None
                    self.flow.measure_small = False
                    self.slip_replan = True
                else:
                    target = np.array([r.x_m, r.y_m]) + rot(r.yaw_rad) @ np.array(p['mean_delta'][:2])
                    if plan_path(self.map, (r.x_m, r.y_m), target, ENVELOPE, escape_start_m=.10) is None:
                        self.soft('SLIP_BACKUP_COLLISION_GUARD', now)  # dev_light
                    b['pulses'] += 1
                    self._slip_event(now, 'inverse_backup_pulse', profile=profile_key(action_of(p), True),
                                     progress_m=progress)
                    return [action_of(p)], False
        if self.slip_replan or (self.slip_blocks and self.path_goal != tuple(xy)):
            self._replan_slip(xy, now)
        cal_count = len(self.cal_rows)
        actions, arrived = super().drive(xy, now, tolerance=tolerance)
        if arrived:
            return actions, arrived
        if any(self._forbidden(a) for a in actions):
            # Re-use the unchanged pulse selector with forbidden directions
            # removed, rather than repeatedly emitting the failed command.
            original = self.pulse_profiles
            allowed = {k: p for k, p in original.items() if not self._forbidden(action_of(p))}
            self._slip_event(now, 'blocked_translation_suppressed', proposed=actions)
            del self.cal_rows[cal_count:]  # The rejected proposal was never issued.
            try:
                self.pulse_profiles = allowed
                actions, arrived = super().drive(xy, now, tolerance=tolerance)
            finally:
                self.pulse_profiles = original
        for a in actions:
            self.slip_progress.issued(a, self.pulse_profiles)
        return actions, arrived

    def record(self):
        out = super().record()
        if self.slip_recovery != 'off':
            out['slip_recovery'] = dict(option=OPTION, parameters=copy.deepcopy(PARAMS),
                rows=copy.deepcopy(self.slip_recovery_rows), gt_inputs=False,
                scope='S2 loaded carry; progress timeout, bounded inverse pulses, local replan',
                dock_initialization='unchanged', no_new_arm_commands=True)
        return out
