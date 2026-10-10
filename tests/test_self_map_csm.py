"""Own-map CSM geometry fixtures and byte goldens. No physics or model calls."""
import copy
import json
import math
from pathlib import Path
import types

import numpy as np
import pytest

from harness.self_map_csm import CSMOptions, CorrelativeMatcher, CorrectedOdomGrid, sample_segments
from harness.self_odom_grid import OdomGrid, transform
from harness.self_wall_memory import SelfWallMemory

ROOT = Path(__file__).resolve().parents[1]
CORNER = np.array([[[2., -1.], [2., 1.]], [[.5, 1.], [2., 1.]]])
STRAIGHT = np.array([[[2., -2.], [2., 2.]]])


def record(t, view, segments=CORNER):
    return {'t_sim': t, 'view_index': view, 'posture': 'other', 'load': False,
            'seg': [[math.hypot(*a), math.atan2(a[1], a[0]), math.hypot(*b), math.atan2(b[1], b[0]), None]
                    for a, b in segments]}


def match(segments, pose=(.15, -.1, 0.), reference=None):
    return CorrelativeMatcher().match(np.array(pose), np.diag([.25**2, .25**2, .08**2]),
                                      sample_segments(segments), np.zeros(2),
                                      segments if reference is None else reference, np.zeros((3, 3)))


@pytest.mark.parametrize('mapping', ['off', 'odom_grid_v1'])
def test_pose_correction_off_golden_old_source_bytes(mapping):
    old = types.ModuleType('before_csm')
    exec((ROOT/'tests/fixtures/self_wall_memory_before_csm.py.txt').read_text(), old.__dict__)
    for option in ({}, {'pose_correction': 'off'}):
        kw = dict(self_map=mapping, self_map_options={'settle_s': None},
                  self_walls_enabled=True, self_walls_text=True, clock=lambda: 10.)
        before, after = old.SelfWallMemory('r1', **kw), SelfWallMemory('r1', **kw, **option)
        for i in range(8):
            command = {'t': float(i), 'kind': 'mecanum', 'forward': .1, 'left': -.03,
                       'turn': .02, 'duration_s': .4, 'true_pose': [999, 999, 999]}
            r = record(i+.5, i)
            for memory in (before, after):
                memory.command(command)
                memory.observe_wall(r, camera_xy=[.16, 0.], robot_id='r1')
                memory.observe({'observation_id': str(i), 'cargo': [], 'self_walls': [r]}, i+.5)
            assert json.dumps(before.snapshot()).encode() == json.dumps(after.snapshot()).encode()
            if mapping != 'off':
                assert json.dumps(before.self_map.export()).encode() == json.dumps(after.self_map.export()).encode()
                assert before.self_map.odom.pose == after.self_map.odom.pose


def test_corner_corrects_known_command_error_without_truth_input():
    result = match(CORNER, pose=(.15, -.10, math.radians(2)))
    assert result['reason'] == 'accepted', result
    assert np.linalg.norm(result['pose'][:2]) < .07
    assert abs(result['pose'][2]) < math.radians(1.1)
    assert len(result['observable_axes_scaled']) == 3


def test_straight_wall_never_corrects_or_shrinks_tangent():
    result = match(STRAIGHT, pose=(.15, .25, 0.))
    assert result['reason'] == 'accepted', result
    assert abs(result['pose'][0]) < .06
    assert result['pose'][1] == pytest.approx(.25)
    assert result['covariance'][1][1] >= result['prior_covariance'][1][1]-1e-10
    assert len(result['observable_axes_scaled']) == 2


def test_repeated_symmetric_walls_are_ambiguous_not_prior_certainty():
    refs = np.concatenate([STRAIGHT+[-.2, 0.], STRAIGHT+[.2, 0.]])
    result = match(STRAIGHT, pose=(0., 0., 0.), reference=refs)
    assert result['reason'] == 'ambiguous_modes', result
    assert result['second_sensor_gap'] < .5
    assert result['pose'] == [0., 0., 0.]
    assert result['covariance'] == result['prior_covariance']


def test_no_overlap_and_window_boundary_cannot_be_accepted():
    for shift in (.5, 5.):
        result = match(CORNER, pose=(0., 0., 0.), reference=CORNER+[shift, 0.])
        assert result['status'] == 'rejected', result


def test_before_insert_reference_private_namespace_duplicate_and_reprojection():
    g = CorrectedOdomGrid('r1', settle_s=None)
    g.observe(record(0., 1), camera_xy=[0., 0.], robot_id='r1')
    assert g.decisions[0]['reference_frames'] == []
    assert g.decisions[0]['status'] == 'bootstrap'
    initial = json.dumps(g.export())
    g.observe(record(0., 1), camera_xy=[0., 0.], robot_id='r1')
    assert json.dumps(g.export()) == initial
    g.observe(record(1., 2), camera_xy=[0., 0.], robot_id='r1')
    assert g.decisions[-1]['reason'] == 'duplicate_geometry'
    assert g.decisions[-1]['reference_frames'] == [1]
    with pytest.raises(ValueError, match='PEER'):
        g.observe(record(2., 3), camera_xy=[0., 0.], robot_id='r2')
    # Rebuild from immutable local observations + their own accepted poses.
    rebuilt = OdomGrid('r1', settle_s=None)
    for row in g.ledger:
        rebuilt.insert(transform([row['camera']], row['pose'])[0],
                       [transform(s, row['pose']) for s in row['segments']])
    assert rebuilt.cells == g.cells


def test_strict_four_metre_free_space_exclusion_and_command_settle():
    g = CorrectedOdomGrid('r1', max_range_m=None)
    g.odom.command({'t': 0., 'kind': 'initial_servo_command', 'pulses': {1: 2000, 3: 740}})
    assert g.observe(record(.1, 1), camera_xy=[0., 0.], robot_id='r1') == []
    assert g.decisions[-1]['reason'] == 'unsettled'
    border = np.array([[[4., 0.], [3.9, 0.]]])
    assert g.observe(record(.3, 2, border), camera_xy=[0., 0.], robot_id='r1') == []
    assert g.cells == {}
    assert g.rejected['range_segments'] == 1
    g.odom.command({'t': .4, 'kind': 'arm', 'servo_id': 1, 'pulse': 1500})
    assert g.observe(record(1., 3), camera_xy=[0., 0.], robot_id='r1') == []
    assert g.decisions[-1]['reason'] == 'unsettled'


def test_bad_match_does_not_insert_and_old_submap_expires_without_certainty_reset():
    g = CorrectedOdomGrid('r1', settle_s=None)
    g.observe(record(0., 1), camera_xy=[0., 0.], robot_id='r1')
    before = copy.deepcopy(g.cells)
    g.observe(record(2., 2, CORNER+[-1.5, 0.]), camera_xy=[0., 0.], robot_id='r1')
    assert g.decisions[-1]['status'] == 'rejected'
    assert g.cells == before
    g.odom.command({'t': 2., 'kind': 'arm', 'servo_id': 1, 'pulse': 1500})
    cov = g.odom.covariance.copy()
    g.observe(record(20., 3), camera_xy=[0., 0.], robot_id='r1')
    assert g.decisions[-1]['status'] == 'bootstrap'
    assert g.decisions[-1]['reference_frames'] == []
    assert g.submap_id == 2
    assert np.all(np.diag(g.odom.covariance) >= np.diag(cov))


def test_gt_fields_and_peer_memory_reports_do_not_change_pose_or_grid():
    memories = [SelfWallMemory('r1', self_map='odom_grid_v1', pose_correction='own_map_csm_v1',
                               self_map_options={'settle_s': None}) for _ in range(2)]
    for i, memory in enumerate(memories):
        command = {'t': 0., 'kind': 'drive', 'forward': .1, 'turn': .02, 'duration_s': 1.}
        if i:
            command.update(true_pose=[999, 999, 999], peer_command=[999, 999])
        memory.command(command)
        memory.observe_wall(record(1., 1), camera_xy=[0., 0.], robot_id='r1')
        if i:
            memory.observe({'observation_id': 'peer', 'cargo': [], 'peer_reports': {'map': [999]}}, 1.)
    assert memories[0].self_map.export() == memories[1].self_map.export()
    with pytest.raises(ValueError, match='NEEDS_SELF_MAP'):
        SelfWallMemory('r1', pose_correction='own_map_csm_v1')
    with pytest.raises(ValueError, match='UNKNOWN_POSE'):
        SelfWallMemory('r1', pose_correction='mcl')
    assert len(memories[0].snapshot()['self_map_text'].encode()) <= 384


def test_noise_covariance_grows_from_own_loaded_lateral_turn_commands():
    g = CorrectedOdomGrid('r1', settle_s=None)
    prior = g.odom.covariance.copy()
    g.odom.command({'t': 0., 'kind': 'initial_servo_command', 'pulses': {1: 1500}})
    g.odom.command({'t': 0., 'kind': 'mecanum', 'forward': .1, 'left': .1, 'turn': .1, 'duration_s': 1.})
    g.odom.advance(1.)
    assert np.linalg.eigvalsh(g.odom.covariance).min() > 0
    assert np.all(np.diag(g.odom.covariance) > np.diag(prior))
    with pytest.raises(ValueError, match='NON_MONOTONIC'):
        g.odom.advance(.5)
    with pytest.raises(ValueError, match='CSM_OPTION'):
        CSMOptions(field_resolution_m=0.)


def test_cached_cartesian_contacts_keep_float_geometry_and_validate():
    g = CorrectedOdomGrid('r1', settle_s=None)
    g.observe_contacts(t=0., frame_id=1, segments=CORNER, camera_xy=[0., 0.], robot_id='r1')
    assert g.ledger[0]['segments'] == CORNER.tolist()
    with pytest.raises(ValueError, match='CONTACTS'):
        g.observe_contacts(t=1., frame_id=2, segments=[[[float('nan'), 0.], [1., 0.]]],
                           camera_xy=[0., 0.], robot_id='r1')
