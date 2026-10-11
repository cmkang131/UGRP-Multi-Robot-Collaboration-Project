"""Own-input motion gating and recovery contracts; no simulator or provider."""
import base64
import hashlib
import json
from pathlib import Path
import cv2
import numpy as np
import pytest
from harness.e2e_stall_odometry import (Options,Detector,Backup,flow_pair,alpha_extra,
                                       install,GATE,PULSE_GATE,RECOVERY,NOISE)
from harness.self_pulse_rotation import RotationPulseOdometry
from harness.active_camera import SEARCH


def texture():
    im=np.full((480,640,3),100,np.uint8)
    rng=np.random.default_rng(11)
    for x,y in rng.integers([70,50],[560,365],size=(100,2)):
        cv2.rectangle(im,(int(x),int(y)),(int(x+8),int(y+8)),(220,220,220),-1)
    return im


def pulse(t,forward=.35):
    return dict(t=t,kind='mecanum',forward=forward,left=0.,turn=0.,duration_s=.1)


def driver():
    d=RotationPulseOdometry();d.command(dict(t=0.,kind='initial_servo_command',pulses=SEARCH));return d


def test_off_is_identity_and_unknown_options_rejected():
    x=object();assert install(x) is x
    for name in ('stall_odometry','stall_recovery','stall_noise'):
        with pytest.raises(ValueError):Options(**{name:'true'})


def test_lk_stationary_motion_and_unknown_texture():
    im=texture();moved=cv2.warpAffine(im,np.float32([[1,0,8],[0,1,0]]),(640,480))
    assert flow_pair(im,im)['status']=='stationary_view'
    assert flow_pair(im,moved)['status']=='changed_view'
    blank=np.zeros_like(im)
    assert flow_pair(blank,blank)['status']=='unknown_texture'


@pytest.mark.parametrize('mode',[GATE,PULSE_GATE])
def test_ungated_predictor_releases_a_stall_without_a_pose_correction(mode):
    d=Detector(driver(),mode);im=texture()
    for i in range(12):
        row=d.observe(t=i*.2,frame_id=i,rgb=im,servo=SEARCH,sha256=str(i))
        d.command(pulse(i*.2))
    assert row['stationary'] and d.nominal.pose[0]>.1
    shifted=cv2.warpAffine(im,np.float32([[1,0,12],[0,1,0]]),(640,480))
    row=d.observe(t=2.4,frame_id=12,rgb=shifted,servo=SEARCH,sha256='moving')
    assert row['status']=='changed_view' and not row['stationary']
    assert d.stationary_since is None


def test_camera_or_turn_resets_history_and_duplicate_frame_rejected():
    d=Detector(driver());im=texture()
    d.observe(t=0.,frame_id=1,rgb=im,servo=SEARCH,sha256='1');d.command(pulse(0.))
    d.observe(t=.2,frame_id=2,rgb=im,servo=SEARCH,sha256='2')
    d.command(dict(t=.2,kind='look',pan_pulse=1550))
    assert not d.frames and not d.suppressed
    with pytest.raises(ValueError):d.observe(t=.2,frame_id=2,rgb=im,servo=SEARCH,sha256='2')


def test_amcl_q_is_nominal_squared_motion_not_recursive_and_zero_at_rest():
    np.testing.assert_array_equal(alpha_extra([.01,0,.02],False),np.zeros(3))
    np.testing.assert_allclose(alpha_extra([.01,0,.02],True),[.0009]*3)
    np.testing.assert_array_equal(alpha_extra([0,0,0],True),np.zeros(3))


def test_recovery_backup_distance_and_timeout_replan():
    b=Backup();assert b.update(9.,[0,0,0],9.)=='idle'
    assert b.update(10.,[0,0,0],10.)=='backup'
    assert b.update(12.,[-.29,0,0],0.)=='backup'
    assert b.update(13.,[-.30,0,0],0.)=='replan'
    b.begin(20.,[0,0,0]);assert b.update(30.,[0,0,0],0.)=='replan'
    assert b.events[-1]['event']=='backup_timeout_replan'


def test_calibrated_reverse_is_available():
    d=driver();d.command(pulse(0.,-.35));d.advance(.2)
    assert d.pose[0]<0 and d.active is None


def robot(options,mapping_budget_s=None):
    from harness.e2e_live_mapping import Robot
    from harness.s4_event_policy import Options as Study
    cov=json.loads(Path('configs/e2e_nees_egomap70_dev_v1.json').read_text())
    return Robot('r1',61001,cov,Study(),exploration_progress='frontier_progress_v1',
        pose_fix='innovation',path_follow='rpp_v1',stall_options=options,mapping_budget_s=mapping_budget_s)


def receive(r,i):
    rgb=np.zeros((480,640,3),np.uint8);_,data=cv2.imencode('.jpg',rgb);data=data.tobytes()
    obs=dict(frame_id=i+1,sim_time=i*.2,sha256=hashlib.sha256(data).hexdigest(),image=base64.b64encode(data).decode())
    return r.receive(obs,rgb)


def test_real_cloud_reporter_and_command_driver_gate_the_same_interval(monkeypatch):
    import harness.e2e_stall_odometry as module
    monkeypatch.setattr(module,'flow_pair',lambda *a:dict(status='stationary_view',tracks=30,cells=6,
        median_px=0.,p90_px=0.,mean_abs_diff=0.))
    r=robot(Options(GATE,RECOVERY,NOISE));view=r.goal._pose_continuity_view
    for i in range(10):
        old=np.asarray(view.base.driver.pose).copy();cloud=view.base.owner.poses.copy()
        trace=receive(r,i)
        if trace['stall_odometry']['translation_gated']:
            np.testing.assert_allclose(view.base.driver.pose,old,atol=1e-12)
            np.testing.assert_allclose(view.base.owner.poses,cloud,atol=1e-12)
            assert sum(trace['stall_odometry']['extra_body_variance'])>0
        r.commanded({k:v for k,v in pulse(i*.2).items() if k!='t'},i*.2)
    assert trace['stall_odometry']['translation_gated']
    assert r.goal.e2e_stall.nominal.pose[0]>view.base.driver.pose[0]
    # Existing progress timeout must start backup BEFORE its hold/blacklist.
    n=r.goal.explorer.navigator;n.action_failed(2.,'progress_timeout_blacklist')
    tr=receive(r,10)
    assert r.nav_command['forward']==-.35 and tr['stall_odometry']['recovery']=='backup'


def test_real_unknown_rgb_keeps_translation_and_off_has_no_detector():
    off=robot(Options());assert not hasattr(off.goal,'e2e_stall')
    r=robot(Options(GATE));view=r.goal._pose_continuity_view
    for i in range(7):
        trace=receive(r,i);r.commanded({k:v for k,v in pulse(i*.2).items() if k!='t'},i*.2)
    assert trace['stall_odometry']['status']=='unknown_texture'
    assert view.base.driver.pose[0]>.06 and not trace['stall_odometry']['translation_gated']


def test_bundle_and_managed_cli_register_all_explicit_toggles():
    from scripts.run_e2e_ownmap_live import bundle
    from sim.workflow_manager import catalog,_option
    b=bundle('a'*40,61001,'study_gemma4_31b_v1',enabled=True,path_follow='rpp_v1',
        stall_odometry=PULSE_GATE,stall_recovery=RECOVERY,stall_noise=NOISE,stall_bundle=True)
    assert b['execution_bundle_id']=='e2e-stall-odometry-v198'
    assert 'harness/e2e_stall_odometry.py' in b['source_sha256']
    rows,_=catalog(Path('.'));w=next(w for w in rows['workflows'] if w['id']==b['execution_bundle_id'])
    assert '--stall-bundle' not in w['required_inputs'] and '--dev-light' not in w['required_inputs']
    for flag in ('--stall-odometry','--stall-recovery','--stall-noise'):assert flag in w['required_inputs']
    assert _option(['--stall-odometry',PULSE_GATE,'--stall-bundle'],'--stall-odometry')==PULSE_GATE


def test_e2e11_registered_calls_reach_relay_admission():
    from scripts.s4_proxy_relay import accepted_call_id
    for batch in ('a','b'):
        for seed in (61001,61002):
            for suffix in ('','-r2'):
                assert accepted_call_id(f'e2e11-{batch}-s{seed}{suffix}:call-0001-r1:1')
    for name in ('e2e11-c-s61001','e2e11-a-s61003','e2e11-a-s61001-r3','other-e2e11-a-s61001'):
        assert not accepted_call_id(name+':call-0001-r1:1')


def test_registered_mission_budget_reaches_goal_and_preserves_legacy_cutoff():
    from scripts.run_e2e_ownmap_live import bundle
    legacy=bundle('a'*40,61001,'study_gemma4_31b_v1',enabled=True,stall_bundle=True)
    assert legacy['execution_bundle_id']=='e2e-stall-odometry-v198'
    assert 'mapping_budget_s' not in legacy['e2e_options']
    fixed=bundle('a'*40,61001,'study_gemma4_31b_v1',enabled=True,stall_bundle=True,mapping_budget='case_cap_v1')
    assert fixed['execution_bundle_id']=='e2e-stall-budget-v199'
    assert fixed['e2e_options']['mapping_budget_s']==fixed['case_cap_s']==1800.
    for selected,limit in ((None,270.),(fixed['e2e_options']['mapping_budget_s'],1800.)):
        r=robot(Options(),selected);receive(r,0)
        receive(r,1349)  # 269.8 SIM seconds, own RGB only.
        assert not r.goal.done
        receive(r,1350)
        assert r.goal.done==(limit==270.)
        if limit==1800.:
            receive(r,8999);assert not r.goal.done
            receive(r,9000);assert r.goal.done
        assert r.goal.stage=='budget_exhausted' and not r.goal.declared
        assert r.goal.events[-1]['leg_budget_s']==limit


def test_mapping_budget_is_finite_and_catalog_input_is_explicit():
    from harness.goal_route_continuous import GoalRoute
    from scripts.run_e2e_ownmap_live import bundle
    from sim.workflow_manager import catalog
    for value in (0.,-1.,float('inf'),float('nan')):
        with pytest.raises(ValueError,match='FINITE_LEG_BUDGET_REQUIRED'):
            GoalRoute(object(),leg_budget_s=value)
    with pytest.raises(ValueError,match='UNKNOWN_MAPPING_BUDGET'):
        bundle('a'*40,61001,'study_gemma4_31b_v1',mapping_budget='guess')
    rows,_=catalog(Path('.'));w=next(w for w in rows['workflows'] if w['id']=='e2e-stall-budget-v199')
    assert '--mapping-budget' in w['required_inputs']
