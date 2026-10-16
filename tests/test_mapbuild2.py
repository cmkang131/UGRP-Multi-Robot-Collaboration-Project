import numpy as np
from scripts.mapbuild2_capture import stimulus


def test_issued_stimulus_preserves_calibrated_pulse_durations():
    tape=np.asarray([stimulus(i/100) for i in range(400)])
    active=np.flatnonzero(np.any(tape!=0,axis=1))
    assert active.tolist()==list(range(100,110))+list(range(200,206))+list(range(300,310))
    assert tape[100].tolist()==[.35]*4
    assert tape[200].tolist()==[-.35,.35,.35,-.35]
    assert tape[300].tolist()==[-.35,.35,-.35,.35]
    assert not np.any(tape[310:])


def test_standard_orb_diagnostic_reports_real_pair_counts_and_unknowns():
    from scripts.mapbuild2_analyze import pipeline
    from harness.active_camera import SEARCH
    rng=np.random.default_rng(123)
    image=rng.integers(0,256,(480,640,3),dtype=np.uint8)
    import cv2
    after=cv2.warpAffine(image,np.float32([[1,0,2],[0,1,1]]),(640,480))
    frames=[dict(frame_id=i,servo=SEARCH) for i in range(2)]
    images={0:{'jpg':image},1:{'jpg':after}}
    rows=pipeline(images,frames)
    assert len(rows)==1 and rows[0]['ratio_n']>=5
    assert rows[0]['features_a']<=500
    frames[0]['servo']={**SEARCH,1:1500}
    assert pipeline(images,frames,masked=True)[0]['reason']=='unqualified_camera'


def test_evaluation_raster_retains_thin_walls_and_rotated_start():
    from scripts.mapbuild2_map_eval import raster,intersects
    static=dict(bounds_m=[-1,1,-1,1],obstacles=[dict(id='wall',kind='wall',center_m=[0,0],half_extents_m=[.025,1])],
        regions={},passages=[])
    truth=raster(static,[0,0,np.pi/4])
    assert any(label=='occupied' for _,_,label in truth['cells'])
    assert len(truth['wall'])>0
    assert intersects([[0,0],[.2,0]],0,.1,static['obstacles'][0]).tolist()==[True,False]


def test_camera_evaluation_never_qualifies_closed_command():
    from scripts.mapbuild2_camera_eval import nominal_unqualified
    from harness.active_camera import SEARCH
    from harness.servo_camera_fk import transform_from_commands
    closed={**SEARCH,1:1500}
    assert transform_from_commands(closed,camera_pose='servo_fk_v1')[0] is None
    for a,b in zip(nominal_unqualified(SEARCH),nominal_unqualified(closed)):
        np.testing.assert_array_equal(a,b)
