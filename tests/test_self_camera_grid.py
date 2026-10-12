import copy
import json
import math

import numpy as np
import pytest

from harness.self_camera_grid import CameraGrid, install, OPTION
from harness.self_wall_memory_robust import SelfWallMemory
from harness.rbpf_motion_gate import install as gate, OPTION as GATE
from harness.wall_confidence import weighted_insert


def packet(t=0., fid=0, **kw):
    return dict(t=t, frame_id=fid, robot_id='r3', camera_xy=[0., 0.],
        segments=[[[1.05, .02], [1.05, .08]]], pose=[0., 0., 0.],
        covariance=np.eye(3)*.01, settled=True, **kw)


def test_inverse_sensor_frame_dedup_hit_wins_clamp_and_free():
    g = CameraGrid('r3')
    r = packet()
    g.integrate(**r)
    assert g.cells[(10, 0)] == pytest.approx(math.log(.7/.3))
    assert g.cells[(0, 0)] == pytest.approx(math.log(.4/.6))
    before = copy.deepcopy(g.cells)
    assert not g.integrate(**r) and g.cells == before and g.frames == 1
    for i in range(1, 30):
        g.integrate(**packet(i, i))
    assert g.cells[(10, 0)] == g.hi and g.cells[(0, 0)] == g.lo
    for i in range(30, 70):
        r = packet(i, i); r['segments'] = [[[2.05, .02], [2.05, .08]]]
        g.integrate(**r)
    assert g.cells[(10, 0)] == g.lo
    assert len(g.ledger) == 70


def test_own_se2_pose_not_static_map_and_weighted_primitive_identical():
    from harness.self_odom_grid import OdomGrid, transform
    g = CameraGrid('r3'); baseline = OdomGrid('r3')
    r = packet(weights=[.3]); r['pose'] = [2., 3., math.pi/2]
    raw = copy.deepcopy(r)
    g.integrate(**r)
    weighted_insert(baseline, transform([r['camera_xy']], r['pose'])[0],
                    [transform(s, r['pose']) for s in r['segments']], [.3])
    assert g.cells == baseline.cells
    np.testing.assert_array_equal(r['covariance'], raw['covariance'])
    assert g.ledger[0]['pose'] == r['pose']


def test_settling_range_peer_and_future_snapshot():
    g = CameraGrid('r3'); r = packet(); r['settled'] = False
    assert not g.integrate(**r)
    r = packet(1., 1); r['segments'] = [[[4.1, 0.], [4.1, .1]]]
    assert not g.integrate(**r)
    r = packet(2., 2); r['robot_id'] = 'r2'
    with pytest.raises(ValueError, match='PEER'): g.integrate(**r)
    g.integrate(**packet(2., 2))
    snap = json.dumps(g.export(), sort_keys=True)
    frozen = copy.deepcopy(g.export())
    g.integrate(**packet(3., 3))
    assert json.dumps(frozen, sort_keys=True) == snap
    with pytest.raises(ValueError, match='NON_MONOTONIC'): g.integrate(**packet(1.5, 4))
    assert g.rejected['unsettled'] == g.rejected['range_segments'] == 1
    assert g.frames == 2


def test_public_contact_and_record_apis_keep_estimator_bytes_but_map_gated_frames():
    kw = dict(self_map='odom_grid_v1', pose_correction='own_map_rbpf_v1',
              self_map_options=dict(settle_s=None), pose_correction_options=dict(particles=30))
    memories = [SelfWallMemory('r3', **kw), SelfWallMemory('r3', map_update='off', **kw),
                SelfWallMemory('r3', map_update=OPTION, **kw)]
    grids = [gate(m.self_map, rbpf_update=GATE) for m in memories]
    frozen = lambda g: json.dumps([g.export(), g.ledger, g.decisions, g.rng.bit_generator.state], sort_keys=True)
    for fid in range(3):
        for grid in grids:
            grid.observe_contacts(t=float(fid)*.2, frame_id=fid, robot_id='r3',
                camera_xy=[0., 0.], segments=[[[1., -.3], [1., .3]]])
        assert len({frozen(g) for g in grids}) == 1
    assert grids[-1].decisions[-1]['reason'] == 'gmapping_motion_gate'
    assert grids[-1].frames == 1 and grids[-1].camera_map.frames == 3
    rec = dict(t_sim=.6, view_index=3, posture='search', load=False,
               seg=[[1., -.3, 1., .3, None]])
    for memory in memories:
        memory.observe_wall(rec, camera_xy=[0., 0.], robot_id='r3')
    assert len({frozen(g) for g in grids}) == 1
    assert grids[-1].camera_map.frames == 4
    assert json.dumps(memories[0].snapshot()) == json.dumps(memories[1].snapshot())
    assert 'independent camera integration' in memories[-1].snapshot()['self_map_text']
    assert not hasattr(grids[0], 'camera_map')
    assert install(grids[0]) is grids[0]


def test_options_fail_closed():
    with pytest.raises(ValueError): SelfWallMemory('r3', map_update=OPTION)
    with pytest.raises(ValueError): install(None, map_update='unknown')
    g = CameraGrid('r3'); r = packet(weights=[-1.])
    with pytest.raises(ValueError): g.integrate(**r)
    assert not g.cells and not g.seen


def test_diagnosis_causes_are_exclusive_and_do_not_hide_cleared_evidence():
    from pathlib import Path
    import importlib.util
    import sys
    path = Path(__file__).parents[1]/'experiments/2026-10-08-camera-map-integration/code'
    old_path = sys.path[:]
    old_replay = sys.modules.pop('replay', None)
    try:
        sys.path.insert(0, str(path))
        spec = importlib.util.spec_from_file_location('camera_eval_test', path/'evaluate.py')
        m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
        assert [m.missing_cause(*flags)[0] for flags in
                [(False, False, False, False), (True, False, False, False),
                 (True, True, False, False), (True, True, True, False),
                 (True, True, True, True)]] == list('abcde')
        # Scoring is the unchanged egomap42 implementation, not a looser copy.
        assert 'scorer.evaluate(\'on\')' in (path/'evaluate.py').read_text()
    finally:
        sys.path[:] = old_path
        sys.modules.pop('replay', None)
        if old_replay is not None: sys.modules['replay'] = old_replay
