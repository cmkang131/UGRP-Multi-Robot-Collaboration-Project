import copy
import json
from types import SimpleNamespace as NS

import numpy as np
import pytest

from harness import zone_solo_cyan_rotation_left as rot
from harness.zone_solo_cyan_pulse_cal import install, action_of


def model():
    return json.loads((rot.ROOT/'configs/s2_motion_v7_pulse_cal_v1.json').read_text())


def fake_runtime(servo, loaded):
    pf = NS(t=0., initialized=True, n=3, px=np.zeros((3, 3)), logw=np.zeros(3),
            load=NS(loaded=loaded), rng=NS(normal=lambda size: np.zeros(size)),
            _map_logprior=lambda px: np.zeros(len(px)))
    pf.command = lambda row: pf.predict_to(row['t'])
    m = model(); live = install(pf, m)
    inner = NS(servo=copy.deepcopy(servo), loc=NS(_pf=pf), runtime_contract={})
    r = NS(pulse_model=m, pulse_profiles=copy.deepcopy(m['profiles']),
           flow=NS(profiles=live), pose=NS(provider=inner), slip_detection='slip_detect_v1')
    r.drive = lambda: copy.deepcopy(r.pulse_profiles[rot.calibration()['profile']])
    r.record = lambda: dict(unchanged=True)
    return r, pf


def test_off_is_exact_noop_and_invalid_options_fail():
    sentinel = object()
    assert rot.attach(sentinel) is sentinel
    with pytest.raises(ValueError, match='UNKNOWN'):
        rot.attach(sentinel, rotation_calibration='bad')
    with pytest.raises(ValueError, match='STIFF'):
        rot.attach(sentinel, rotation_calibration=rot.OPTION)


def test_port_changes_only_original_left_yaw_mean():
    m = model(); before = copy.deepcopy(m); cal = rot.calibration()
    p = m['profiles'][cal['profile']]; q = rot.corrected_profile(m)
    assert m == before
    assert q['mean_delta'][:2] == p['mean_delta'][:2]
    np.testing.assert_array_equal(np.array(q['mean_curve'])[:, :2], np.array(p['mean_curve'])[:, :2])
    np.testing.assert_array_equal(np.array(q['mean_curve'])[:, 2], np.array(p['mean_curve'])[:, 2]*cal['gain'])
    assert q['mean_delta'][2] == p['mean_delta'][2]*cal['gain']
    assert all(q[k] == p[k] for k in p if k not in ('mean_curve', 'mean_delta'))


@pytest.mark.parametrize('loaded,servo,turn,expected', [
    (False, rot.SEARCH, .35, True), (False, rot.SEARCH, -.35, False),
    (True, {1:1500,3:1050,4:2035,5:1894,6:1500}, .35, False),
    (False, {**rot.SEARCH,3:1050}, .35, False),
    (False, {**rot.SEARCH,6:1230}, .35, False),
])
def test_pf_and_planner_share_scope_and_stopping_tail(loaded, servo, turn, expected):
    a, pa = fake_runtime(servo, loaded); b, pb = fake_runtime(servo, loaded)
    rot.attach(b, rotation_calibration=rot.OPTION, servo_stiffness='real_v1')
    key = f'{int(loaded)}:turn:{turn:.2f}:0.10'
    p = a.pulse_model['profiles'][key]; cmd = dict(t=0., **action_of(p))
    before = json.dumps(b.flow.profiles)
    for pf in (pa, pb):
        pf.command(cmd); pf.predict_to(.1)
        pf.command(dict(t=.1, kind='hold')); pf.predict_to(p['times'][-1])
    assert json.dumps(b.flow.profiles) == before
    if expected:
        chosen = b.drive()
        np.testing.assert_allclose(pb.px, np.tile(chosen['mean_delta'], (3, 1)), atol=1e-12)
        assert len(b.rotation_left_audit['rows']) == 1
    else:
        assert pa.px.tobytes() == pb.px.tobytes()
        assert b.rotation_left_audit['rows'] == []
    assert b.pulse_profiles == a.pulse_profiles
