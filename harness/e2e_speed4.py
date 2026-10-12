"""Default-off DEV compute budgets; own RGB/commands only, new cohorts only.

Unlike exact-speed options these change the observations/particle approximation.
No physics timestep, audit hash, communication policy or acceptance gate changes.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass

import numpy as np


@dataclass(frozen=True)
class Options:
    render_half: bool = False
    rbpf_particles: int = 0  # 0 = unchanged constructor default (100)
    floor_ray_stride: int = 1
    moving_observation_stride: int = 1
    vector_envelopes: bool = False

    def __post_init__(self):
        for key in ('render_half', 'vector_envelopes'):
            if type(getattr(self, key)) is not bool:
                raise ValueError('SPEED4_BOOLEAN_REQUIRED:'+key)
        for key, choices in (('rbpf_particles', (0, 30, 50)),
                             ('floor_ray_stride', (1, 2, 4)),
                             ('moving_observation_stride', (1, 2))):
            if type(getattr(self, key)) is not int or getattr(self, key) not in choices:
                raise ValueError('INVALID_SPEED4_OPTION:'+key)

    @property
    def enabled(self):
        return self != OFF


OFF = Options()
_ACTIVE = ContextVar('e2e_speed4', default=OFF)


def current():
    return _ACTIVE.get()


@contextmanager
def using(options):
    token = _ACTIVE.set(options)
    try:
        yield
    finally:
        _ACTIVE.reset(token)


def record(options):
    return dict(options=asdict(options), inherited_results=False,
                sensor_raster=[320, 240] if options.render_half else [640, 480],
                controller_raster=[640, 480],
                camera_pose_fov='unchanged; scaled K then linear resize for fixed calibration',
                floor_rays='subsample observed free rays only; every wall endpoint retained',
                moving_observation='mapping translation only; hold/turn/transport remain 5 Hz')


def processing_due(robot, now, phase):
    """Keep issuing finite 0.2 s commands, skip at most one translation receive.

    Stop and turn observations always run. No command duration is extended, and
    this function does not inspect actual displacement or evaluation state.
    """
    opt = getattr(robot, 'speed4', OFF)
    if opt.moving_observation_stride == 1 or phase != 'mapping' or robot.last_obs is None:
        return True
    cmd = robot.nav_command
    translating = (cmd.get('kind') in ('mecanum', 'drive') and
                   abs(float(cmd.get('turn', 0))) < 1e-12 and
                   any(abs(float(cmd.get(k, 0))) > 0 for k in ('forward', 'left')))
    if not translating or robot.packet is not None:
        return True
    # A newly issued look/arm command requires a fresh frame at the next tick.
    if getattr(robot, '_speed4_servo_changed', False):
        robot._speed4_servo_changed = False
        return True
    return now - float(robot.last_obs['sim_time']) >= .2 * opt.moving_observation_stride - 1e-8


def envelope_samples(optical):
    """Vectorized box chords and near-plane intersections, same sample set."""
    i, j = np.tril_indices(len(optical), -1)
    a, b = optical[i], optical[j]
    f = np.array([.25, .5, .75])[None, :, None]
    chords = (a[:, None]*(1-f) + b[:, None]*f).reshape(-1, 3)
    cross = (a[:, 2]-.001)*(b[:, 2]-.001) < 0
    a, b = a[cross], b[cross]
    near = a + ((.001-a[:, 2])/(b[:, 2]-a[:, 2]))[:, None]*(b-a)
    return np.concatenate((optical[optical[:, 2] >= .001], chords[chords[:, 2] >= .001], near))
