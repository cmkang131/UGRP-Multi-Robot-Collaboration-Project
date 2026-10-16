"""Release14 offline regressions: pixels/command math and clock-only runner."""
import copy
import inspect
import math
from types import SimpleNamespace

import numpy as np
import pytest

from sim import release14 as new
from sim import release_regrasp as check
from sim.visible_belief import odometry
from sim.lookaround_localization import Camera
from tests.test_release_regrasp import stripe, teachers, frame, commands


def test_polar_line_and_coupled_feedback_reject_centroid_only():
    t=teachers()['r1']
    r=new.LineAlign(t,0.,camera=Camera(),undistort=lambda f:f,
                    wheel_command=lambda *a:None,clearance=lambda *a:True)
    t.pwm.update(r.expected)
    clipped=new.line_features(stripe(630))
    step=new.line_step(clipped,r.camera,t.pwm)
    assert clipped['line'] is None and step['kind']=='recover_direction'
    assert step['left']==0. and step['yaw']!=0. and not step['aligned']
    # Same image centre but different direction must change the yaw command.
    a=new.line_step(new.line_features(stripe(315,.02)),r.camera,t.pwm)
    b=new.line_step(new.line_features(stripe(315,.12)),r.camera,t.pwm)
    assert a['yaw']!=pytest.approx(b['yaw'])
    assert b['left'] and b['yaw']
    w,d=new.pulse_for(0.,b['left'],b['yaw'],t.odometry_profile)
    nominal=odometry([v*dt/.1 for v,dt in zip(w,d)],.1,t.odometry_profile)
    assert np.array(nominal)==pytest.approx([0.,b['left'],b['yaw']],abs=1e-6)


def test_fresh_line_feedback_corrects_uncommanded_lateral_yaw_coupling():
    from sim.release_regrasp_recovery import image_jacobian
    t=teachers()['r1']
    align=new.LineAlign(t,0.,camera=Camera(),undistort=lambda f:f,
        wheel_command=lambda *a:None,clearance=lambda *a:True)
    t.pwm.update(align.expected)
    j,goal=image_jacobian(align.camera,t.pwm)
    state=goal+j@np.array([.018,0.])
    yaws=[]
    # Algebraic feature-space plant, NOT a simulation/physical performance test.
    # Unknown +yaw accompanies commanded right motion; only the next observed
    # two-feature vector tells the controller about it.
    for _ in range(100):
        f=dict(valid=True,unclipped=True,center_error=state[0],slope_error=state[1])
        f['line']=new.polar_line(f).tolist()
        step=new.line_step(f,align.camera,t.pwm)
        if step['aligned']:break
        yaws.append(step['yaw'])
        state+=j@np.array([step['left'],step['yaw']-4*step['left']])
    assert step['aligned'] and any(abs(yaw)>.001 for yaw in yaws)


def test_direction_missing_never_strafes_and_search_is_finite():
    t=teachers()['r1'];issued=[];scheduled=[]
    r=new.LineAlign(t,0.,camera=Camera(),undistort=lambda f:f,
        wheel_command=lambda rid,w,d,now:issued.append(odometry([v*x/.1 for v,x in zip(w,d)],.1,t.odometry_profile)),
        clearance=lambda *a:True)
    def schedule(rid,seq,now):scheduled[:]=[(now+dt,p) for dt,p in seq]
    for k in range(200):
        now=k*.1
        while scheduled and scheduled[0][0]<=now+1e-8:
            _,p=scheduled.pop(0);t.pwm.update(p)
        status=r.tick(now,lambda *a:stripe(630),schedule)
        if status=='failed':break
    assert r.failure=='release14_direction_search_cap'
    assert issued and all(abs(x)+abs(y)<1e-10 and yaw for x,y,yaw in issued)


def localizer(y=.75,yaw=math.pi/2):
    # Actual static rectangle, with no truth or simulator object available.
    from sim.global_landmark_localization import GlobalLandmarkMatcher
    static=dict(bounds_m=[0.,2.,0.,2.],obstacles=[dict(id='north',kind='wall',
        center_m=[1.,1.5],half_extents_m=[1.,.075])],regions={})
    return SimpleNamespace(own=SimpleNamespace(x=np.array([1.,y,yaw]),P=np.eye(3)*.0001),
        map_pose_known=True,decision={'accepted':True},
        global_matcher=GlobalLandmarkMatcher(static))


def test_static_wall_blocks_rear_and_unknown_never_uses_spawn():
    t=teachers()['r1'];loc=localizer(1.20,-math.pi/2)
    plan,rec=new.backoff_plan(loc,t)
    assert plan==[] and rec['action']=='stationary_relook'
    loc=localizer(.75,-math.pi/2)
    plan,rec=new.backoff_plan(loc,t)
    assert plan and rec['distance_m']==.15
    loc.map_pose_known=False
    assert new.backoff_plan(loc,t)[0]==[]


def test_reapproach_checks_whole_path():
    t=teachers()['r1'];loc=localizer(1.1,math.pi/2)
    t.belief.observe('released_band',[.40,0.,0.],0.,source='own_command')
    with pytest.raises(ValueError,match='approach_map_clearance'):
        new.approach_plan(loc,t,0.)
    loc.map_pose_known=True;loc.decision={'accepted':False,'truth_pose':[1.,.5,0.]}
    assert new.backoff_plan(loc,t)[0]==[]


@pytest.mark.parametrize('end,bgr', [('teal',[153,242,5]),('blue',[242,5,5])])
def test_assigned_end_is_evidence_but_wrong_end_and_static_image_are_not(end,bgr):
    imgs=[frame(fresh=k) for k in (1,2,3)]
    for f in imgs:f[15:225,15:305]=bgr
    assert check.lift_evidence(*imgs,commands())['answer']=='no'
    assert check.lift_evidence(*imgs,commands(),end=end)['answer']=='yes'
    other='blue' if end=='teal' else 'teal'
    assert check.lift_evidence(*imgs,commands(),end=other)['answer']=='no'
    assert check.lift_evidence(imgs[0],imgs[0],imgs[0],commands(),end=end)['answer']=='unknown'


@pytest.mark.parametrize('key,value', [('pose_anchor','legacy_truth_v0'),('held_object','visible_v0'),
    ('own_pose_source','truth_comparison'),('lookaround','setdown_lookaround_v1'),('placement','margin_v0')])
def test_recording_rejects_gt_paths_before_backend(tmp_path,key,value):
    from scripts.run_grasp_act_release import run
    opts={**new.SAFE,key:value}
    with pytest.raises(ValueError,match='unsafe configuration'):
        run(dict(end_color_scene='grasp_act_teal_blue_v1'),tmp_path/'never',
            release_profile=new.PROFILE,record_training=True,**opts)
    assert not (tmp_path/'never').exists()


def test_legacy_defaults_and_safe_recording_fail_closed(tmp_path):
    from scripts.run_grasp_act_release import run
    sig=inspect.signature(run)
    assert sig.parameters['release_profile'].default=='off'
    assert sig.parameters['pose_anchor'].default=='legacy_truth_v0'
    assert sig.parameters['held_object'].default=='visible_v0'
    with pytest.raises(ValueError,match='safe profile'):
        run({},tmp_path/'legacy',record_training=True)
    with pytest.raises(ValueError,match='gate and student writer'):
        run(dict(end_color_scene='grasp_act_teal_blue_v1'),tmp_path/'safe',
            release_profile=new.PROFILE,record_training=True,**new.SAFE)
    assert not (tmp_path/'safe').exists()
