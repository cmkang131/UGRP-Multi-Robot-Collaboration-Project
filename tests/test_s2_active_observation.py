import copy,json,math
from types import SimpleNamespace as NS
import numpy as np
import pytest
from harness import zone_solo_cyan_active_observation as m


def test_off_is_identity_for_methods_attributes_rng_and_bytes():
    r=NS(record=lambda:dict(pose=[1.,2.,3.]),step=lambda t:[('r3',{'kind':'hold'})],rng=np.random.default_rng(41))
    before=dict(r.__dict__);state=copy.deepcopy(r.rng.bit_generator.state);data=json.dumps(r.record()).encode()
    assert m.attach(r) is r and m.attach(r,active_localization='off') is r
    assert r.__dict__==before and r.rng.bit_generator.state==state and json.dumps(r.record()).encode()==data
    with pytest.raises(ValueError):m.attach(r,active_localization='invalid')


def test_observation_probability_and_information_no_identity_or_unknown_leak():
    f=np.array([[0,1.,0.],[0,1.,0.],[0,2.,.2],[-1,0.,0.]])
    prob=m.observation_probabilities(f)
    np.testing.assert_allclose(prob.sum(1),1.)
    np.testing.assert_array_equal(prob[0],prob[1])
    np.testing.assert_allclose(m.observation_probabilities(np.array([[-1,0.,0.]]*4)),.25)
    px=np.array([[0,0,0],[0,0,0],[1,0,0],[2,0,0]])
    h=m.entropy(np.bincount(m.bins(px))/4)
    after=m.expected_posterior_entropy(px,np.ones(4)/4,prob)
    assert 0<=after<h


def test_static_occlusion_does_not_see_through_wall():
    static={'obstacles':[dict(center_m=[1,0],half_extents_m=[.025,1])]}
    assert m.ray_clear(np.array([[0.,0.],[0.,2.]]),np.array([[2.,0.],[2.,2.]]),static).tolist()==[False,True]


def test_budget_clearance_stay_and_count_constraints():
    stay=dict(name='stay',expected_reduction_nats=.1,added_s=0,clearance_m=1.)
    good=dict(name='turn+45',expected_reduction_nats=.4,added_s=5.,clearance_m=.01)
    bad=dict(name='turn-45',expected_reduction_nats=.8,added_s=5.,clearance_m=-.01)
    assert m.choose([bad,good,stay],45,0,0)==good
    assert m.choose([bad,good,stay],44,0,0) is None
    assert m.choose([good,stay],100,0,5) is None
    assert m.choose([{**good,'expected_reduction_nats':.1},stay],100,0,0) is None
    assert m.choose([good,stay],100,6,1) is None


def test_frozen_pulses_rotation_bound_no_grip_or_translation_commands():
    from harness import zone_s2_realism_contract_v122 as c
    model=c.old.hp.base.read(c.ROOT/c.PULSE_MODEL)
    for loaded in (False,True):
        actions=m.actions(model['profiles'],loaded)
        assert len(actions)==4
        for a in actions:
            assert abs(a['delta'][2])<=math.pi/2
            assert a['command']['forward']==a['command']['left']==0
            assert a['return_command']['turn']==-a['command']['turn']
            assert a['added_s']==pytest.approx((a['pulses']+a['return_pulses'])*.2+3.8)


def test_registration_constants_and_no_gt_or_physics_in_planner():
    from pathlib import Path
    r=json.loads(Path('experiments/2026-10-06-s2-realism/active-observation-registration.json').read_text())
    assert m.LIMITS==r['limits']
    assert r['physical_seeds']==[1060,1062,1063,1064]
    assert r['offline_gates']['s1060_action_before_s']==124.8
    s=Path(m.__file__).read_text()
    assert 'eval_only' not in s and 'import mujoco' not in s and 'agent_lock' not in s


def test_real_stack_default_off_record_and_first_commands_identical():
    from pathlib import Path
    from scripts.run_s2_unknown_start import runtime_factory
    from harness import zone_solo_cyan_contract_v106 as c
    b=json.loads(Path('tests/fixtures/s2_ci/v133-bundle.json').read_text())
    from scripts.run_s2_landmarks_dev import runtime_factory as make
    r=make(b)(c.hp.resolve(c.MAP_ID)[0],c.ROOT/c.CALIBRATION,c.CALIBRATION_SHA,**b['task'])
    try:
        methods=(r.step,r.on_frames,r.pose.provider.loc._pf.update_obs)
        data=json.dumps(r.record()).encode();rng=copy.deepcopy(r.pose.provider.loc._pf.rng.bit_generator.state)
        m.attach(r,active_localization='off')
        assert methods==(r.step,r.on_frames,r.pose.provider.loc._pf.update_obs)
        assert json.dumps(r.record()).encode()==data and r.pose.provider.loc._pf.rng.bit_generator.state==rng
        # On only wraps the score, returning the exact original value.
        m.attach(r,active_localization=m.OPTION)
        assert r.record()['active_localization']['gt_inputs'] is False
    finally:r.close()


def test_new_admission_is_only_v139_plus_active_and_old_seeds_unchanged():
    from harness import zone_s2_active_observation_contract as c
    from harness import zone_s2_unknown_start_contract as old
    assert old.registration()['seeds']==[1059,1060,1061]
    b=c.bundle('a'*40,1060,active_localization=m.OPTION)
    c.require_execution(b)
    frozen=old.bundle('a'*40,1060,**old.NEW_OPTIONS)
    assert {k:v for k,v in b['options'].items() if k!='active_localization'}==frozen['options']
    assert b['task']==frozen['task'] and b['case_cap_s']==900
    with pytest.raises(ValueError):c.require_execution(c.bundle('a'*40,1060))
    with pytest.raises(ValueError):c.bundle('a'*40,1054)


def test_active_action_scheduling_preserves_grip_and_resumes(monkeypatch):
    from pathlib import Path
    from scripts.run_s2_landmarks_dev import runtime_factory
    from harness import zone_solo_cyan_contract_v106 as c
    b=json.loads(Path('tests/fixtures/s2_ci/v133-bundle.json').read_text())
    r=runtime_factory(b)(c.hp.resolve(c.MAP_ID)[0],c.ROOT/c.CALIBRATION,c.CALIBRATION_SHA,**b['task'])
    try:
        r.initial_commands(0.,{'r3':{1:1500,3:740,4:2320,5:1320,6:1500}})
        r.state='carry';r.next_control=0.;r.last_report=NS(x_m=0.,y_m=0.,std_xy_m=.01)
        m.attach(r,active_localization=m.OPTION)
        state=m.closure(r.step)['state'];state['pending']=dict(t=99.,ess=10.,n=2000,trigger=True)
        a=m.actions(r.pulse_profiles,True)[0]
        a.update(expected_reduction_nats=1.,clearance_m=1.)
        stay=dict(name='stay',expected_reduction_nats=0.,clearance_m=1.,added_s=0.)
        monkeypatch.setattr(m,'rank',lambda *args:[a,stay])
        issued=[]
        for t in np.arange(100.,100.+a['added_s']+.01,.05):issued.extend(r.step(float(t)))
        assert sum(q['kind']=='mecanum' for _,q in issued)==a['pulses']+a['return_pulses']
        assert all(q['kind'] in ('mecanum','hold') for _,q in issued)
        assert r.state=='carry' and r.servo[1]==1500 and state['event'] is None
        assert r.record()['active_localization']['added_s']==pytest.approx(a['added_s'])
        assert r.path==[] and r.path_goal is None
    finally:r.close()
