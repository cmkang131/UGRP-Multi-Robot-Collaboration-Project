"""S2 fixed calibration, real predictor path, no GT/SIM, old byte identity."""
import copy
import json
import math
from types import SimpleNamespace as NS
import numpy as np
import pytest
from test_solo_cyan_v106 import static,cal,FakePose,FakeVision,rt
from harness.zone_solo_cyan_pulse_cal import Runtime,Previous,install,select_pulse,action_of,response,profile_key
from harness import zone_s2_realism_contract_v122 as c
from scripts.fit_s2_pulse_calibration import training


def model():return json.loads((c.ROOT/c.PULSE_MODEL).read_text())


def test_option_off_commands_records_and_inputs_are_byte_identical(static,cal):
    a=Previous(static,None,None,provider_factory=lambda *a,**k:FakePose(copy.deepcopy(cal)),vision_factory=FakeVision)
    b=Runtime(static,None,None,provider_factory=lambda *a,**k:FakePose(copy.deepcopy(cal)),vision_factory=FakeVision)
    try:
        for r in (a,b):
            r.initial_commands(0.,{'r3':{1:1500,**rt.high.HIGH}})
            r.last_report=r.pose.report(1.);r.state='carry';r.receipt=True
        for t in (1.,1.05,1.10,1.2,1.65,1.8):
            x,y=a.step(t),b.step(t)
            assert json.dumps(x).encode()==json.dumps(y).encode()
            for r,rows in ((a,x),(b,y)):
                for rid,action in rows:r.on_command(rid,t,action)
        assert json.dumps(a.record()).encode()==json.dumps(b.record()).encode()
    finally:a.close();b.close()


def test_actual_delayed_provider_predicts_calibrated_pulse_in_both_load_states(static):
    b=c.bundle('a'*40,seed=1046,**c.NEW_OPTIONS)
    kwargs={k:v for k,v in b['options'].items() if k not in ('drive_profile','stagnation_watch','idle_robot_contacts','dev_grasp_policy','eval_camera_trace')}
    r=Runtime(static,c.ROOT/c.old.CALIBRATION,c.old.CALIBRATION_SHA,
        **kwargs,motion_model=b['motion_model'],pulse_calibration=b['pulse_calibration'])
    try:
        pf=r.pose.provider.loc._pf
        # Mean response isolated from random PF samples; not a physical test.
        pf.rng=NS(normal=lambda size:np.zeros(size));pf.n=4
        for loaded in (False,True):
            for key in (f'{int(loaded)}:forward:0.35:0.10',f'{int(loaded)}:left:-0.35:0.06',f'{int(loaded)}:left:0.65:0.65'):
                pf.t=0.;pf.px=np.zeros((4,3));pf.logw=np.zeros(4);pf.initialized=True;pf.load.loaded=loaded
                p=model()['profiles'][key];action=action_of(p)
                pf.command(dict(t=0.,**action))
                pf.predict_to(p['duration_s']);pf.command(dict(t=p['duration_s'],kind='hold'))
                pf.predict_to(p['times'][-1]);np.testing.assert_allclose(pf.px,np.tile(p['mean_delta'],(4,1)),atol=1e-10)
                before=pf.px.copy();pf.predict_to(2.);np.testing.assert_array_equal(pf.px,before)
        assert r.pose.provider.runtime_contract['s2_pulse_motion_model']['id']==model()['id']
        assert 's2_pulse_cal' in r.pose.source
    finally:r.close()


def test_same_model_planner_fine_resolution_and_monotone_stopped_feedback():
    profiles=model()['profiles']
    # Reproduce an old 4 cm remaining lateral error: coarse .166 m would pass
    # the target and oscillate. Both signs now choose ~7 mm fine pulses.
    for loaded in (False,True):
        for sign in (-1,1):
            p,score=select_pulse(profiles,loaded,[0,sign*.04],0)
            assert p['axis']=='left' and p['u']==sign*.35 and p['duration_s']==.06
            assert abs(p['mean_delta'][1])<.035 and score['after']<score['before']
        p,_=select_pulse(profiles,loaded,[0,.5],0)
        assert p['u']==.65
        p,_=select_pulse(profiles,loaded,[0,0],.07)
        assert p['axis']=='turn' and p['u']<0
    # Deterministic model acceptance is not physics: finite route converges,
    # old 65/.65 conversion is not applied to the selected fine command.
    xy=np.zeros(2);yaw=0.;goal=np.array([.4,.5]);pulses=[]
    for _ in range(150):
        if np.linalg.norm(goal-xy)<=.03 and abs(yaw)<=.06:break
        co,si=math.cos(yaw),math.sin(yaw);rot=np.array([[co,-si],[si,co]])
        p,_=select_pulse(profiles,True,rot.T@(goal-xy),yaw)
        assert p is not None
        d=np.asarray(p['mean_delta']);xy+=rot@d[:2];yaw+=d[2];pulses.append(p)
    assert np.linalg.norm(goal-xy)<=.03 and len(pulses)<100


def test_fresh_pose_after_stop_required_and_step_bypasses_old_conversion():
    r=object.__new__(Runtime);r.pulse_option='v7_pulse_cal_v1';r.state='carry';r.failure=None
    r.cal_until=1.06;r.cal_settled_at=1.2;r.robot_id='r3';r.real_pulse_until=r.fine_until=None
    r.last_report=NS(t_est=1.04)
    assert r.step(1.05)==[]
    assert r.step(1.10)==[('r3',dict(kind='hold'))]
    assert r.step(1.2)==[] and r.step(1.35)==[]


def test_calibration_data_split_and_declared_missing_loaded_fine():
    assert training(dict(loaded=False,seed=1042,t=50))
    assert not training(dict(loaded=False,seed=1044,t=50))
    assert training(dict(loaded=True,seed=1045,t=399.9))
    assert not training(dict(loaded=True,seed=1045,t=400))
    p=model()['profiles']['1:left:0.35:0.06']
    assert p['n']==0 and 'UNQUALIFIED' in p['transfer']['qualification']
    assert p['prediction_variance'][1]>=.005**2
    for key in ('0:forward:-0.35:0.06','0:forward:-0.35:0.10','1:forward:-0.35:0.10'):
        assert model()['profiles'][key]['transfer'] is not None
    assert model()['heldout']['1:forward:-0.35:0.10']['n']==88


def test_new_bundle_defaults_admission_no_gt_and_existing_bundle_preserved(tmp_path):
    from scripts.run_s2_realism_v122 import parser,run
    args=parser().parse_args(['--expected-source-sha','a'*40,'--output',str(tmp_path)])
    assert args.pulse_motion_model=='off'
    off=c.bundle('a'*40,seed=1046)
    assert off['pulse_calibration'] is None
    b=c.bundle('a'*40,seed=1046,**c.NEW_OPTIONS);c.require_execution(b)
    assert b['options']['idle_robot_contacts']=='freeze_v1' and b['effective_motion_model']=='v7_pulse_cal_v1'
    for seed in (1042,1043,1044,1045,1029):
        bad=copy.deepcopy(b);bad['task']['seed']=seed
        with pytest.raises(ValueError,match='unregistered'):c.require_execution(bad)
    for flag in ('scenario','research_result','confirmation_sample'):
        bad=copy.deepcopy(b);bad[flag]='S3' if flag=='scenario' else True
        with pytest.raises(ValueError):c.require_execution(bad)
    def no_world(*args,**kwargs):raise RuntimeError('synthetic preflight IO failure')
    result=run(b,tmp_path/'no-sim',backend_factory=no_world)
    assert result['status']=='HOST_ERROR' and result['physical_success'] is False
    assert result['options']['pulse_motion_model']=='v7_pulse_cal_v1'
