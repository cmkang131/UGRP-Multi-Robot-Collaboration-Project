"""Paper queue rules, OR histogram semantics, connected classified floor, off ABI."""
import json
import math
import numpy as np
import pytest
from harness.wall_floor_ulrich import UlrichFloorState, first_contacts, OPTION
from harness.wall_floor_boundary import hsi,histograms


def hist(a=100,b=180):
    h=np.zeros(256);i=np.zeros(256);i[[a,b]]=100
    return h,i


def test_strict_distance_and_turn_rejection_precedes_promotion():
    s=UlrichFloorState('r3');h,i=hist()
    s.update(1,[0,0,0],h,i)
    _,_,d=s.update(2,[1,0,0],h,i)
    assert d['promoted']==[]
    _,_,d=s.update(3,[1.001,0,0],h,i)
    assert d['promoted']==[1]
    s=UlrichFloorState('r3');s.update(1,[0,0,0],h,i)
    _,_,d=s.update(2,[2,0,math.radians(19)],h,i)
    assert d['rejected_turn']==[1] and d['promoted']==[]
    s=UlrichFloorState('r3');s.update(1,[0,0,math.radians(179)],h,i)
    _,_,d=s.update(2,[2,0,math.radians(-179)],h,i)
    assert d['promoted']==[1]


def test_reference_last_ten_and_or_not_sum():
    s=UlrichFloorState('r3');h,i=hist();i[100]=40
    for f in range(15):s.update(f,[f*2,0,0],h,i)
    ah,ai,d=s.update(15,[30,0,0],h,i)
    assert d['reference_frame_ids']==list(range(5,15))
    assert ai[180] and not ai[100] and not ah.any()  # ten rare bins cannot sum to support
    assert not UlrichFloorState('r2').references


def test_two_floor_colours_do_not_break_classified_connectivity():
    # This tests appearance classes, not an edge heuristic; both floor modes learned.
    image=np.full((100,200,3),100,np.uint8)
    image[50:,100:]=180;image[:20]=240
    hue,_,intensity,valid=hsi(image)
    ref=np.indices((100,200))[0]>=50
    hh,ih,h,i=histograms(hue,intensity,valid,ref)
    s=UlrichFloorState('r3');s.update(1,[0,0,0],hh,ih)
    ah,ai,_=s.update(2,[1.01,0,0],hh,ih)
    floor=~((valid & ~ah[h])|~ai[i])
    assert floor[20:].all() and not floor[:20].any()
    ids,uv,n=first_contacts(floor,np.ones_like(floor),[50,150],[100,100])
    assert uv.tolist()==[[50.,19.],[150.,19.]] and n==0


def test_boundary_does_not_jump_obstacle_at_bottom_or_invalid_gap():
    floor=np.ones((10,3),bool);floor[:3]=False;floor[-1,0]=False
    support=np.ones_like(floor);support[5,1]=False
    ids,uv,n=first_contacts(floor,support,[0,1,2],[10,10,8])
    assert len(ids)==0 and n==2  # bottom obstacle / self; invalid gap never crossed


def test_full_state_duplicate_frame_cold_start_and_off_frozen_bytes():
    from test_wall_contact_types import fixture
    from harness.active_wall_vision import observe
    from harness.self_wall_segment_points import contact_points
    _,image,servo=fixture();s=UlrichFloorState('r3')
    for fn in (observe,contact_points):
        before=json.dumps(fn(image,servo)).encode()
        assert before==json.dumps(fn(image,servo,contact_rule='off',contact_state=s)).encode()
    kw=dict(contact_rule=OPTION,contact_state=s,frame_id=1,odometry_pose=[0,0,0])
    assert contact_points(image,servo,**kw)['points']==[]
    assert observe(image,servo,**kw)['segments']==[]
    assert len(s.candidates)==1 and s.last_result['diagnostics']['reason']=='untrained'
    with pytest.raises(ValueError,match='SAME_FRAME_CHANGED'):
        contact_points(image,servo,**{**kw,'odometry_pose':[1,0,0]})
    kw.update(frame_id=2,odometry_pose=[1.01,0,0])
    result=contact_points(image,servo,**kw)
    assert s.last_result['diagnostics']['reference_frame_ids']==[1]
    assert s.last_result['diagnostics']['reason']=='classified'
    assert result==contact_points(image,servo,**kw)
    assert len(s.candidates)==1
    with pytest.raises(ValueError,match='EXPLICIT_FLOOR_STATE_REQUIRED'):
        observe(image,servo,contact_rule=OPTION)
