"""Saved-input and pure geometry checks; no physics, renderer or World."""
import json
import math
from copy import deepcopy
from pathlib import Path
import pytest
from harness.grasp_act_input_audit import AuditedTeacherInput,new_input_audit
from scripts.run_grasp_act_teacher import run
from scripts.zone_teacher import PeerDisc,FOLDED
from sim.grasp_act_recovery import safe_prefix,peer_goal_blocked
from sim.grasp_act_visible_route import constraints,free,segment_free
from sim.grasp_act_teacher_v3 import VisibleOnlyGraspTeacher
from scripts.replay_grasp_act_recovery import KW

CASES=json.loads((Path(__file__).parent/'fixtures/grasp_act_search8_blocks.json').read_text())['cases']


def make(row,mode='approach_recovery_v1'):
    end='blue' if row['episode'] in (3,8,14,32) else 'teal'
    t=VisibleOnlyGraspTeacher(row['rid'],end,row['pwm'],**KW,approach_recovery=mode)
    t.folded_ready=True
    return t


@pytest.mark.parametrize('idx',[8,14,32])
def test_peer_occupied_goal_moves_only_to_safe_prefix_then_waits(idx):
    row=next(r for r in CASES if r['episode']==idx);w=row['world'];r=row['rid'];t=make(row)
    radius,ds,rects=constraints(w,r,True);pose=w['robots'][r]['pose'];goal=t._geometry(w)[3]
    original=deepcopy(w);assert peer_goal_blocked(goal,ds,rects,radius)
    old=make(row,'off');baseline=old._route(w,goal,0.,w['t']);assert not any(baseline['wheels'])
    value=t._route(w,goal,0.,w['t']);assert any(value['wheels'])
    assert t.peer_route and t.peer_route[-1]!=goal and t._geometry(w)[3]==goal
    assert all(free(p,ds,rects,radius) for p in t.peer_route[1:])
    assert all(segment_free(a,b,ds,rects,radius) for a,b in zip(t.peer_route,t.peer_route[1:]))
    assert w==original and t.outcome is None
    # A waiter never declares READY at an intermediate point.
    w2=deepcopy(w);w2['robots'][r]['pose'][:2]=t.peer_route[-1]
    value=t._peer_route(w2,goal,w['t']+.1);assert not any(value['wheels'])
    assert not t.ready_geometry(w2)
    # A finite budget holds even if the band disappears before the next route call.
    value,done=t.step({'beam':None},w['t']+12)
    assert not done and not any(value['wheels']) and t.outcome=='approach_blocked_handoff'


def test_peer_memory_expiry_does_not_authorize_entry_but_fresh_clear_view_does():
    row=next(r for r in CASES if r['episode']==32);t=make(row);w=deepcopy(row['world']);goal=t._geometry(w)[3]
    t._peer_route(w,goal,w['t']);del w['robots']['r1'];w['visibility']['r2']['peers']=[]
    assert not any(t._peer_route(w,goal,w['t']+1)['wheels']) and t.peer_wait_since is not None
    w['robots']['r1']={'pose':[goal[0]+2,goal[1]+2,0]};w['visibility']['r2']['peers']=['r1']
    t._peer_route(w,goal,w['t']+2)
    assert t._peer_route(w,goal,w['t']+2.4) is None and t.peer_wait_since is None


def test_other_cargo_and_static_wall_are_never_relaxed():
    for row in CASES:
        if row['episode'] not in (3,17):continue
        t=make(row);w=row['world'];rad,ds,rects=constraints(w,row['rid'],True)
        assert not peer_goal_blocked(t._geometry(w)[3],ds,rects,rad)
        if row['episode']==17:
            cmd,done=t.step(w,w['t'])
            assert t.outcome=='approach_blocked_handoff' and not any(cmd['wheels']) and not t.recovery_log
        else:
            assert t._peer_route(w,t._geometry(w)[3],w['t']) is None


def test_prefix_cannot_jump_over_blocked_start_connector_or_another_obstacle():
    start=(0.,0.);goal=(1.,0.);ds=[PeerDisc((1,0,.17)),(.5,0,.1)]
    path=safe_prefix(start,goal,(-2,2,-2,2),ds,[],.13)
    assert path and all(segment_free(a,b,ds,[],.13) for a,b in zip(path,path[1:]))
    assert all(free(p,ds,[],.13) for p in path[1:])


def test_seen_then_lost_target_uses_finite_scan_not_fixed_pitch_forever():
    row=CASES[0];t=make(row);t.ever_seen=True;t.search_since=0.;t.phase='search'
    w={'beam':None,'visibility':{t.rid:{'visible_probes':0}}}
    value=t._observe_stable(w,7.3);assert t.sc['stage']=='sweep' and not any(value['wheels'])
    t._observe_stable(w,58.)
    assert t.outcome=='search_timeout_handoff'
    old=make(row,'off');old.ever_seen=True;old.search_since=0.;old.phase='search'
    value=old._observe_stable(w,7.3);assert old.sc is None and any(value['wheels'])


def test_input_capability_rejects_world_reads_and_audits_zero_clean_access():
    audit=new_input_audit(True,'issued');w=AuditedTeacherInput(CASES[0]['world'],audit)
    assert w['robots'] and w.get('beam') and audit['held_world_reads']==0
    for key in ('world','data','model','contacts','joint_held'):
        with pytest.raises(ValueError,match='held world'):w.get(key)
    assert audit['held_world_reads']==5
    with pytest.raises(ValueError,match='nonvisual'):AuditedTeacherInput({'world':object()},audit)
    assert audit['held_world_reads']==6


def test_profile_rejected_before_any_host_or_physics_work(tmp_path):
    with pytest.raises(ValueError,match='approach recovery'):
        run({},tmp_path,approach_recovery='approach_recovery_v1')
    with pytest.raises(ValueError,match='approach recovery'):
        VisibleOnlyGraspTeacher('r1','blue',FOLDED,approach_recovery='approach_recovery_v1')


def test_speed_gate_cannot_mix_recovery_profiles(tmp_path,monkeypatch):
    from scripts import run_grasp_act_batch as batch
    prior=tmp_path/'runs'/'probe';prior.mkdir(parents=True)
    (prior/'RUN_META.json').write_text(json.dumps({'sha':'old'}))
    (prior/'resource-admission.json').write_text('{}')
    monkeypatch.setattr(batch.subprocess,'check_output',lambda *a,**kw:'old\n')
    monkeypatch.setattr(batch,'execution_tree',lambda *a:{})
    monkeypatch.setattr(batch,'same_machine',lambda *a:None)
    with pytest.raises(ValueError,match='approach recovery mode mismatch'):
        batch.reuse_speed_gate(prior,tmp_path/'plan.json',16,3.5,{},approach_recovery='approach_recovery_v1')
