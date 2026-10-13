import numpy as np
import pytest
from harness.e2e_vo_innovation import select_increment


def record(**kw):
    return dict(command_delta=[.01, 0., .02], fused_delta=[.1, -.04, -.5], status='measured', nis=80., **kw)


def test_off_preserves_previous_replacement_and_copies():
    r=record();a,why=select_increment(r);assert np.array_equal(a,r['fused_delta']);a[0]=3
    assert r['fused_delta'][0]==.1 and why=='unchanged'


def test_rejects_innovation_instead_of_assuming_visual_is_correct():
    r=record();a,why=select_increment(r,option='nis_reject_v1')
    assert np.array_equal(a,r['command_delta']) and why=='rejected_visual_innovation'
    r['nis']=2.;assert np.array_equal(select_increment(r,option='nis_reject_v1')[0],r['fused_delta'])


def test_stationarity_must_be_observed_and_yaw_is_not_fabricated():
    r=record(gate={'stationary':True});a,why=select_increment(r,option='nis_stationary_v1')
    assert np.array_equal(a,[0.,0.,.02]) and why=='rgb_stationary_translation'
    r['gate']['stationary']=False
    assert np.array_equal(select_increment(r,option='nis_stationary_v1')[0],r['command_delta'])


def test_missing_visual_measurement_is_not_zero_motion():
    r=record();r.update(status='unknown_texture',fused_delta=r['command_delta']);r.pop('nis')
    assert np.array_equal(select_increment(r,option='nis_stationary_v1')[0],r['command_delta'])


def test_invalid_inputs_fail_explicitly():
    with pytest.raises(ValueError):select_increment(record(),option='invented')
    r=record();r['nis']=float('nan')
    with pytest.raises(ValueError):select_increment(r,option='nis_reject_v1')


def test_static_localizer_off_needs_no_map_or_state():
    from harness.e2e_static_rgb_localizer import create
    assert create(None) is None
    with pytest.raises(ValueError):create(None,option='truth_initial_pose')
