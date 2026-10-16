import copy
import json
import math
from pathlib import Path
from types import ModuleType
import numpy as np
import pytest
from harness.self_wall_export import export_walls, memory_text
from harness.self_pose_graph import rebuild


def fixture():
    rows = [dict(robot_id='r3',t=float(i),frame_id=i,pose=[0,0,0],camera=[0,0],
                 segments=[[[1.,-.5],[1.,.5]]]) for i in (1,2)]
    g = rebuild('r3', rows).export()
    meta = {i: dict(frame_sha256=str(i)*64, pose_covariance=np.eye(3)*.01) for i in (1,2)}
    return g, rows, meta


def test_export_provenance_nonprobability_and_immutable():
    g, rows, meta = fixture(); before = json.dumps([g,rows])
    v = export_walls(g, rows, robot_id='r3', wall_export='segments_confidence_v1',
                     observations=meta, pose_covariance=np.eye(3)*.04, now=10.)
    assert before == json.dumps([g,rows])
    assert v['coordinate_frame']['world_alignment'] is None
    assert v['coordinate_frame']['current_std_xy_m'] == .2
    assert v['audience']=='own_llm_only' and v['items']
    for item in v['items']:
        assert item['source']=='own' and item['evidence']['scan_count']==2
        assert item['evidence']['observation_ids']==['r3-obs-000001','r3-obs-000002']
        assert item['frame_sha256']=='2'*64 and item['age_s']==8.
        assert 'NOT calibrated' in item['evidence']['semantics']
    text = memory_text(v, max_bytes=512)
    assert len(text.encode())<=512 and 'support!=wall_probability' in text and 'source=own' in text
    json.dumps(v, allow_nan=False)


def test_unknown_uncertainty_never_fabricates_zero():
    g, rows, _ = fixture()
    v = export_walls(g, rows, robot_id='r3', wall_export='segments_confidence_v1')
    assert v['coordinate_frame']['current_std_xy_m'] is None
    assert v['items'][0]['observer_pose']['std_xy_m'] is None
    assert v['items'][0]['frame_sha256'] is None


def test_peer_frames_duplicates_and_invalid_covariance_refused():
    g, rows, meta = fixture()
    with pytest.raises(ValueError, match='OWN_FRAME'):
        export_walls(g, rows, robot_id='r2', wall_export='segments_confidence_v1')
    other = copy.deepcopy(rows); other[0]['robot_id']='r2'
    with pytest.raises(ValueError, match='PEER'):
        export_walls(g, other, robot_id='r3', wall_export='segments_confidence_v1')
    with pytest.raises(ValueError, match='DUPLICATE'):
        export_walls(g, rows+rows, robot_id='r3', wall_export='segments_confidence_v1')
    with pytest.raises(ValueError, match='COVARIANCE'):
        export_walls(g, rows, robot_id='r3', wall_export='segments_confidence_v1', pose_covariance=-np.eye(3))
    assert export_walls(None,None,robot_id=None) is None and memory_text(None)==''


def test_memory_off_nonempty_snapshot_bytes_rng_and_peer_isolation():
    from harness.self_wall_memory_robust import SelfWallMemory as New
    old = ModuleType('frozen_robust')
    source = Path(__file__).with_name('fixtures')/'self_wall_memory_before_export.py.txt'
    exec(compile(source.read_text(),str(source),'exec'),old.__dict__)
    kw = dict(self_map='odom_grid_v1', pose_correction='own_map_rbpf_v1',
              self_map_options=dict(settle_s=None), pose_correction_options=dict(particles=30))
    instances = [old.SelfWallMemory('r3',**kw),New('r3',**kw),New('r3',wall_export='off',**kw),
                 New('r3',wall_export='segments_confidence_v1',**kw)]
    for m in instances:
        m.observe_wall(dict(t_sim=1.,view_index=1,posture='search',load=False,
            seg=[[math.sqrt(1.25),-.463647609,math.sqrt(1.25),.463647609,None]]),
            camera_xy=[0,0],robot_id='r3')
    legacy = json.dumps(instances[0].snapshot(),sort_keys=True)
    assert all(json.dumps(m.snapshot(),sort_keys=True)==legacy for m in instances[1:3])
    enabled=instances[-1]; state=copy.deepcopy(enabled.self_map.rng.bit_generator.state)
    before=json.dumps(enabled.self_map.export(),sort_keys=True)
    snap=enabled.snapshot()
    assert 'self_wall_export_text' in snap and 'self_wall_export' not in snap
    assert state==enabled.self_map.rng.bit_generator.state
    assert before==json.dumps(enabled.self_map.export(),sort_keys=True)
    export=enabled.export_wall_memory()
    enabled.receive(dict(message_id='peer1',sender_id='r2',kind='observation',content='wall',
                         observed_ids=[],sent_sim_time=1.,wall_export={'source':'peer'}))
    assert export==enabled.export_wall_memory()
