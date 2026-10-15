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


def test_held_scan_never_fabricates_fix_or_shrinks_covariance(monkeypatch):
    import sim.destination_visual_acquire as m
    static,_=static_input();c=CarryToZone(static,'A',start=task_start(static))
    c.started=0;c.goal=(1,1);c.loc.own.P=np.eye(3)
    monkeypatch.setattr(m,'information_views',lambda *a:dict(views=[dict(body_yaw_deg=90)]))
    q=DestinationAcquire(c);P=c.loc.own.P.copy();fix=c.loc.fixes
    assert q.relocalize_step(1,{})==(0,0,.1)
    q.issue([0,0,math.pi/2]);assert q.relocalize_step(2,{})==(0,0,0)
    assert q.relocalize_step(2.8,{})==(0,0,0)
    np.testing.assert_array_equal(P,c.loc.own.P);assert c.loc.fixes==fix
    assert q.relocalize_step(3,{}) is None and q.relocalizations==1
    assert q.events[-1]['actual_dwelled_views']==1


def test_unobservable_loaded_view_requests_existing_setdown(monkeypatch):
    import sim.destination_visual_acquire as m
    static,_=static_input();c=CarryToZone(static,'A',start=task_start(static),recovery_profile='carry5_active_localization_v1')
    c.started=0;c.goal=(1,1);c.loc.own.P=np.eye(3)
    monkeypatch.setattr(m,'information_views',lambda *a:dict(views=[],expected_gain_nats=0))
    q=DestinationAcquire(c);assert q.relocalize_step(1,{})==(0,0,0)
    assert c.recovery_reason=='reloc19_unobservable_loaded_view'
    assert q.events[-1]['blocked_object']=='static_landmarks_outside_issued_camera_fov'


def test_information_planner_uses_actual_loaded_camera_and_no_predicted_fix(monkeypatch):
    import sim.grasp_act_solo_lookback as look
    from sim.destination_visual_acquire import information_views
    static,_=static_input()
    monkeypatch.setattr(look,'project',lambda *a:(np.array([[-100,-100]]),np.array([True])))
    pwm={1:1500,3:777,4:2053,5:1646,6:1500}
    plan=information_views(static,[0,0,0],np.eye(3),pwm)
    assert plan['views']==[] and plan['expected_gain_nats']==0

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


def test_scene_wall_pixels_cannot_become_destination_floor():
    from harness.reloc16_floor_mask import floor_clear,OPTION,PROFILE
    from harness.scene_colour_boundary import ColourBoundaryState,RELOC16_OPTION
    from pathlib import Path
    import json
    calibration=json.loads((Path(__file__).resolve().parents[1]/'experiments/2026-10-16-reloc16/colour-calibration.json').read_text())
    state=ColourBoundaryState(PROFILE,calibration,option=RELOC16_OPTION)
    # Original wall class H133 aliases C's inherited133..155 band.
    frame=cv2.cvtColor(np.full((480,640,3),(133,80,88),np.uint8),cv2.COLOR_HSV2BGR)
    clear,audit=floor_clear(frame,np.ones((480,640),bool),state=state,option=OPTION)
    assert audit['excluded_visible_pixels']==480*640
    pwm={1:1500,3:777,4:2053,5:1646,6:1500}
    xy,r=floor_patch(frame,pwm,'C',(.3,.7),clear=clear)
    assert xy is None and r['pixels']==0


def test_pan_search_slews_restores_and_never_spins_chassis():
    static,_=static_input();c=CarryToZone(static,'A',start=task_start(static))
    c.grip_xy=(.2,0);c.slot=c.region['center_m']
    q=DestinationAcquire(c,camera_pan=True);c.destination_acquire=q
    pwm={1:1500,3:777,4:2053,5:1646,6:1500};low={3:777,4:2053,5:1646,6:1500}
    blank=np.zeros((480,640,3),np.uint8)
    assert q.step(0,blank,pwm,low,'red')==((0,0,0),False,None)
    assert q.desired_pan==500 and q.mode=='pan_scan'
    pwm[6]=500
    assert q.step(.4,blank,pwm,low,'red')==((0,0,0),False,None)
    q.step(.8,blank,pwm,low,'red');assert q.desired_pan==2500
    pwm[6]=2500;q.step(2.1,blank,pwm,low,'red');assert q.desired_pan==1500
    pwm[6]=1500;q.step(2.9,blank,pwm,low,'red');assert q.mode=='expand' and q.turn==0


def test_recent_rgb_patch_memory_moves_only_by_issued_commands():
    static,_=static_input();c=CarryToZone(static,'A',start=task_start(static))
    q=DestinationAcquire(c,camera_pan=True);q.memory_target=np.array([1.,0.]);q.memory_t=1.
    q.issue([.1,0,math.pi/2]);np.testing.assert_allclose(q.memory_target,[0,-.9],atol=1e-10)
    assert q.memory_t==1.  # Commands never refresh image age.


def test_xy_relocalization_respects_existing_loaded_metric_admission(monkeypatch):
    import sim.destination_visual_acquire as m
    static,_=static_input();c=CarryToZone(static,'A',start=task_start(static),recovery_profile='carry5_active_localization_v1')
    c.started=0;c.goal=(1,1);c.loc.own.P=np.eye(3)
    c.loc.tracker=SimpleNamespace(last=dict(camera_admission='loaded_or_unknown_prediction_only'))
    monkeypatch.setattr(m,'information_views',lambda *a:pytest.fail('unqualified loaded metric camera cannot provide XY fix'))
    q=DestinationAcquire(c);assert q.relocalize_step(1,{})==(0,0,0)
    assert c.recovery_reason=='reloc19_loaded_metric_camera_unqualified'
    assert q.events[-1]['blocked_object']=='issued_loaded_camera_metric_fk_unqualified'
