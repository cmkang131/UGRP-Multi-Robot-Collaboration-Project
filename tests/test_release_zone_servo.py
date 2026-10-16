"""Offline RGB/geometry checks; no MuJoCo, rendering, or world input."""
import math
from types import SimpleNamespace

import numpy as np
import pytest

from sim.release_zone_servo import fit_rectangle, pair_choice, ZoneCenterServo


def edges(center=(1., .1), angle=.07):
    a=np.array([math.cos(angle),math.sin(angle)]); b=np.array([-a[1],a[0]]); c=np.array(center)
    fs=[]
    for n,h,t in [(a,.7,b),(-a,.7,b),(b,.3,a),(-b,.3,a)]:
        # The partial segment midpoint is deliberately NOT the edge midpoint.
        p=c-h*n+.08*t
        fs.append(dict(kind='floor_line',hue=13.,normal=n.tolist(),
                       endpoints=[(p-.075*t).tolist(),(p+.075*t).tolist()]))
    return fs


@pytest.mark.parametrize('angle',[-.13,0.,.13])
@pytest.mark.parametrize('cx',[.2,.7,1.4])
def test_partial_edges_recover_local_center_with_outlier(angle,cx):
    fs=edges((cx,-.1),angle)
    outlier=edges((cx+1.3,.8),angle)[0]
    fit=fit_rectangle([{'features':fs[:3]},{'features':[fs[0],fs[2],fs[3],outlier]}],.7,.3,13.)
    assert fit['accepted']
    assert fit['center_body_m']==pytest.approx([cx,-.1],abs=1e-7)
    assert fit['map_pose_known'] is False


def test_blank_single_axis_single_view_and_ambiguous_rectangle_rejected():
    fs=edges()
    for views in [[],[{'features':fs}], [{'features':fs[2:]},{'features':fs[2:]}],
                  [{'features':fs+edges((2.5,.1))},{'features':fs+edges((2.5,.1))}]]:
        assert not fit_rectangle(views,.7,.3,13.)['accepted']


def test_wrong_hue_and_off_zone_transverse_line_not_a_center():
    fs=edges(); fs[0]['hue']=100;fs[1]['hue']=100
    wrong=edges((1.,1.5))[0]
    assert not fit_rectangle([{'features':fs+[wrong]}]*2,.7,.3,13.)['accepted']


def test_pair_center_not_first_inside_margin_and_no_evidence_fails_closed():
    def msg(s):return {'zone_center':{'accepted':True,'shift_body_m':s}}
    robots=('r1','r2')
    choice=pair_choice({'r1':msg(.77),'r2':msg(-.75)},robots,1.)
    assert choice['action']=='shift' and choice['shift_m']==.5
    assert pair_choice({'r1':msg(-.25),'r2':msg(.26)},robots,1.)['shift_m']<0
    assert pair_choice({'r1':msg(.04),'r2':msg(-.03)},robots,1.)['action']=='lower'
    assert pair_choice({'r1':msg(.3),'r2':msg(.3)},robots,1.)['reason']=='zone_center_disagreement'
    assert pair_choice({'r1':msg(0),'r2':{}},robots,1.)['action']=='stop'


def test_image_adapter_blank_and_unqualified_camera_have_no_evidence():
    from harness import zone_pair_highpose_contract as contract
    from sim.lookaround_localization import LookaroundLocalizer,look_servo,LOOK_ARM
    static=contract.resolve('zone_wide_two_doors_final_v3')[0]
    loc=LookaroundLocalizer(static,[0,0,0],map_pose_known=False)
    servo=ZoneCenterServo(static,'zone_A',loc.camera,loc.vl.mp)
    servo.observe(np.zeros((480,640,3),np.uint8),look_servo(0,LOOK_ARM),0.)
    assert not servo.finalize([.6,0])['accepted']
    rec=servo.observe(np.zeros((480,640,3),np.uint8),{**look_servo(0),1:1500},1.)
    assert rec['reason']=='loaded_or_unknown_load_not_qualified'
    with pytest.raises(ValueError,match='640x480'):
        servo.observe(np.zeros((240,320,3),np.uint8),look_servo(0),2.)


def test_rgb_ground_edge_projection_and_center_from_two_views():
    """Synthetic pinhole RGB arrays test the adapter, without simulator imports."""
    from harness.zone_solo_cyan_landmarks import hue
    # Plane image: x in [0,2], y in [-1,1], camera points straight down.
    origin=np.array([1.,0.,1.]); rot=np.diag([1.,-1.,-1.])
    K=np.array([[300.,0,320],[0,300.,240],[0,0,1.]])
    mp=SimpleNamespace(K_INV=np.linalg.inv(K),undistort=lambda bgr:bgr)
    static={'regions':{'z':{'rgba':[.65,.35,.15,1.],'center_m':[99,99],'half_extents_m':[.3,.7]}}}
    servo=ZoneCenterServo(static,'z',SimpleNamespace(pose=lambda p:((origin,rot),None)),mp)
    yy,xx=np.indices((480,640));x=1+(xx-320)/300.;y=-(yy-240)/300.
    rgb=np.full((480,640,3),128,np.uint8)
    mask=(abs(x-1)<.7)&(abs(y-.05)<.3);rgb[mask]=[166,89,38]
    # Use a static-map colour within the established floor detector's saturation domain.
    rgb[mask]=[166,110,80];static['regions']['z']['rgba']=[166/255,110/255,80/255,1.]
    servo=ZoneCenterServo(static,'z',SimpleNamespace(pose=lambda p:((origin,rot),None)),mp)
    assert abs(servo.hue-hue([166/255,110/255,80/255]))<1e-4
    for t in [0.,1.]:servo.observe(rgb,{},t)
    fit=servo.finalize([.65,.05])
    assert fit['accepted'],fit
    assert fit['center_body_m']==pytest.approx([1.,.05],abs=.02)
    assert fit['shift_body_m']==pytest.approx(.35,abs=.02)


@pytest.mark.parametrize('cx,angle',[(-.15,-.12),(.2,.12),(.65,0),(1.2,-.12),(1.4,.12)])
def test_commanded_camera_fisheye_floor_sweep_observes_fresh_centers(cx,angle):
    """Algebraic image fixture: same optics/command FK, no physics or renderer."""
    import cv2
    from harness import zone_pair_highpose_contract as contract
    from sim.lookaround_localization import LookaroundLocalizer,look_servo,LOOK_ARM,LOOK_ARM_V2
    from sim.masterpi_camera_profile import CAMERA_FISHEYE_D
    static=contract.resolve('zone_wide_two_doors_final_v3')[0]
    loc=LookaroundLocalizer(static,[0,0,0],map_pose_known=False)
    servo=ZoneCenterServo(static,'zone_A',loc.camera,loc.vl.mp)
    yy,xx=np.indices((480,640));uv=np.c_[xx.ravel(),yy.ravel()].astype(float)
    norm=cv2.fisheye.undistortPoints(uv.reshape(-1,1,2),loc.vl.mp.K,np.array(CAMERA_FISHEYE_D)).reshape(-1,2)
    rays_camera=np.c_[norm,np.ones(len(norm))]
    axis=np.array([math.cos(angle),math.sin(angle)]);lateral=np.array([-axis[1],axis[0]])
    for arm,pans in [(LOOK_ARM_V2,(-60.,0.,60.)),(LOOK_ARM,(-35.,0.,35.))]:
        for pan in pans:
            pwm=look_servo(pan,arm);(origin,rot),_=loc.camera.pose(pwm)
            rays=rays_camera@rot.T
            with np.errstate(divide='ignore',invalid='ignore'):
                q=origin-rays*origin[2]/rays[:,2,None]
            offset=q[:,:2]-[cx,.05]
            valid=(rays[:,2]<0)&(abs(offset@axis)<.7)&(abs(offset@lateral)<.3)
            rgb=np.full((len(q),3),128,np.uint8);rgb[valid]=[166,110,80]
            servo.observe(rgb.reshape(480,640,3),pwm,len(servo.views))
    result=servo.finalize([.65,.05])
    assert result['accepted'],result
    assert result['center_body_m']==pytest.approx([cx,.05],abs=.04)
