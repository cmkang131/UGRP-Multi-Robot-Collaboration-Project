import copy
import json
import numpy as np
import pytest
from harness.self_pose_graph import rebuild
from harness.self_wall_validation import OPTION,validated_grid


def scans(positions):
    return [dict(robot_id='r3',t=i,frame_id=i,pose=[x,0,0],camera=[0,0],
        segments=[[[2-x,-.1],[2-x,.1]]],insertion_weights=[.7]) for i,x in enumerate(positions)]


def apply(rows):
    grid=rebuild('r3',rows).export()
    return validated_grid(grid,rows,robot_id='r3',wall_validation=OPTION)


def test_strict_open3d_threshold_and_no_duplicate_view_support():
    for poses in ([0,0,0,0,0],[0,.2,.4]):
        grid,evidence=apply(scans(poses))
        assert evidence['confirmed']==0 and not any(c[2]>0 for c in grid['cells'])
    grid,evidence=apply(scans([0,.2,.4,.6]))
    assert evidence['confirmed']>0 and any(c[2]>0 for c in grid['cells'])
    assert all(c['weight']==4 for c in evidence['cells'])


def test_free_clearing_resets_support_and_does_not_turn_unknown_into_free():
    rows=scans([0,.2,.4,.6])
    # Repeated farther returns carve away the old obstacle.
    for i in range(4,16):rows.append(dict(robot_id='r3',t=i,frame_id=i,pose=[0,0,0],camera=[0,0],
        segments=[[[3,-.3],[3,.3]]],insertion_weights=[1.]))
    grid,evidence=apply(rows)
    assert sum(e['cleared_support'] for e in evidence['events'])>0
    old=rebuild('r3',rows).export()
    assert [c for c in grid['cells'] if c[2]<=0]==[c for c in old['cells'] if c[2]<=0]
    assert evidence['confirmed']==0


def test_default_off_bytes_and_on_input_immutability_peer_mismatch():
    rows=scans([0,.2,.4,.6]);original=rebuild('r3',rows).export()
    encoded=json.dumps(original).encode();lineage=copy.deepcopy(rows)
    out,support=validated_grid(original,None,robot_id='ignored')
    assert out is original and support is None and json.dumps(out).encode()==encoded
    validated_grid(original,rows,robot_id='r3',wall_validation=OPTION)
    assert json.dumps(original).encode()==encoded and rows==lineage
    with pytest.raises(ValueError,match='PEER'):validated_grid(original,rows,robot_id='r2',wall_validation=OPTION)
    bad=copy.deepcopy(original);bad['cells'][0][2]+=.1
    with pytest.raises(ValueError,match='MISMATCH'):validated_grid(bad,rows,robot_id='r3',wall_validation=OPTION)


def test_memory_off_golden_and_confirmed_map_snapshot():
    from harness.self_wall_memory_robust import SelfWallMemory as Old
    from harness.self_wall_memory_validation import SelfWallMemory as New
    opts=dict(self_map='odom_grid_v1',pose_correction='own_map_csm_v2')
    a,b=Old('r3',**opts),New('r3',wall_validation='off',**opts)
    rows=scans([0,.2,.4,.6])
    for m in (a,b):
        m._graph_view=rebuild('r3',rows)
        m.pose_graph_result=dict(ledger=copy.deepcopy(rows))
    assert json.dumps(a.snapshot()).encode()==json.dumps(b.snapshot()).encode()
    c=New('r3',wall_validation=OPTION,**opts)
    c._graph_view=rebuild('r3',rows);c.pose_graph_result=dict(ledger=rows)
    s=c.snapshot()
    assert s['self_map_support']['confirmed']>0
    assert 'walls none yet' not in s['self_map_text']
