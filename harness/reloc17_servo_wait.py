"""Own-command servo completion scheduling; no measured actuator input.

CameraRobotPort._advance_servos uses 2000 PWM/s. A routine wheel hold cancels
that interpolation, while the mapper retains the requested final PWM. Keep the
existing servo trajectory running by issuing an existing zero-wheel primitive
only until its command-derived deadline. Terminal holds still cancel everything.
See reloc17 investigation-complete.md and the ROS2 joint-trajectory preemption
reference: trajectory cancellation and an independent base stop are distinct.
"""
RATE_PWM_PER_S = 2000.0  # existing CameraRobotPort schedule, not a fitted limit


class ServoWait:
    def __init__(self):
        self.until = -float('inf')

    def issued(self, row, previous_servo):
        if row['kind'] == 'look':
            servo, target = 6, row['pan_pulse']
        elif row['kind'] == 'arm':
            servo, target = row['servo_id'], row['pulse']
        else:
            return
        # Normal waits cannot revoke an in-flight trajectory in this profile;
        # the previous requested PWM is therefore complete before the next pan.
        start = previous_servo.get(servo, target)
        self.until = max(self.until, row['t'] + abs(target-start)/RATE_PWM_PER_S)

    def command(self, command, *, t, terminal):
        if (command is None or command['kind'] != 'hold' or terminal or
                t >= self.until-1e-8):
            return command
        # Existing native .1s primitive; zero wheels stop the base without
        # revoking camera/arm interpolation. No state/GT/servo feedback read.
        return dict(t=float(t), kind='mecanum', forward=0., left=0., turn=0., duration_s=.1)
