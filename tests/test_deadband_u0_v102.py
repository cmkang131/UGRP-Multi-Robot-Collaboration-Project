"""v102 affine dead zone ``deadband.u0`` for the loaded pair plant (simulator-free).

The measured loaded steady speed is affine in the command above a small dead zone, v = g*sign(u)*max(|u| - u0, 0)
(experiments/2026-10-05-loaded-gain-calibration-v102). The shared static map ``deadband_effective`` is used by the PF
predictor, the partner operand and (inverted) by ``motor_command``. Without ``u0`` every earlier calibration keeps its
exact prediction, bit for bit.
"""
import copy
import math

import numpy as np
import pytest

from harness import zone_final_pair_skill as skill
from harness.zone_pair_deadband import effective as deadband_effective
from harness.vision_pose_source_pair_v3 import pair_motion_module
from tests.test_zone_pair_v6e import V6

RAMP = {'c0': [0., 0., 0.], 'u1': [0.026556708949971457, 0.028235672526345113, 0.031909184676893604]}
AFFINE = {'c0': [0., 0., 0.], 'u1': [1e-6, 1e-6, 0.031909184676893604], 'u0': [0.0056, 0.0072, 0.]}
GAIN = [[1.57, 0., 0.], [0., 1.175, 0.], [0., 0., 0.9073]]
TAU = [0.97, 0.97, 0.6555]


def old_ramp(u, db):
    """The pre-v102 expression, copied verbatim (bit-for-bit reference)."""
    u = np.asarray(u, float)
    c0, u1 = np.asarray(db['c0'], float), np.asarray(db['u1'], float)
    return u*np.where(u1 > c0, np.clip((np.abs(u) - c0)/np.maximum(u1 - c0, 1e-9), 0., 1.), 1.)


def test_without_u0_the_static_map_is_bit_identical_to_the_old_ramp():
    rng = np.random.default_rng(3)
    for _ in range(300):
        u = rng.normal(size=3)*rng.choice([.001, .02, .08, .15])
        assert np.array_equal(deadband_effective(u, RAMP), old_ramp(u, RAMP))
        db = {**RAMP, 'u0': [0., 0., 0.]}                              # u0 == 0 is also exactly the identity
        assert np.array_equal(deadband_effective(u, db), old_ramp(u, RAMP))
    assert np.array_equal(deadband_effective(np.zeros(3), RAMP), np.zeros(3))


def test_affine_dead_zone_subtracts_u0_symmetrically_and_leaves_the_turn_axis_alone():
    u = np.array([.05, -.0622, .1])
    eff = deadband_effective(u, AFFINE)
    assert eff[0] == pytest.approx(.05 - .0056, abs=2e-6) and eff[1] == pytest.approx(-(.0622 - .0072), abs=2e-6)
    assert eff[2] == old_ramp(u, RAMP)[2]                                            # u0 = 0 on the turn axis
    assert np.all(deadband_effective(np.array([.005, -.007, 0.]), AFFINE) == 0.)       # inside the dead zone: no motion
    assert np.array_equal(deadband_effective(-u, AFFINE), -deadband_effective(u, AFFINE))


@pytest.mark.parametrize('profile_db', [RAMP, AFFINE])
def test_motor_command_inverts_the_forward_static_map(profile_db):
    profile = {'gain': GAIN, 'deadband': copy.deepcopy(profile_db)}
    assert np.array_equal(skill.motor_command(profile, np.zeros(3)), np.zeros(3))
    for speed in np.linspace(.004, .09, 15):
        for sign in (-1., 1.):
            v = np.array([sign*speed, -sign*speed*.7, sign*speed*.5])
            u = skill.motor_command(profile, v)
            assert np.all(np.isfinite(u))
            reached = np.asarray(GAIN) @ deadband_effective(u, profile['deadband'])
            np.testing.assert_allclose(reached, v, atol=1e-6)
    if 'u0' in profile_db:      # at the carry speed the command is the dead zone plus v/g: 0.06/1.175 + 0.0072
        assert skill.motor_command(profile, np.array([0., .06, 0.]))[1] == pytest.approx(.06/1.175 + .0072, abs=2e-6)


def _pair_cloud(db, seed=7):
    """The registered pair PF subclass (``PairMotion``) with a fixed loaded particle cloud (no fix ever arrives)."""
    loc = pair_motion_module().OwnCamLocalizer(V6['map'], V6['params'], seed=seed)
    rng = np.random.default_rng(99)
    loc.px = np.stack([.6 + .03*rng.normal(size=loc.n), .03*rng.normal(size=loc.n), .05*rng.normal(size=loc.n)], 1)
    loc.scale = 1. + rng.normal(size=(loc.n, 3))*loc.params['motion']['scale_std']
    loc.logw = np.zeros(loc.n)
    loc.initialized = True
    loc.load.loaded = True
    loc.params = {**loc.params, 'motion_loaded': {**loc.params['motion_loaded'], 'gain': GAIN, 'tau_axis_s': TAU,
                                                  'tau_s': TAU[0], 'tau_stop_s': .085, 'deadband': copy.deepcopy(db)}}
    return loc


def _affine_cloud(command, db=AFFINE):
    loc = _pair_cloud(db)
    loc.predict_to(3.)
    loc.command({'t': 3., 'kind': 'mecanum', 'forward': 0., 'left': command, 'turn': 0., 'duration_s': 30.})
    return loc


def test_pf_predictor_steady_speed_follows_the_affine_map():
    for u in (.025, .0622):
        loc = _affine_cloud(u)
        loc.predict_to(33.)
        assert float(loc.vel[1]) == pytest.approx(1.175*(u - .0072), rel=1e-3)
    # a command inside the dead zone gives no motion and the shared stop lag, not the drive lag
    loc = _affine_cloud(.006)
    loc.predict_to(13.)
    assert abs(float(loc.vel[1])) < 1e-12
    assert float(loc.cmd[1]) == .006                      # the issued command is restored after the loaded prediction


def test_pf_predictor_without_u0_is_the_unchanged_ramp_prediction():
    plain, ramp_only = _affine_cloud(.0622, RAMP), _affine_cloud(.0622, {**RAMP, 'u0': [0., 0., 0.]})
    for loc in (plain, ramp_only):
        loc.predict_to(20.)
    assert np.array_equal(plain.px, ramp_only.px) and np.array_equal(plain.vel, ramp_only.vel)
    assert float(plain.vel[1]) == pytest.approx(1.175*.0622*min(1., .0622/RAMP['u1'][1]), rel=1e-3)


def test_dev_validator_accepts_u0_and_rejects_malformed_values(tmp_path, monkeypatch):
    from tests.test_highpose_dev_pilot import MAPS, admit, dev_file
    from harness import zone_pair_highpose_contract as c

    def ok(cal):
        cal['params']['motion_loaded']['deadband'].update(u0=[.0056, .0072, 0.], u1=[1e-6, 1e-6, .0319])
    path, _ = dev_file(tmp_path, mutate=ok)
    admit(monkeypatch, c.base.sha(path))
    cal = c.dev_pilot_calibration(path, c.base.sha(path), MAPS[0])
    assert cal['params']['motion_loaded']['deadband']['u0'] == [.0056, .0072, 0.]
    for i, bad in enumerate(([.0056, .0072], [-.001, 0., 0.], ['a', 0., 0.], 'x')):
        def mutate(cal, bad=bad):
            ok(cal)
            cal['params']['motion_loaded']['deadband']['u0'] = bad
        folder = tmp_path/f'bad{i}'
        folder.mkdir()
        path, _ = dev_file(folder, mutate=mutate)
        admit(monkeypatch, c.base.sha(path))
        with pytest.raises(ValueError):
            c.dev_pilot_calibration(path, c.base.sha(path), MAPS[0])
