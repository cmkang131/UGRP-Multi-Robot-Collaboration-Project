import copy
import cv2
import numpy as np
import pytest
from harness import s2_extrinsic_targets as t
from harness.zone_final_pair_camera import floor_camera


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


def test_calibration_jig_board_has_no_contacts_or_welds():
    import xml.etree.ElementTree as ET
    from sim.s2_extrinsic_capture import board_xml
    root=ET.fromstring(board_xml('<mujoco><asset/><worldbody/></mujoco>'))
    assert not root.findall('.//equality')
    assert len(root.findall('.//geom'))==55
    assert all(g.get('contype')==g.get('conaffinity')=='0' for g in root.findall('.//geom'))
