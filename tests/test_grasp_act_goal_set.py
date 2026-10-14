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
from sim.grasp_act_goal_set import select_goal
from sim.grasp_act_visible_route import constraints, free, segment_free


def saved():
    row=json.loads((Path(__file__).parent/'fixtures/grasp_act_ep030_blocked_goal.json').read_text())
    model=VisibleWorld(row['rid'],row['end'])
    for sample in row['inputs']:
        world=model.observe(sample['measurements'],sample['t'])
        model.issue(sample['issued'])
    return row,world


def teacher(row, mode='approach_goal_set_v1'):
    t=VisibleOnlyGraspTeacher(row['rid'],row['end'],row['pwm'],bounds=(-20,20,-20,20),
        teacher_stability='align_relook_v1',teacher_search='search_body_scan_v2',approach_goal_set=mode)
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


def test_clear_nominal_goal_is_preserved_and_cached():
    row,w=saved();w['walls']=[];w['objects']={};w['robots']={'r1':w['robots']['r1']}
    t=teacher(row);t._approach(w,w['t'])
    assert t.approach_choice==(0.,.203)
    assert len(t.goal_set_log[-1]['candidates'])==1
    t._approach(w,w['t']+.1)
    assert len(t.goal_set_log)==1


def test_new_wall_invalidates_cached_goal_before_next_replan():
    row,w=saved();clear=deepcopy(w);clear['walls']=[]
    t=teacher(row);t._approach(clear,w['t'])
    assert t.approach_choice==(0.,.203)
    t._approach(w,w['t']+.1)
    assert t.approach_choice[0]!=0 and len(t.goal_set_log)==2


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
    for kwargs in ({'approach_goal_set':'bogus'}, {'approach_goal_set':'approach_goal_set_v1'}):
        with pytest.raises(ValueError):VisibleOnlyGraspTeacher('r1','teal',FOLDED,bounds=(-20,20,-20,20),**kwargs)


def test_recording_gate_rejects_different_approach_profile(tmp_path):
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
    with pytest.raises(ValueError,match='approach mode'):
        recording_admission(gate,**kwargs,approach_goal_set='approach_goal_set_v1')
    gate['approach_goal_set']='approach_goal_set_v1'
    with pytest.raises(ValueError,match='mixed approach'):
        recording_admission(gate,**kwargs,approach_goal_set='approach_goal_set_v1')
    for row in gate['rows']:row['approach_goal_set']='approach_goal_set_v1'
    assert recording_admission(gate,**kwargs,approach_goal_set='approach_goal_set_v1')['qualified']
