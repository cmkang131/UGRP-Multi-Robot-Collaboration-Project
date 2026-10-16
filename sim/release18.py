"""Opt-in reuse of an unchanged open/hover command after reapproach.

Command age is not measured joint state. Fresh RGB alignment, the 0.3 s
visual stability window and all release17 guards remain mandatory. Only the
redundant open (1.2 s) or complete open/hover (2.6 s) wait is omitted. See release18.md for evidence.
"""
from __future__ import annotations

import math

from sim import release17, release_global_observation as global_observation

PROFILE = 'release18_v1'
PROFILES = (*release17.PROFILES, PROFILE)
REUSE = 'settled_command_v1'
REUSE_MODES = ('off', REUSE)
GOAL_REGION = 'inside_margins_v1'
GOAL_MODES = ('off', GOAL_REGION)
SETTLE_S = 2.6
OPEN_WAIT_S = 1.2
HOVER_WAIT_S = 1.4


def validate(profile, record_training, options, plan):
    reuse = options.get('release_settle_reuse', 'off')
    goal = options.get('release_goal_region','off')
    if goal not in GOAL_MODES or (goal != 'off' and profile != PROFILE):
        raise ValueError('release_goal_region requires release18_v1 and a known mode')
    if reuse not in REUSE_MODES:
        raise ValueError('unknown release_settle_reuse')
    if reuse != 'off' and profile != PROFILE:
        raise ValueError('release_settle_reuse requires release18_v1')
    release17.validate(release17.PROFILE if profile == PROFILE else profile,
                       record_training, options, plan)


class CommandHistory:
    """Last change of the complete issued PWM snapshot, in SIM time only."""
    def __init__(self):
        self.pwm = None
        self.since = None
        self.last = None
        self.changed_at = {}

    def observe(self, pwm, now):
        if not math.isfinite(now) or (self.last is not None and now < self.last):
            raise ValueError('nonmonotonic command history')
        for sid, value in pwm.items():
            if self.pwm is None or self.pwm.get(sid) != value:
                self.changed_at[sid] = now
        if self.pwm != pwm:
            self.pwm = dict(pwm)
            self.since = now
        self.last = now

    def age(self, pwm, now):
        # A stale caller cannot authorize reuse. Unknown history fails closed.
        if self.pwm != pwm or self.last != now or self.since is None:
            return None
        return now-self.since

    def servo_age(self, sid, value, now):
        if self.last != now or self.pwm is None or self.pwm.get(sid) != value:
            return None
        return now-self.changed_at[sid]


class LineAlign(release17.LineAlign):
    def __init__(self, teacher, now, *, settle_reuse='off', command_history=None,
                 after_approach=False, before_approach=False, idle=lambda: False, **kwargs):
        if settle_reuse not in REUSE_MODES:
            raise ValueError('unknown release_settle_reuse')
        super().__init__(teacher, now, **kwargs)
        self.settle_reuse = settle_reuse
        self.command_history = command_history
        self.after_approach = after_approach
        self.before_approach = before_approach
        self.idle = idle

    def tick(self, now, capture, schedule):
        if self.state == 'open' and self.settle_reuse == REUSE:
            age = None if self.command_history is None else self.command_history.age(self.expected, now)
            if (self.after_approach and not self.teacher.holding and self.teacher.pwm == self.expected
                    and age is not None and age >= SETTLE_S-1e-9 and self.idle()):
                self.state = 'align'
                self.until = now
                self.progress = now
                self.records.append(dict(t=now, event='reuse_settled_open_hover', command_age_s=age,
                                         omitted_wait_s=SETTLE_S, source='own issued PWM history'))
            elif (self.before_approach and not self.teacher.holding and self.teacher.pwm.get(1)==2000
                  and self.command_history is not None and self.command_history.pwm==self.teacher.pwm and self.idle()):
                opened = None if self.command_history is None else self.command_history.servo_age(1,2000,now)
                if opened is not None and opened >= OPEN_WAIT_S-1e-9:
                    schedule(self.teacher.rid, [(0.,self.hover)], now)
                    self.state = 'align'
                    self.until = now+HOVER_WAIT_S
                    self.progress = self.until
                    self.records.append(dict(t=now,event='reuse_settled_open',command_age_s=opened,
                                             omitted_wait_s=OPEN_WAIT_S,source='own issued gripper PWM history'))
        return super().tick(now, capture, schedule)

    def record(self):
        return dict(super().record(), release18=dict(settle_reuse=self.settle_reuse))


map_motion_clear = release17.map_motion_clear
backoff_plan = release17.backoff_plan
approach_plan = release17.approach_plan


def pair_choice(reports, robots, now, *, goal_region='off', **kwargs):
    """Accept the RGB margin goal region after every existing safety rejection.

    The original pair chooser checks localization, axis, lateral clearance and
    cross-robot slack consistency first. Reuse that result; replace only an
    extra centering leg when BOTH reported end margins already satisfy 4 cm.
    No simulator/evaluator inputs are accepted.
    """
    if goal_region not in GOAL_MODES:
        raise ValueError('unknown release_goal_region')
    choice = global_observation.pair_choice(reports,robots,now,**kwargs)
    if (goal_region==GOAL_REGION and choice.get('reason')=='localized_margin_correction'
            and choice['action']=='shift'):
        margins = [reports[r]['margin_m'] for r in robots]
        if all(math.isfinite(m) and m>=global_observation.MARGIN_M for m in margins):
            return dict(action='lower',reason='localized_margins_inside',t=now,margins_m=margins,
                        release_goal_region=goal_region)
    return choice
