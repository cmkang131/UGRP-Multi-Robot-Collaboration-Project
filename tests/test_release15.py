"""Own-pixel/command/static-map regressions; no simulator, rendering or network."""
import json
import math
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from sim import release14, release15 as new, release_regrasp as check
from sim.global_landmark_localization import GlobalLandmarkMatcher
from sim.lookaround_localization import Camera
from tests.test_release_regrasp import teachers, stripe, commands, frame
from tests.test_grasp_act_release_run import fake_backend
from scripts import run_grasp_act_release as runner


def near_wall(yaw=-1.69, sigma=.005):
    static=json.loads((runner.ROOT/'maps/zones/zone_wide_door_geometry_v3.json').read_text())
    return SimpleNamespace(own=SimpleNamespace(x=np.array([4.849,1.232,yaw]),P=np.eye(3)*sigma**2),
        map_pose_known=True,decision={'accepted':True},global_matcher=GlobalLandmarkMatcher(static))


@pytest.mark.parametrize('sigma', [.005,.02])
def test_real_map_escape_and_parallel_not_blanket_rejected(sigma):
    loc=near_wall(sigma=sigma)
    assert not release14.map_motion_clear(loc,.05,0.)
    assert new.map_motion_clear(loc,.05,0.)  # forward is SOUTH, away from north wall
    assert not new.map_motion_clear(loc,-.05,0.)  # rear is NORTH: must remain rejected
    assert new.map_motion_clear(loc,0.,.004)
    assert not new.map_motion_clear(loc,0.,-.004)  # oblique heading: 0.48 mm closer
    loc.own.x[2]=math.pi/2
    assert new.map_motion_clear(loc,-.05,0.)  # same position, rear now points away
    assert new.map_motion_clear(loc,0.,.004) and new.map_motion_clear(loc,0.,-.004)
    loc.map_pose_known=False
    assert not new.map_motion_clear(loc,-.05,0.)


def test_escape_does_not_allow_new_wall_or_crossing():
    loc=near_wall(math.pi/2)
    assert not new.map_motion_clear(loc,0.,-1.)  # east wall
    assert not new.map_motion_clear(loc,-10.,0.)  # crosses wall on full swept path
    loc.own.x[1]=1.5
    assert not new.map_motion_clear(loc,-.05,0.)  # inside actual wall


def aligner(*, interior=False):
    t=teachers()['r1'];issued=[];scheduled=[]
    loc=near_wall()
    if interior:loc.own.x[:2]=[4.6,.4]
    a=new.LineAlign(t,0.,camera=Camera(),undistort=lambda f:f,
        wheel_command=lambda *v:issued.append(v),clearance=lambda *v:new.map_motion_clear(loc,*v))
    def schedule(rid,seq,now):scheduled.extend((now+dt,p) for dt,p in seq)
    def tick(now,image):
        while scheduled and scheduled[0][0]<=now+1e-8:
            _,p=scheduled.pop(0);t.pwm.update(p)
        return a.tick(now,lambda *v:image,schedule)
    tick(0.,None);tick(1.2,None)
    return a,t,issued,tick


def top_fragment():
    im=np.full((480,640,3),60,np.uint8)
    im[13:135,220:365]=[5,220,150]
    im[13:40,220:365]=[153,242,5]
    return im


def test_clipped_top_reframes_before_any_yaw_and_checks_real_map():
    a,t,issued,tick=aligner();f=new.line_features(top_fragment(),'teal')
    assert f['line'] is None and not f['fov_safe']
    assert tick(2.6,top_fragment())=='pending'
    step=a.records[-1]
    assert step['event']=='recover_fov' and step['yaw']==0. and step['forward']>0.
    assert step['predicted_merit']<step['merit']
    assert issued


def test_single_invalid_frame_stops_then_recovers_and_one_second_fails():
    a,t,issued,tick=aligner()
    assert tick(2.6,None)=='pending'
    assert issued[-1][1]==[0.]*4
    assert tick(2.8,stripe())=='pending'
    assert a.missing is None and not a.failure
    assert tick(3.,None)=='pending'
    assert tick(3.8,None)=='pending'
    assert tick(4.,None)=='failed' and a.failure=='release15_shaft_unobserved_1s'


def test_return_from_reframing_restarts_line_progress_budget():
    a,t,issued,tick=aligner(interior=True)
    tick(2.6,stripe(320,.08));a.best=0.;a.progress=0.
    assert tick(2.8,top_fragment())=='pending'
    assert a.progress==2.8 and a.mode=='recover_fov'
    assert tick(4.,stripe(320,.08))=='pending'
    assert a.progress==4. and a.mode=='line_ibvs' and not a.failure


def test_observed_edge_interrupts_rotation_and_predicted_edge_blocks_it():
    a,t,issued,tick=aligner(interior=True)
    tick(2.6,stripe(320,.08))
    assert a.records[-1]['yaw']!=0.
    tick(2.8,stripe(550,.08))
    assert a.records[-1]['event']=='recover_fov' and a.records[-1]['yaw']==0.
    # Pixel fixture: shaft is aligned in rows but the assigned band reaches
    # the right margin. Unconstrained IBVS would rotate that band out of view.
    im=stripe(150);im[390:410,70:576]=[153,242,5]
    f=new.line_features(im,'teal')
    old=release14.line_step(f,Camera(),t.pwm)
    assert f['fov_safe'] and not new.inside(new.project_motion(f['points'],Camera(),t.pwm,[0.,old['left'],old['yaw']]))
    step=new.line_step(f,Camera(),t.pwm,clearance=lambda *v:True)
    assert step['kind']=='recover_fov' and step['yaw']==0.
    predicted=new.project_motion(f['points'],Camera(),t.pwm,[step['forward'],step['left'],0.])
    assert new.recovery_keeps_features(f['points'],predicted)


def test_new_teal_range_excludes_cyan_but_legacy_is_unchanged():
    hsv=np.full((240,320,3),(90,255,255),np.uint8);cyan=cv2.cvtColor(hsv,cv2.COLOR_HSV2BGR)
    assert check.assigned_beam_mask(cyan,'teal').any()
    assert not check.assigned_beam_mask(cyan,'teal',colour_profile=new.PROFILE).any()
    for hue in (70,79,83):
        hsv[:,:,0]=hue
        assert check.assigned_beam_mask(cv2.cvtColor(hsv,cv2.COLOR_HSV2BGR),'teal',colour_profile=new.PROFILE).any()


@pytest.mark.parametrize('profile', ['off',new.PROFILE])
def test_output_extensions_are_profile_gated(tmp_path,fake_backend,profile):
    plan=json.loads((runner.ROOT/'experiments/2026-10-14-e2e18-grasp-rootcause/release14-diagnostic-plan.json').read_text())
    opts={**plan['execution_profile'],'release_profile':profile}
    out=tmp_path/profile
    result=runner.run(plan['episodes'][0],out,cap_s=3.,**opts)
    rows=[json.loads(s) for s in (out/'teacher-r1.jsonl').read_text().splitlines()]
    assert ('release_profile' in result)==(profile!='off')
    assert ('training_exclusions' in result)==(profile!='off')
    assert (out/'training-segments.json').exists()==(profile!='off')
    assert all(('training_eligible' in row)==(profile!='off') for row in rows)
    if profile!='off':assert all(row['training_exclusion']=='measurement_only_release' for row in rows)


def test_real_barrier_assigned_end_to_evidence_and_retry_linealign():
    ts=teachers();schedules={r:[] for r in ts};calls=[];created=[]
    loc=near_wall()
    def factory(t,now):
        a=new.LineAlign(t,now,camera=Camera(),undistort=lambda f:f,wheel_command=lambda *a:None,
            clearance=lambda *v:new.map_motion_clear(loc,*v))
        created.append(a);return a
    b=check.RegraspBarrier(ts,5,0.,wheel_commands=lambda r:[0.]*4,
        assigned_end_evidence=True,colour_profile=new.PROFILE,recovery_factory=factory)
    def schedule(rid,seq,now):schedules[rid]=[(now+dt,p) for dt,p in seq]
    def capture(rid,now,label):
        calls.append((rid,now,label))
        if label=='line_recheck':return stripe()
        im=frame(fresh=1+len(calls)%250)
        im[15:225,15:305]=[153,242,5] if rid=='r1' else [242,5,5]
        if rid=='r1' and b.attempts[rid]==1:im[15:225,15:305]=60
        return im
    for k in range(1200):
        now=k*.1
        for rid,seq in schedules.items():
            while seq and seq[0][0]<=now+1e-9:
                _,p=seq.pop(0);ts[rid].pwm.update(p)
        status=b.tick(now,capture,schedule)
        if status in ('failed','ready'):break
    assert status=='ready' and b.attempts=={'r1':2,'r2':1}
    assert len(created)==1 and created[0].state=='done'
    evidence=[s for s in b.samples if 'assigned_end' in s]
    assert {s['assigned_end'] for s in evidence}=={'teal','blue'}
    assert all(s['colour_profile']==new.PROFILE for s in evidence)
    assert any(s['answer']=='no' for s in evidence) and any(s['answer']=='yes' for s in evidence)
    assert any(e['event']=='retry_realign' for e in b.records)


def test_runner_real_map_near_wall_and_actual_pixel_barrier(tmp_path,fake_backend,monkeypatch):
    from sim.lookaround_localization import LookaroundLocalizer
    from sim import release_global_observation as active
    world,ports=fake_backend
    def own_image(rid,now,pwm):
        if pwm[1]>=1900:return stripe()
        im=np.full((480,640,3),60,np.uint8)
        im[20:460,20:620]=[153,242,5] if rid=='r1' else [242,5,5]
        im[:16,:16]=int(now*10)%250
        return im
    world.own_image=own_image
    fitted_ids=[]
    def fitted(self):
        if id(self) not in fitted_ids:fitted_ids.append(id(self))
        self.map_pose_known=True
        self.own.x=near_wall().own.x.copy() if fitted_ids.index(id(self))==0 else np.array([4.6,.4,math.pi/2])
        self.own.P=np.eye(3)*.005**2;self.decision={'accepted':True};return self.decision
    # Robot id is not assumed here; inspect the actual localizer field below.
    monkeypatch.setattr(LookaroundLocalizer,'finalize',fitted)
    calls=[]
    def margins(loc,t,now,**kwargs):
        calls.append(t.rid)
        return dict(phase='observe',kind='localized_margin',margin_m=.4,expected_slack_m=.8,
            lateral_clearance_m=.025 if len(calls)<=2 else .2,lateral_shift_lo_m=.015,lateral_shift_hi_m=.43)
    monkeypatch.setattr(active,'margin_report',margins)
    # Exact synthetic pixels, skip lens distortion (the test has no physical lens).
    from harness.vision_loc_protocol import load_vis3
    monkeypatch.setattr(load_vis3()[0].mp,'undistort',lambda f:f)
    def forbidden(*a,**kw):raise AssertionError('GT perception entered new release control')
    monkeypatch.setattr(runner.Eyes,'classify',forbidden);monkeypatch.setattr(runner.Eyes,'visible',forbidden)
    monkeypatch.setattr(runner,'own_end_world',forbidden)
    plan=json.loads((runner.ROOT/'experiments/2026-10-14-e2e18-grasp-rootcause/release14-diagnostic-plan.json').read_text())
    opts={**plan['execution_profile'],'release_profile':new.PROFILE}
    result=runner.run(plan['episodes'][0],tmp_path/'scheduler',cap_s=180.,**opts)
    assert result['release_outcome']=='teacher_done'
    assert len(result['line_rechecks'])==4 and all(c['state']=='done' for c in result['line_rechecks'])
    assert result['map_backoff_checks'][0]['action']=='stationary_relook'
    assert result['input_audit']['held_world_reads']==0
    assert {'approach','repick','line_aligned_station'} <= {p['phase'] for p in result['input_audit']['pick_target_uses']}
    samples=[s for b in result['regrasp_verification'] for s in b['samples'] if 'assigned_end' in s]
    assert samples and {s['assigned_end'] for s in samples}=={'teal','blue'}
