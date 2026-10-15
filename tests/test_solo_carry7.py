"""Saved proposals and actual numerical/control paths; no simulation/render."""
import copy
import json
import math
from pathlib import Path
import numpy as np
import pytest
from sim.solo_carry7 import (OPTION, innovation_gate, sensor_modes, correction_gate,
                             CargoReacquirer, world_point, body_point)
from sim.solo_carry6 import partial_posterior
from tests.test_solo_carry5 import recovery_teacher
from tests.test_grasp_act_solo_carry import command

FIXTURE=json.loads(Path('tests/fixtures/solo_carry7_proposals.json').read_text())['rows']


def unique(pose):
    return sensor_modes([pose],[0.])


def test_saved_dangerous_partial_and_full_updates_rejected_before_collapse():
    for seed,seconds in ((93266,32.9),(93261,67.4),(93262,76.9)):
        r=next(r for r in FIXTURE if r['seed']==seed and round(r['t'],1)==seconds)
        P=np.diag(np.square(r['prior_sigma']))
        gate=correction_gate(r['prior'],P,r['proposal'],unique(r['proposal']))
        assert not gate['accepted'] and 'prediction_3sigma' in gate['reasons']
        assert gate['prediction_nis'] > 9.
    # The last93266 fix is close to an ALREADY wrong prior; a tighter scalar
    # gate alone cannot repair this. It needs the pre-collapse ambiguity test.
    r=next(r for r in FIXTURE if r['seed']==93266 and round(r['t'],1)==60.3)
    assert innovation_gate(r['prior'],np.diag(np.square(r['prior_sigma'])),r['proposal'])['accepted']


def test_modes_are_circular_and_prior_does_not_hide_symmetric_alternative():
    modes=sensor_modes([[0,0,math.pi-.01],[0,0,-math.pi+.01]],[0.,-.01])
    assert not modes['ambiguous']
    modes=sensor_modes([[0,0,0],[0,0,math.pi/2]],[0.,-.1])
    assert modes['ambiguous'] and len(modes['hypotheses'])==2
    gate=correction_gate(np.zeros(3),np.eye(3)*.01,np.zeros(3),modes)
    assert not gate['accepted'] and gate['additional_view_required']
    assert 'ambiguous_sensor_modes' in gate['reasons']
    assert correction_gate(np.zeros(3),np.eye(3),np.zeros(3),unique([0,0,0]))['accepted']
    assert not correction_gate(np.zeros(3),np.eye(3),np.zeros(3),None)['accepted']


def test_full_covariance_and_yaw_wrap_in_prediction_gate():
    assert innovation_gate([0,0,math.pi-.01],np.eye(3)*.01,[0,0,-math.pi+.01])['accepted']
    P=np.array([[1.,.99,0.],[.99,1.,0.],[0.,0.,1.]])
    assert not innovation_gate([0,0,0],P,[1,-1,0])['accepted']
    assert not innovation_gate([0,0,0],P,[math.nan,0,0])['accepted']


def test_ambiguity_blocks_rank2_covariance_shrink_and_full_acceptance():
    from sim.lookaround_localization import LookaroundLocalizer
    from harness.zone_final_environment import resolve
    f=json.loads(Path('tests/fixtures/solo_carry6_rank2.json').read_text())
    s=resolve('zone_wide_two_doors_final_v3')[0]
    loc=LookaroundLocalizer(s,f['prior']);loc.rank_aware_v1=True;loc.robust_recovery_v1=True
    P=np.diag(np.square(f['prior_sigma']));loc.own.P=P.copy();prior=loc.own.x.copy();rec={}
    loc._grid_update([],f['features'],rec)
    receipt=loc.fix_acceptance([],f['features'],[],prior,P)
    assert rec['sensor_modes']['available'] and receipt['robust_gate']['additional_view_required']
    assert partial_posterior(prior,P,loc.own.x,loc.own.P,loc._acceptance_rows,receipt) is None
    # Exercise the real full-rank residual gate with controlled mode evidence.
    loc.own.x=np.array([0.,0.,0.]);prior=loc.own.x.copy();P=np.eye(3)*.01;loc.own.P=P*.5
    walls=np.array([l['xy'] for l in loc.landmarks if l['group'] in ('wall_west:e','wall_south:n')])
    loc._sensor_modes=unique(prior)
    assert loc.fix_acceptance(walls,[],[],prior,P)['accepted']
    loc._sensor_modes=sensor_modes([prior,[0,0,math.pi/2]],[0.,0.])
    assert not loc.fix_acceptance(walls,[],[],prior,P)['accepted']


def test_reacquisition_turns_body_to_memory_then_scans_both_sides_with_model_clock():
    from sim.grasp_act_solo_teacher import primitives
    from harness.drive_model import CommandDriveModel
    ops=primitives();pwm=dict(ops.folded);pose=np.array([0.,0.,math.pi])
    search=CargoReacquirer(pose,[.8,0.,.024],0.,pwm,ops,source='previous_own_visible_target')
    assert search.budget_s > 60.
    model=CommandDriveModel();turns=0
    for i in range(1500):
        now=i*.1
        turn,pwm=search.tick(now,pose,pwm)
        wheels,durations=ops.duty([0,0,.65*turn])
        dx,dy,da=model.delta(wheels,durations,.1)
        assert dx==dy==0.  # memory never translates the robot
        pose[2]+=da;turns+=bool(turn)
        if search.failure:break
    assert search.failure=='carry_reacquire_unconfirmed'
    assert [e['offset_deg'] for e in search.events]==[0.,-25.,25.,0.]
    assert turns>0 and now < search.deadline


def test_teacher_uses_fresh_visibility_only_and_avoids_old_60second_timeout():
    t,m,look=recovery_teacher();t.robust_recovery_v1=True
    t.phase='carry_reobserve';t.phase_t=0.;t.recovery_started=0.
    t.previous_t=60.;t.previous=command(60.);t.skill_started=0.
    look.step=lambda now,pwm,rgb:(command(now),False)
    t.step(60.1,own_rgb=lambda:None)
    assert t.phase=='carry_reobserve' and t.result is None
    t.phase='carry_reacquire';t.phase_t=60.1;t.recovery_return='approach'
    t.reacquirer=CargoReacquirer(m.loc.pose,world_point(m.loc.pose,[-1.,0.,.024]),60.1,t.sink.pwm,t.ops,source='previous_own_visible_target')
    _,done=t.step(60.2,own_rgb=lambda:None)
    assert not done and t.phase=='carry_reacquire' and t.target is None
    t.step(60.3,measurement={'xyz':[.5,0.,.024],'yaw':0.},own_rgb=lambda:None)
    assert t.phase=='approach' and t.recovery_world is None and t.recovery_started is None


def test_accepted_ready_capture_finishes_before_chasing_old_yaw_again():
    t,m,_=recovery_teacher()
    from sim.grasp_act_solo_lookaround import SoloLookaround
    look=SoloLookaround(m.static,ops=t.ops,truth_free_v1=True,command_pose=m.loc,carry5=True,
        carry5_rank_aware_views_v1=True,carry7_robust_recovery_v1=True)
    look.arm();look.deadline=100.
    class Runner:
        done=False
        def tick(self,now,**cb):
            cb['capture'](now)
            self.done=False
    look.runner=Runner()
    def observe(*args):
        look.loc.own.P=np.eye(3)*.001
        return dict(status='measured',fix_acceptance=dict(accepted=True))
    look.loc.observe=observe
    _,done=look.step(0.,t.sink.pwm,lambda:None)
    assert done and m.loc.fixes==1 and look.events[-1]['event']=='accepted_ready_stop'


def test_world_memory_transform_and_default_off_validation():
    local=[.7,-.2,.024];pose=[1,2,.8]
    np.testing.assert_allclose(body_point(pose,world_point(pose,local)),local)
    t,m,look=recovery_teacher()
    assert not t.robust_recovery_v1 and not m.robust_recovery_v1 and not look.robust_recovery_v1
    assert OPTION not in t.diagnostic()
    from scripts.run_solo_grasp_act_teacher import validate_carry
    from scripts.make_solo_carry7_plan import prepare7,queue7,PLAN
    plan=prepare7();assert [e['seed'] for e in plan['episodes']]==[93261,93262,93266,*range(93280,93288)]
    old=json.loads(Path('experiments/2026-10-15-map-carry-zone/diagnostic-plan-v6.json').read_text())['episodes']
    for e in plan['episodes']:
        validate_carry(e,enabled=True,training_rgb=False,truth_free=True,lift='solo_lift_lookback_v1',negative=False)
        if e['seed'] in (93261,93262,93266):
            prev=next(p for p in old if p['seed']==e['seed'])
            for key in ('spawns','cargo_pose_m','map_id','item_id','scenario_id','scenario_source_sha256'):
                assert e[key]==prev[key]
    q=queue7(json.loads(Path(PLAN).read_text()),'a'*40)
    assert q['run_count']==11 and q['max_parallel']==1
    for obj in [q,q['coordinator_approval'],*q['runs'],*q['execution_stages']]:
        assert all(obj[k] is False for k in ('approved','enabled','ready','stage_ready','execute','submitted'))
    bad={**plan['episodes'][0],OPTION:'yes'}
    with pytest.raises(ValueError):
        validate_carry(bad,enabled=True,training_rgb=False,truth_free=True,lift='solo_lift_lookback_v1',negative=False)
