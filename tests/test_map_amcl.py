import copy
import json
import math
from pathlib import Path
import numpy as np
import pytest
from harness import map_amcl as amcl
from scripts import extract_e2e_pose_features as extraction
from scripts.replay_map_amcl import replay, jump_metrics, score, validate_features, aggregate

SERVO = {1: 2000, 3: 740, 4: 2320, 5: 1320, 6: 1500}


def arena():
    return dict(bounds_m=[-1., 2., -1., 2.], obstacles=[
        dict(kind='wall', center_m=[.5, -.9], half_extents_m=[1.5, .05]),
        dict(kind='wall', center_m=[1.9, .5], half_extents_m=[.05, 1.5])],
        regions={'A': dict(center_m=[0., 0.], half_extents_m=[.5, .5], rgba=[.2, .3, .7, 1.])})


def step(pf, t, **kwargs):
    args = dict(t=t, points=[], delta=[0., 0., 0.], servo=SERVO, features=[])
    args.update(kwargs)
    return pf.step(**args)


def test_off_does_not_touch_input_and_global_prior_has_no_pose_hint():
    assert amcl.create(None) is None
    a = amcl.create(arena(), option='amcl_walls_v1', seed=2)
    b = amcl.create(arena(), option='amcl_walls_v1', seed=2)
    assert np.array_equal(a.px, b.px)
    assert np.ptp(a.px[:, 0]) > 2.6 and np.ptp(a.px[:, 2]) > 6.
    assert (a.field.distances(a.px[:, :2]) > .15).all()
    with pytest.raises(TypeError):
        amcl.create(arena(), option='amcl_walls_v1', initial_pose=[0, 0, 0])
    with pytest.raises(TypeError):
        a.step(t=0, points=[], delta=[0, 0, 0], servo=SERVO, held_object_world=[1, 2])


def test_kld_nav2_literal_quantile_and_adaptive_count():
    p = amcl.Parameters()
    assert amcl.sample_limit(1, p) == 2000
    assert amcl.sample_limit(2, p) == 500
    assert amcl.sample_limit(10000, p) == 2000
    k = 50
    expected = math.ceil((k-1)/.1 * (1-2/(9*(k-1))+math.sqrt(2/(9*(k-1)))*.99)**3)
    assert amcl.sample_limit(k, p) == expected
    pf = amcl.create(arena(), option='amcl_walls_v1')
    pf.px[:] = 0.
    pf.px[::2, 0] = .51
    row = pf._resample(0.)
    assert row['occupied_bins'] == 2 and pf.n == 501
    assert row['injected'] == 0
    assert set(pf.px[:, 0]) == {0., .51}


def test_augmented_recovery_uses_absolute_scores_not_normalized_weights(monkeypatch):
    pf = amcl.create(arena(), option='amcl_walls_v1',
                    parameters=amcl.Parameters(min_particles=200, max_particles=200))
    monkeypatch.setattr(amcl.field, 'likelihood', lambda field, px, pts: np.full(len(px), 10.))
    a = step(pf, 0, points=[[1., 0.]])
    assert a['sensor']['w_avg'] == pytest.approx(.05)
    monkeypatch.setattr(amcl.field, 'likelihood', lambda field, px, pts: np.full(len(px), 1.))
    b = step(pf, 1, points=[[1., 0.]], servo=SERVO | {6: 1700})
    slow, fast = .05+.001*(.005-.05), .05+.1*(.005-.05)
    assert b['sensor']['w_slow'] == pytest.approx(slow)
    assert b['sensor']['injection_probability'] == pytest.approx(1-fast/slow)
    assert b['sensor']['injected'] > 0
    assert pf.w_slow == pf.w_fast == 0


def test_no_scan_does_not_resample_and_prediction_retains_command_motion():
    pf = amcl.create(arena(), option='amcl_walls_v1')
    original = pf.px.copy()
    a = step(pf, 0)
    b = step(pf, 1, delta=[.1, 0., .1])
    assert not b['updated'] and b['updates'] == b['resamples'] == 0
    assert np.array_equal(original, pf.px)
    assert b['covariance'][2][2] >= a['covariance'][2][2]
    with pytest.raises(ValueError, match='CAUSAL'):
        step(pf, 1)
    with pytest.raises(ValueError, match='STATIC_RGB_FEATURES_ONLY'):
        step(pf, 2, features=[dict(kind='held_cargo', center=[1, 2])])


def test_same_view_is_not_counted_twice_but_command_gate_advances():
    pf = amcl.create(arena(), option='amcl_walls_v1')
    a = step(pf, 0, points=[[.8, -.9]])
    b = step(pf, 1, points=[[.8, -.9]])
    c = step(pf, 2, points=[[.8, -.9]], delta=[.3, 0., 0.])
    assert a['updated'] and not b['updated'] and c['updated']
    assert c['updates'] == c['resamples'] == 2


def test_omni_motion_preserves_strafe_and_nav2_variance():
    pf = amcl.create(arena(), option='amcl_walls_v1', seed=20,
                    parameters=amcl.Parameters(min_particles=10000, max_particles=10000))
    pf.px[:] = 0.
    pf._predict(np.array([0., .4, .1]))
    assert np.allclose(pf.px.mean(0), [0., .4, .1], atol=.008)
    assert np.allclose(pf.px.var(0), .2*(.4**2+.1**2), atol=.002)


def test_likelihood_field_prefers_map_contact_and_floor_only_is_measurement():
    f = amcl.field.Field(arena())
    likelihood = amcl.field.likelihood(f, np.array([[0., 0., 0.], [0., 1., 0.]]), [[0., -.9]])
    assert likelihood[0] > likelihood[1]
    pf = amcl.create(arena(), option='amcl_landmarks_v1')
    edge = pf.landmark_map.edges[0]
    features = [dict(kind='floor_line', endpoints=[edge['a'].tolist(), edge['b'].tolist()],
                     normal=edge['normal'].tolist(), hue=edge['hue'])]
    row = step(pf, 0, features=features)
    assert row['updated'] and row['resamples'] == 1


def packet_rows():
    return [dict(robot_id='r1', t=52.3+i, physical_t=1.3+i, frame_id=i, sha256=str(i),
                 servo=SERVO, command_delta=[.1, .03*i, .05], fused_delta=[.1, .03*i, .05],
                 settled=True, points=[], features=[]) for i in range(5)]


def test_replay_no_truth_initialization_and_eval_rigid_alignment():
    rows = packet_rows()
    poses, _ = replay(rows, 'off', 'fused_delta')
    poisoned = copy.deepcopy(rows)
    for r in poisoned:
        r.update(robot_xyz_m=[999, 888, 777], held_world=[1000, 2000])
    other, _ = replay(poisoned, 'off', 'fused_delta')
    assert np.array_equal(poses, other)
    assert np.array_equal(poses[0], [0., 0., 0.])
    truth = [dict(t=r['physical_t'], robot_xyz_m=[p[0]+2, p[1]+3, 0.], robot_yaw_rad=p[2])
             for p, r in zip(poses, rows)]
    m = score(poses, rows, truth, dict(cutoff_s=52.3))
    assert m['passed_pr480'] and m['absolute_xy_median_m'] > 3
    summary, _ = jump_metrics(poses, rows)
    assert summary['acceptable_n'] == summary['N'] == 4
    poses[2, 0] += 1
    summary, _ = jump_metrics(poses, rows)
    assert summary['flagged_n'] == 2
    truth[0]['t'] += .5
    with pytest.raises(ValueError, match='CLOCK'):
        score(poses, rows, truth, dict(cutoff_s=52.3))


def test_feature_alignment_and_missing_denominator_are_fail_closed():
    rows = packet_rows()
    assert validate_features(copy.deepcopy(rows), rows) == rows
    bad = copy.deepcopy(rows)
    bad[1]['sha256'] = 'other'
    with pytest.raises(ValueError, match='SOURCE_MISMATCH'):
        validate_features(bad, rows)
    with pytest.raises(ValueError, match='FULL_INTERVAL'):
        validate_features(rows[:-1], rows)
    a = aggregate([dict(status='missing_features')]*80, 80)
    assert a['evaluated_N'] == 0 and a['passed_pr480_n'] is None and a['unavailable_N'] == 80


def test_packet_identity_uses_frame_id_not_repeated_jpeg_hash(tmp_path):
    d = tmp_path/'robots/r1'
    d.mkdir(parents=True)
    frames = [dict(frame_id=i, sim_time=i+1.3, sha256='same', path=f'robots/r1/rgb/{i}.jpg',
                   commanded_servo=dict(SERVO) | {6: 1500+100*i}) for i in range(2)]
    own = [dict(frame_id=i, t=52.3+i, sha256='same',
                stall_odometry=dict(command_substeps=i, command_delta=[.1, 0, 0], fused_delta=[.2, 0, 0]),
                eval_only=dict(pose=[999, 999, 999])) for i in range(2)]
    for name, rows in [('frames', frames), ('ownmap', own)]:
        (d/f'{name}.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
    p = extraction.packets(tmp_path, 'r1')
    assert [r['servo'][6] for r in p] == [1500, 1600]
    assert p[0]['fused_delta'] == [0, 0, 0] and 'eval_only' not in p[0]
    assert extraction.availability(p)['missing'] == 2
    with pytest.raises(FileNotFoundError, match='SAVED_OWN_RGB_REQUIRED'):
        extraction.extract(tmp_path, tmp_path/'absent-map.json', tmp_path/'output', ('r1',))
    assert not (tmp_path/'output').exists()
