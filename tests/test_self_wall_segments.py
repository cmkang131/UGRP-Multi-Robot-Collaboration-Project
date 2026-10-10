import json
import math
import numpy as np
import pytest
from harness.self_wall_segments import extract,merge,build_segment_map


def observation(points):
    return dict(points=np.asarray(points).tolist(),covariances=np.tile(np.eye(2)*.002**2,(len(points),1,1)).tolist(),
                pose_covariance=np.diag([.01**2,.01**2,math.radians(1)**2]).tolist())


def test_split_corner_and_preserve_door_gap():
    p=np.vstack([np.c_[np.linspace(-1,0,30),np.ones(30)],np.c_[np.zeros(30),np.linspace(1,2,30)]])
    lines=extract(p,observation(p)['covariances'],[0,0])
    assert len(lines)==2
    p=np.c_[np.r_[np.linspace(-2,-1,30),np.linspace(0,1,30)],np.ones(60)]
    lines=extract(p,observation(p)['covariances'],[0,0])
    assert len(lines)==2
    assert all(np.linalg.norm(x['ends'][1]-x['ends'][0])<1.01 for x in lines)


def test_ci_does_not_halve_repeated_correlated_covariance():
    a=dict(mean=np.array([1.,0.]),covariance=np.diag([.02,.01]),ends=np.array([[1,0],[1,1]]),points=20,frames={1})
    b={**a,'frames':{2}}
    out=merge(a,b)
    np.testing.assert_allclose(out['covariance'],a['covariance'])
    assert out['frames']=={1,2}


def test_own_axis_transforms_and_peer_is_rejected():
    p=np.c_[np.linspace(-1,1,30),np.ones(30)]
    obs={1:observation(p),2:observation(p)}
    rows=[dict(robot_id='r3',frame_id=i,camera=[0,0],pose=[.2,.1,.4]) for i in (1,2)]
    out=build_segment_map(rows,obs,robot_id='r3',wall_map='segments_v1')
    assert len(out['segments'])==1 and out['segments'][0]['observations']==2
    assert abs((out['axis_rad']-.4+math.pi/4)%(math.pi/2)-math.pi/4)<1e-6
    with pytest.raises(ValueError,match='PEER'):build_segment_map(rows,obs,robot_id='r2',wall_map='segments_v1')
    assert build_segment_map(None,None,robot_id='r3') is None


def test_off_memory_bytes_identical():
    from harness.self_wall_memory_motion import SelfWallMemory as Old
    from harness.self_wall_memory_segments import SelfWallMemory as New
    a,b=Old('r3'),New('r3',wall_map='off')
    for t in (0,1,2):
        for m in (a,b):m.observe({'cargo': [], 'robots': []},t)
        assert json.dumps(a.snapshot())==json.dumps(b.snapshot())
