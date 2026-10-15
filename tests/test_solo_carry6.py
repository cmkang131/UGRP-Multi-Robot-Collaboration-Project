"""carry6 numerical and control-path regressions; no physics or rendering."""
import json
import math
from pathlib import Path
import numpy as np
import pytest
from sim.solo_carry6 import partial_posterior, rank_aware_plan, sigma_poses, validate_calibration
from sim.solo_carry_pose import CommandPose, task_start
from sim.solo_carry_to_zone import CarryToZone
from tests.test_grasp_act_solo_carry import static, command
from tests.test_solo_carry5 import recovery_teacher, PROFILE

DIR = Path('experiments/2026-10-15-map-carry-zone')


def test_saved93240_floor_detection_grid_partial_keeps_x():
    from harness.zone_final_environment import resolve
    from sim.lookaround_localization import LookaroundLocalizer
    f=json.loads(Path('tests/fixtures/solo_carry6_rank2.json').read_text())
    plan=json.loads((DIR/'diagnostic-plan-v5.json').read_text())['episodes'][0]
    loc=LookaroundLocalizer(resolve(plan['map_id'])[0], f['prior']);loc.rank_aware_v1=True
    P=np.diag(np.square(f['prior_sigma']));loc.own.P=P.copy();prior=loc.own.x.copy()
    loc._grid_update([],f['features'],{})
    receipt=loc.fix_acceptance([],f['features'],[],prior,P)
    assert not receipt['accepted'] and receipt['pose_rank']==2
    result=partial_posterior(prior,P,loc.own.x,loc.own.P,loc._acceptance_rows,receipt)
    x,C,_=result
    assert x[0]==pytest.approx(prior[0]) and C[0,0]==pytest.approx(P[0,0])
    assert x[1]-prior[1]==pytest.approx(.201,abs=.002)
    assert x[2]-prior[2]==pytest.approx(.177,abs=.002)


def test_rank2_partial_preserves_unobserved_x_and_cannot_renew_full_fix():
    prior=np.array([0.,0.,0.]); P=np.diag([.16,.16,.04])
    post=np.array([.23,.20,.17]); C=P*.1
    receipt=dict(accepted=False,pose_rank=2,residual_count=2,inlier_fraction=1.,
                 innovation_chi2=1.01,information_gain=5.5,minimum_information_gain=.05)
    x,cov,rec=partial_posterior(prior,P,post,C,[[0,1,0],[0,0,1]],receipt)
    assert x[0] == 0 and cov[0,0] == pytest.approx(P[0,0])
    np.testing.assert_allclose(x[1:],post[1:])
    assert rec['null_variance_after'] == pytest.approx(rec['null_variance_before'])
    assert np.linalg.eigvalsh(cov).min() > 0 and not rec['counts_as_fix']
    p=CommandPose(task_start(static()));p.distance_since_fix=1.3
    old=p.sigmas(); p.own.P=np.diag(np.square(old));p.own.P[1,1]*=.25
    p.partial_fix()
    assert p.sigmas()[0] == pytest.approx(old[0]) and p.sigmas()[1] < old[1]
    assert p.fixes == 0 and p.last_fix is None and p.distance_since_fix == 1.3
    p.issue(command(t=p.now),.1)
    assert p.sigmas()[0] > old[0]
    for bad in ({'pose_rank':3},{'inlier_fraction':.755},{'innovation_chi2':12.}, {'information_gain':0.},
                {'inlier_fraction':float('nan')}):
        assert partial_posterior(prior,P,post,C,[[0,1,0],[0,0,1]],{**receipt,**bad}) is None


def test_rank_planner_checks_corners_and_uses_body_when_pans_are_rank2():
    lm=[dict(id='y',group='y',xy=(0,1),model='line_point',normal=(0,1),sigma=.04),
        dict(id='x',group='x',xy=(1,0),model='line_point',normal=(1,0),sigma=.04),
        dict(id='y2',group='y',xy=(1,1),model='line_point',normal=(0,1),sigma=.04)]
    P=np.diag([.01,.01,.001]);p=(0,0,0)
    def visible(p,yaw,pan,l):
        return l['id']!='x' or yaw!=0
    plan=rank_aware_plan(p,P,lm,visible)
    assert plan['rotated'] and plan['rank_aware']['robust_feasible']
    assert plan['rank_aware']['minimum_eigenvalue'] >= 100
    samples=sigma_poses(p,P)
    assert len(samples)==27 and any(np.allclose(s,[.2,.2,2*math.sqrt(.001)]) for s in samples)
    fallback=rank_aware_plan(p,P,lm,lambda p,y,pan,l:l['id']!='x',retry=2)
    assert not fallback['rank_aware']['robust_feasible']
    assert all(v['body_yaw_deg']==-90 for v in fallback['views'])


def test_same_place_retries_use_full_twelve_attempts_then_stop():
    s=static();m=CarryToZone(s,'A',start=task_start(s),recovery_profile=PROFILE,carry5_rank_aware_views_v1=True)
    m.request_recovery(0,'pose_budget')
    for attempt in range(1,12):
        assert m.recovery_count==attempt and not m.finish_recovery(0,0)
        assert m.failure is None
    assert m.recovery_count==12 and not m.finish_recovery(0,0)
    assert m.failure=='carry_relocalization_unconfirmed' and m.loc.fixes==0


def test_teacher_rescans_instead_of_failing_after_first_attempt():
    # Exercise real teacher branch; view completion stub only, no backend.
    t,m,look=recovery_teacher();m.rank_aware_v1=True
    t._start_carry_scan(0.)
    look.step=lambda now,pwm,rgb:(command(now),True)
    calls=[]
    look.start=lambda now,pan:calls.append((now,look.rank_retry))
    t.step(.1,own_rgb=lambda:None)
    assert t.result is None and t.phase=='carry_reobserve'
    assert m.recovery_count==2 and calls==[(.1,1)]


def test_capture_partial_preserves_budget_replans_and_bounds_same_scene_loop():
    from sim.grasp_act_solo_lookaround import SoloLookaround
    from sim.grasp_act_solo_teacher import primitives
    t,m,_=recovery_teacher();p=m.loc;p.distance_since_fix=1.3
    look=SoloLookaround(m.static,ops=primitives(),truth_free_v1=True,command_pose=p,
                        carry5=True,carry5_rank_aware_views_v1=True)
    look.arm(); before=p.sigmas()[0]
    class Runner:
        done=False
        def tick(self,now,**callbacks):
            callbacks['capture'](now)
            self.done=False  # runner finalisation must not undo the budget stop
    look.runner=Runner()
    def observe(now,frame,pwm):
        look.loc.own.x[1]+=.1;look.loc.own.P[1,1]*=.5
        return dict(status='measured',fix_acceptance=dict(accepted=False),partial_update=dict(applied=True))
    look.loc.observe=observe
    replans=[]
    look.start=lambda now,pan,**kw:replans.append(kw)
    for i in range(3):
        _,done=look.step(0.,t.sink.pwm,lambda:None)
        assert p.fixes==0 and p.last_fix is None and p.distance_since_fix==1.3
        assert p.sigmas()[0]==pytest.approx(before)
    assert len(replans)==2 and all(r['continuation'] for r in replans) and done


def test_trim_changes_mixed_yaw_once_but_leaves_pure_body_turns():
    cal=json.loads((DIR/'carry6-trim-calibration.json').read_text());validate_calibration(cal)
    a=CommandPose(task_start(static()),drive_model_deadband_v1=True)
    b=CommandPose(task_start(static()),drive_model_deadband_v1=True,
                  carry5_trim_yaw_calibration_v1=True,trim_calibration=cal)
    cmd={**command(),'duration_s':[.10,.08,.10,.08]}
    a.issue(cmd,.1);b.issue(cmd,.1)
    assert b.last_delta[2]==pytest.approx(a.last_delta[2]*cal['trim_yaw_scale'])
    assert b.cached_delta(cmd,.1)==b.last_delta
    pure={**command(.1),'wheels':[-.35,.35,-.35,.35]}
    a.issue(pure,.1);b.issue(pure,.1)
    assert b.last_delta[2]==a.last_delta[2]
    with pytest.raises(ValueError):
        validate_calibration({**cal,'validation_ids':cal['calibration_ids']})
    with pytest.raises(ValueError):
        validate_calibration({**cal,'drive_model_sha256':'0'*64})


def test_plan_and_queue_are_explicitly_separate_disabled_conditions():
    from scripts.make_solo_carry6_plan import PLAN, queue6
    from scripts.run_solo_grasp_act_teacher import validate_carry
    plan=json.loads(Path(PLAN).read_text())
    assert [e['seed'] for e in plan['episodes']]==[93240,*range(93260,93267)]
    for e in plan['episodes']:
        validate_carry(e,enabled=True,training_rgb=False,truth_free=True,lift='solo_lift_lookback_v1',negative=False)
        assert e['carry5_rank_aware_views_v1'] and not e['carry5_trim_yaw_calibration_v1']
    q=queue6(plan,'a'*40)
    assert q['max_parallel']==1 and not q['previous_results_combinable']
    for row in [q,q['coordinator_approval'],*q['runs'],*q['execution_stages']]:
        assert all(row[k] is False for k in ('approved','enabled','ready','stage_ready'))
