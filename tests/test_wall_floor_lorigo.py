"""Paper window counting/median, thin-line robustness and unchanged default ABI."""
import json
import numpy as np
import pytest
from harness.wall_floor_lorigo import window_histogram,features,boundary_arrays,OPTION,Diagnostics


def test_integral_counts_match_explicit_windows_and_ignore_invalid_hs():
    b=np.arange(64*64).reshape(64,64)%32;b[::3,::2]=-1
    h=window_histogram(b)
    assert h.shape==(55,45,32)
    for y,x in [(0,0),(22,14),(54,44)]:
        z=b[y:y+10,x:x+20].ravel();z=z[z>=0]
        np.testing.assert_array_equal(h[y,x],np.bincount(z,minlength=32))


def test_single_row_unknown_colour_is_not_a_pixel_veto():
    b=np.full((64,64),10);b[35]=20
    h=window_histogram(b)
    support=np.ones((64,64),bool);own=np.zeros_like(support)
    module,fused,_,distance,_=boundary_arrays([h,h,h,h,h],support,own)
    assert distance[1].max()==80  # two count histograms, one altered 20-pixel row
    assert not module.any() and not fused.any()  # strict >80, no bin veto


def test_gray_checker_and_lighting_do_not_change_normalized_colour():
    y,x=np.indices((64,64));a=np.where(((x//9+y//9)%2)==0,70,160).astype(np.uint8)
    a[32]=110;a[:,30:32]=120  # antialiased grey boundaries
    rgb=np.repeat(a[...,None],3,axis=2)
    fs,_=features(rgb)
    assert np.unique(fs[1]).tolist()==[10] and np.unique(fs[2]).tolist()==[10]
    assert np.all(fs[3]==-1) and np.all(fs[4]==-1)
    _,fused,_,_,_=boundary_arrays([window_histogram(f) for f in fs],np.ones((64,64),bool),np.zeros((64,64),bool))
    assert not fused.any()  # gradient alone cannot outvote two colour modules


def test_broad_colour_obstacle_has_boundary_and_nearest_one_wins():
    a=np.full((64,64,3),120,np.uint8);a[:30]=[170,70,50];a[:10]=[20,200,20]
    fs,_=features(a)
    m,fused,_,_,_=boundary_arrays([window_histogram(f) for f in fs],np.ones((64,64),bool),np.zeros((64,64),bool))
    assert np.all((fused>=28)&(fused<=34))
    np.testing.assert_array_equal(fused,np.median(m,axis=0))


def test_masked_reference_abstains_without_jumping_self():
    h=window_histogram(np.ones((64,64),int));support=np.ones((64,64),bool)
    own=np.zeros_like(support);own[60:]=True
    m,f,_,_,reason=boundary_arrays([h]*5,support,own)
    assert not f.any() and set(reason)=={'self_reference'}
    support[:]=False
    assert set(boundary_arrays([h]*5,support,own)[-1])=={'no_valid_reference'}


def test_real_rgb_option_stateless_and_off_bytes():
    from test_wall_contact_types import fixture
    from harness.active_wall_vision import observe
    from harness.self_wall_segment_points import contact_points
    _,image,servo=fixture();state=Diagnostics()
    for fn in (observe,contact_points):
        old=json.dumps(fn(image,servo)).encode()
        assert old==json.dumps(fn(image,servo,contact_rule='off',contact_state=state)).encode()
        result=fn(image,servo,contact_rule=OPTION,contact_state=state)
        assert result==fn(image,servo,contact_rule=OPTION)
        assert state.last_result['diagnostics']['module_rows']
        with pytest.raises(ValueError,match='REQUIRES_ORIGINAL'):
            fn(image,servo,contact_rule=OPTION,wall_detector='appearance_contact_v1')
