import numpy as np
import pytest

from scripts.diagnose_grasp_act_act15 import command_errors, distribution


def test_decode_boundary_is_visible_in_error_metrics():
    target = np.array([.35]*4+[2/3]*4+[0.]*5+[0.])
    prediction = target.copy(); prediction[:4] = .15
    errors = command_errors(prediction, target)
    assert errors['wheel_sign_mismatch'] == 1.
    assert errors['wheel_mae'] == .35
    assert errors['pulse_mae_ms'] == pytest.approx(100.)
    assert errors['pwm_mae'] == 0.
    assert distribution([errors])['wheel_mae']['p95'] == .35
