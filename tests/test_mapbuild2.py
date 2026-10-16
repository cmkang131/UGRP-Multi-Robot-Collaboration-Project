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


def test_increment_covariance_does_not_repeat_cumulative_pose_uncertainty():
    from scripts.mapbuild2_commands import increments
    from harness.active_camera import SEARCH
    frames=[dict(sequence='drive-off',frame_id=i,t=i/10,servo=SEARCH) for i in range(41)]
    rows=increments(frames,[dict(t=1.,axis='forward',value=.35,duration_s=.1)])
    assert np.count_nonzero(rows['drive-off',0]['command_covariance'])==0
    assert np.trace(rows['drive-off',12]['command_covariance'])>0
    assert np.count_nonzero(rows['drive-off',40]['command_covariance'])==0


def test_evaluation_heading_includes_roll_pitch_coupling():
    from scripts.mapbuild2_capture import quaternion_heading
    yaw,pitch,roll=.7,.3,.4
    cy,sy=np.cos(yaw/2),np.sin(yaw/2);cp,sp=np.cos(pitch/2),np.sin(pitch/2);cr,sr=np.cos(roll/2),np.sin(roll/2)
    q=[cy*cp*cr+sy*sp*sr,cy*cp*sr-sy*sp*cr,sy*cp*sr+cy*sp*cr,sy*cp*cr-cy*sp*sr]
    import pytest
    assert quaternion_heading(q)==pytest.approx(yaw)


def test_external_pose_grid_does_not_open_unused_motion_calibration(monkeypatch):
    from scripts.mapbuild2_map import new_grid
    import harness.self_odom_grid as grid
    def unavailable():raise FileNotFoundError('unused calibration must not be read')
    monkeypatch.setattr(grid,'motion_profiles',unavailable)
    assert new_grid().resolution_m==.1
