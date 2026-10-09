import copy
import json
import cv2
import numpy as np
import pytest
from harness import s2_extrinsic_targets as t
from harness.zone_final_pair_camera import floor_camera
from test_solo_cyan_v106 import static,cal,FakePose,FakeVision,rt


def samples():
    origin, axes=t.nominal(t.HIGH)
    # Independent known synthetic camera, offset from board layout aid.
    delta,_=cv2.Rodrigues(np.array([.015,-.055,.008]))
    axes=axes@delta;origin=origin+np.array([.001,-.002,.007])
    rv,_=cv2.Rodrigues(axes.T);tv=-axes.T@origin
    rows=copy.deepcopy(t.boards(t.HIGH))
    for row in rows:
        obj=np.asarray(row['object_points_floor_m'],float)
        pix,_=cv2.fisheye.projectPoints(obj.reshape(1,-1,3),rv,tv,t.K,t.D)
        row['corners_px']=pix.reshape(-1,2).tolist()
    return rows,origin,axes


def test_pnp_uses_known_targets_and_fisheye_pixels_not_nominal_or_gt():
    rows,origin,axes=samples()
    rec,quality=t.fit(rows);got=floor_camera(rec)
    np.testing.assert_allclose(got['origin_m'],origin,atol=1e-8)
    np.testing.assert_allclose(got['rotation'],axes,atol=1e-8)
    assert quality['holdout']['rms_px']<1e-7
    rows[-1]['corners_px']=(np.asarray(rows[-1]['corners_px'])+[4,3]).tolist()
    with pytest.raises(ValueError,match='REPROJECTION_REJECTED'):t.fit(rows)


def test_real_pixel_corner_detection_and_missing_target_refusal():
    image=np.full((480,640,3),255,np.uint8)
    for y in range(6):
        for x in range(9):
            image[100+y*35:100+(y+1)*35,160+x*35:160+(x+1)*35]=(0 if (x+y)%2==0 else 255)
    points=t.detect(image)
    assert points.shape==(40,2)
    np.testing.assert_allclose(points[0],[194.5,134.5],atol=.3)
    with pytest.raises(ValueError,match='NOT_DETECTED'):t.detect(np.zeros_like(image))


def test_pose_coverage_and_board_fit_holdout_separation():
    poses=t.poses()
    assert len(poses)==len(set((s,t.key(p)) for s,p in poses))
    for pose in (t.HIGH,t.VIA_110,t.VIA_130,t.grasp_postures()[0]):
        assert ('loaded',pose) in poses and ('unloaded',pose) in poses
    for state,pose in poses:
        boards=t.boards(pose)
        assert [b['role'] for b in boards]==['fit','fit','holdout']
        assert min(np.asarray(b['object_points_floor_m'])[:,2].min() for b in boards)>0
    assert t.capture_poses() == poses
    assert t.capture_poses('real_carry_v1') == [('unloaded', {3:600,4:2200,5:1400,6:1500})]
    with pytest.raises(ValueError):t.capture_poses('loaded')


def test_calibration_jig_board_has_no_contacts_or_welds():
    import xml.etree.ElementTree as ET
    from sim.s2_extrinsic_capture import board_xml
    root=ET.fromstring(board_xml('<mujoco><asset/><worldbody/></mujoco>'))
    assert not root.findall('.//equality')
    assert len(root.findall('.//geom'))==55
    assert all(g.get('contype')==g.get('conaffinity')=='0' for g in root.findall('.//geom'))


def test_moving_target_uses_mocap_kinematics_no_step_or_render():
    mujoco=pytest.importorskip('mujoco')
    from sim.s2_extrinsic_capture import board_xml
    m=mujoco.MjModel.from_xml_string(board_xml('<mujoco><asset/><worldbody/></mujoco>'))
    d=mujoco.MjData(m);mid=int(m.body('cal_board').mocapid[0])
    assert mid>=0
    d.mocap_pos[mid]=[.2,.3,.4]
    m.geom('cal_0_0').pos[:]=[.01,.02,.03]
    mujoco.mj_forward(m,d)
    np.testing.assert_allclose(d.geom('cal_0_0').xpos,[.21,.32,.43])
    assert d.time==0


def test_default_and_explicit_off_preserve_command_and_record_bytes(static,cal):
    from harness.zone_solo_cyan_extrinsic import Runtime,Previous
    rows=[cls(static,None,None,provider_factory=lambda *a,**k:FakePose(copy.deepcopy(cal)),
        vision_factory=FakeVision,**kw) for cls,kw in
        [(Previous,{}),(Runtime,{}),(Runtime,dict(camera_calibration='off'))]]
    try:
        for r in rows:
            r.initial_commands(0.,{'r3':{1:1500,**rt.high.HIGH}})
            r.last_report=r.pose.report(1.);r.state='carry';r.receipt=True
        for now in (1.,1.05,1.1,1.2,1.65,1.8):
            actions=[r.step(now) for r in rows]
            assert len(set(json.dumps(x).encode() for x in actions))==1
            for r,commands in zip(rows,actions):
                for rid,cmd in commands:r.on_command(rid,now,cmd)
        assert len(set(json.dumps(r.record()).encode() for r in rows))==1
    finally:
        for r in rows:r.close()


def test_partial_calibration_cannot_enter_controller():
    from harness.zone_solo_cyan_extrinsic import validate,Runtime
    table=t.contract.old.hp.base.read(t.contract.ROOT/'configs/calibration/s2_camera_v3_extrinsic_v1.json')
    assert not table['load_qualified'] and not table['camera_models']['loaded']
    with pytest.raises(ValueError,match='LOADED_CAMERA_CALIBRATION_UNAVAILABLE'):validate(table)
    with pytest.raises(ValueError,match='LOADED_CAMERA_CALIBRATION_UNAVAILABLE'):
        Runtime(None,None,None,camera_calibration=t.OPTION,extrinsic_calibration=table,
            camera_profile=t.old.camera.PROFILE_ID)


def test_pf_wall_and_block_projection_share_instance_table_without_globals():
    from harness.zone_solo_cyan_extrinsic import apply
    from harness.zone_solo_cyan_vision_v106 import CyanVision
    # Synthetic test-only qualification, never a registered calibration product.
    table=t.contract.old.hp.base.read(t.contract.ROOT/'configs/calibration/s2_camera_v3_extrinsic_v1.json')
    table.update(status='MEASURED_SIM_RGB_PNP_LEVEL_FIXTURE',load_qualified=True)
    table['camera_models']['loaded'][t.key(t.HIGH)]=copy.deepcopy(table['camera_models']['unloaded'][t.key(t.HIGH)])
    c=t.contract.old
    sources=[t.old.build_provider(c.hp.resolve(c.MAP_ID)[0],c.ROOT/c.CALIBRATION,c.CALIBRATION_SHA,7) for _ in range(2)]
    try:
        a,b=sources;original=json.dumps(b.provider.calibration)
        captured=a.provider.calibration;apply(a,table)
        vision=CyanVision(a.provider.calibration)
        assert vision.calibration is captured is a.provider.calibration
        pose=rt.pose_of('inspect');a.provider.loc._pf.load.loaded=False
        cm=a.provider.loc._pf.column_model_for(pose)
        origin,axes=vision.extrinsics(pose)
        np.testing.assert_allclose(cm.origin,origin,atol=1e-12)
        np.testing.assert_allclose(cm._rot,axes.T,atol=1e-12)
        a.provider.loc._pf.load.loaded=True
        got=a.provider.loc._pf.column_model_for(t.HIGH)
        expected=floor_camera(table['camera_models']['loaded'][t.key(t.HIGH)])
        np.testing.assert_allclose(got.origin,expected['origin_m'],atol=1e-12)
        assert json.dumps(b.provider.calibration)==original
    finally:
        for s in sources:s.close()
