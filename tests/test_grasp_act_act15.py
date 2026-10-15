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


def test_initial_coverage_does_not_admit_exogenous_actions(tmp_path):
    from tests.test_grasp_act_data import episode
    from harness.grasp_act_data import paired_segments
    _, obs, labels = episode(tmp_path, 1)
    obs, labels = obs[:4], labels[:4]
    for i, label in enumerate(labels):
        label.update(local_skill_sample=i==3, teacher_phase=('start','fold','approach','align')[i])
    assert sum(map(len, paired_segments(obs,labels))) == 1
    groups=paired_segments(obs,labels,include_initial_approach_v1=True)
    assert sum(map(len, groups)) == 4
    assert labels[0]['local_skill_sample'] is False
    labels[1].update(perturbation_interval=True)
    groups=paired_segments(obs,labels,include_initial_approach_v1=True)
    assert sum(map(len, groups)) == 3
    assert [len(g) for g in groups] == [1,2]
