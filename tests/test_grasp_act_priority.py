"""Serial control, boolean protocol and static counterexamples; no physics."""
import hashlib
import json
import math
from copy import deepcopy
from pathlib import Path
import pytest
from harness.grasp_act_start_sync import GraspApproachSync
from harness.grasp_act_input_audit import AuditedTeacherInput,new_input_audit
from scripts.analyze_grasp_act_priority import witness
from scripts.replay_grasp_act_recovery import KW
from sim.grasp_act_priority import MODE,beam_xy,reserved_constraints
from sim.grasp_act_teacher_v3 import VisibleOnlyGraspTeacher
from sim.grasp_act_visible_route import constraints,segment_free
from scripts.zone_teacher import FOLDED

CASES=json.loads((Path(__file__).parent/'fixtures/grasp_act_search10_peer.json').read_text())['cases']


def teacher(rid='r1',end='teal'):
    t=VisibleOnlyGraspTeacher(rid,end,FOLDED,**KW,approach_recovery='off',approach_coordination=MODE)
    t.started=True;t.folded_ready=True;t.phase_t=0.;t.skill_started=0.;t.episode_started=0.
    return t


def world():
    return {'beam':{'pose':[0.,0.,0.],'ends':{'teal':[-.27,0.,.035],'blue':[.27,0.,.035]}},
            'robots':{'r1':{'pose':[1.1,.4,math.pi]},'r2':{'pose':[-.9,-.65,0.]}},
            'objects':{},'walls':[],
            'visibility':{r:{'visible_probes':15,'peers':[q for q in ('r1','r2') if q!=r],'objects':[]} for r in ('r1','r2')}}


@pytest.mark.parametrize('case',CASES,ids=lambda c:str(c['episode']))
def test_saved_visible_geometry_has_three_safe_serial_paths(case):
    proof=witness(case)
    assert proof['exists'] and min(proof['clearance_m'].values())>=.34
    # Runtime's leader planner uses these reservations, not just the report.
    w=deepcopy(case['world']);r=next(r for r,e in case['roles'].items() if e=='teal')
    blue=next(q for q in case['roles'] if q!=r);w['robots'][blue]['pose'][:2]=proof['parking_point']
    t=teacher(r,'teal');t.priority.round=1
    w['visibility']={r:{'visible_probes':15,'peers':[blue],'objects':[]}}
    audit=new_input_audit(True,'issued');data=AuditedTeacherInput(w,audit)
    pose,g,heading,goal=t._geometry(data)
    cmd=t._route(data,goal,heading,w['t'])
    assert any(cmd['wheels']) and t.path
    radius,discs,rects=t._constraints(data)
    assert all(segment_free(a,b,discs,rects,radius) for a,b in zip([pose[:2],*t.path],t.path))
    assert not t.recovery_log and t.peer_wait_since is None
    assert audit['held_world_reads']==audit['invisible_measurements']==0


def test_only_boolean_ready_and_fresh_go_ack_can_advance_each_round():
    s=GraspApproachSync(('r1','r2'),{'r1':0.,'r2':.4})
    with pytest.raises(ValueError,match='READY'):s.tick({'r1':{'pose':[0,0]},'r2':True},0.)
    assert not any(s.tick({'r1':True,'r2':False},0.).values())
    for round_no,at in [(0,1.),(1,3.)]:
        assert not any(s.tick({'r1':True,'r2':True},at).values()) # GO
        assert all(s.tick({'r1':True,'r2':True},at+.1).values()) # ACK
        assert s.round==round_no
        assert not any(s.tick({'r1':False,'r2':True},at+.2).values())
    assert s.round==2
    assert not any(s.tick({'r1':True,'r2':True},5.).values())
    assert s.tick({'r1':True,'r2':True},5.1)=={'r1':True,'r2':False}
    assert all(s.tick({'r1':True,'r2':True},5.5).values())
    assert {e['round'] for e in s.events if e['event']=='GO'}=={0,1,2}


def test_readiness_revocation_before_ack_blocks_approach():
    s=GraspApproachSync(('a','b'),{'a':0.,'b':0.})
    assert not any(s.tick({'a':True,'b':True},0.).values())
    assert not any(s.tick({'a':False,'b':True},.1).values())
    assert s.round==0 and not s.delivered


def test_real_teachers_do_not_translate_together_or_pick_on_approach_go():
    ts={'r1':teacher(),'r2':teacher('r2','blue')};w=world();s=GraspApproachSync(ts,{'r1':0.,'r2':0.})
    ts['r2'].priority.park_goal(w,'r2')
    for now in (0.,.1):
        permits=s.tick({r:t.prepare_signal(w,now) for r,t in ts.items()},now)
        cmds={r:t.step(w,now,permit_pick=permits[r])[0] for r,t in ts.items()}
        assert not any(cmds['r2']['wheels'])
        if now==0.:assert not any(cmds['r1']['wheels'])
    assert all(t.priority.round==1 for t in ts.values())
    assert any(cmds['r1']['wheels']) and all(t.phase!='pick' for t in ts.values())
    # Frozen geometry, not physical motion: place the first robot at its goal.
    w['robots']['r1']['pose']=[-.473,0.,0.];ts['r1'].phase='ready'
    for now in (.2,.3):
        permits=s.tick({r:t.prepare_signal(w,now) for r,t in ts.items()},now)
        cmds={r:t.step(w,now,permit_pick=permits[r])[0] for r,t in ts.items()}
        assert not any(cmds['r1']['wheels'])
    assert all(t.priority.round==2 for t in ts.values())
    assert any(cmds['r2']['wheels']) and all(t.phase!='pick' for t in ts.values())


def test_leader_cannot_resume_translation_during_follower_round(monkeypatch):
    t=teacher();t.priority.round=2;t.phase='align';w=world()
    # Even a revoked READY cannot cause both robots to approach at once.
    monkeypatch.setattr(t,'_approach',lambda *args:pytest.fail('leader moved'))
    cmd,done=t.step(w,1.,permit_pick=False)
    assert not any(cmd['wheels']) and not done


def test_visible_handoff_has_no_truth_input_and_bounds_visual_memory():
    from harness.grasp_act_handoff import visible_local_sample
    w=world();w['robots']['r1']['pose']=[-.473,0.,0.]
    audit=new_input_audit(True,'issued');observed=AuditedTeacherInput(w,audit)
    assert visible_local_sample(observed,'r1','teal',handed_off=True)==(True,pytest.approx(.203))
    assert not visible_local_sample(observed,'r1','teal',handed_off=False)[0]
    assert not visible_local_sample(observed,'r1','teal',handed_off=True,coordinated_wait=True)[0]
    w['visibility']['r1']['visible_probes']=0
    assert visible_local_sample(observed,'r1','teal',handed_off=True)==(False,None)
    w['t']=5.;w['beam']['seen_t']=0.
    assert visible_local_sample(observed,'r1','teal',handed_off=True)[0]
    w['t']=5.3
    assert visible_local_sample(observed,'r1','teal',handed_off=True)==(False,None)
    w['visibility']['r1']['visible_probes']=15;w['beam']=None
    assert visible_local_sample(observed,'r1','teal',handed_off=True)==(False,None)
    assert audit['held_world_reads']==audit['invisible_measurements']==0


def test_roles_are_color_based_and_waiter_requires_visible_clear_parking():
    t=teacher('r1','blue');w=world();w['robots']['r1']['pose']=[-.9,-.65,0.]
    w['robots']['r2']['pose']=[1.1,.4,math.pi]
    t.priority.park_goal(w,'r1');assert t.prepare_signal(w,0.)
    w['robots']['r1']['pose'][1]=-.55
    assert not t.prepare_signal(w,0.)
    w['robots']['r1']['pose'][1]=-.65;w['visibility']['r1']['visible_probes']=0
    assert not t.prepare_signal(w,0.) # remembered geometry cannot release GO
    w['visibility']['r1']['visible_probes']=15;w['objects']['block']={'xy':[-.9,-.65],'radius':.2,'top_z_bound_m':.2}
    assert not t.prepare_signal(w,0.)


def test_wait_and_parking_failure_are_finite_and_keep_zero_wheels():
    t=teacher();cmd,done=t.step({'beam':None},118.)
    assert not any(cmd['wheels']) and not done and t.outcome=='approach_blocked_handoff'
    t=teacher('r2','blue');w=world();w['robots']['r2']['pose'][1]=-.4
    w['objects']['block']={'xy':[-.9,-.65],'radius':.2,'top_z_bound_m':.2}
    for now in (0.,1.,2.,3.):cmd,done=t.priority.step_wait(t,w,now)
    assert not any(cmd['wheels']) and not done and t.outcome=='approach_blocked_handoff'


def test_issued_pulse_is_checked_against_reserved_peer_goal(monkeypatch):
    t=teacher();t.priority.round=1;w=world();w['robots']['r1']['pose']=[.88,0.,math.pi]
    cmd=t._continuous(0.,.15,0.,0.)
    # Pulse crosses the .38m reserved circle; ideal path validation is not enough.
    w['robots']['r1']['pose'][0]=.855
    monkeypatch.setattr(t,'_step',lambda *a,**kw:(cmd,False))
    actual,done=t.step(w,0.)
    assert not any(actual['wheels']) and not done


def test_profile_rejected_before_host_or_physics(tmp_path):
    from scripts.run_grasp_act_teacher import run
    with pytest.raises(ValueError,match='coordination'):
        run({},tmp_path,approach_coordination=MODE)
    with pytest.raises(ValueError,match='coordination'):
        VisibleOnlyGraspTeacher('r1','blue',FOLDED,approach_coordination=MODE)
    with pytest.raises(ValueError,match='coordination'):
        VisibleOnlyGraspTeacher('r1','blue',FOLDED,**KW,approach_coordination=MODE,approach_recovery='approach_recovery_v2')
    with pytest.raises(ValueError,match='visible handoff'):
        run({},tmp_path,handoff_observation='visible_handoff_v1')


def test_speed_and_recording_cannot_inherit_other_coordination_modes(tmp_path,monkeypatch):
    from scripts import run_grasp_act_batch as batch
    from harness.grasp_act_admission import recording_admission,CRITERIA
    prior=tmp_path/'runs/probe';prior.mkdir(parents=True)
    (prior/'RUN_META.json').write_text(json.dumps({'sha':'old'}));(prior/'resource-admission.json').write_text('{}')
    monkeypatch.setattr(batch.subprocess,'check_output',lambda *a,**kw:'old\n')
    monkeypatch.setattr(batch,'execution_tree',lambda *a:{})
    monkeypatch.setattr(batch,'same_machine',lambda *a:None)
    with pytest.raises(ValueError,match='coordination mode mismatch'):
        batch.reuse_speed_gate(prior,tmp_path/'plan.json',16,3.5,{},approach_coordination=MODE)
    import scripts.grasp_act_host as host
    monkeypatch.setattr(host,'same_machine',lambda *a:None)
    plan=tmp_path/'plan.json';plan.write_text('{}')
    gate={'qualified':True,'n':40,'N':40,'source_sha':'sha','teacher_profile':'visible_only','object_kind':'long_beam',
          'criteria':CRITERIA,'self_pose_source':'issued','plan_sha256':hashlib.sha256(plan.read_bytes()).hexdigest()}
    with pytest.raises(ValueError,match='coordination mode mismatch'):
        recording_admission(gate,source_sha='sha',teacher_profile='visible_only',gate_plan=plan,execution_host={},approach_coordination=MODE)
    with pytest.raises(ValueError,match='handoff observation mode mismatch'):
        recording_admission(gate,source_sha='sha',teacher_profile='visible_only',gate_plan=plan,execution_host={},handoff_observation='visible_handoff_v1')
    with pytest.raises(ValueError,match='handoff observation mode mismatch'):
        batch.reuse_speed_gate(prior,plan,16,3.5,{},handoff_observation='visible_handoff_v1')


from sim.grasp_act_priority import OBSERVED_MODE,ObservedPriorityApproach,checked_path
from harness.grasp_act_start_sync import GraspConditionalApproachSync
RESERVATIONS=json.loads((Path(__file__).parent/'fixtures/grasp_act_search12_reservations.json').read_text())['cases']


def conditional(rid='r1',end='teal'):
    t=VisibleOnlyGraspTeacher(rid,end,FOLDED,**KW,approach_coordination=OBSERVED_MODE)
    t.started=True;t.folded_ready=True;t.phase_t=0.;t.skill_started=0.;t.episode_started=0.
    return t


@pytest.mark.parametrize('case',RESERVATIONS,ids=lambda c:str(c['episode']))
def test_actual_no_path_is_reservation_not_peer_body(case):
    w=case['world'];start,goal=case['start'],case['goal'];old=teacher(case['rid'],case['end']);old.priority.round=1
    cs=old._constraints(w)
    assert not checked_path(start,goal,old.bounds,cs)
    from scripts.zone_teacher import PeerDisc
    assert not checked_path(start,goal,old.bounds,(cs[0],[d for d in cs[1] if not isinstance(d,PeerDisc)],cs[2]))
    new=conditional(case['rid'],case['end']);new.activate_coordination(w['t']);new.priority.round=1
    assert new._constraints(w)==constraints(w,new.rid,True)
    assert checked_path(start,goal,new.bounds,new._constraints(w))


def blocked_world():
    w=world();w['t']=0.;w['robots']['r1']['pose']=[-.9,0.,0.];w['robots']['r2']['pose']=[-.55,0.,math.pi]
    return w


def test_conditional_activation_requires_current_blocking_peer_and_net_stall():
    t=conditional();w=blocked_world()
    assert t.priority is None and not t.request_coordination(w,0.)
    assert not t.request_coordination(w,2.9)
    assert t.request_coordination(w,3.)
    sync=GraspConditionalApproachSync(('r1','r2'),{'r1':0.,'r2':0.})
    assert sync.request({'r1':True,'r2':False},3.)
    t.activate_coordination(3.)
    assert t.priority.round==0 and t.priority_request.events[-1]['stalled_s']==3.
    assert not t.request_coordination(w,4.) and not sync.request({'r1':True,'r2':True},4.)
    with pytest.raises(ValueError,match='BLOCKED'):sync.request({'r1':{'xy':[0.,0.]},'r2':False},5.)


@pytest.mark.parametrize('variant',['not_visible','far','ready','search','moving','clear_path'])
def test_nearby_or_remembered_peer_alone_never_changes_baseline(variant):
    t=conditional();w=blocked_world()
    if variant=='not_visible':w['visibility']['r1']['peers']=[]
    if variant=='far':w['robots']['r2']['pose']=[2.,0.,0.]
    if variant in ('ready','search'):t.phase=variant
    if variant=='clear_path':w['robots']['r2']['pose']=[-.9,.6,0.]
    for now in (0.,1.,2.,3.,4.):
        if variant=='moving':w['robots']['r1']['pose'][0]-=.011
        assert not t.request_coordination(w,now)
    assert t.priority is None


def test_dormant_sync_is_exact_pick_barrier_and_cannot_interrupt_pick():
    s=GraspConditionalApproachSync(('a','b'),{'a':0.,'b':.4})
    from harness.grasp_act_start_sync import GraspStartSync
    b=GraspStartSync(('a','b'),{'a':0.,'b':.4})
    for now in (0.,.1,.4):
        assert not s.request({'a':False,'b':False},now)
        assert s.tick({'a':True,'b':True},now)==b.tick({'a':True,'b':True},now)
    assert s.events==b.events and not s.request({'a':True,'b':True},.5)


def test_fixed_parking_does_not_drift_with_reobserved_beam_and_block_second_go():
    w=world();w['t']=0.;t=conditional('r2','blue');t.activate_coordination(0.)
    goal=t.priority.park_goal(w,'r2');assert goal is not None
    w['robots']['r2']['pose'][:2]=goal
    assert t.prepare_signal(w,0.)
    t.priority.advance(t,1.)
    # In ep2/3 the old moving goal became 25.323/25.437 mm away while the
    # waiter could no longer move (25 mm READY tolerance). Fix the goal frame.
    w['beam']['pose'][0]+=.03
    for e in w['beam']['ends'].values():e[0]+=.03
    assert t.priority.park_goal(w,'r2')==goal and t.prepare_signal(w,2.)
    s=GraspApproachSync(('r1','r2'),{'r1':0.,'r2':0.});s.round=1
    assert not any(s.tick({'r1':True,'r2':t.prepare_signal(w,2.)},2.).values())
    assert all(s.tick({'r1':True,'r2':t.prepare_signal(w,2.1)},2.1).values())


def test_no_safe_parking_is_bounded_and_recording_refuses_gt_labels(tmp_path):
    w=world();w['t']=0.;w['visibility']['r2']['peers']=[]
    t=conditional('r2','blue');t.activate_coordination(0.)
    for now in (0.,1.,2.,3.):cmd,done=t.priority.step_wait(t,w,now)
    assert t.outcome=='approach_blocked_handoff' and not done and not any(cmd['wheels'])
    from scripts.run_grasp_act_teacher import run
    with pytest.raises(ValueError,match='recording requires visible handoff'):
        run({},tmp_path,teacher_profile='visible_only',record_training=True)
