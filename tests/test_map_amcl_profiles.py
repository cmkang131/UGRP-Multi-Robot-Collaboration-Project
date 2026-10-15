"""No simulator/renderer: sensor stubs, numeric posteriors and saved ledgers."""
import json

import numpy as np
import pytest

from harness import map_amcl as amcl
from harness.map_amcl_profiles import RGBPipeline, parameters_for
from scripts.audit_map_amcl_motion import coverage
from scripts.profile_map_amcl import no_material_loss, run
from tests.test_map_amcl import arena, SERVO, step


def test_profiles_are_explicit_and_do_not_change_legacy_parameters():
    assert parameters_for('off') == amcl.Parameters()
    assert parameters_for('amcl4_motion_v1') == amcl.Parameters()
    assert parameters_for('amcl4_balanced_v1').resample_interval == 2
    with pytest.raises(ValueError, match='UNKNOWN_AMCL4'):
        amcl.create(None, profile='amcl4_typo')
    with pytest.raises(ValueError, match='EXCLUSIVE'):
        amcl.create(arena(), profile='amcl4_motion_v1', parameters=amcl.Parameters())
    for kw in ({'resample_interval': 0}, {'resample_interval': True},
               {'max_beams': 61}, {'max_beams': 0}, {'max_landmarks': 0}):
        with pytest.raises(ValueError):
            amcl.Parameters(**kw)


def test_lazy_frontend_matches_eager_posterior_and_keeps_every_command(monkeypatch):
    from harness import self_map_closed_loop as front
    calls = []
    def measurement(rgb, servo):
        calls.append(servo[6])
        return dict(points=[[1., -.9], [.8, -.9]], columns=[], uv=[])
    monkeypatch.setattr(front, 'own_measurement', measurement)
    a, b = [RGBPipeline(arena(), profile=p, option='amcl_walls_v1')
            for p in ('off', 'amcl4_motion_v1')]
    for i in range(70):
        servo = SERVO | {6: 1700 if i >= 35 else 1500}
        kwargs = dict(t=i*.1, rgb=None, delta=[.02 if i else 0., 0., 0.], servo=servo)
        ar, br = a.step(**kwargs), b.step(**kwargs)
        assert ar['pose'] == br['pose']
        assert ar['covariance'] == br['covariance']
        assert np.array_equal(a.pf.px, b.pf.px)
        assert np.array_equal(a.pf.logw, b.pf.logw)
    ta, tb = a.metrics.snapshot()['timers'], b.metrics.snapshot()['timers']
    assert tb['rgb_features']['calls'] < ta['rgb_features']['calls']/3
    assert ta['measurement_model']['calls'] == tb['measurement_model']['calls']
    assert a.pf.odom[0] == pytest.approx(1.38)
    assert a.pf.last_t == b.pf.last_t == 6.9
    assert a.pf.updates == b.pf.updates
    with pytest.raises(ValueError, match='CAUSAL'):
        b.step(**kwargs)


def test_motion_peek_accumulates_and_empty_epoch_does_not_consume_view():
    pf = amcl.create(arena(), option='amcl_walls_v1')
    original = pf.rng.bit_generator.state
    assert pf.measurement_due([0, 0, 0], SERVO)
    assert pf.rng.bit_generator.state == original
    step(pf, 0, points=[[1, -.9]])
    assert not pf.measurement_due([.1, 0, 0], SERVO)
    step(pf, 1, delta=[.1, 0, 0])
    assert pf.measurement_due([.16, 0, 0], SERVO)
    step(pf, 2, delta=[.16, 0, 0])  # no measurement, do not move anchor
    assert pf.measurement_due([0, 0, 0], SERVO)
    step(pf, 3, points=[[1, -.9]])
    assert not pf.measurement_due([0, 0, 0], SERVO)


def test_resample_interval_counts_only_updates_and_keeps_prior_weights(monkeypatch):
    pf = amcl.create(arena(), option='amcl_walls_v1', profile='amcl4_resample2_v1')
    scores = np.linspace(1., 3., pf.n)
    monkeypatch.setattr(amcl.field, 'likelihood', lambda *args: scores)
    first = step(pf, 0, points=[[1, 0]])
    assert first['updates'] == 1 and first['resamples'] == 0
    assert np.allclose(pf._weights(), scores/scores.sum())
    before = pf.logw.copy()
    step(pf, 1, points=[[1, 0]])
    assert np.array_equal(before, pf.logw) and pf.updates == 1
    captured = []
    real_resample = pf._resample
    def resample(probability):
        captured.append(pf._weights().copy())
        return real_resample(probability)
    monkeypatch.setattr(pf, '_resample', resample)
    step(pf, 2, points=[[1, 0]], servo=SERVO | {6: 1700})
    assert pf.resamples == 1
    assert np.allclose(captured[0], scores**2/(scores**2).sum())


def test_feature_budget_and_adaptive_floor_do_not_shrink_unknown_prior(monkeypatch):
    pf = amcl.create(arena(), option='amcl_landmarks_v1', profile='amcl4_balanced_v1')
    assert pf.n == 2000
    assert amcl.sample_limit(1, pf.parameters) == 2000
    assert amcl.sample_limit(2, pf.parameters) == 250
    measured = []
    monkeypatch.setattr(amcl.field, 'likelihood', lambda f, poses, points:
        measured.append(('walls', len(points))) or np.ones(len(poses)))
    monkeypatch.setattr(amcl, 'landmark_likelihood', lambda f, poses, features:
        measured.append(('landmarks', len(features))) or np.ones(len(poses)))
    doors = [dict(kind='door', center=[i*.1, 1], width=.5) for i in range(8)]
    step(pf, 0, points=np.zeros((60, 2)), features=doors)
    assert measured == [('walls', 30), ('landmarks', 4)]
    with pytest.raises(ValueError, match='STATIC_RGB_FEATURES_ONLY'):
        step(pf, 1, features=doors+[dict(kind='cargo')])


def test_alpha_one_step_coverage_does_not_cover_accumulated_bias():
    commands = np.tile([.01, 0, 0], (100, 1))
    truth = np.c_[np.arange(101)*.0075, np.zeros((101, 2))]
    result = coverage(commands, truth)
    assert result['xy_within_1sigma_n'] == result['moving_N'] == 100
    assert result['path_ratio'] == pytest.approx(4/3)
    assert result['final_xy_error_m'] == pytest.approx(.25)
    assert not result['final_within_3maxsigma']
    stationary = coverage(np.zeros((1, 3)), np.array([[0, 0, 0], [.002, 0, 0]]))
    assert stationary['stationary_residual_gt_1mm_n'] == 1
    assert stationary['moving_N'] == 0 and stationary['xy_sigma_ratio_median'] is None


def test_accuracy_rejects_tail_loss_even_if_median_improves():
    base = dict(absolute_xy_median_m=.1, absolute_xy_p95_m=.3,
                absolute_yaw_median_deg=10., absolute_yaw_p95_deg=30.)
    assert no_material_loss(base, base)
    assert not no_material_loss(base, base | dict(absolute_xy_median_m=.05, absolute_xy_p95_m=.4))


def test_missing_rgb_reports_every_profile_and_never_initializes_filter(tmp_path, monkeypatch):
    from scripts import profile_map_amcl as runner
    monkeypatch.setattr(runner, 'RGBPipeline', lambda *a, **k: pytest.fail('missing RGB entered filter'))
    monkeypatch.setattr(runner, 'original_timing', lambda raw: {})
    for rid in ('r1', 'r2'):
        p = tmp_path/f'robots/{rid}'
        p.mkdir(parents=True)
        frames = [dict(frame_id=1, sim_time=1.3, sha256='missing',
                       path=f'robots/{rid}/rgb/00000.jpg', commanded_servo=SERVO)]
        own = [dict(frame_id=1, t=0., sha256='missing', stall_odometry={})]
        for name, rows in [('frames', frames), ('ownmap', own)]:
            (p/f'{name}.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
    report = run(tmp_path)
    assert report['status'] == 'BLOCKED_MISSING_SAVED_RGB'
    assert report['missing_rgb'] == 2
    assert len(report['comparisons']) == 6
    assert all(r['evaluated_N'] == 0 and not r['adopted'] for r in report['comparisons'])
    assert report['prediction']['wall_per_sim'] is None


def test_recording_controller_timers_on_saved_synthetic_bitmap(tmp_path):
    from scripts.profile_map_amcl import controller_replay
    from scripts.extract_e2e_pose_features import packets
    from tests.test_map_amcl_recording import fixture_run
    _, raw = fixture_run(tmp_path)
    for rid in ('r1', 'r2'):
        path = raw/f'robots/{rid}/ownmap.jsonl'
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        for row in rows:
            row['command'] = dict(kind='hold')
        path.write_text(''.join(json.dumps(r)+'\n' for r in rows))
    inputs = {rid: packets(raw, rid) for rid in ('r1', 'r2')}
    result = controller_replay(raw, inputs, rectangle_batch=True)
    assert result['N'] == 10 and result['map_amcl_calls'] == 0
    assert result['timing']['timers']['record_controller_other']['calls'] == 10
    assert result['timing']['timers']['record_landmark_features']['calls'] == 10
