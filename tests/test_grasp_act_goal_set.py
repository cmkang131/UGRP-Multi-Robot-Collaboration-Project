"""Saved visible inputs + static planning only; no MuJoCo or physics calls."""
import json
import math
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import pytest
from harness.grasp_act_visible_world import VisibleWorld
from scripts.zone_teacher import FOLDED
from sim.grasp_act_teacher_v3 import VisibleOnlyGraspTeacher
from sim.grasp_act_goal_set import nominal_goal_blocked, select_goal
from sim.grasp_act_visible_route import constraints, free, segment_free


def saved():
    row=json.loads((Path(__file__).parent/'fixtures/grasp_act_ep030_blocked_goal.json').read_text())
    model=VisibleWorld(row['rid'],row['end'])
    for sample in row['inputs']:
        world=model.observe(sample['measurements'],sample['t'])
        model.issue(sample['issued'])
    return row,world


def teacher(row, mode='approach_goal_set_v1', **kwargs):
    t=VisibleOnlyGraspTeacher(row['rid'],row['end'],row['pwm'],bounds=(-20,20,-20,20),
        teacher_stability='align_relook_v1',teacher_search='search_body_scan_v2',approach_goal_set=mode,**kwargs)
    t.folded_ready=True
    return t


def test_episode030_issued_replay_single_goal_blocked_but_goal_set_has_safe_path():
    from harness.static_keepouts import rect_distance
    row,w=saved();old=teacher(row,'off');pose,end,heading,goal=old._geometry(w)
    radius,discs,rects=constraints(w,'r1',True)
    assert min(rect_distance(goal,r) for r in rects)==pytest.approx(.002689185127,abs=1e-9)
    assert all(math.dist(goal,d[:2])>=radius+d[2] for d in discs)
    value,_=old._approach(w,w['t'])
    assert not old.path and not any(value['wheels'])
    assert old.blocked_goal_calls==old.no_path_calls==1
    new=teacher(row);value,_=new._approach(w,w['t'])
    assert new.path and any(value['wheels']) and new.no_path_calls==0
    assert new.approach_choice[0]!=0
    assert free(new.path_goal,discs,rects,radius)
    points=[pose[:2],*new.path]
    assert all(segment_free(a,b,discs,rects,radius) for a,b in zip(points,points[1:]))
    candidates=new.goal_set_log[-1]['candidates']
    assert new.goal_set_log[-1]['selected']['cost']==min(c['cost'] for c in candidates if c['reason']=='feasible')
    # New observations preserve the chosen end-relative orientation, including READY.
    selected=deepcopy(w);_,_,heading,goal=new._geometry(w)
    selected['robots']['r1']['pose']=[*goal,heading];new.phase='align'
    assert new.ready_geometry(selected)
    _,ready=new._approach(selected,w['t']+1.)
    _,ready=new._approach(selected,w['t']+1.4)
    assert ready and new.approach_choice[0]!=0


def test_gcp_ep006_full_candidate_ledger_has_nine_feasible_stances():
    from collections import Counter
    row=json.loads((Path(__file__).parent/'fixtures/grasp_act_77ee_ep006_goal_set.json').read_text())
    w=row['world'];t=teacher(row)
    selected,checked=select_goal(w,'r1','teal',t.bounds,True)
    assert Counter(c['reason'] for c in checked)=={'blocked_goal':30,'feasible':9}
    assert len(checked)==len(row['candidates'])==39
    for actual,expected in zip(checked,row['candidates']):
        assert actual['reason']==expected['reason']
        assert actual['goal']==pytest.approx(expected['goal'],abs=1e-12)
    assert selected['choice']==pytest.approx(row['selected']['choice'],abs=1e-12)
    assert selected['cost']==pytest.approx(row['selected']['cost'],abs=1e-12)
    value,_=t._approach(w,w['t'])
    assert any(value['wheels']) and t.approach_blocked_since is None and t.outcome is None


def test_all_goals_blocked_handoff_in_three_seconds_and_terminal_hold():
    row,w=saved();t=teacher(row);end=w['beam']['ends']['teal']
    w['objects']['visible_obstacle']={'xy':end[:2],'radius':.6,'top_z_bound_m':.4}
    for dt in (0.,.1,1.,2.,2.9,3.):
        value,_=t._approach(w,w['t']+dt)
        assert not any(value['wheels'])
    assert t.outcome=='approach_blocked_handoff'
    assert t.planner_calls<=4 and not t.path
    value,done=t.step(w,w['t']+50.)
    assert not done and not any(value['wheels'])


def test_lost_view_cannot_reset_blocked_deadline():
    row,w=saved();t=teacher(row)
    w['objects']['block']={'xy':w['beam']['ends']['teal'][:2],'radius':.6,'top_z_bound_m':.4}
    t._approach(w,w['t'])
    value,_=t.step({'beam':None},w['t']+3.)
    assert t.outcome=='approach_blocked_handoff' and not any(value['wheels'])


@pytest.mark.parametrize('phase',['approach','align','ready'])
def test_static_clearance_cannot_bypass_pending_peer_block(phase):
    row,w=saved();t=teacher(row)
    w['objects']['block']={'xy':w['beam']['ends']['teal'][:2],'radius':.6,'top_z_bound_m':.4}
    t._approach(w,w['t'])
    # The static obstruction clears, but a peer now covers every stance.
    # The former _uses_goal_set=False reset lost the deadline here; at the
    # nominal stance it also permitted READY despite that dynamic occupancy.
    w['walls']=[];w['objects']={}
    pose,end,heading,goal=t._geometry(w)
    w['robots']['r1']['pose']=[*goal,heading]
    w['robots']['r2']['pose']=[*end[:2],0.]
    assert not nominal_goal_blocked(w,'r1','teal',t.bounds,True)
    t.phase=phase;t.started=True;t.skill_started=w['t'];t.phase_t=w['t']
    assert not t.ready_geometry(w)
    t.prepare_signal(w,w['t']+.1)
    for dt in (.1,1.1,2.1,3.1):
        value,done=t.step(w,w['t']+dt,permit_pick=True)
        assert not done and not any(value['wheels']) and t.phase not in ('ready','pick','complete')
    assert t.outcome=='approach_blocked_handoff' and not t.prepare_signal(w,w['t']+3.2)
    assert len([e for e in t.events if e.get('approach')=='all_goals_blocked_handoff'])==1


def test_align_cannot_use_an_invalid_goal_set_plan():
    row,w=saved();t=teacher(row)
    t.approach_choice=(math.pi/2,.208)
    _,_,heading,goal=t._geometry(w);w['robots']['r1']['pose']=[*goal,heading]
    t.phase='align';t.approach_plan_valid=False
    assert not t.ready_geometry(w)
    _,ready=t._approach(w,w['t'])
    assert t.approach_plan_valid and not ready


@pytest.mark.parametrize('use_step',[False,True])
def test_visible_clear_nominal_goal_cancels_fallback_deadline(use_step):
    row,w=saved();t=teacher(row);blocked=deepcopy(w)
    blocked['objects']['block']={'xy':w['beam']['ends']['teal'][:2],'radius':.6,'top_z_bound_m':.4}
    t._approach(blocked,w['t'])
    assert t.approach_blocked_since is not None
    clear=deepcopy(w);clear['walls']=[];clear['objects']={};clear['robots']={'r1':clear['robots']['r1']}
    (t.step if use_step else t._approach)(clear,w['t']+3.)
    assert t.approach_blocked_since is None and t.outcome is None


def test_clear_nominal_goal_is_preserved_and_cached():
    row,w=saved();w['walls']=[];w['objects']={};w['robots']={'r1':w['robots']['r1']}
    t=teacher(row);t._approach(w,w['t'])
    assert t.approach_choice==(0.,.203)
    assert not t.goal_set_log and t.planner_calls==1
    t._approach(w,w['t']+.1)
    assert not t.goal_set_log and t.planner_calls==1


def test_new_wall_invalidates_cached_goal_before_next_replan():
    row,w=saved();clear=deepcopy(w);clear['walls']=[]
    t=teacher(row);t._approach(clear,w['t'])
    assert t.approach_choice==(0.,.203)
    t._approach(w,w['t']+.1)
    assert t.approach_choice[0]!=0 and len(t.goal_set_log)==1


NOMINAL_CASES=json.loads((Path(__file__).parent/'fixtures/grasp_act_nominal_regression.json').read_text())['cases']


@pytest.mark.parametrize('row',NOMINAL_CASES,ids=lambda r:f"{r['episode']}-{r['rid']}-{r['kind']}")
@pytest.mark.parametrize('handoff',['off','nominal_blocked_handoff_v1'])
def test_six_baseline_starts_and_late_divergences_preserve_frozen_decisions(row,handoff):
    w=row['world'];t=teacher(row,nominal_blocked_handoff=handoff);expected=row['expected']
    assert not nominal_goal_blocked(w,row['rid'],row['end'],t.bounds,True)
    value,ready=t._approach(w,w['t'])
    # This includes clear direct routes, A* grid segments rejected by v1,
    # nominal alignment without a planner call, and the temporary peer block.
    assert list(t._geometry(w)[3])==expected['goal']
    assert [list(p) for p in t.path]==expected['path']
    assert value==expected['command'] and ready==expected['ready']
    assert t.phase==expected['phase']
    assert (t.planner_calls,t.no_path_calls)==(expected['planner_calls'],expected['no_path_calls'])
    assert t.approach_choice==(0.,.203) and not t.goal_set_log


@pytest.mark.parametrize('phase',['approach','align','ready','search'])
def test_episode030_nominal_map_block_hands_off_before_any_alternative(monkeypatch,phase):
    import sim.grasp_act_goal_set as goals
    from scripts.run_grasp_act_teacher import finalize_outcomes
    from scripts.run_grasp_act_batch import handoff_only,FailureStop,summarize
    row,w=saved();t=teacher(row,nominal_blocked_handoff='nominal_blocked_handoff_v1')
    t.phase=phase;t.started=True;t.phase_t=w['t'];t.skill_started=w['t']
    # A feasible alternative must not be considered under the new contract.
    assert select_goal(w,t.rid,t.end,t.bounds,True)[0] is not None
    monkeypatch.setattr(goals,'select_goal',lambda *a,**kw:pytest.fail('alternative selected'))
    assert not t.prepare_signal(w,w['t'])
    issued,done=t.step(w,w['t'],permit_pick=True)
    assert not done and not any(issued['wheels']) and t.outcome=='approach_blocked_handoff'
    assert not t.goal_set_log and t.nominal_handoff_log[0]['t']==w['t']
    assert not t.diagnostic()['alternative_goal_path_enabled']
    peer=SimpleNamespace(outcome=None,command_complete=False)
    finalize_outcomes({'r1':t,'r2':peer},strict=True,joint_held=False)
    result={'status':'complete','physical_success':False,'approach_handoff':True,
            'teachers':{'r1':t.diagnostic(),'r2':vars(peer)}}
    assert handoff_only(result) and not FailureStop('repeated_cause_v1').observe(6,result)
    assert summarize([result],40)['n']==0 and summarize([result],40)['N']==1


def test_nominal_map_predicate_ignores_cargo_and_peer_but_checks_bounds():
    row,w=saved();w['walls']=[]
    t=teacher(row,nominal_blocked_handoff='nominal_blocked_handoff_v1')
    w['objects']['block']={'xy':w['beam']['ends'][t.end][:2],'radius':1.,'top_z_bound_m':.4}
    assert nominal_goal_blocked(w,t.rid,t.end,t.bounds,True)
    assert not nominal_goal_blocked(w,t.rid,t.end,t.bounds,True,static_map_only=True)
    t._approach(w,w['t'])
    assert t.outcome is None and not t.goal_set_log
    assert nominal_goal_blocked(w,t.rid,t.end,(0.,.01,0.,.01),True,static_map_only=True)


def test_fresh_gate_map_handoff_distribution_reports_original_exclusions():
    from scripts.make_grasp_act_plan import prepare,nominal_start_blocked_roles
    from harness.zone_final_environment import resolve
    original=prepare(count=40,seed=86000,visible_start=True)
    plan=prepare(count=40,seed=86000,visible_start=True,start_nominal_goal_feasible='start_nominal_goal_feasible_v1')
    report=plan['nominal_goal_filter']
    bad=[r['seed'] for r in original['episodes'] if nominal_start_blocked_roles(r,resolve(r['map_id'])[0])]
    assert report['original_blocked_n']==len(bad)>0
    assert report['original_planned_N']==40 and report['original_blocked_rate']==len(bad)/40
    assert [r['seed'] for r in report['original_blocked_starts']]==bad
    assert report['rejected_proposals_n']==plan['rejected_proposals']['start_nominal_goal_blocked']
    assert sum(r['nominal_goal_rejected_proposals'] for r in plan['episodes'])==report['rejected_proposals_n']
    assert [r['seed'] for r in plan['episodes']]==list(range(86000,86040))
    assert all(not nominal_start_blocked_roles(r,resolve(r['map_id'])[0]) for r in plan['episodes'])
    for row in plan['episodes']:
        if row['seed'] not in bad:
            before=next(r for r in original['episodes'] if r['seed']==row['seed'])
            assert row['beam_pose']==before['beam_pose'] and row['spawns']==before['spawns']
    with pytest.raises(ValueError):prepare(count=1,start_nominal_goal_feasible='unknown')


def test_peer_only_block_waits_without_changing_stance_or_starting_handoff():
    row=next(r for r in NOMINAL_CASES if r['episode']=='episode-001' and r['rid']=='r2')
    w=row['world'];t=teacher(row)
    radius,discs,rects=constraints(w,t.rid,True)
    assert not free(t._geometry(w)[3],discs,rects,radius)
    for dt in (0.,1.,2.,3.,4.):
        value,_=t._approach(w,w['t']+dt)
        assert not any(value['wheels'])
    assert t.outcome is None and t.approach_blocked_since is None
    assert t.approach_choice==(0.,.203) and not t.goal_set_log
    clear=deepcopy(w);clear['robots']={t.rid:clear['robots'][t.rid]}
    value,_=t._approach(clear,w['t']+5.)
    assert t.path and any(value['wheels'])


def test_goal_set_rejects_unreachable_ik(monkeypatch):
    import sim.grasp_act_goal_set as goals
    row,w=saved()
    monkeypatch.setattr(goals,'grasp_poses',lambda *a:(_ for _ in ()).throw(ValueError('unreachable')))
    result,checked=select_goal(w,'r1','teal',(-20,20,-20,20),True)
    assert result is None and all(c['reason']=='ik_unreachable' for c in checked)


def test_new_handoff_retains_denominator_and_independent_failure():
    from scripts.run_grasp_act_teacher import finalize_outcomes
    from scripts.run_grasp_act_batch import handoff_only,summarize
    for peer in (None,'alignment_no_progress'):
        ts={'r1':SimpleNamespace(outcome='approach_blocked_handoff',command_complete=False),
            'r2':SimpleNamespace(outcome=peer,command_complete=False)}
        finalize_outcomes(ts,strict=True,joint_held=False)
        result={'index':6,'status':'complete','physical_success':False,'approach_handoff':True,
                'teachers':{rid:vars(t) for rid,t in ts.items()}}
        assert handoff_only(result)==(peer is None)
        summary=summarize([result,{'status':'interrupted','exit':130}],40)
        assert (summary['n'],summary['N'],summary['planned_N'])==(0,1,40)
        assert summary['approach_handoff_n']==1 and summary['approach_handoff_indices']==[6]


def test_goal_set_requires_named_stability_and_valid_toggle():
    for kwargs in ({'approach_goal_set':'bogus'}, {'approach_goal_set':'approach_goal_set_v1'},
                   {'nominal_blocked_handoff':'unknown'},{'nominal_blocked_handoff':'nominal_blocked_handoff_v1'}):
        with pytest.raises(ValueError):VisibleOnlyGraspTeacher('r1','teal',FOLDED,bounds=(-20,20,-20,20),**kwargs)


@pytest.mark.parametrize('key,mode,error',[
    ('approach_goal_set','approach_goal_set_v1','approach'),
    ('nominal_blocked_handoff','nominal_blocked_handoff_v1','nominal handoff')])
def test_recording_gate_rejects_different_approach_profile(tmp_path,key,mode,error):
    import hashlib
    from harness.grasp_act_admission import recording_admission,CRITERIA
    host={'schema':'ugrp.grasp_act.host.v1','provider':'gcp','project_id':'ugrp-act-train-1014',
          'instance':'test','machine_type':'test-16','zone':'test-zone','cpu_count':16}
    plan=tmp_path/'plan.json';plan.write_text('{}')
    gate={'n':40,'N':40,'qualified':True,'source_sha':'abc','teacher_profile':'visible_only',
          'plan_sha256':hashlib.sha256(plan.read_bytes()).hexdigest(),'object_kind':'long_beam',
          'criteria':CRITERIA,'execution_host':host,'self_pose_source':'issued',
          'rows':[{'status':'complete','exit':0,'physical_success':True,'source_sha':'abc',
                   'teacher_profile':'visible_only','execution_host':host} for _ in range(40)]}
    kwargs={'source_sha':'abc','teacher_profile':'visible_only','gate_plan':plan,'execution_host':host}
    with pytest.raises(ValueError,match=error+' mode'):
        recording_admission(gate,**kwargs,**{key:mode})
    gate[key]=mode
    with pytest.raises(ValueError,match='mixed '+error):
        recording_admission(gate,**kwargs,**{key:mode})
    for row in gate['rows']:row[key]=mode
    assert recording_admission(gate,**kwargs,**{key:mode})['qualified']
