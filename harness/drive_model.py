"""Fixed v7 own-command model; no measured state or simulator imports.

DC steady state: omega = T0 * effective_command / B. The input relay and
B=(T0-Tk)/omega0 are taken from masterpi_drive_friction_v7, not fitted to
body GT. Unexplained additional damping is deliberately NOT charged here.
This predicts free motion, not contact, external pushing, or pulse transients.
See experiments/2026-10-15-drive-model-deadband/README.md for provenance.
"""
from dataclasses import dataclass
import math


NAME = 'drive_model_deadband_v1'


def validate_options(enabled=False, *, search17_odometry='off', profile='off'):
    if type(enabled) is not bool:
        raise ValueError('drive_model_deadband_v1 must be a bool')
    if enabled and (search17_odometry != 'off' or profile != 'off'):
        raise ValueError('drive_model_deadband_v1 is mutually exclusive with fixed odometry corrections')


@dataclass(frozen=True)
class DriveParameters:
    wheel_radius_m: float = .0325
    # Static geometry in the recorded v3 scene (not a runtime pose).
    lx_plus_ly_m: float = .12435
    no_load_rpm: float = 150.
    torque_cap_nm: float = 1.2 * 9.80665 / 100
    no_load_current_a: float = .1
    stall_current_a: float = 1.2
    start_fraction: float = .325

    def __post_init__(self):
        if any(not math.isfinite(v) or v <= 0 for v in vars(self).values()):
            raise ValueError('fixed drive parameters must be finite and positive')
        if not 0 < self.kinetic_fraction < self.start_fraction < 1:
            raise ValueError('requires 0 < kinetic < start < 1')

    @property
    def kinetic_fraction(self):
        return self.no_load_current_a / self.stall_current_a

    @property
    def omega0(self):
        return self.no_load_rpm * 2 * math.pi / 60

    @property
    def damping_nm_s(self):
        return (self.torque_cap_nm - self.torque_cap_nm*self.kinetic_fraction) / self.omega0


DEFAULT_PARAMETERS = DriveParameters()


def wheel_speed(command, previous_direction=0, *, parameters=DEFAULT_PARAMETERS):
    """Return rad/s and input-relay direction using only command history.

    A stopped/reversing wheel starts strictly above .325. Same-direction
    commands stay latched strictly above bk=1/12, exactly as v7 command_step.
    """
    command = float(command)
    if not math.isfinite(command) or abs(command) > 1 or previous_direction not in (-1, 0, 1):
        raise ValueError('finite normalized command and signed relay state required')
    sign = (command > 0) - (command < 0)
    same = previous_direction != 0 and sign == previous_direction
    on = abs(command) > parameters.start_fraction or (same and abs(command) > parameters.kinetic_fraction)
    effective = command - sign*parameters.kinetic_fraction if on else 0.
    return parameters.torque_cap_nm*effective / parameters.damping_nm_s, sign if on else 0


class CommandDriveModel:
    """One instance per robot; reset when starting an episode.

    Calls describe consecutive command intervals. durations_s gives each
    wheel's remaining on-time at the start; a shorter pulse resets its relay
    during the remaining interval. Equal duration/dt means no observed gap.
    Pass a zero command for gaps. No coast or external motion is inferred.
    """
    def __init__(self, parameters=DEFAULT_PARAMETERS):
        self.parameters = parameters
        self.reset()

    def reset(self):
        self.directions = (0, 0, 0, 0)

    def delta(self, wheels, durations_s, dt):
        if len(wheels) != 4 or len(durations_s) != 4:
            raise ValueError('four wheel commands and durations required')
        if not math.isfinite(dt) or dt < 0 or any(not math.isfinite(d) or d < 0 for d in durations_s):
            raise ValueError('finite nonnegative interval and durations required')
        speeds = [wheel_speed(w, state, parameters=self.parameters)
                  for w, state in zip(wheels, self.directions)]
        if dt == 0:
            return 0., 0., 0.
        angles = [speed*min(dt, d) for (speed, _), d in zip(speeds, durations_s)]
        self.directions = tuple(state if d >= dt else 0 for (_, state), d in zip(speeds, durations_s))
        a, b, c, d = angles
        r, length = self.parameters.wheel_radius_m, self.parameters.lx_plus_ly_m
        return r*(a+b+c+d)/4, r*(-a+b+c-d)/4, r*(-a+b-c+d)/(4*length)
