"""Connectivity regression: do not jump past a rejected first boundary."""
import numpy as np
import pytest
from harness.wall_bottom_connected import candidate_mask, OPTION


def synthetic(edges, *, masked=None, self_top=20):
    top=np.zeros((20,1),int)
    for edge in edges:top[edge:,0]=edge
    rows=np.arange(18,2,-1)[:,None]
    valid=np.ones((20,1),bool)
    if masked is not None:valid[masked]=False
    return rows[:,0],candidate_mask(top,rows,valid,np.array([self_top]))[:,0]


def test_only_first_boundary_band_no_upper_patch_fallback():
    rows,mask=synthetic([5,6,12,13,14])
    assert rows[mask].tolist()==[14,13,12]
    wall_test=rows<10  # first boundary fails wall test; patch above passes
    assert not (mask & wall_test).any()


def test_self_occlusion_and_internal_invalid_gap_are_not_floor():
    assert not synthetic([5],self_top=16)[1].any()
    assert not synthetic([5],masked=10)[1].any()
    assert not synthetic([])[1].any()
    # Only external remap padding can be cropped; first real boundary remains.
    rows,mask=synthetic([5,6],masked=slice(17,20))
    assert rows[mask].tolist()==[6,5]


def test_public_option_off_matches_prior_rgb_bytes():
    import json
    from test_wall_contact_types import fixture
    from harness.active_wall_vision import observe
    from harness.self_wall_segment_points import contact_points
    _,image,servo=fixture()
    for fn in (observe,contact_points):
        assert json.dumps(fn(image,servo)).encode()==json.dumps(fn(image,servo,contact_rule='off')).encode()
        with pytest.raises(ValueError,match='UNKNOWN_CONTACT_RULE'):
            fn(image,servo,contact_rule='bad')
        with pytest.raises(ValueError,match='REQUIRES_ORIGINAL'):
            fn(image,servo,contact_rule=OPTION,wall_detector='appearance_contact_v1')
    # On may discard old contacts but must not create an upper-edge alternative.
    old=contact_points(image,servo);new=contact_points(image,servo,contact_rule=OPTION)
    assert set(new['columns'])<=set(old['columns'])
    before=dict(zip(old['columns'],old['points']))
    assert all(point==before[col] for col,point in zip(new['columns'],new['points']))


def test_empty_observations_cannot_create_multiview_support():
    from harness.self_pose_graph import rebuild
    from harness.self_wall_pr import grid_support,segment_support,apply,OPTION as SUPPORT
    from harness.self_wall_segments import build_segment_map
    ll=[dict(robot_id='r3',frame_id=1,t=1.,pose=[0,0,0],camera=[0,0],segments=[],insertion_weights=[])]
    observations={1:dict(points=[],covariances=[],pose_covariance=np.eye(3).tolist())}
    grid=rebuild('r3',ll).export()
    segments=build_segment_map(ll,observations,robot_id='r3',wall_map='segments_v1')
    nonempty=[r for r in ll if r['segments']]
    for kind,base,support in [('grid',grid,grid_support(grid,nonempty,robot_id='r3')),
                              ('segments',segments,segment_support(segments,nonempty,robot_id='r3'))]:
        result=apply(base,support,wall_validation=SUPPORT,min_views=1,min_angle_deg=30)
        assert not result['cells' if kind=='grid' else 'segments']
