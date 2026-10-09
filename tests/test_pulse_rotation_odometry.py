"""Own-command PF integration and default-off invariance; no physics/GT."""
import copy
import json
from types import SimpleNamespace as NS
import numpy as np
import pytest
from harness.pulse_rotation_odometry import OPTION, selected_model
from harness.zone_solo_cyan_pulse_cal import Runtime, action_of
from harness import zone_s2_realism_contract_v122 as c
from test_solo_cyan_v106 import static, cal, FakePose, FakeVision, rt


def model(): return json.loads((c.ROOT/c.PULSE_MODEL).read_text())


def test_off_identity_and_rotation_only_calibration():
    original=model();before=json.dumps(original).encode()
    assert selected_model(original) is original
    on=selected_model(original,pulse_odometry=OPTION)
    assert json.dumps(original).encode()==before
    for key,p in original['profiles'].items():
        q=on['profiles'][key]
        if p['axis']!='turn' or p['loaded']:
            assert json.dumps(p).encode()==json.dumps(q).encode()
        else:
            assert np.array_equal(np.array(p['mean_curve'])[:,2],np.array(q['mean_curve'])[:,2])
            assert p['times']==q['times'] and p['mean_delta'][2]==q['mean_delta'][2]
            assert np.all(np.array(q['prediction_variance'])>=p['prediction_variance'])
            assert q['prediction_variance'][2]>p['prediction_variance'][2]*50
            assert np.linalg.norm(q['mean_delta'][:2])<np.linalg.norm(p['mean_delta'][:2])
    with pytest.raises(ValueError):selected_model(original,pulse_odometry='unknown')


def test_explicit_off_commands_records_bytes(static,cal):
    kwargs=dict(provider_factory=lambda *a,**k:FakePose(copy.deepcopy(cal)),vision_factory=FakeVision)
    a=Runtime(static,None,None,**kwargs);b=Runtime(static,None,None,pulse_odometry='off',**kwargs)
    try:
        for r in (a,b):
            r.initial_commands(0.,{'r3':{1:1500,**rt.high.HIGH}})
            r.last_report=r.pose.report(1.);r.state='carry';r.receipt=True
        for t in (1.,1.05,1.1,1.2,1.65,1.8):
            aa,bb=a.step(t),b.step(t)
            assert json.dumps(aa).encode()==json.dumps(bb).encode()
            for r,actions in ((a,aa),(b,bb)):
                for rid,action in actions:r.on_command(rid,t,action)
        assert json.dumps(a.record()).encode()==json.dumps(b.record()).encode()
    finally:a.close();b.close()


def test_actual_provider_records_same_table_for_planning_prediction_and_noise(static):
    b=c.bundle('a'*40,seed=1046,**c.NEW_OPTIONS)
    options={k:v for k,v in b['options'].items() if k not in ('drive_profile','stagnation_watch','idle_robot_contacts','dev_grasp_policy','eval_camera_trace')}
    r=Runtime(static,c.ROOT/c.old.CALIBRATION,c.old.CALIBRATION_SHA,**options,
        motion_model=b['motion_model'],pulse_calibration=b['pulse_calibration'],pulse_odometry=OPTION)
    try:
        pf=r.pose.provider.loc._pf
        expected=selected_model(b['pulse_calibration'],pulse_odometry=OPTION)
        assert r.pulse_profiles==expected['profiles']==pf.pulse_calibration['profiles']
        assert r.record()['pulse_motion_model']['model']['pulse_odometry']['runtime_gt'] is False
        pf.n=10000;pf.initialized=True;pf.t=0.;pf.px=np.zeros((pf.n,3));pf.logw=np.zeros(pf.n)
        pf.load.loaded=False;pf._map_logprior=lambda p:np.zeros(len(p));pf.rng=np.random.default_rng(14202)
        p=r.pulse_profiles['0:turn:0.35:0.10']
        pf.command(dict(t=0.,**action_of(p)));pf.predict_to(.1);pf.command(dict(t=.1,kind='hold'));pf.predict_to(.2)
        assert abs(pf.px[:,2].mean()-p['mean_delta'][2])<.0005
        assert .9*p['prediction_variance'][2]<pf.px[:,2].var()<1.1*p['prediction_variance'][2]
        assert np.linalg.norm(pf.px[:,:2].mean(0)-p['mean_delta'][:2])<.00005
        before=pf.px.copy();pf.predict_to(.4);assert np.array_equal(before,pf.px)
    finally:r.close()
