"""DEV veto regression on real pair admission/driver, no simulator or GT."""
import copy
import json
import math
import subprocess
from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest

from harness import zone_s3_dev_light as dev
from harness import zone_s3_global_diversity as diversity
from harness import zone_s3_no_prior_contract as old


def test_off_identity_and_frozen_sources():
    obj = object()
    assert dev.attach(obj) is obj
    assert diversity.attach(obj) is obj
    for path in ('harness/zone_s3_no_prior.py', 'harness/zone_s3_host_heading_contract.py',
                 'harness/zone_pair_highpose_runtime.py', 'harness/zone_own_executor.py',
                 'harness/zone_solo_cyan_kld_start.py', 'configs/simulation_workflows.json'):
        assert (old.ROOT/path).read_bytes() == subprocess.check_output(
            ['git', 'show', 'bfbfbe78:'+path], cwd=old.ROOT)


def test_new_bundle_and_cli_are_explicit_no_execution(monkeypatch, capsys):
    from harness import zone_s3_continue_contract as contract
    from scripts import run_s3_continue as runner
    b = contract.bundle('a'*40)
    contract.verify(b)
    assert b['execution_bundle_id'] == 'zone-s3-continue-v147'
    assert b['provider_seeds'] == dict(r1=14201, r2=14202, r3=14203)
    assert b['s3_camera_binding'] == 'v3_persistent_v1'
    assert b['options']['heading_mode'] == 'path_tangent_v1'
    assert b['options']['s3_dev_light'] == dev.OPTION
    assert b['options']['global_diversity'] == diversity.OPTION
    assert b['options']['mode_head_look'] == diversity.HEAD_OPTION
    assert not b['convergence_thresholds_changed']
    monkeypatch.setattr(runner, 'run', lambda *a, **k: pytest.fail('plan executed'))
    assert runner.main(['--expected-source-sha', 'a'*40, '--output', '/nonexistent/plan']) == 0
    assert not json.loads(capsys.readouterr().out)['execution_started']


@pytest.mark.parametrize('std', [.084268, .212761, 1.478844])
def test_real_pair_admission_sweep_and_driver_progress_with_large_sigma(std):
    from tests.test_highpose_relook import executor, StuckPose
    from tests.test_zone_own_executor import Driver
    from tests.test_solo_cyan_v106 import observation
    from harness.zone_own_driver import GuardedDriver
    ex = executor('r2', StuckPose(sx=std/math.sqrt(2), sy=std/math.sqrt(2)))
    d = Driver(ex); d.frame()
    ex.last_obs = observation(d.t, rid='r2')[0]
    ex.mode = 'm1'
    audit = dev.Audit()
    assert ex.pair_readiness(d.t) == 'uncertain'
    original_report = ex.last_report
    dev.attach_actor(ex, audit)
    assert ex.pair_readiness(d.t) == 'available'
    assert ex.last_report is original_report and not ex.gate.ok
    # The real look job used to fail SWEEP_TRANSITION_BLOCKED at large sigma.
    ex.mode = 'diagnostic'  # The scripted source is never admitted as a real M1 provider.
    ex.look_around(); d.run(25., stop=lambda: ex.job is None)
    assert ex.jobs_done[-1]['confirmation'] != 'failed'
    assert ex.jobs_done[-1]['outcome'] == 'LOOKED_POSE_UNCERTAIN'
    # This stand-in is an own estimate fixture, not a simulator pose.
    est = dict(initialized=True, x=-.9, y=-.85, yaw=0., std_xy_m=std,
               std_yaw_rad=.01, fix_age_s=.1, t=0., last_fix_t=0.)
    loc = SimpleNamespace(predict_to=lambda t: est.update(t=t), estimate=lambda: dict(est))
    driver = GuardedDriver(loc, ex.map, ex.params, loaded=False, goal_xy=(-.5, -.85),
        door_xy=ex.door_xy, initial_servo=dict(d.servo), seed=5, gate=ex.gate, guard=ex.guard)
    dev.attach_driver(driver, ex, audit)
    driver.monitor.look_failures = 100
    driver.state='drive'; driver.state_since=d.t
    rows = driver.tick(d.t)
    assert any(c['kind']=='mecanum' and any(c.get(k,0) for k in ('forward','left','turn')) for c in rows)
    assert ex.last_report.std_xy_m == pytest.approx(std)
    assert any(r['code']=='SELF_UNCERTAIN' for r in audit.rows)
    assert any(r['code']=='POSE_UNCERTAIN_PROGRESS' for r in audit.rows)
    assert driver.monitor.look_failures == 100
    driver._finish(d.t, 'arrival_not_confirmed_by_view')
    assert driver.outcome == 'arrived'
    assert any(r['code']=='APPROACH_ARRIVAL_NOT_CONFIRMED_BY_VIEW' for r in audit.rows)
    driver._finish(d.t, 'execution_error')
    assert driver.outcome == 'execution_error'


def test_augmented_recovery_is_not_disabled_by_high_ess(monkeypatch):
    p = diversity.Policy(); p.slow=1.; p.fast=.1
    pf = SimpleNamespace(n=10, _weights=lambda: np.full(10,.1))
    seen=[]
    def resample(pf, probability, params):
        seen.append(probability)
        return dict(injected=3, samples=pf.n)
    monkeypatch.setattr(diversity.kld,'resample',resample)
    row=p.measure(pf,np.full(10,.1),np.zeros(10),{3:1,4:2,5:3,6:4},False)
    assert row['ess'] == pytest.approx(10)
    assert row['resampled'] and seen[0]>0 and row['injected']==3
    assert p.slow == p.fast == 0


def test_mode_information_prefers_discriminating_view_not_within_mode_detail():
    w=np.full(4,.25); labels=np.array([0,0,1,1])
    separating=np.array([[.99,.01],[.99,.01],[.01,.99],[.01,.99]])
    within=np.array([[.99,.01],[.01,.99],[.99,.01],[.01,.99]])
    assert diversity.mode_information(w,labels,separating)>.5
    assert diversity.mode_information(w,labels,within)==pytest.approx(0.)


def test_multimode_head_look_adds_two_real_pan_commands_then_resumes(monkeypatch):
    pf=SimpleNamespace(t=0.,px=np.array([[0.,0.,0.],[4.,0.,math.pi]]))
    inner=SimpleNamespace(loc=SimpleNamespace(_pf=pf),failure=None,runtime_contract={})
    queued=[]
    runtime=SimpleNamespace(pose=SimpleNamespace(provider=inner),global_policy=SimpleNamespace(active=True),
        _control=lambda now,idle:['resume'],record=lambda:{},state='scan',terminal=False,
        global_scan_started=0.,scan_queue=[],queue=lambda p,t,**kw:queued.append((p,t)))
    monkeypatch.setattr(diversity,'rank_views',lambda pf,pans:[dict(pan=p) for p in pans])
    diversity.attach(runtime,mode_head_look=diversity.HEAD_OPTION)
    assert runtime._control(10.,True)==[{'kind':'hold'}]
    assert runtime._control(12.,True)==[{'kind':'hold'}]
    assert runtime._control(14.,True)==['resume']
    assert [p[6] for p,t in queued]==[700,2300]
    assert runtime.record()['global_diversity']['extra_views']==2
    assert not runtime.record()['global_diversity']['gt_inputs']


def test_initial_expansion_preserves_seed_and_old_particles_and_handoff():
    from harness.zone_s3_continue import solo_factory
    config=old.controller_config()
    args=(old.hp.resolve(old.old.solo.MAP_ID)[0], old.ROOT/old.old.solo.CALIBRATION,
          old.old.solo.CALIBRATION_SHA)
    baseline=solo_factory(config)(*args,seed=14201,robot_id='r1')
    config['options'].update(global_diversity=diversity.OPTION,mode_head_look=diversity.HEAD_OPTION)
    candidate=solo_factory(config)(*args,seed=14201,robot_id='r1')
    try:
        pf=candidate.pose.provider.loc._pf
        assert pf.n==400000
        np.testing.assert_array_equal(pf.px[:100000],baseline.pose.provider.loc._pf.px)
        assert candidate.pose.provider.prior['known_own_dock'] is False
        candidate.initial_commands(0.,{'r1':{1:2000,3:740,4:2320,5:1320,6:1500}})
        candidate.on_command('r1',.05,dict(kind='mecanum',forward=.1,left=0.,turn=0.,duration_s=.1))
        assert pf.n==2000 and not candidate.global_policy.active
        assert candidate.kld_audit['handoff']['before']==400000
    finally:
        baseline.close(); candidate.close()


def test_real_pair_endpoint_keeps_go_failure_and_removes_repeat_soft_stop():
    from harness.zone_s3_continue import Runtime
    from tests.test_solo_cyan_v106 import observation
    config=old.controller_config();config['options']['s3_dev_light']=dev.OPTION
    runtime=Runtime(old.hp.resolve(old.old.solo.MAP_ID)[0],old.inputs()[2]['orders'],
        old.ROOT/old.old.solo.CALIBRATION,old.old.solo.CALIBRATION_SHA,seed=14201,config=config)
    try:
        runtime.initial_commands(0.,{r:{1:2000,3:740,4:2320,5:1320,6:1500} for r in ('r1','r2','r3')})
        runtime.boot_finished_at=.1
        runtime.on_frames(.2,{r:observation(.2,1,rid=r) for r in runtime.localizers})
        pair=runtime.pair.producer if hasattr(runtime.pair,'producer') else runtime.pair
        for rid,own in pair.actors.items():
            own.last_report=replace(own.last_report,x_m=-.9,y_m=-.85,yaw_rad=0.,std_xy_m=.212761,std_yaw_rad=.01)
        pair.look_recovery.state['r2']['exhausted']={'code':'LOOK_RECOVERY_EXHAUSTED'}
        assert not pair.look_recovery.exhausted('r2')
        assert pair.look_recovery.failures()=={}
        # Submit via the saved local link, preserving independent pair API calls.
        a=runtime.links['r1'].submit('r1','cargoX','B','r2',now=.2)
        assert a['accepted'], a
        b=runtime.links['r2'].submit('r2','cargoX','B','r1',now=.2)
        assert b['accepted'], b
        ep=pair.team.sessions[0]['endpoints']['r2']; ctl=ep.controller
        for _ in range(25):
            ctl.fail('ALIGN_TIMEOUT',.3)
        assert not ep.terminal and ctl.state!='failed'
        ep.abort(.4,'PARTNER_MISSED_GO')
        assert ep.terminal and pair.actors['r2'].jobs_done[-1]['outcome']=='PARTNER_MISSED_GO'
    finally:
        runtime.close()
