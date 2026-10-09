"""Consumer-boundary regressions for shared observation consistency."""
import copy
import functools
import json
from types import SimpleNamespace

import numpy as np
import pytest

from harness import pf_observation_consistency as c


def test_off_does_not_touch_consumers_or_arrays():
    invalid_consumer = object()
    score = np.array([-2., -8.])
    profiles = {'not_a_profile': object()}
    assert c.attach_s3(invalid_consumer) is invalid_consumer
    assert c.attach_ownmap(invalid_consumer) is invalid_consumer
    assert c.log_score(score, None) is score
    assert c.alpha_profiles(profiles) is profiles


def test_s3_actual_factory_binds_measurement_and_same_pulse_dictionary():
    from harness.zone_s3_sweep_contract import inputs, ROOT, hp
    from harness.zone_s3_sweep_contract import bundle
    from harness.zone_s3_consistent_runtime import Runtime
    b = bundle('0'*40)
    b['controller_config']['options']['observation_consistency'] = 'effective_sqrt_alpha_v1'
    rt = Runtime(hp.resolve(b['map_id'])[0], inputs()[2]['orders'], ROOT/b['calibration'],
        b['calibration_sha256'], seed=b['seed'], config=b['controller_config'])
    try:
        from harness.zone_solo_cyan_landmarks import Measurement
        for own in rt.localizers.values():
            pf = own.pose.provider.loc._pf
            selected = c._closure(pf.update_obs, 'selected').cell_contents
            score = selected.__globals__['likelihood']
            # Empty evidence remains exactly neutral, without fake precision.
            value = score(None, pf.px, Measurement(np.empty((0, 2)), []))
            assert np.array_equal(value, np.ones(pf.n))
            profiles = own.pulse_profiles
            pending = [pf.command]; found = False; seen = set()
            while pending:
                function = pending.pop()
                if id(function) in seen: continue
                seen.add(id(function))
                for cell in getattr(function, '__closure__', ()) or ():
                    value = cell.cell_contents
                    found |= value is profiles
                    if callable(value): pending.append(value)
            assert found, 'command predictor must consume the modified profile table'
            assert profiles is own.pulse_profiles
            assert own.observation_consistency_audit['scores'] == 1
            assert own.pulse_profiles['0:forward:0.35:0.10']['prediction_variance'][2] > 1e-6
    finally:
        rt.close()


def likelihood(field, points, poses, sigma, effective_points=12.):
    return np.full(len(np.atleast_2d(poses)), -len(points), float)


def proposal(field, points, camera, prior, covariance, rng, options, *, yaw_window_deg):
    # The real proposal uses the same function at all three boundaries.
    return tuple(likelihood(field, points, prior, 1.) for _ in range(3))


def test_ownmap_private_proposal_and_calibration_are_isolated():
    from harness.zone_s2_realism_contract_v122 import PULSE_MODEL
    from pathlib import Path
    profiles = json.loads(Path(PULSE_MODEL).read_text())['profiles']
    base = copy.deepcopy(profiles)
    original = functools.partial(proposal, yaw_window_deg=20.)
    grid = SimpleNamespace(_selective_proposal=original,
        odom=SimpleNamespace(driver=SimpleNamespace(profiles=profiles)))
    c.attach_ownmap(grid, observation_consistency='effective_sqrt_alpha_v1')
    args = (None, np.zeros((48, 2)), None, np.zeros((1, 3)), None, None, None)
    before, after = original(*args), grid._selective_proposal(*args)
    assert all(np.array_equal(x, [-48.]) for x in before)
    assert all(np.allclose(x, [-48/np.sqrt(12)]) for x in after)
    assert profiles == base
    assert grid.odom.driver.profiles is not profiles
    for key, p in grid.odom.driver.profiles.items():
        assert p['mean_curve'] == base[key]['mean_curve']
        assert p['mean_delta'] == base[key]['mean_delta']
        assert np.all(np.asarray(p['prediction_variance']) >= base[key]['prediction_variance'])
