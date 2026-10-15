"""Nonphysics checks for route debt, observation boundaries and RGB recording."""
from types import SimpleNamespace, ModuleType
import json
import sys

import pytest

from harness.beampair_approach import ApproachRepairMixin, MODE, stale_blockers, CheckedArc
from harness.failure_rgb_tail import FailureRGBTail


def test_gcp2_host_port_preserves_real_metadata_and_restores_pinned_admission(monkeypatch):
    from harness.beampair_host import gcp2_identity
    mod = ModuleType('fixture_host')
    mod.GCP_PROJECT = 'ugrp-act-train-1014'
    monkeypatch.setitem(sys.modules, mod.__name__, mod)
    def identity(_):
        return dict(project_id=mod.GCP_PROJECT, instance='ugrp-sim-gcp2', machine_type='n4-highcpu-64')
    identity.__module__ = mod.__name__
    assert gcp2_identity(identity)['project_id'] == 'ugrp-sim-b-1014'
    assert mod.GCP_PROJECT == 'ugrp-act-train-1014'
    def wrong(_):
        return dict(project_id=mod.GCP_PROJECT, instance='ugrp-sim-gcp1', machine_type='n4-highcpu-64')
    wrong.__module__ = mod.__name__
    with pytest.raises(ValueError):
        gcp2_identity(wrong)
    assert mod.GCP_PROJECT == 'ugrp-act-train-1014'


def test_gate_queue_stays_held_for_scene_and_targets_only_gcp2(tmp_path, monkeypatch):
    import scripts.queue_beampair4 as queue
    import subprocess
    source = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    seeds = [8318620, 8318626, 8318600, 8318604, 8318611, 8318631]
    evidence = tmp_path/'summary.json'
    evidence.write_text(json.dumps(dict(runs=[dict(seed=s,adapter_sha=source) for s in seeds])))
    def previous(*args, **kwargs):
        return dict(source_hashes={}, runs=[dict(name=f'beampair2-{s}',seed=s,episode=i,
            command=['python3','scripts/remote_run.py','--host','gcp1','--per-run-mb','128'])
            for i,s in enumerate(seeds)])
    monkeypatch.setattr(queue,'previous',previous)
    q = queue.build(source,evidence,tmp_path/'table.json')
    assert q['status']=='HOLD_SCENE' and not any(q[k] for k in ('ready','approved','submitted','scene_approved'))
    assert q['host']=='gcp2' and q['project_id']=='ugrp-sim-b-1014'
    assert [r['seed'] for r in q['runs'][:2]]==seeds[:2]
    assert all(r['command'][r['command'].index('--host')+1]=='gcp2' for r in q['runs'])
    assert q['max_parallel']==16 and not q['training_rgb']


def test_named_reobserve_includes_stale_geometric_wall_but_excludes_held_cargo():
    teacher=SimpleNamespace(rid='r2', goal_set_log=[dict(candidates=[dict(collision_audit=[
        dict(id=k,blocked=True,gap_m=0.) for k in ('north','west','beam_1','fresh')])])])
    obs={k:dict(kind='cargo' if k=='beam_1' else 'wall',seen_t=1.)
         for k in ('north','west','beam_1','fresh')}
    obs['fresh']['seen_t']=10.
    w=dict(t=10.,visibility={'r2':{'observations':obs}})
    assert set(stale_blockers(teacher,w))=={'north','west'}


def test_route_observer_is_scoped_and_restored_on_error(monkeypatch):
    calls=[]
    mod=ModuleType('sim.grasp_act_search21')
    mod.route_progress=lambda t,w,g,h,n:calls.append('arc')
    mod.route_projection=lambda p,path:(0,p,p[0])
    monkeypatch.setitem(sys.modules,mod.__name__,mod)
    class Base:
        def _route(self,w,g,h,n):
            self.progress.observe_goal((0,0,0),g,h,n)
            raise RuntimeError('fixture')
    class T(ApproachRepairMixin,Base):pass
    t=T();t.approach_repair=MODE;t.search19_body_active=False;t.path=[(0,0),(1,1)]
    original=lambda *a:calls.append('goal')
    t.progress=SimpleNamespace(observe_goal=original)
    with pytest.raises(RuntimeError):t._route({},(1,1),0,1)
    assert calls==['arc'] and t.progress.observe_goal is original
    t.approach_repair='off'
    with pytest.raises(RuntimeError):t._route({},(1,1),0,1)
    assert calls==['arc','goal']


def test_reobserve_starts_only_after_original_planner_rejects():
    class Base:
        def _plan_approach(self,w,n):return self.valid
    class T(ApproachRepairMixin,Base):pass
    t=T();t.valid=False;t.approach_repair=MODE;t.outcome=None;t.rid='r2'
    t.approach_repair_log=[];t.goal_set_log=[dict(candidates=[dict(failure_audit=[
        dict(id='north',gap_m=0.,margin_m=.05)])])]
    calls=[]
    t.reobserver=SimpleNamespace(active=None,begin=lambda *a:calls.append(a) or True)
    t.approach_blocked_since=2.;t.search21_recovery={'competing':True}
    w=dict(t=3.,beam={},visibility={'r2':dict(visible_probes=15,
        observations={'north':dict(kind='wall',seen_t=1.)})})
    assert t._plan_approach(w,3.) is False
    assert len(calls)==1 and t.approach_blocked_since is None and t.search21_recovery is None
    assert t.approach_repair_log[-1]['blocked_object']=='north'
    t.valid=True;t._plan_approach(w,4.)
    assert len(calls)==1
    t.valid=False;w['beam']=None;t._plan_approach(w,5.)
    assert len(calls)==1


def test_tail_uses_sim_time_and_flushes_only_failure(tmp_path):
    calls=[]
    world=SimpleNamespace(render_jpeg=lambda **kw:calls.append(kw['robot_id']) or b'fixture-jpeg')
    tail=FailureRGBTail()
    for i in range(151):tail.capture(world,{'r1':'teal','r2':'blue'},i/10)
    assert len(tail.frames)==101
    tail.finish(tmp_path/'failure',failed=True)
    report=json.loads((tmp_path/'failure/manifest.json').read_text())
    assert len(report['frames'])==202
    assert report['frames'][0]['t']==5. and report['frames'][-1]['t']==15.
    assert report['stored_bytes']==202*len(b'fixture-jpeg')
    tail.finish(tmp_path/'success',failed=False)
    assert not list((tmp_path/'success').glob('*/*.jpg'))


def test_arc_credits_a_detour_and_cannot_be_earned_by_replanning_or_oscillation():
    tracker=CheckedArc()
    # Known bent route: first movement goes away from the final (1,1) goal.
    def project(p,path):
        return 0,p,-p[0] if p[1]==0 else 1+p[1]
    path=[(0,0),(-1,0),(-1,1),(1,1)]
    assert not tracker.advance((0,0,0),path,.01,project)
    assert tracker.advance((-.1,0,0),path,.01,project)
    assert not tracker.advance((-.1,0,0),list(reversed(path)),.01,project)
    assert not tracker.advance((0,0,0),path,.01,project)
    assert not tracker.advance((-.1,0,0),path,.01,project)
    assert tracker.advance((-.2,0,0),path,.01,project)


def test_arc_after_goal_reset_initializes_original_before_credit(monkeypatch):
    from harness.beampair_approach import BOUNDED_MODE
    mod=ModuleType('sim.grasp_act_search21')
    mod.route_projection=lambda p,path:(0,p,p[0])
    mod.route_progress=lambda *a:None
    monkeypatch.setitem(sys.modules,mod.__name__,mod)
    class Base:
        def _route(self,w,g,h,n):return self.progress.observe_goal((1.,0.,0.),g,h,n)
    class T(ApproachRepairMixin,Base):pass
    t=T();t.approach_repair=BOUNDED_MODE;t.search19_body_active=False;t.path=[(0,0),(2,0)]
    progress=SimpleNamespace(since=None,best_distance=None,required_movement_m=.01,retried=False)
    def original(*args):
        assert progress.since is None or progress.best_distance is not None
        progress.best_distance=1.;progress.since=3.
    progress.observe_goal=original;t.progress=progress
    t._approach_checked_arc=CheckedArc();t._approach_checked_arc.previous=(0.,0.)
    assert t._route({},(2,0),0.,4.) is None
    assert progress.best_distance==1. and progress.since==4.
