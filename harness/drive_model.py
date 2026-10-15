"""Fixed v7 own-command model; no measured state or simulator imports.

DC steady state: |omega| = max(0, T0*(|u|-bk)-tau_c)/(B+b1) while latched.
The input relay and B=(T0-Tk)/omega0 come from masterpi_drive_friction_v7.
Rolling contact loss tau_c=1.857e-3 Nm and b1=2.86e-5 Nm s are fitted to
v7-results.json rows v7-empty-forward-u035/050/100 in the drive-friction
experiment (2026-10-06). They are simulator calibration, not hardware data.
An exact first-order ODE integrates pulses, coast, stops and reversals from
own commands only. Inertia is an XML/mass estimate, not measured wheel state.
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
    rolling_torque_nm: float = 1.857e-3
    contact_damping_nm_s: float = 2.86e-5
    # m*r^2/4 + hub spin inertia + armature + carried roller estimate;
    # saved 1.1 kg v3 XML gives 3.8586e-4 kg m^2 (rounded, see README).
    effective_inertia_kg_m2: float = 3.85e-4

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

    @property
    def total_damping_nm_s(self):
        return self.damping_nm_s + self.contact_damping_nm_s


DEFAULT_PARAMETERS = DriveParameters()


def _source_torque(command, previous_direction, parameters):
    command = float(command)
    if not math.isfinite(command) or abs(command) > 1 or previous_direction not in (-1, 0, 1):
        raise ValueError('finite normalized command and signed relay state required')
    sign = (command > 0) - (command < 0)
    same = previous_direction != 0 and sign == previous_direction
    on = abs(command) > parameters.start_fraction or (same and abs(command) > parameters.kinetic_fraction)
    effective = command - sign*parameters.kinetic_fraction if on else 0.
    return parameters.torque_cap_nm*effective, sign if on else 0


def wheel_speed(command, previous_direction=0, *, parameters=DEFAULT_PARAMETERS):
    """Steady rad/s after rolling loss, and the v7 input-relay direction.

    Start/reverse strictly above .325; hold above bk=1/12. Contact can stop
    a weak latched command without changing this command-only relay state.
    """
    torque, direction = _source_torque(command, previous_direction, parameters)
    speed = max(0., abs(torque)-parameters.rolling_torque_nm) / parameters.total_damping_nm_s
    return direction*speed, direction


def _advance(omega, torque, seconds, parameters):
    """Exact integral of I*w' = torque-C*w-tau_c*sign(w), sticking at zero.

    Constant torque can cross zero at most once. Split there so Coulomb
    friction always opposes motion; zero torque never causes a reversal.
    """
    c, loss = parameters.total_damping_nm_s, parameters.rolling_torque_nm
    time_constant = parameters.effective_inertia_kg_m2 / c
    angle = 0.
    for _ in range(2):
        if seconds <= 0:
            break
        if omega == 0 and abs(torque) <= loss:
            break
        sign = math.copysign(1., omega if omega else torque)
        target = (torque-sign*loss) / c
        opposing = loss-sign*torque
        stop = (time_constant*math.log1p(c*abs(omega)/opposing)
                if omega and opposing > 0 else math.inf)
        elapsed = min(seconds, stop)
        decay = -math.expm1(-elapsed/time_constant)
        angle += omega*elapsed + (target-omega)*(elapsed-time_constant*decay)
        omega += (target-omega)*decay
        seconds -= elapsed
        if elapsed == stop:
            omega = 0.
        else:
            break
    return angle, omega


class CommandDriveModel:
    """One instance per robot; reset when starting an episode.

    Calls describe consecutive command intervals. durations_s gives each
    wheel's remaining on-time at the start; a shorter pulse resets its relay
    during the remaining interval. Equal duration/dt means no observed gap.
    Pass a zero command for gaps: command-predicted coast is integrated until
    Coulomb stop. No measured velocity, load or external pushing is inferred.
    """
    def __init__(self, parameters=DEFAULT_PARAMETERS):
        self.parameters = parameters
        self.reset()

    def reset(self):
        self.directions = (0, 0, 0, 0)
        self.angular_speeds = (0., 0., 0., 0.)

    def delta(self, wheels, durations_s, dt):
        if len(wheels) != 4 or len(durations_s) != 4:
            raise ValueError('four wheel commands and durations required')
        if not math.isfinite(dt) or dt < 0 or any(not math.isfinite(d) or d < 0 for d in durations_s):
            raise ValueError('finite nonnegative interval and durations required')
        sources = [_source_torque(w, state, self.parameters)
                  for w, state in zip(wheels, self.directions)]
        if dt == 0:
            return 0., 0., 0.
        angles, speeds = [], []
        for omega, (torque, _), duration in zip(self.angular_speeds, sources, durations_s):
            active = min(dt, duration)
            angle, omega = _advance(omega, torque, active, self.parameters)
            coast, omega = _advance(omega, 0., dt-active, self.parameters)
            angles.append(angle+coast)
            speeds.append(omega)
        self.directions = tuple(state if d >= dt else 0 for (_, state), d in zip(sources, durations_s))
        self.angular_speeds = tuple(speeds)
        a, b, c, d = angles
        r, length = self.parameters.wheel_radius_m, self.parameters.lx_plus_ly_m
        return r*(a+b+c+d)/4, r*(-a+b+c-d)/4, r*(-a+b-c+d)/(4*length)
