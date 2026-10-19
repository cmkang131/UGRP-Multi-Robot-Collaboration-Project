"""Frozen closed-loop transition overlay for the act18-loop candidate (B5).

Post-processes only the student's own issued base commands, using no teacher,
ground-truth, top-camera or map input. It targets the diagnosed closed-loop
divergence: the student keeps driving the base during the grasp hold and does
not retreat during release. Constants are pre-registered and must not be tuned
on validation outcomes.

Gripper-closed is servo 1 below 1900 (`act18_gripper_state`); servo 5 is the
shoulder and must not trigger the hold brake.
"""
import numpy as np

from act18_gripper_state import (GRIPPER_OPEN_PWM, GRIPPER_SERVO,
                                 gripper_closed)

HOLD_WHEEL_SCALE = .25
HOLD_TICKS = 20
RETREAT_TICKS = 15
RETREAT_WHEEL = .31
STOP_THRESHOLD = .155
CLOSE_STREAK = 3


def overlay_receipt():
    return dict(kind='closed_loop_transition_overlay_v1',
        scope='own issued base command post-processing only; no teacher/GT/top-camera input',
        hold_wheel_scale=HOLD_WHEEL_SCALE, hold_ticks=HOLD_TICKS,
        # Legacy receipt key, kept for schema stability: 1900 is the servo-1
        # "clearly open" cutoff, so closed is pwm['1'] < 1900, not > 1900.
        close_pwm=GRIPPER_OPEN_PWM,
        gripper_servo=GRIPPER_SERVO, gripper_closed_rule='pwm[1] < 1900',
        gripper_open_pwm=GRIPPER_OPEN_PWM,
        retreat_ticks=RETREAT_TICKS, retreat_wheel=RETREAT_WHEEL, stop_threshold=STOP_THRESHOLD,
        close_streak=CLOSE_STREAK,
        approach_direction='sign of mean own grasp-phase wheel command (own history only)')


class LoopOverlay:
    def __init__(self):
        self.skill = None
        self.hold = 0
        self.closed_streak = 0
        self.release_ticks = 0
        self.grasp_sum = np.zeros(4)
        self.grasp_count = 0

    def reset(self, skill):
        self.skill = skill
        self.hold = 0
        self.closed_streak = 0
        self.release_ticks = 0
        self.grasp_sum = np.zeros(4)
        self.grasp_count = 0

    def step(self, skill, command):
        """Return (command, event|None); event is only for the evidence log."""
        event = None
        if skill != self.skill:
            # Preserve the grasp-phase direction when entering release (own history).
            previous, self.skill = self.skill, skill
            self.hold = 0
            self.closed_streak = 0
            self.release_ticks = 0
            if skill == 'grasp':
                self.grasp_sum = np.zeros(4)
                self.grasp_count = 0
        wheels = np.asarray(command['wheels'], np.float64)
        moving = bool(np.abs(wheels).max() > STOP_THRESHOLD)
        if skill == 'grasp':
            if moving:
                self.grasp_sum += wheels
                self.grasp_count += 1
            closed = gripper_closed(command['pwm'])
            self.closed_streak = self.closed_streak+1 if closed else 0
            if self.closed_streak == CLOSE_STREAK:
                self.hold = HOLD_TICKS
            if self.hold > 0:
                before = wheels.tolist()
                command = {**command, 'wheels': [float(w*HOLD_WHEEL_SCALE) for w in wheels]}
                event = dict(kind='hold_brake', wheels_before=before, wheels_after=command['wheels'])
                self.hold -= 1
        elif skill == 'release':
            self.release_ticks += 1
            if self.release_ticks <= RETREAT_TICKS and not moving and self.grasp_count:
                direction = self.grasp_sum/self.grasp_count
                sign = np.sign(direction)
                if np.abs(sign).sum() > 0:
                    command = {**command, 'wheels': [float(-s*RETREAT_WHEEL) for s in sign],
                               'duration_s': [.1]*4}
                    event = dict(kind='release_retreat', direction=sign.tolist(),
                                 wheels_after=command['wheels'])
        return command, event
