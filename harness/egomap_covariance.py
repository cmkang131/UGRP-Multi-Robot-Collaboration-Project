"""Opt-in empirical covariance scale, selected using past own commands only.

Offline NEES calibrates fixed factors; no truth/error/NEES enters this module.
P_report = factor * P_raw is multiplicative inflation, not a pose correction.
The facade is read by route uncertainty/association and reported covariance;
RBPF particle propagation, pending process noise and RNG remain unchanged.
"""
import copy
import hashlib
import json
import math
from pathlib import Path

import numpy as np

OPTION = 'nees_stratified_v1'
ARTIFACT = Path(__file__).with_name('data') / 'egomap_covariance_v1.json'


def stratum(stage, previous_command):
    """Observable error-mechanism proxies, not ground-truth cause labels."""
    command = previous_command or {}
    turn = float(command.get('turn', 0.))
    if turn:
        motion = 'turn_left' if turn > 0 else 'turn_right'
    elif command.get('forward', 0.) or command.get('left', 0.):
        motion = 'translation'
    else:
        motion = 'hold'
    return ('return' if stage == 'return' else 'approach') + '/' + motion


def validate(calibration):
    if calibration.get('option') != OPTION:
        raise ValueError('UNKNOWN_COVARIANCE_CALIBRATION')
    if calibration.get('dof') != 2 or calibration.get('target') != 'xy':
        raise ValueError('XY_NEES_CALIBRATION_REQUIRED')
    for value in [calibration['pooled_factor'], *calibration['factors'].values()]:
        if not math.isfinite(float(value)) or float(value) < 1.:
            raise ValueError('FINITE_NONSHRINKING_FACTOR_REQUIRED')
    if set(calibration.get('fit_seeds', [])) & set(calibration.get('check_seeds', [])):
        raise ValueError('DISJOINT_SEED_SPLIT_REQUIRED')
    return calibration


def load():
    raw = ARTIFACT.read_bytes()
    return validate(json.loads(raw)), hashlib.sha256(raw).hexdigest()


def inflated(covariance, factor):
    """Scale the complete SPD matrix so cross-covariances remain consistent."""
    value = np.asarray(covariance, dtype=float)
    if value.shape != (3, 3) or not np.isfinite(value).all():
        raise ValueError('FINITE_POSE_COVARIANCE_REQUIRED')
    if not math.isfinite(factor) or factor < 1.:
        raise ValueError('FINITE_NONSHRINKING_FACTOR_REQUIRED')
    if not np.allclose(value, value.T, rtol=1e-9, atol=1e-12):
        raise ValueError('SYMMETRIC_COVARIANCE_REQUIRED')
    if np.linalg.eigvalsh(value).min() <= 0.:
        raise ValueError('POSITIVE_DEFINITE_COVARIANCE_REQUIRED')
    return factor * value


class CovarianceView:
    def __init__(self, base, calibration):
        self.base = base
        self.calibration = calibration
        self.key = 'approach/hold'
        self.factor = float(calibration['pooled_factor'])

    def __getattr__(self, name):
        base = self.__dict__.get('base')
        if base is None:
            raise AttributeError(name)
        return getattr(base, name)

    def select(self, stage, command):
        self.key = stratum(stage, command)
        self.factor = float(self.calibration['factors'].get(self.key, self.calibration['pooled_factor']))

    @property
    def covariance(self):
        return inflated(self.base.covariance, self.factor)


def install(controller, *, covariance_inflation='off', calibration=None):
    if covariance_inflation == 'off':
        return controller
    if covariance_inflation != OPTION:
        raise ValueError('UNKNOWN_COVARIANCE_INFLATION')
    if getattr(controller, '_covariance_inflation', None) is not None:
        raise ValueError('COVARIANCE_INFLATION_ALREADY_INSTALLED')
    values, digest = load() if calibration is None else (validate(calibration), 'test_fixture')
    g = controller.explorer.memory.self_map
    view = CovarianceView(g.odom, copy.deepcopy(values))
    g.odom = view
    original = controller.receive
    controller._covariance_inflation = dict(option=OPTION, sha256=digest)

    def receive(**kw):
        view.select(controller.stage, getattr(controller, 'last_command', None))
        command, trace = original(**kw)
        raw = np.asarray(view.base.covariance)
        trace['covariance_inflation'] = dict(option=OPTION, sha256=digest,
            stratum=view.key, factor=view.factor, covariance_raw=raw.tolist(),
            covariance=inflated(raw, view.factor).tolist(),
            selection_inputs='stage_before_frame_and_previous_issued_command',
            online_truth=False, modifies_particles=False)
        controller.last_trace = copy.deepcopy(trace)
        return command, trace

    controller.receive = receive
    return controller
