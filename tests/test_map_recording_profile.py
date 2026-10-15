"""Saved-input computation only: no world, renderer, or remote connection."""
import copy
import json
from types import SimpleNamespace

import numpy as np
import pytest

from harness.e2e_exact_speedups import OFF
from harness.map_recording_speed import PROFILE, configure, controller_profile, squared_grid_cost
from scripts.profile_map_recording import command_schedule, controller_accuracy, project_first30


def test_profiles_are_instance_scoped_and_default_off():
    robot, peer = SimpleNamespace(exact_speedups=OFF), SimpleNamespace(exact_speedups=OFF)
    assert configure(robot).exact_speedups == OFF
    configure(robot, 'exact_v1')
    assert all(vars(robot.exact_speedups).values()) and peer.exact_speedups == OFF
    with pytest.raises(RuntimeError), controller_profile('squared_v1'):
        assert PROFILE.get() == 'squared_v1'
        raise RuntimeError('cleanup')
    assert PROFILE.get() == 'off'
    with pytest.raises(ValueError):
        configure(robot, 'unknown')


@pytest.mark.parametrize('interior', [False, True])
def test_squared_cost_retains_all_points_candidates_and_winner(interior):
    from harness.e2e_b_partial import rect_sd
    rng = np.random.default_rng(56)
    points = rng.normal(0, .8, (300, 2))
    centers = rng.normal(0, 1.2, (1681, 2))
    for yaw in (0., .39269908169872414, 1.5707963267948966):
        d = rect_sd(points[None], centers[:, None], yaw, [.4, .4])
        reference = (np.minimum(np.maximum(d, 0) if interior else abs(d), .06)**2).mean(axis=1)
        candidate = squared_grid_cost(points, centers, yaw, [.4, .4], .06, interior=interior)
        np.testing.assert_allclose(candidate, reference, rtol=1e-13, atol=1e-17)
        assert np.argmin(candidate) == np.argmin(reference)


def test_own_frame_accuracy_uses_fixed_initial_transform_only():
    yaw = .7
    c, s = np.cos(yaw), np.sin(yaw)
    poses = np.array([[0., 0., 0.], [.1, .2, .3], [.2, .3, .4]])
    truth = [dict(t=1.3+i*.1, robot_xyz_m=[*(np.array([2., -3.])+
        p[:2] @ np.array([[c, s], [-s, c]])), .1], robot_yaw_rad=p[2]+yaw)
        for i, p in enumerate(poses)]
    inputs = [dict(t=i*.1, physical_t=1.3+i*.1) for i in range(3)]
    untouched = copy.deepcopy(truth)
    score = controller_accuracy(poses, inputs, truth)
    assert score['absolute_xy_p95_m'] < 1e-14
    assert score['absolute_yaw_p95_deg'] < 1e-12
    bad = poses.copy(); bad[-1, 0] += .5
    assert controller_accuracy(bad, inputs, truth)['absolute_xy_p95_m'] > .4
    assert truth == untouched


def test_issued_schedule_checks_clock_and_excludes_shutdown(tmp_path):
    from harness.active_camera import SEARCH
    rows = [dict(t=i*.1, physical_t=1.3+i*.1, frame_id=i+1) for i in range(301)]
    commands = [dict(t=1.3, kind='initial_servo_command', pulses=SEARCH)]
    commands += [dict(t=1.3, kind='look', pan_pulse=v) if k == 6 else
                 dict(t=1.3, kind='arm', servo_id=k, pulse=v) for k, v in SEARCH.items()]
    commands += [dict(t=1.3+i*.1, kind='hold') for i in range(0, 301, 2)]
    path = tmp_path/'robots/r1/commands.jsonl'; path.parent.mkdir(parents=True)
    path.write_text(''.join(json.dumps(c)+'\n' for c in commands))
    assert len(command_schedule(tmp_path, 'r1', rows)) == 150
    commands[8]['t'] += .1
    path.write_text(''.join(json.dumps(c)+'\n' for c in commands))
    with pytest.raises(ValueError, match='TIME_MISMATCH'):
        command_schedule(tmp_path, 'r1', rows)


def test_projection_cannot_use_profiler_partial_replay_or_other_controller():
    quality = dict(absolute_xy_median_m=.1, absolute_xy_p95_m=.2,
                   absolute_yaw_median_deg=1., absolute_yaw_p95_deg=2.)
    def result(mode, seconds):
        return dict(mode=mode, profile=False, N=602, sources={'RGB': 'hash'}, raw='same',
            original_timing=dict(first30_wall_s=485.5, outside_physics_camera_eval_s=386.7),
            robots={rid: dict(frames=301, exact_proposed_commands=301, exact_issued_commands=150,
                controller={'total_s': seconds/2}, accuracy=quality) for rid in ('r1', 'r2')})
    a, b = result('legacy', 200.), result('squared_v1', 100.)
    got = project_first30([a, a], [b, b])
    assert got['predicted_wall_per_sim'] == pytest.approx((98.8+386.7*.5)/30)
    assert not got['meets_nominal_target'] and not got['ready']
    assert got['sensitivity'][-1]['wall_per_sim'] > got['predicted_wall_per_sim']
    for key, value in [('profile', True), ('N', 600), ('mode', 'batch')]:
        bad = copy.deepcopy(a); bad[key] = value
        with pytest.raises(ValueError):
            project_first30([bad, a], [b, b])
