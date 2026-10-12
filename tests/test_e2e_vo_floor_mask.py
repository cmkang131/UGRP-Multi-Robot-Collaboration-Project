"""Pure camera geometry and saved-image estimator contracts; no physics."""
import math

import cv2
import numpy as np
import pytest

from harness import e2e_rgb_vo as vo
from harness import e2e_vo_floor_mask as mask
from harness.active_camera import SEARCH, transform
from harness.self_pulse_rotation import RotationPulseOdometry


def project(points, servo=SEARCH):
    o, r = transform(servo)
    return cv2.fisheye.projectPoints(((np.asarray(points)-o) @ r).reshape(-1, 1, 3),
        np.zeros(3), np.zeros(3), mask.K, mask.D)[0].reshape(-1, 2)


def test_wall_occlusion_horizon_and_floor_with_rotated_map_frame():
    # Same physical wall expressed in two map coordinate frames.
    wall = ((.8, 0., .025, 2., .4, 0.),)
    a = mask.geometric_mask(SEARCH, wall, (0., 0., 0.))
    b = mask.geometric_mask(SEARCH, ((2., 3.8, .025, 2., .4, math.pi/2),), (2., 3., math.pi/2))
    np.testing.assert_array_equal(a, b)
    for xyz, expected in [([.8, 0., .15], 0), ([.55, 0., 0.], 255), ([1.8, 0., 0.], 0)]:
        x, y = np.rint(project([xyz])[0]).astype(int)
        assert a[y, x] == expected
    _, direction = mask.rays(vo._servo_key(SEARCH))
    assert not a.reshape(-1)[direction[:, 2] >= 0].any()


def test_wall_behind_camera_does_not_mask_floor_and_height_matters():
    far = mask.geometric_mask(SEARCH, ((-3., 0., .025, 2., .4, 0.),), (0., 0., 0.))
    short = mask.geometric_mask(SEARCH, ((.8, 0., .025, 2., .01, 0.),), (0., 0., 0.))
    tall = mask.geometric_mask(SEARCH, ((.8, 0., .025, 2., .4, 0.),), (0., 0., 0.))
    x, y = np.rint(project([[.8, 0., .15]])[0]).astype(int)
    assert far[y, x] == short[y, x] == 255 and tall[y, x] == 0


def test_missing_registration_is_explicit_unknown_not_own_start_or_identity():
    a = np.full((480, 640, 3), 120, np.uint8); b = a.copy(); b[0, 0] += 1
    assert mask.geometric_mask(SEARCH, (), None) is None
    r = vo.ground_pair(a, b, SEARCH, vo_floor_mask='geom_v1', static_walls=((.8, 0., .025, 2., .4, 0.),))
    assert r['status'] == 'unknown_map_registration'
    with pytest.raises(ValueError, match='FINITE_REGISTERED'):
        mask.geometric_mask(SEARCH, (), [math.nan, 0, 0])


def test_ledger_join_does_not_confuse_local_slam_with_static_world_registration():
    frame = dict(frame_id=3, sim_time=1.7, sha256='rgb3')
    ledger = dict(frame_id=3, t=.4, sha256='rgb3', pose_own_m=[.2, .3, .1],
                  pose_continuity=dict(map_to_odom=[1., 2., .4]))
    kw = dict(robot_id='r1', origin=1.3, static_map_sha256='map1', map_frame='world')
    assert mask.registered_map_pose(frame, None, **kw) == (None, 'missing_controller_pose')
    assert mask.registered_map_pose(frame, ledger, **kw) == (None, 'missing_static_map_to_own_transform')
    ledger['static_map_registration'] = dict(source='own_rgb_static_map', own_frame='r1/own_start',
        map_frame='world', static_map_sha256='map1', map_from_own=[2., 3., math.pi/2],
        rgb_refs=[dict(robot_id='r1', t_sim=.2, frame_id=2, sha256='rgb2')])
    pose, status = mask.registered_map_pose(frame, ledger, **kw)
    np.testing.assert_allclose(pose, [1.7, 3.2, math.pi/2+.1]); assert status == 'registered'
    with pytest.raises(ValueError, match='FRAME_JOIN'):
        mask.registered_map_pose({**frame, 'sha256':'different'}, ledger, **kw)
    with pytest.raises(ValueError, match='REGISTRATION_REQUIRED'):
        mask.registered_map_pose(frame, ledger, **{**kw, 'static_map_sha256':'different'})
    ledger['static_map_registration']['rgb_refs'][0]['t_sim'] = 1.
    with pytest.raises(ValueError, match='CAUSAL_OWN'):
        mask.registered_map_pose(frame, ledger, **kw)


@pytest.mark.parametrize('option,expect_homography', [('map_v1', False), ('geom_v1', True)])
def test_map_only_and_combined_apply_both_frame_masks(monkeypatch, option, expect_homography):
    a = np.random.default_rng(8).integers(50, 160, (480, 640), dtype=np.uint8)
    a = np.repeat(a[:, :, None], 3, axis=2); b = np.roll(a, 1, axis=1)
    poses = []; calls = []
    def geometry(servo, boxes, pose):
        poses.append(pose)
        result = np.full((480, 640), 255, np.uint8);result[:, :100] = 0
        return result
    def h(p, q):
        calls.append(True); assert (p[:, 0] >= 100).all() and (q[:, 0] >= 99.5).all()
        return np.ones(len(p), bool)
    monkeypatch.setattr(mask, 'geometric_mask', geometry)
    monkeypatch.setattr(mask, 'homography_inliers', h)
    vo.ground_pair(a, b, SEARCH, vo_floor_mask=option, static_walls=(),
                   before_map_pose=[0., 0., 0.], after_map_pose=[.1, 0., 0.])
    assert poses == [[0., 0., 0.], [.1, 0., 0.]]
    assert bool(calls) == expect_homography


@pytest.mark.parametrize('policy,expected', [('no_ransac_v1', 'off'), ('command_v1', None)])
def test_turn_policy_uses_issued_axis_including_tail_not_parasitic_translation(monkeypatch, policy, expected):
    calls = []
    def pair(*args, **kw):
        calls.append(kw.get('vo_floor_mask', 'off'))
        return dict(status='unknown_texture', tracks=0, inliers=0, cells=0)
    monkeypatch.setattr(vo, 'ground_pair', pair)
    d = RotationPulseOdometry();d.command(dict(t=0., kind='initial_servo_command', pulses=SEARCH))
    f = vo.VOFusion(d, vo_floor_mask='homography_v1', rotation_policy=policy)
    a = np.full((480, 640, 3), 120, np.uint8)
    f.observe(t=1., frame_id=1, rgb=a, servo=SEARCH)
    f.command(dict(t=1., kind='mecanum', turn=.35, forward=0., left=0., duration_s=.1))
    r = f.observe(t=1.2, frame_id=2, rgb=a, servo=SEARCH)
    assert r['commanded_turn'] and abs(r['command_delta'][1]) > .001
    assert calls == ([] if expected is None else [expected])
    f.observe(t=1.4, frame_id=3, rgb=a, servo=SEARCH)
    assert calls[-1] == 'homography_v1'  # completed tail must not mark future hold as turn


def test_missing_geometry_never_contributes_fallback_as_mask_accuracy(monkeypatch, tmp_path):
    import json
    from scripts import replay_e2e_vomask as replay
    monkeypatch.setattr(replay, 'CASES', [('test-r2', 'r1')])
    prior = [dict(run='test', robot='r1', t=t, sha256=str(t), vo2=[0., 0., 0.], truth=[t, 0., 0.]) for t in (0., .2)]
    truth = [dict(run='test', robot='r1', t0=0., t1=.2, kind='moving', truth_increment=[.2, 0., 0.])]
    monkeypatch.setattr(replay.subprocess, 'check_output', lambda cmd: json.dumps(
        prior if 'predictions' in cmd[-1] else truth).encode())
    predictions = [dict(run='test-r2', robot='r1', t=t, sha256=str(t),
        poses={k:[0., 0., 0.] for k in replay.OPTIONS},
        measurements={k:dict(status='unknown_map_registration') for k in replay.OPTIONS},
        registration=dict(status='missing_static_map_to_own_transform')) for t in (0., .2)]
    metrics, scored = replay.score(predictions, tmp_path)
    for k in ('map_v1', 'geom_v1'):
        m = metrics['intervals_by_kind']['moving']['metrics'][k]
        assert m['n'] == 0 and m['N'] == 1 and m['sum_xy_mm'] is None
        assert scored[0]['metrics'][k]['unregistered_fallback_only']['xy_mm'] == 200.


def test_v207_selects_only_replayed_policy_keeps_v206_off_and_wires_real_robot():
    import json
    from pathlib import Path
    from scripts.run_e2e_ownmap_live import bundle
    from scripts.s4_proxy_relay import accepted_call_id
    from harness.e2e_live_mapping import Robot
    from harness.e2e_stall_odometry import Options as StallOptions
    from harness.s4_event_policy import Options
    kw = dict(enabled=True, stall_odometry='rgb_vo_us_v1', ultrasonic_front='on_v1',
        exploration_progress='frontier_progress_v1', boundary_views='candidate_views_v1', b_marker_detect='contrast_v1')
    base = bundle('sha', 61001, 'study_gemma4_31b_v1', **kw)
    selected = dict(vo_floor_mask='homography_v1', vo_rotation_policy='no_ransac_v1')
    candidate = bundle('sha', 61001, 'study_gemma4_31b_v1', **kw, **selected)
    assert base['execution_bundle_id'] == 'e2e-usstall-v206'
    assert candidate['execution_bundle_id'] == 'e2e-vomask-turn-v207'
    assert candidate['workflow_version'] == '7.100.0'
    for k in ('schema', 'execution_bundle_id', 'workflow_version', 'source_sha256', 'vo_mask_scope'):
        base.pop(k, None); candidate.pop(k, None)
    for k, v in selected.items():
        assert candidate['e2e_options'].pop(k) == v
    assert base == candidate
    for bad in ({'vo_floor_mask':'geom_v1'}, {'vo_rotation_policy':'command_v1'}, {'vo_floor_mask':'homography_v1'}):
        with pytest.raises(ValueError, match='SELECTED_TURN_POLICY'):
            bundle('sha', 61001, 'study_gemma4_31b_v1', **kw, **bad)
    cov = json.loads(Path('configs/e2e_nees_egomap70_dev_v1.json').read_text())
    robot = Robot('r1', 61001, cov, Options(), stall_options=StallOptions('rgb_vo_us_v1'), **selected)
    assert robot.goal.e2e_vo.vo_floor_mask == 'homography_v1'
    assert robot.goal.e2e_vo.rotation_policy == 'no_ransac_v1'
    assert robot.goal.e2e_vo.range_stall is not None
    for arm in 'ab':
        for seed in (61001, 61002, 61003):
            assert accepted_call_id(f'e2e-vomask-{arm}-s{seed}:call-0001-r1:1')
    assert not accepted_call_id('e2e-vomask-a-s61004:call-0001-r1:1')


def test_homography_rejects_outliers_in_undistorted_coordinates():
    p = np.array([(x, y) for x in (.45, .6, .85, 1.1, 1.4) for y in (-.3, -.1, .1, .3)])
    q = p - [.012, .002]
    a = project(np.column_stack((p, np.zeros(len(p)))))
    b = project(np.column_stack((q, np.zeros(len(q)))))
    b[-3:] += [25, -30]
    keep = mask.homography_inliers(a, b)
    assert keep[:-3].all() and not keep[-3:].any()
    assert not mask.homography_inliers(a[:3], b[:3]).any()
    assert not mask.homography_inliers(np.ones((8, 2)), np.ones((8, 2))).any()


def test_ransac_inliers_only_reach_metric_fit(monkeypatch):
    a = np.random.default_rng(8).integers(50, 160, (480, 640), dtype=np.uint8)
    a = np.repeat(a[:, :, None], 3, axis=2); b = np.roll(a, 1, axis=1)
    seen = []
    def choose(p, q):
        keep = np.arange(len(p)) % 2 == 0
        seen.append(p[keep].copy())
        return keep
    def fit(p, q):
        np.testing.assert_allclose(p, vo.ground(SEARCH, seen[0])[0])
        return None
    monkeypatch.setattr(mask, 'homography_inliers', choose)
    monkeypatch.setattr(vo, 'rigid_ransac', fit)
    out = vo.ground_pair(a, b, SEARCH, vo_floor_mask='homography_v1')
    assert seen and out['status'] == 'unknown_rigid_consensus'
    assert out['homography_inliers'] < out['pre_homography_tracks']


def test_missing_map_keeps_command_increment_and_pose_propagation():
    d = RotationPulseOdometry(); d.command(dict(t=0., kind='initial_servo_command', pulses=SEARCH))
    f = vo.VOFusion(d, vo_floor_mask='geom_v1')
    a = np.full((480, 640, 3), 120, np.uint8)
    f.observe(t=1., frame_id=1, rgb=a, servo=SEARCH)
    f.command(dict(t=1., kind='mecanum', forward=.35, left=0., turn=0., duration_s=.1))
    b = a.copy(); b[0, 0] += 1
    r = f.observe(t=1.2, frame_id=2, rgb=b, servo=SEARCH)
    assert r['status'] == 'unknown_map_registration'
    assert r['fusion'] == 'command_kept' and r['command_delta'][0] > 0
    assert r['command_delta'] == r['fused_delta']


def test_off_never_reads_optional_map_input_and_is_identical():
    a = np.random.default_rng(7).integers(50, 160, (480, 640), dtype=np.uint8)
    a = np.repeat(a[:, :, None], 3, axis=2); b = np.roll(a, 1, axis=1)
    assert vo.ground_pair(a, b, SEARCH) == vo.ground_pair(a, b, SEARCH,
        vo_floor_mask='off', static_walls=object(), before_map_pose=object(), after_map_pose=object())


def test_static_map_whitelist_and_option_validation():
    m = dict(obstacles=[dict(kind='wall', center_m=[.8, 0], half_extents_m=[.025, 2.], height_m=.4)],
             robot_spawns=object(), evaluation=object())
    assert mask.wall_boxes(m) == ((.8, 0., .025, 2., .4, 0.),)
    with pytest.raises(ValueError, match='UNKNOWN_VO_FLOOR_MASK'):
        vo.VOFusion(RotationPulseOdometry(), vo_floor_mask='oops')


def test_cli_preserves_mask_rotation_options_and_expected_id(capsys):
    import json
    from scripts.run_e2e_ownmap_live import main
    args = ['--expected-source-sha', 'x', '--output', '/tmp/unused', '--seed', '61001',
            '--driver-profile', 'study_gemma4_31b_v1', '--relay-receipt', '/tmp/receipt.json',
            '--exploration-progress', 'frontier_progress_v1', '--stall-odometry', 'rgb_vo_us_v1',
            '--ultrasonic-front', 'on_v1', '--boundary-views', 'candidate_views_v1',
            '--b-marker-detect', 'contrast_v1', '--vo-floor-mask', 'homography_v1',
            '--vo-rotation-policy', 'no_ransac_v1']
    main([*args, '--expected-workflow-id', 'e2e-vomask-turn-v207'])
    b = json.loads(capsys.readouterr().out)
    assert b['execution_bundle_id'] == 'e2e-vomask-turn-v207'
    assert b['e2e_options']['vo_floor_mask'] == 'homography_v1'
    assert b['e2e_options']['vo_rotation_policy'] == 'no_ransac_v1'
    with pytest.raises(ValueError, match='WORKFLOW_BUNDLE_ID_MISMATCH'):
        main([*args, '--expected-workflow-id', 'e2e-usstall-v206'])
    assert not capsys.readouterr().out
