"""Numerical counterexamples and saved RGB/command cases, no physics."""
import copy
import ast
import inspect
import json
import math
import subprocess
from pathlib import Path
from types import SimpleNamespace as NS
import numpy as np
import pytest
from sim import release18,release21,release23 as new
from sim.visible_belief import rates,odometry
from sim.release_global_observation import lateral_shift_plans
from tests.test_release_regrasp import teachers
from sim.lookaround_localization import Camera,rotate_plan
from scripts.run_grasp_act_release import run
from scripts import run_grasp_act_release as runner
from tests.test_grasp_act_release_run import fake_backend  # noqa: F401


def reports(m):
    return {rid:dict(kind='localized_margin',margin_m=v,lateral_clearance_m=.1,
        expected_slack_m=.8,axis_error_rad=0.,zone_axis_width_m=1.4,
        observation_epoch=1,observed_at=1.) for rid,v in zip(('r1','r2'),m)}


def choice(m,**opts):
    return new.pair_choice(reports(m),('r1','r2'),2.,goal_region=release18.GOAL_REGION,**opts)


def test_asymmetric_bias_counterexample_cannot_lower(monkeypatch):
    # Actual [-.01,.81], observed [-.02,.68] -> projection [.05,.75].
    # Common-mode alone falsely accepts; the measured residual bound rejects.
    r=choice([-.02,.68],margin_common_mode=new.MARGIN)
    assert r['corrected_margins_m']==pytest.approx([.05,.75])
    assert r['action']=='shift' and min(r['margin_lower_bounds_m'])<.04
    monkeypatch.setattr(new,'ERROR_BOUND_M',0.)
    assert choice([-.02,.68],margin_common_mode=new.MARGIN)['action']=='lower'


def test_same_corrected_lower_bound_at_final_goal_and_no_threshold_relaxation():
    assert choice([.0381,.684],margin_common_mode=new.MARGIN)['action']=='shift'
    r=choice([.10,.62],margin_common_mode=new.MARGIN)
    assert r['action']=='lower' and min(r['margin_lower_bounds_m'])>=.04
    assert min(r['corrected_margins_m'])-new.ERROR_BOUND_M>=.04


def test_off_preserves_legacy_and_toggles_are_independent():
    for m in ([-.36,1.11],[.04,.68],[.2,.6]):
        old=release18.pair_choice(reports(m),('r1','r2'),2.,goal_region=release18.GOAL_REGION)
        assert choice(m)==old
    assert abs(choice([-.36,1.11],release_leg_budget=new.LEG)['shift_m'])==.30
    assert abs(choice([-.36,1.11])['shift_m'])==.20
    for key in new.OPTIONS:assert inspect.signature(run).parameters[key].default=='off'


@pytest.mark.parametrize('mutate',[
    lambda d:d['r2'].update(observation_epoch=2),
    lambda d:d['r1'].update(observed_at=3.),
    lambda d:d['r1'].update(margin_m=math.nan),
    lambda d:d['r1'].update(zone_axis_width_m=1.5),
    lambda d:d['r1'].update(margin_m=.9),
    lambda d:d['r1'].update(margin_m=-.3),
])
def test_missing_inconsistent_or_out_of_domain_reports_reobserve(mutate):
    r=reports([.10,.62]);mutate(r)
    assert new.pair_choice(r,('r1','r2'),2.,margin_common_mode=new.MARGIN)['action']=='observe'


def test_budget_uses_sim_cost_and_keeps_three_corrections():
    assert new.leg_admission(new.LEG_COST_S+new.TAIL_S,2)['accepted']
    assert not new.leg_admission(new.LEG_COST_S+new.TAIL_S-.01,2)['accepted']
    assert not new.leg_admission(180,3)['accepted']


def test_saved_110618_does_not_target_the_noisy_goal_boundary():
    # Actual saved same-round own-RGB reports (DEV1 epoch2); no truth input.
    r=reports([.03499901188660859,.6701831683048443])
    r['r1']['axis_error_rad']=.13952716998704062
    r['r2']['axis_error_rad']=.12306970585159926
    c=new.pair_choice(r,('r1','r2'),2.,goal_region=release18.GOAL_REGION,
        margin_common_mode=new.MARGIN,release_leg_budget=new.LEG)
    assert c['action']=='shift' and c['shift_target']=='existing_end_balance'
    assert c['shift_m']==.30  # existing balance target, rather than a 2.04mm leg
    assert min(c['margin_lower_bounds_m'])<.04  # threshold never relaxed


def test_lateral_cal_changes_only_lateral_and_inverse_plans_match_propagation():
    old=rates('yaw_cal_v1');cal=rates(new.LATERAL)
    assert cal==pytest.approx((.129,.122,1.05)) and (cal[0],cal[2])==(old[0],old[2])
    ts=teachers()
    for t in ts.values():t.zone_rect=(0,0,.3,.7);t.odometry_profile=new.LATERAL
    loc={r:NS(decision={'accepted':True},own=NS(x=np.array([0.,0.,math.pi/2]))) for r in ts}
    p=lateral_shift_plans(loc,ts,.1,profile=new.LATERAL)
    for row in p.values():
        delta=sum((np.array(odometry([w*d/.1 for w,d in zip(ws,ds)],.1,new.LATERAL)) for ws,ds in row),np.zeros(3))
        assert delta==pytest.approx([0.,-.1,0.])
    assert rotate_plan(.05,new.LATERAL)==rotate_plan(.05,'yaw_cal_v1')


def test_continuous_sweep_checks_midpath_beam_and_both_robots():
    ts=teachers();static=dict(bounds_m=[-3,3,-3,3],obstacles=[])
    loc={r:NS(map_pose_known=True,decision={'accepted':True},
          own=NS(x=np.array([0.,i*.8,0.]),P=np.zeros((3,3))),
          global_matcher=NS(static=static)) for i,r in enumerate(ts)}
    plans={r:t.shift_plan(.30,1.) for r,t in ts.items()}
    result=new.sweep(loc,ts,plans,0.)
    json.dumps(result,allow_nan=False)  # actual result writer, including nested checks
    assert result['accepted'] and {c['body'].split()[0] for c in result['checks']}==set(ts)
    # This thin wall lies between start/end robot centers. Whole hull sees it.
    static['obstacles']=[dict(id='thin_wall',center_m=[.15,.175],half_extents_m=[.002,.002])]
    from harness.static_keepouts import pose_clear,disc_footprint
    wall=(.15,.175,.002,.002,0.)
    assert all(pose_clear((x,0.,0.),disc_footprint(.18),[wall],margin=.02) for x in (0.,.30))
    result=new.sweep(loc,ts,plans,0.)
    json.dumps(result,allow_nan=False)
    assert not result['accepted'] and result['blocking_object']=='thin_wall'
    assert result['minimum_gap']<0 and result['computation_checks']>0
    loc['r1'].decision['accepted']=False
    assert not new.sweep(loc,ts,plans,0.)['accepted']


def test_saved_88639_keeps_cap_and_evaluates_lateral_then_fresh_rgb(monkeypatch):
    saved=json.loads((Path(__file__).parent/'fixtures/release23_yaw_88639.json').read_text())
    t=teachers()['r1'];t.pwm={int(k):v for k,v in saved['pwm'].items()};t.odometry_profile='yaw_cal_v1'
    a=new.LineAlign(t,saved['t'],camera=Camera(),undistort=lambda f:f,
        wheel_command=lambda *a:None,clearance=lambda *a:True)
    a.motion=np.array(saved['motion']);f=saved['feature']
    # Saved final error/proposal, no oracle or synthetic new RGB trajectory.
    step=release21.LineAlign.choose_step(a,f,.1,saved['t'])
    assert np.any(a.motion+abs(a.pulse((0.,step['left'],step['yaw']))[2])>new.MOTION_CAP)
    a.last_quantum=None
    r=a.choose_step(f,.1,saved['t'])
    assert r['yaw']==0 and not r['aligned']
    assert any(e['event']=='release23_yaw_budget_reject' for e in a.records)
    assert a.motion.tolist()==saved['motion']
    assert np.all(a.motion+abs(np.array(odometry([w*d/.1 for w,d in zip(*r['allocated_pulse'])],.1,t.odometry_profile)))<=new.MOTION_CAP+1e-9)


def test_compute_budget_does_not_read_wall_time_or_world():
    source=inspect.getsource(new)
    assert not any(s in source for s in ('time.monotonic(', 'perf_counter(', 'data.body(', 'world.'))


def test_release23_off_equals_frozen_release21_runner(tmp_path,fake_backend):
    src=subprocess.run(['git','show','46afd8b0:scripts/run_grasp_act_release.py'],text=True,cwd=runner.ROOT,check=True,stdout=subprocess.PIPE).stdout
    fn=next(n for n in ast.parse(src).body if isinstance(n,ast.FunctionDef) and n.name=='run')
    ns=runner.__dict__.copy();exec(compile(ast.Module(body=[fn],type_ignores=[]),'<release21>','exec'),ns)
    p=json.loads((runner.ROOT/'experiments/2026-10-14-e2e18-grasp-rootcause/release21-dev6-plan.json').read_text())
    world,ports=fake_backend;top=world.render_team_jpeg
    old=ns['run'](p['episodes'][0],tmp_path/'old',cap_s=25.,**p['execution_profile'])
    actions={r:copy.deepcopy(v.actions) for r,v in ports.items()}
    world.data.time=0.;world.steps=0;world.closed=False;ports.clear();world.render_team_jpeg=top
    result=run(p['episodes'][0],tmp_path/'new',cap_s=25.,**p['execution_profile'])
    assert actions=={r:v.actions for r,v in ports.items()}
    for rid in ('r1','r2'):
        assert (tmp_path/'old'/f'teacher-{rid}.jsonl').read_bytes()==(tmp_path/'new'/f'teacher-{rid}.jsonl').read_bytes()
    for k in ('code_decisions','line_rechecks','map_backoff_checks','release_outcome','input_audit'):
        assert old[k]==result[k]


def test_queue_requires_existing_rejection_table_and_full_sha(tmp_path):
    from scripts.prepare_release23_queue import build,verify
    with pytest.raises(ValueError,match='missing'):build('a'*40,tmp_path/'missing')
    table=tmp_path/'table.json';table.write_text('{}')
    with pytest.raises(ValueError,match='full'):build('46afd8b0',table)
    q=build('a'*40,table);verify(q)
    assert [r['seed'] for r in q['runs'][:2]]==[110622,88639]
    assert q['max_combined_concurrency']==6 and not q['training_rgb']
