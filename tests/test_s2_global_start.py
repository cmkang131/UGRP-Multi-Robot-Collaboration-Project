import copy
import json
from types import SimpleNamespace as NS

import numpy as np
import pytest

from test_solo_cyan_v106 import static, cal, FakePose, FakeVision
from harness import zone_solo_cyan_global_start as m


def test_default_off_commands_and_records_are_byte_equal(static, cal):
    runs = [cls(static, None, None,
        provider_factory=lambda *a, **k: FakePose(copy.deepcopy(cal)),
        vision_factory=FakeVision, **kw) for cls, kw in
        [(m.Previous, {}), (m.Runtime, {}), (m.Runtime, {'start_localization': 'off'})]]
    try:
        for r in runs:
            r.initial_commands(0., {'r3': {1: 2000, 3: 600, 4: 2200, 5: 1400, 6: 1500}})
        assert len({json.dumps(r.record()).encode() for r in runs}) == 1
    finally:
        for r in runs:
            r.close()


def test_separated_dock_modes_are_not_averaged_into_empty_middle():
    p = np.array([[0., -2.25, 0.]]*7 + [[0., .55, 0.]]*3)
    labels = m.cluster_labels(p)
    mean, cov, d = m.maximum_mode(p, np.full(10, .1), labels)
    assert mean[1] == pytest.approx(-2.25)
    assert d == {'cluster_count': 2, 'maximum_cluster_weight': pytest.approx(.7)}
    assert not m.converged(p)
    assert cov[2, 2] == pytest.approx(-2*np.log(.7))
    # Nav2 source uses exact integer yaw keys (wrap TODO still inactive).
    edge = np.array([[0., 0., -np.pi+.01], [0., 0., np.pi-.01]])
    assert len(set(m.cluster_labels(edge))) == 2


def test_uniform_uses_only_static_free_space_and_rejects_late_reset():
    def sample(n):
        rng = np.random.default_rng(3)
        return np.c_[rng.uniform(-1, 5, n), rng.uniform(-3, 1, n), rng.uniform(-np.pi, np.pi, n)]
    pf = NS(t=0., n=2000, _uniform_free=sample, initialized=False,
        stats={'resamples': 0}, estimate=lambda: dict(std_xy_m=3., yaw=0.),
        _weights=lambda: np.full(2000, .0005))
    audit = m.initialize(pf)
    assert np.array_equal(pf.px, sample(2000)) and np.array_equal(pf.logw, np.zeros(2000))
    assert audit['known_own_dock'] is False and audit['gt_inputs'] is False
    assert pf.estimate()['global_modes']['all_particles_converged'] is False
    pf.t = 1.
    with pytest.raises(ValueError):
        m.initialize(pf)


def test_bounded_active_spin_is_own_command_only_and_uncertainty_logs():
    r = object.__new__(m.Runtime)
    r.start_localization = m.OPTION; r.global_done = False
    r.global_started = r.global_sector_t = 0.; r.global_sector = 0
    r.global_angle = 0.; r.global_wait_until = 0.; r.state = 'global_start_spin'
    r.failure = None; r.last_report = NS(x_m=0., y_m=0., yaw_rad=0., std_xy_m=1., std_yaw_rad=1., initialized=True)
    pf = NS(last_scan_t=1., px=np.array([[0., 0., 0.], [2., 2., 0.]]))
    r.pose = NS(provider=NS(failure=None, loc=NS(_pf=pf)))
    r.servo = {}; r.guard = NS(_clear=lambda *a: False)
    r.pulse_profiles = {m.PARAMS['turn_profile']: dict(axis='turn', u=.35, duration_s=.1,
        times=[0., .3], mean_delta=[0., 0., .09])}
    r.global_start = dict(rows=[]); stops=[]
    r.soft = lambda code, now: stops.append(code)
    r.set_state = lambda state, now: setattr(r, 'state', state)
    rows = r._control(1., True)
    assert rows == [dict(kind='mecanum', forward=0., left=0., turn=.35, duration_s=.1)]
    assert stops == ['GLOBAL_START_COLLISION_GUARD']
    assert r._control(1.1, True) == [dict(kind='hold')]
    assert r._control(121., True) == [dict(kind='hold')]
    assert r.global_done and r.state == 'search_move' and stops[-1] == 'GLOBAL_START_UNRESOLVED'


def test_registered_parameters_and_validation(static):
    from pathlib import Path
    c = json.loads(Path('experiments/2026-10-06-s2-realism/dock-global-criteria.json').read_text())
    assert c['parameters'] == m.PARAMS
    for kw in [dict(start_localization='bad'), dict(start_localization=m.OPTION)]:
        with pytest.raises(ValueError):
            m.Runtime(static, None, None, **kw)
