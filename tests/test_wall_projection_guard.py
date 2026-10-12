"""Pinhole sign, map input boundary and frozen legacy bytes; no simulator."""
import json
import math
from pathlib import Path
import types

import numpy as np
import pytest

from harness.self_wall_memory import SelfWallMemory
from harness.wall_projection_guard import filter_segments, floor_depths

ROT = np.array([[0., 0., 1.], [-1., 0., 0.], [0., -1., 0.]])
ORIGIN = np.array([.16, 0., .2])
FRONT = [[2., -.4], [2., .4]]
BACK = [[-1., -.4], [-1., .4]]


def rec(segments, t=1., frame=1):
    return {'t_sim': t, 'view_index': frame, 'posture': 'other', 'load': False,
            'seg': [[math.hypot(*a), math.atan2(a[1], a[0]), math.hypot(*b), math.atan2(b[1], b[0]), None]
                    for a,b in segments]}


def test_standard_forward_ray_and_behind_intersection():
    z, t, valid = floor_depths([FRONT, BACK], ORIGIN, ROT)
    np.testing.assert_allclose(z, t)
    np.testing.assert_equal(valid, [[True,True],[False,False]])
    assert (z[1] < 0).all()
    kept, log = filter_segments([FRONT,BACK], wall_projection_guard='positive_depth_v1', camera_origin=ORIGIN, camera_rotation=ROT)
    assert kept == [FRONT] and log['rejected_segments'] == 1
    assert log['segments'][1]['reason'] == 'nonpositive_depth_or_ray_t'


def test_horizon_zero_nonfinite_and_straddling_segment_are_not_clipped():
    # Optical Z=0, nonfinite XY, and a face crossing the optical plane.
    bad = [[[.16,0.],[.16,1.]], [[float('nan'),0.],[2.,0.]], [FRONT[0],BACK[1]]]
    kept, log = filter_segments(bad, wall_projection_guard='positive_depth_v1', camera_origin=ORIGIN, camera_rotation=ROT)
    assert kept == [] and log['rejected_segments'] == 3
    json.dumps(log, allow_nan=False)


def test_guard_uses_forward_ray_not_chassis_x_or_trace_coordinate():
    yaw = math.pi
    r = np.array([[math.cos(yaw), -math.sin(yaw),0.],[math.sin(yaw),math.cos(yaw),0.],[0.,0.,1.]])
    _, _, valid = floor_depths([BACK,FRONT], r@ORIGIN, r@ROT)
    np.testing.assert_equal(valid, [[True,True],[False,False]])


def test_no_floor_distance_when_camera_on_plane_and_off_is_inert():
    _, _, valid = floor_depths([FRONT], [.16,0.,0.], ROT)
    assert not valid.any()
    nonsense = object()
    kept, log = filter_segments(nonsense, camera_origin=nonsense, camera_rotation=nonsense)
    assert kept is nonsense and log is None
    with pytest.raises(ValueError, match='UNKNOWN'):
        filter_segments([FRONT], wall_projection_guard='oops')
    with pytest.raises(ValueError, match='CAMERA_GEOMETRY'):
        filter_segments([FRONT], wall_projection_guard='positive_depth_v1')


@pytest.mark.parametrize('option', ['off','own_map_csm_v1','own_map_csm_v2','own_map_csm_prob_v1','own_map_rbpf_v1'])
def test_memory_filters_hit_and_free_evidence_and_all_rejected_advances_time(option):
    args = {'self_map':'odom_grid_v1', 'pose_correction':option, 'self_map_options':{'settle_s':None}}
    guarded = SelfWallMemory('r1', wall_projection_guard='positive_depth_v1', **args)
    reference = SelfWallMemory('r1', **args)
    guarded.observe_wall(rec([BACK]), camera_xy=ORIGIN[:2], robot_id='r1', camera_origin=ORIGIN, camera_rotation=ROT)
    reference.self_map.odom.advance(1.)
    reference.self_map.seen.add((1.,1))
    assert guarded.self_map.cells == {} and guarded.self_map.frames == 0
    assert guarded.self_map.odom.t == 1.
    kwargs = {'camera_xy':ORIGIN[:2], 'robot_id':'r1'}
    guarded.observe_wall(rec([FRONT,BACK],2.,2), **kwargs, camera_origin=ORIGIN,camera_rotation=ROT)
    reference.observe_wall(rec([FRONT],2.,2), **kwargs)
    assert json.dumps(guarded.self_map.export()) == json.dumps(reference.self_map.export())
    before = json.dumps([guarded.self_map.export(), guarded.projection_guard_events])
    guarded.observe_wall(rec([FRONT,BACK],2.,2), **kwargs)
    assert json.dumps([guarded.self_map.export(), guarded.projection_guard_events]) == before
    with pytest.raises(ValueError, match='PEER_INPUT'):
        guarded.observe_wall(rec([FRONT],3.,3), camera_xy=ORIGIN[:2],robot_id='r2')


@pytest.mark.parametrize('mode', ['off','own_map_csm_v1','own_map_csm_v2','own_map_csm_prob_v1','own_map_rbpf_v1'])
def test_explicit_and_default_off_match_frozen_before_guard_bytes(mode):
    old = types.ModuleType('before_guard')
    exec((Path(__file__).parent/'fixtures/self_wall_memory_before_projection_guard.py.txt').read_text(),old.__dict__)
    args = {'self_map':'odom_grid_v1','pose_correction':mode,'self_map_options':{'settle_s':None},'clock':lambda:9.}
    memories = [old.SelfWallMemory('r1',**args),SelfWallMemory('r1',**args),
                SelfWallMemory('r1',**args,wall_projection_guard='off')]
    for i in range(3):
        for memory in memories:
            memory.command({'t':float(i),'kind':'drive','forward':.01,'turn':.01,'duration_s':.2})
            memory.observe_wall(rec([FRONT,BACK],float(i),i),camera_xy=ORIGIN[:2],robot_id='r1')
        serial = [json.dumps([m.snapshot(),m.self_map.export()]).encode() for m in memories]
        assert serial[0] == serial[1] == serial[2]


def test_on_requires_consistent_camera_geometry_and_map():
    with pytest.raises(ValueError,match='NEEDS_SELF_MAP'):
        SelfWallMemory('r1',wall_projection_guard='positive_depth_v1')
    m = SelfWallMemory('r1',self_map='odom_grid_v1',wall_projection_guard='positive_depth_v1')
    with pytest.raises(ValueError,match='CAMERA_GEOMETRY'):
        m.observe_wall(rec([FRONT]),camera_xy=[0.,0.],robot_id='r1')
    with pytest.raises(ValueError,match='FRAME_MISMATCH'):
        m.observe_wall(rec([FRONT]),camera_xy=[0.,0.],robot_id='r1',camera_origin=ORIGIN,camera_rotation=ROT)
    assert m.self_map.cells == {} and m.projection_guard_events == []


def replay_module():
    import importlib.util
    path = Path(__file__).resolve().parents[1]/'experiments/2026-10-05-ego-wall-map-probe/code/projection_guard_replay.py'
    spec = importlib.util.spec_from_file_location('projection_guard_replay_test',path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_frozen_replay_preserves_estimates_and_no_truth_input(monkeypatch):
    module = replay_module()
    monkeypatch.setattr(module,'own_camera',lambda frame:(ORIGIN,ROT))
    row = {'frame_id':1,'t':1.,'pose':[.8,.2,.1],'camera':ORIGIN[:2].tolist(),'segments':[FRONT,BACK]}
    frames = {1:{'frame_id':1,'sim_time':1.,'robot_id':'r1','camera':'robot_cam'}}
    disabled,_ = module.guarded_rows([row],frames,'r1','off')
    kept,logs = module.guarded_rows([row],frames,'r1','positive_depth_v1')
    assert disabled == [row]
    assert kept[0]['pose'] == row['pose'] and kept[0]['segments'] == [FRONT]
    assert row['segments'] == [FRONT,BACK]
    assert logs[0]['rejected_segments'] == 1
    rebuilt = module.rebuild('r1',kept)
    direct = module.base.OdomGrid('r1')
    direct.insert(module.base.transform([ORIGIN[:2]],row['pose'])[0],[module.base.transform(FRONT,row['pose'])])
    assert rebuilt.export()['cells'] == direct.export()['cells']


def test_preregistered_precision_and_recall_gate_boundaries():
    module = replay_module()
    ref = {'precision_015':.5,'recall_visible':.7}
    kwargs = dict(behind_false_cells=0.,invalid_endpoints=0,golden={'same':True},pose_fixed=True)
    checks = module.criterion(ref,{'precision_015':.5,'recall_visible':.68},**kwargs)
    assert all(checks.values())
    assert not module.criterion(ref,{'precision_015':.49,'recall_visible':.7},**kwargs)['precision_nondecrease']
    assert not module.criterion(ref,{'precision_015':.6,'recall_visible':.679},**kwargs)['visible_recall_loss_at_most_2pp']
