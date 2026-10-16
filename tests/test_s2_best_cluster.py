import copy
import json
import math
from types import SimpleNamespace as NS

import numpy as np
import pytest

from test_solo_cyan_v106 import static, cal, FakePose, FakeVision, rt
from harness import zone_solo_cyan_best_cluster as m
from harness.zone_solo_cyan_look_ahead import Runtime as Previous


def test_default_off_command_and_record_bytes(static, cal):
    Wrapped = m.runtime_class(Previous)
    runs = [cls(static, None, None,
        provider_factory=lambda *a, **k: FakePose(copy.deepcopy(cal)),
        vision_factory=FakeVision, **kw) for cls, kw in
        [(Previous, {}), (Wrapped, {}), (Wrapped, dict(pose_estimate='off'))]]
    try:
        for r in runs:
            r.initial_commands(0., {'r3': {1: 1500, **rt.high.HIGH}})
            r.last_report = r.pose.report(1.); r.state = 'lift'; r.receipt = True
        for t in (1., 1.05, 1.1, 1.2, 1.65, 1.8):
            commands = [r.step(t) for r in runs]
            assert len({json.dumps(q).encode() for q in commands}) == 1
            for r, rows in zip(runs, commands):
                for rid, a in rows: r.on_command(rid, t, a)
        assert len({json.dumps(r.record()).encode() for r in runs}) == 1
    finally:
        for r in runs: r.close()


def test_nav2_cluster_mean_but_overall_covariance_and_pan():
    p = np.array([[0., -2.25, 0.]]*7 + [[0., .55, 0.]]*3)
    out = m.extract(p, np.ones(10)/10, m.connected_labels(p), dict(pan_yaw_offset=.2))
    assert out['y'] == pytest.approx(-2.25)
    assert out['yaw'] == pytest.approx(.2)
    assert out['cov'][1][1] == pytest.approx(.7*.3*2.8**2)
    assert out['best_cluster']['cluster_count'] == 2
    assert out['best_cluster']['maximum_cluster_weight'] == pytest.approx(.7)
    assert out['best_cluster']['selected_cluster_cov'][2][2] == pytest.approx(-2*math.log(.7))
    assert out['std_yaw_rad'] == pytest.approx(0., abs=1e-6)


def test_low_weight_bridges_are_not_pruned_and_yaw_seam_is_not_joined():
    p = np.array([[0., y, 0.] for y in np.arange(0., 3.1, .5)])
    w = np.full(len(p), 1e-9); w[0] = .6; w[-1] = .4; w /= w.sum()
    assert len(set(m.connected_labels(p))) == 1
    out = m.extract(p, w, m.connected_labels(p), {})
    assert out['y'] == pytest.approx(w@p[:, 1])
    edge = np.array([[0., 0., -np.pi+.01], [0., 0., np.pi-.01]])
    assert len(set(m.connected_labels(edge))) == 2


def test_vectorized_partition_matches_nav2_neighbor_reference():
    rng = np.random.default_rng(3)
    for n in (3, 90, 2000):
        p = rng.uniform([-2, -3, -np.pi], [5, 1, np.pi], (n, 3))
        np.testing.assert_array_equal(m.connected_labels(p), m.cluster_labels(p))


def test_exact_tie_uses_reverse_kdtree_leaf_allocation():
    for y in ((0., 3.), (3., 0.)):
        p = np.array([[0., v, 0.] for v in y])
        out = m.extract(p, np.array([.5, .5]), m.connected_labels(p), {})
        assert out['y'] == 3.  # Upper split child allocated last in either order.


def test_report_boundary_survives_handoff_and_in_place_prediction():
    p = np.array([[0., 0., 0.], [0., 3., 0.]])
    pf = NS(px=p, t=0., diag={}, _weights=lambda: np.array([.7, .3]))
    pf.estimate = lambda: dict(initialized=True, x=0., y=.9)
    loc = NS(_pf=pf, estimate=lambda: pf.estimate())
    inner = NS(loc=loc, runtime_contract={})
    source = NS(provider=inner)
    before = p.tobytes(); audit = m.install(source)
    assert loc.estimate()['y'] == 0.
    assert p.tobytes() == before
    pf.estimate = lambda: dict(initialized=True, x=0., y=99.)  # global handoff
    assert loc.estimate()['y'] == 0.
    p[0, 1] = 2.6  # Prediction within same resample count/time: now connected.
    assert loc.estimate()['y'] == pytest.approx(.7*2.6+.3*3.)
    assert audit['rows'][-1]['cluster_count'] == 1
    pf.estimate = lambda: dict(initialized=False, failure='sensor error')
    assert loc.estimate() == dict(initialized=False, failure='sensor error')


def test_low_maximum_mass_records_uncertainty_without_stopping():
    p = np.array([[0., y, 0.] for y in (0., 2., 4.)])
    out = m.extract(p, np.array([.4, .35, .25]), m.connected_labels(p), {})
    class Base:
        def on_frames(self, now, frames):
            self.last_report = NS(observation_quality={'diagnostics': {'pose_estimate': out['best_cluster']}})
        def soft(self, code, now): self.logs.append((code, now))
    Runtime = m.runtime_class(Base)
    r = object.__new__(Runtime); r.pose_estimate = m.OPTION; r.logs = []
    r.on_frames(3., {})
    assert r.logs == [('POSE_CLUSTER_UNCERTAIN', 3.)]


def test_invalid_option_rejected_before_provider(static):
    with pytest.raises(ValueError, match='unknown pose_estimate'):
        m.runtime_class(Previous)(static, None, None, pose_estimate='bad')


def test_control_pose_report_uses_selected_cluster(static):
    from harness import zone_solo_cyan_contract_v106 as c
    from harness.zone_own_guards import OwnPose
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    r = m.runtime_class(Previous)(static, root/c.CALIBRATION, c.CALIBRATION_SHA, pose_estimate=m.OPTION)
    try:
        pf = r.pose.provider.loc._pf
        pf.px[:1400] = [0., -2.25, 0.]; pf.px[1400:] = [0., .55, 0.]
        pf.logw[:] = 0.; pf.initialized = True
        report = r.pose.provider.report(0.)
        own = OwnPose.from_report(report)
        assert report.y_m == pytest.approx(-2.25)
        assert own.y == pytest.approx(-2.25)
        assert report.std_xy_m == pytest.approx(math.sqrt(.7*.3*2.8**2))
    finally: r.close()
