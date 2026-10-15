"""Saved counterexamples and metadata tests only; no simulator or renderer."""
import importlib.util
import json
import math
from copy import deepcopy
from pathlib import Path
import pytest
from scripts.run_crate_teacher import make_grasp_teacher,run
from scripts.zone_teacher import FOLDED
from sim.crate_navigation_v12 import WallFootprint
from sim.crate_candidate_recovery import staging_view
from sim.crate_approach_recovery import safe_pulse
from sim.crate_inspection_return import reverse_lift,inspection_choice
from sim.crate_cartesian_lift import plan_lift
from harness.visual_arm_v3 import solve_grip_site_ik
ROOT=Path(__file__).resolve().parents[1]
CASES=json.loads((ROOT/'tests/fixtures/crate13_inputs.json').read_text())

def teacher(mode='crate_candidates_v1'):
 return make_grasp_teacher('r1','teal',FOLDED,teacher_stability='align_relook_v1',teacher_search='search_reacquire_v1',
  approach_goal_set='approach_goal_set_v1',crate_lift_pose='crate_antipodal_grasp_v1',crate_approach_recovery='crate_approach_recovery_v1',
  crate_wall_footprint='crate_footprint_v1',crate_stances='crate_stances_v1',crate_pulse_safety='crate_no_closer_v1',crate_candidate_recovery=mode)

@pytest.mark.parametrize('name',CASES)
def test_real_blocked_stations_get_safe_navigation_goal_never_ready(name):
 w=deepcopy(CASES[name]['world']);t=teacher();t.folded_ready=True
 assert not t._plan_approach(w,w['t'])
 assert all(c['reason'] in ('blocked_goal','grasp_geometry') for c in t.goal_set_log[-1]['candidates'])
 v=staging_view(w,t);assert v is not None
 nav=WallFootprint(w,'r1',True,t.cargo_profile,t.bounds)
 assert nav.free(v['goal'],v['heading'])
 assert all(nav.segment(a,b,nav.pose[2] if i==0 else v['heading'],v['heading']) for i,(a,b) in enumerate(zip(v['path'],v['path'][1:])))
 cmd=t._staging_recovery(w,w['t']);checked=t._check_navigation_pulse(w,cmd,w['t'])
 assert any(checked['wheels']) and not t.approach_plan_valid
 assert safe_pulse(checked,nav.pose,nav.discs,nav.rects,nav.radius,mode='crate_no_closer_v1',wall_footprint=True)
 assert t.crate_recovery_log[0]['ready'] is False
 assert t.staging_since==w['t']
 t._staging_recovery(w,w['t']+12.)
 assert t.outcome=='approach_blocked_handoff'


def test_staging_does_not_remove_peer_or_wall_and_repeated_choice_expires():
 w=deepcopy(CASES['crate-diag-77990-fd724191']['world']);t=teacher();t.folded_ready=True
 for dt in (0,1,2,3):t._staging_recovery(w,w['t']+dt)
 assert t.staging_excluded
 first=next(iter(t.staging_excluded))
 v=staging_view(w,t,t.staging_excluded);assert v is None or v['key']!=first
 before=deepcopy(w);w['walls']=[(0,0,3,3,0)]
 assert staging_view(w,t) is None
 c=t._staging_recovery(w,w['t']+4)
 assert not any(c['wheels']) and t.arm.until>w['t']+4
 assert t.crate_recovery_log[-1]['recovery']=='staging_no_safe_route_reobserve'
 assert before['robots'].keys()==w['robots'].keys()


def test_off_keeps_legacy_three_second_handoff():
 w=deepcopy(CASES['crate-diag-77990-fd724191']['world']);t=teacher('off');t.folded_ready=True
 assert not t._plan_approach(w,w['t'])
 assert t.approach_blocked_since==w['t']
 t._plan_approach(w,w['t']+3.)
 assert t.outcome=='approach_blocked_handoff'


def lift_history():
 closed={1:1500,**solve_grip_site_ik((.1962,0.,.024))};p,_=plan_lift(closed);assert p is not None
 samples=[dict(closed)]
 for at in sorted({e[0] for e in p['events']}):
  q=dict(samples[-1]);q.update({sid:v for t,sid,v in p['events'] if t==at});samples.append(q)
 history=[{'wheels':[0.]*4,'pwm':q} for q in samples]
 return closed,p['issued_pwm'],history


def test_inspection_is_exact_reverse_not_destination_inside():
 closed,current,history=lift_history();path=reverse_lift(closed,current,history)
 assert len(path)==24 and path[-1][0]==pytest.approx(2.4)
 assert path[-1][1]=={s:closed[s] for s in (3,4,5,6)}
 assert [p for _,p in path]==[{s:c['pwm'][s] for s in (3,4,5,6)} for c in reversed(history[:-1])]
 choice={'action':'observe','signals':['UNKNOWN','UNKNOWN']}
 assert inspection_choice(choice,{'r1':path,'r2':path},used=False,after_visible=False)=='return_to_pickup_for_observation'
 assert choice['signals']==['UNKNOWN','UNKNOWN']
 for paths,used,after in (({'r1':path,'r2':None},False,False),({'r1':path},True,False),({'r1':path},False,True)):
  assert inspection_choice(choice,paths,used=used,after_visible=after)=='insufficient'

@pytest.mark.parametrize('change',('wheel','unknown_arm','open_grip','wrong_endpoint'))
def test_inspection_rejects_nonreversible_command_evidence(change):
 closed,current,history=lift_history()
 if change=='wheel':history[8]['wheels']=[.35]*4
 if change=='unknown_arm':history[8]['pwm'][6]+=20
 if change=='open_grip':current[1]=2000
 if change=='wrong_endpoint':current[3]+=1
 assert reverse_lift(closed,current,history) is None


def test_v6_generation_and_exclusion_preserve_proposal_index_and_rng(monkeypatch):
 from scripts import make_crate_teacher_plan as p
 kw=dict(seed=79314,split='crate13_diagnostic',assignment='fixed_rgb_lugs_v1',scenario_set='v6')
 a=p.prepare(count=12,**kw);b=p.prepare(count=10,near_wall_policy='exclude_report_v1',**kw)
 assert b['episodes']==[e for e in a['episodes'] if not e['near_wall']]
 f=b['near_wall_filter'];assert (f['drawn_episode_count'],f['excluded_count'],f['accepted_count'])==(12,2,10)
 assert f['excluded_rate']==pytest.approx(2/12)
 for e in b['episodes']:
  s=json.loads((ROOT/'configs/zone_study_scenarios_v6'/f"{e['scenario_id']}.json").read_text())
  assert not {q['kind'] for q in s['eval']['setup']['placements']}&{'tile','can','tri_frame'}
 # Metadata-only 40-accepted contract; no reservation or saved real plan.
 monkeypatch.setattr(p,'check_range',lambda *args:None)
 gate=p.prepare(count=40,near_wall_policy='exclude_report_v1',**kw)
 assert len(gate['episodes'])==40 and all(not e['near_wall'] for e in gate['episodes'])
 assert gate['near_wall_filter']['drawn_episode_count']==40+gate['near_wall_filter']['excluded_count']
 assert gate['criteria']['minimum_episodes']==40


def test_old_generator_episode_payload_unchanged():
 from scripts.make_crate_teacher_plan import prepare
 old=json.loads((ROOT/'experiments/2026-10-14-crate-teacher/diag_plan_crate12_77990.json').read_text())
 new=prepare(count=10,seed=77990,split='crate_diagnostic',assignment='fixed_rgb_lugs_v1',scenario_set='v5')
 assert new['episodes']==old['episodes']


def test_v6_loader_resolves_canonical_scene_without_world():
 from harness.zone_environment_registry import load_scenario
 for sid in ('s2_unmapped_blockage_v6','s8_mixed_tiers_v6'):
  assert load_scenario(sid)['scenario_id']==sid

@pytest.mark.parametrize('kwargs,match',[
 ({},'held_object'),({'held_object':'hidden_v1','own_pose_source':'truth_comparison'},'truth pose'),
 ({'held_object':'hidden_v1','recording_mode':'training'},'not implemented'),
 ({'held_object':'hidden_v1','observe_mode':'gaze_v2'},'backoff_v3')])
def test_profile_rejects_forbidden_input_and_recording_before_world(tmp_path,kwargs,match):
 opts={'crate_profile':'crate13_v1','observe_mode':'backoff_v3',**kwargs}
 with pytest.raises(ValueError,match=match):run({},tmp_path/'not-created',**opts)
 assert not (tmp_path/'not-created').exists()


def test_queue_all_admission_flags_false_and_speed_is_record_only():
 p=ROOT/'experiments/2026-10-14-crate-teacher/crate13_queue.py';spec=importlib.util.spec_from_file_location('queue13',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
 q=m.build('f'*40,{})
 assert len(q['runs'])==13 and not q['coordinator_approval']['approved'] and not q['gate_approved']
 assert not q['ready'] and not any(q['stage_ready'].values())
 assert all(not r['ready'] and not r['stage_ready'] and not r['runs_enabled'] for r in q['runs'])
 assert q['speed_limit']['warn_above']==3.5 and q['speed_limit']['median_wall_per_sim_max']==6.
 assert all(not r['near_wall'] for r in q['runs'] if r['stage']=='diagnostic')
