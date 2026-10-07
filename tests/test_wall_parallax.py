"""Analytical triangulation/covariance, degeneracy and own-input boundaries."""
import inspect
import numpy as np
import pytest
from harness import wall_parallax as p

K=np.array([[400.,0.,320.],[0.,400.,240.],[0.,0.,1.]])
R=np.array([[0.,0.,1.],[-1.,0.,0.],[0.,-1.,0.]])
ORIGIN=np.array([.08,0.,.3])


def observations(point=(2.,.3,.12),process=.0001):
    out=[]
    common=np.diag([.01,.01,.001])
    for i in range(3):
        pose=np.array([0.,i*.12,0.])
        f=np.eye(3)
        f[0,2]=-pose[1]
        cov=f@common@f.T+np.eye(3)*i*process
        c,r=p.camera(pose,ORIGIN,R)
        uv=K@r.T@(np.array(point)-c)
        out.append(dict(pose=pose,cov=cov,uv=uv[:2]/uv[2],frame_id=i))
    return out


def test_depth_is_triangulated_without_floor_height_constraint():
    for z in (.0,.12,.8):
        h=observations(point=(2.,.3,z))
        result,reason=p.triangulate(h,ORIGIN,R,K)
        assert reason=='accepted'
        np.testing.assert_allclose(result['xyz'],[2.,.06,z],atol=1e-10)
        assert 0<result['confidence']<1 and result['depth_sigma_m']>0
        assert np.linalg.eigvalsh(result['covariance']).min()>-1e-10


def test_pose_correlation_and_noise_propagation():
    h=observations(process=0.)
    a,b=h[0],h[-1]
    cov=p.joint_pose_covariance(a['pose'],a['cov'],b['pose'],b['cov'])
    assert np.linalg.eigvalsh(cov).min()>-1e-10
    assert np.any(cov[:3,3:])
    low,_=p.triangulate(h,ORIGIN,R,K)
    high,_=p.triangulate(observations(process=.01),ORIGIN,R,K)
    assert high['depth_sigma_m']>low['depth_sigma_m']
    assert high['confidence']<low['confidence']
    # A common global translation cancels in body-local triangulation.
    shifted=observations(process=0.)
    for row in shifted:row['cov'][:2,:2]+=np.eye(2)*100
    invariant,_=p.triangulate(shifted,ORIGIN,R,K)
    np.testing.assert_allclose(invariant['covariance'],low['covariance'],atol=1e-7)


def test_degenerate_bad_and_out_of_range_tracks_are_not_floor_fallbacks():
    h=observations()
    assert p.triangulate(h[:2],ORIGIN,R,K)[1]=='insufficient_views'
    repeated=[h[0],h[0],h[0]]
    assert p.triangulate(repeated,ORIGIN,R,K)[1]=='zero_baseline'
    h[1]['uv']+=10
    assert p.triangulate(h,ORIGIN,R,K)[1]=='reprojection'
    assert p.triangulate(observations(point=(-2.,.3,.1)),ORIGIN,R,K)[1]=='behind_camera'
    assert p.triangulate(observations(point=(5.,.3,.1)),ORIGIN,R,K)[1]=='beyond_4m'


def test_option_off_is_byte_identical_and_does_not_inspect_state():
    blob=b'old\x00scan\n'
    assert p.detect(blob,state=object(),und_bgr=object()) is blob
    with pytest.raises(ValueError):p.detect(blob,wall_detector=p.OPTION)
    assert p.ParallaxWallDetector('r3',intrinsic=K).option=='off'
    # No untrusted world/pose-source callback is accepted by the detector.
    names=set(inspect.signature(p.ParallaxWallDetector.observe).parameters)
    assert not names & {'truth','world','static_map','other_robot','trajectory','actuator_state'}


def test_flat_image_abstention_peer_and_duplicate_frame_rejection():
    d=p.ParallaxWallDetector('r3',intrinsic=K,wall_detector=p.OPTION)
    args=dict(und_bgr=np.zeros((480,640,3),np.uint8),robot_id='r3',frame_id=1,t=1.,
              pose=np.zeros(3),covariance=np.eye(3),camera_origin=ORIGIN,camera_rotation=R,
              columns=np.array([20.,600.]),boundary_rows=np.array([100.,100.]),servo_key=(1,2,3,4))
    result=d.observe(**args)
    assert not result['points'] and not d.tracks
    with pytest.raises(ValueError,match='MONOTONIC'):d.observe(**args)
    with pytest.raises(ValueError,match='PEER'):d.observe(**dict(args,robot_id='r2',frame_id=2,t=2.))


def test_roi_does_not_join_missing_wall_columns():
    mask=p.roi_mask((50,50),[5,15,25,35],[20,np.nan,20,20])
    assert mask[20,30] and not mask[20,10]


def test_annotation_recall_preserves_absent_points_and_deduplicates(monkeypatch):
    import sys
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    sys.path.insert(0,str(root/'experiments/2026-10-07-wall-parallax/code'))
    import replay as ev
    assert len(ev.hashes())==len(ev.FILES)  # All provenance paths exist before RGB extraction.
    monkeypatch.setattr(ev.metric,'project',lambda uv,*a:(np.zeros((len(uv),2)),np.ones(len(uv)),np.ones(len(uv),bool)))
    annotation=dict(polylines=[[[0,50],[639,50]]],ignore=[])
    empty=ev.annotate([],[],annotation,ORIGIN,R)['all']
    assert empty==dict(predicted=0,tp=0,positive=96,covered=0)
    point=dict(uv=[float(ev.COLS[10]),50.],range_m=1.)
    same=ev.annotate([point,point],[0.,0.],annotation,ORIGIN,R)['all']
    assert same==dict(predicted=2,tp=2,positive=96,covered=1)


@pytest.mark.parametrize('pixel_step',[5.,20.])
def test_real_lk_tracks_three_views_of_a_translating_textured_edge(pixel_step):
    import cv2
    d=p.ParallaxWallDetector('r3',intrinsic=K,wall_detector=p.OPTION)
    image=np.zeros((480,640,3),np.uint8)
    for x in range(180,460,35):cv2.rectangle(image,(x,210),(x+12,240),(255,255,255),-1)
    result=None
    for i in range(3):
        moved=cv2.warpAffine(image,np.array([[1.,0.,pixel_step*i],[0.,1.,0.]]),(640,480))
        result=d.observe(moved,robot_id='r3',frame_id=i,t=.1*i,pose=[0.,pixel_step/200*i,0.],
            covariance=np.eye(3)*i*.0001,camera_origin=ORIGIN,camera_rotation=R,
            columns=np.arange(2,638,6),boundary_rows=np.full(106,240.),servo_key=(1,2,3,4))
    if pixel_step==20.:
        # Periodic edges alias to backward flow. Cheirality must reject them.
        assert not result['points'] and result['counts']['behind_camera']>0
    else:
        assert result['points']
        assert all(abs(q['xyz'][0]-2.08)<.02 for q in result['points'])
