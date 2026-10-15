"""Numerical camera/route recovery checks: no MuJoCo or rendering."""
import math
from types import SimpleNamespace
import cv2
import numpy as np
import pytest
from sim.destination_visual_acquire import floor_patch, ellipse_candidates, DestinationAcquire, CHI2_XY_95
from sim.grasp_act_solo_lookback import project
from sim.solo_carry_to_zone import CarryToZone
from sim.solo_carry_pose import task_start
from harness.selfmap4_geometry import static_input


def test_empty_colour_and_foreign_colour_cannot_acquire():
    p={1:1500,3:777,4:2053,5:1646,6:1500}
    for bgr in (np.zeros((480,640,3),np.uint8),np.full((480,640,3),100,np.uint8)):
        xy,r=floor_patch(bgr,p,'A',(.5,.5))
        assert xy is None and r['reason']=='destination_colour_absent'


def test_homography_feature_is_camera_local_and_held_mask_excludes_it():
    p={1:1500,3:777,4:2053,5:1646,6:1500}
    frame=np.zeros((480,640,3),np.uint8)
    # Analytic projection of a known plane into a synthetic test image.
    corners=np.array([[x,y,0] for x,y in ((.3,-.08),(.5,-.08),(.5,.08),(.3,.08))])
    uv,front=project(corners,p);assert front.all()
    bgr=cv2.cvtColor(np.uint8([[[12,180,180]]]),cv2.COLOR_HSV2BGR)[0,0]
    cv2.fillConvexPoly(frame,np.rint(uv).astype(np.int32),tuple(map(int,bgr)))
    xy,r=floor_patch(frame,p,'A',(.5,.5))
    assert xy is not None and .28<xy[0]<.52 and abs(xy[1])<.03
    hidden,r=floor_patch(frame,p,'A',(.5,.5),excluded=np.ones((480,640),bool))
    assert hidden is None


def test_covariance_ellipse_is_finite_rotation_aware_and_deterministic():
    a=ellipse_candidates([2,3,1],np.diag([1,.25,.1]),(.3,.4))
    assert a and a==ellipse_candidates([2,3,1],np.diag([1,.25,.1]),(.3,.4))
    for x,y in a:assert (x-2)**2+4*(y-3)**2<=CHI2_XY_95+1e-8
    assert ellipse_candidates([0,0,0],np.zeros((3,3)),(.3,.4))==[]
    with pytest.raises(ValueError):ellipse_candidates([0,0,0],np.diag([-1,1,1]),(.3,.4))


def test_default_has_no_acquisition_and_command_issue_only_counts_turn():
    static,_=static_input();c=CarryToZone(static,'A',start=task_start(static))
    assert c.destination_acquire is None and not c.carry_relocalize_v1
    q=DestinationAcquire(c);c.destination_acquire=q
    before=c.loc.pose[:];q.issue([.3,.1,.05]);assert q.turn==pytest.approx(.05)
    assert c.loc.pose==before and q.record()['truth_inputs']==0


def test_held_scan_never_fabricates_fix_or_shrinks_covariance():
    static,_=static_input();c=CarryToZone(static,'A',start=task_start(static))
    c.started=0;c.goal=(1,1);c.loc.own.P=np.eye(3)
    q=DestinationAcquire(c);P=c.loc.own.P.copy();fix=c.loc.fixes
    assert q.relocalize_step(1)==(0,0,.1)
    q.issue([0,0,2*math.pi]);assert q.relocalize_step(64)==(0,0,0)
    np.testing.assert_array_equal(P,c.loc.own.P);assert c.loc.fixes==fix
    assert q.relocalize_step(65) is None and q.relocalizations==1

@pytest.mark.parametrize('enabled',[False,True])
def test_teacher_arrival_enters_acquisition_only_when_opted_in(enabled):
    from sim.grasp_act_solo_teacher import SoloTeacher, PROFILE
    static,_=static_input();c=CarryToZone(static,'A',start=task_start(static),now=1.)
    c.goal=tuple(c.loc.pose[:2]);c.slot=tuple(c.region['center_m']);c.grip_xy=(.2,0);c.started=0.
    if enabled:c.destination_acquire=DestinationAcquire(c)
    pwm={1:1500,3:777,4:2053,5:1646,6:1500}
    t=SoloTeacher('red','west',pwm,profile=PROFILE,held_object_hidden_v1=True,
        rgb_lift_mode='solo_lift_lookback_v1',solo_carry_to_zone_v1=True,carry=c)
    t.skill_started=0.;t.phase='carry_to_zone';t.phase_t=0.;t.holding=True
    t.step(1.)
    assert t.phase==('destination_acquire' if enabled else 'zone_place_view')
    if enabled:
        c.destination_acquire.step=lambda *a:((0,0,0),True,None)
        t.step(1.1,own_rgb=lambda:np.zeros((480,640,3),np.uint8))
        assert t.phase=='zone_place_view' and t.holding
