import copy

import pytest

from scripts.offline_self_map import replay, safe_rgb_path, score


def scene():
    return {'bounds_m': [0, 3, 0, 3], 'obstacles': [
        {'center_m': [2.5, 1.5], 'half_extents_m': [.5, 1.5], 'kind': 'wall'}]}


def test_occupancy_iou_keeps_unknown_and_outside_false_positives():
    snapshot = {'resolution_m': 1., 'cells': [[2, 0, 1.], [0, 0, -1.], [5, 5, 1.]]}
    before = copy.deepcopy(snapshot)
    result = score(snapshot, scene(), [0, 0, 0])
    assert result['occupancy_intersection'] == 1
    assert result['occupancy_union'] == 4
    assert result['occupancy_iou'] == .25
    assert result['false_occupied_outside_domain'] == 1
    assert result['free_coverage_n'] == 1 and result['free_coverage_N'] == 6
    assert result['wall_error_rmse_m'] > 0
    assert snapshot == before


def test_empty_prediction_not_perfect_or_complete_and_denominator_fixed():
    result = score({'resolution_m': 1., 'cells': []}, scene(), [0, 0, 0])
    assert result['occupancy_iou'] == 0.
    assert result['free_coverage'] == 0.
    assert result['wall_error_rmse_m'] is None
    assert result['all_wall_samples_N'] > 0


def test_alignment_fixed_to_initial_pose_without_fitting():
    result = score({'resolution_m': 1., 'cells': [[0, 0, 1.]]}, scene(), [2., 0., 0.])
    assert result['occupancy_intersection'] == 1
    assert result['origin_eval_only'] == [2., 0., 0.]


def test_replay_rejects_evaluation_and_peer_image_paths(tmp_path):
    assert safe_rgb_path(tmp_path, 'robots/r1/rgb/a.jpg', 'r1').name == 'a.jpg'
    for path in ('eval_only/a.jpg', 'robots/r2/rgb/a.jpg', '../../a.jpg'):
        with pytest.raises(ValueError, match='OWN_RGB'):
            safe_rgb_path(tmp_path, path, 'r1')


def test_replay_default_off_does_not_read_or_write(tmp_path):
    output = tmp_path/'not-created'
    assert replay(tmp_path/'missing', tmp_path/'missing', 'r1', output, 's2_pulse_v122')['status'] == 'DISABLED'
    assert not output.exists()
