"""Default-off S2 solo carry pose from the real delivery stack.

Offline command candidate, NOT admitted by an execution bundle. The old HIGH
lift/check and descent are retained; only the intervening transport pose changes.
Real servo ordering/duration is reused, not concurrent invented interpolation.
No image acquired at HIGH is reinterpreted as this camera pose. The existing
provider remains prediction-only outside its calibrated HIGH pose. A new-pose
camera/motion qualification and genuine image replay are needed for admission.
"""
import copy

from scripts.red_block.poses import servo_steps
from harness.zone_solo_cyan_visual_fix import Runtime as Previous
from harness import zone_solo_cyan_v106 as old

OPTION = 'real_delivery_v1'
# physical_state_machine_reference.DELIVERY_CARRY_POSE and real trace
# 20260902T145131Z-real-19bb30fd / pick-b5f9a960 event67. No live hardware import.
CARRY = {1: 1500, 3: 600, 4: 2200, 5: 1400, 6: 1500}
REAL_COMMAND_WAIT_S = .15  # red_block.robot.Robot.move_servo


def at_carry(servo):
    return all(servo.get(sid) == pwm for sid, pwm in CARRY.items())


def transition(current, target, *, lowering=False):
    """Only own issued PWM history; return real sequential servo proposals."""
    return [({sid: pulse}, duration, REAL_COMMAND_WAIT_S)
            for sid, pulse, duration in servo_steps(current, target, lowering=lowering)]


class Runtime(Previous):
    def __init__(self, *args, carry_pose='off', **kwargs):
        if carry_pose not in ('off', OPTION):
            raise ValueError('unsupported carry_pose')
        if carry_pose != 'off' and kwargs.get('setdown_relook') != 'off':
            raise ValueError('real solo carry candidate requires setdown_relook=off')
        self.carry_pose = carry_pose
        super().__init__(*args, **kwargs)

    def set_state(self, state, now):
        if self.carry_pose != 'off' and state == 'carry' and self.state == 'lift':
            for p, duration, settle in transition(self.servo, CARRY):
                self.queue(p, now, duration=duration, settle=settle)
            return super().set_state('real_carry_transition', now)
        return super().set_state(state, now)

    def _control(self, now, idle):
        if (self.carry_pose == 'off' or self.state not in
                ('real_carry_transition', 'carry', 'real_carry_return')):
            return super()._control(now, idle)
        # Same execution/command guards as v106. DEV visual uncertainty remains
        # log-only; this command-state guard never asserts physical grasp.
        if self.terminal:
            return [{'kind': 'hold'}]
        if now-self.started_at >= old.CAP_S:
            return self.fail('LOCAL_TIMEOUT', now)
        if self.pose.provider.failure:
            return self.fail('POSE_PROVIDER_ERROR', now)
        if not idle:
            return [{'kind': 'hold'}]
        expected = (old.high.at_high(self.servo) if self.state == 'real_carry_return'
                    else at_carry(self.servo))
        if not self.beam_grasp_confirmed or not expected:
            return self.fail('LOADED_COMMAND_STATE_LOST', now)
        if self.state == 'real_carry_transition':
            self.event('real_delivery_carry_pose', now, commanded_servo=dict(self.servo),
                       physical_success=None, camera_calibration='unqualified; predict only')
            super().set_state('carry', now)
        elif self.state == 'real_carry_return':
            for p, duration, settle in old.high.lower_path():
                self.queue({**p, 1: 1500}, now, duration=duration, settle=settle)
            super().set_state('lower', now)
        else:
            commands, arrived = self.drive(self.route[self.route_i], now)
            if arrived:
                self.event('carry_checkpoint', now, index=self.route_i,
                           last_fix_t=self.last_report.last_fix_t)
                self.skipped_relooks.append(self.route_i)
                self.event('cyan_setdown_relook_disabled', now, index=self.route_i,
                           last_fix_t=self.last_report.last_fix_t, physical_success=None)
                self.route_i += 1
                if self.route_i == len(self.route):
                    # Return to the existing descent entry, never open in transit.
                    for p, duration, settle in transition(
                            self.servo, {1: 1500, **old.high.HIGH}, lowering=True):
                        self.queue(p, now, duration=duration, settle=settle)
                    super().set_state('real_carry_return', now)
                else:
                    self.arm.until = now+old.high.HIGH_SETTLE_S
            return commands
        return [{'kind': 'hold'}]

    def record(self):
        out = super().record()
        if self.carry_pose != 'off':
            out['carry_pose'] = dict(option=OPTION, commanded_servo=copy.deepcopy(CARRY),
                scope='S2 solo DEV offline command candidate', runtime_admitted=False,
                loaded_camera='unqualified; provider predicts outside calibrated HIGH',
                loaded_motion='HIGH calibration transfer unqualified',
                visual_stall='existing HIGH-only monitor not qualified at real carry',
                approach='existing lift/check, real sequential carry transition, HIGH return/descent',
                physical_success=None)
        return out
