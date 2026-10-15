"""No physics/render/ML: protocol release, retained ACT action, input boundary."""
from copy import deepcopy
import subprocess
from types import ModuleType

import pytest

from harness.beamact_pair_student import StudentBarrier, Funnel, STAGES


def command(t=0., grip=2000):
    return dict(t=t,wheels=[.35]*4,duration_s=[.1]*4,
                pwm={'1':grip,'3':800,'4':2400,'5':1320,'6':1500})


def sync():
    # Execute the EXACT protocol from the clean pinned dependency; no teacher
    # or simulator imports. Its PairCarrySync is the shared audited module.
    from harness.beampair_teacher import DEPENDENCY_SHA
    raw=subprocess.check_output(['git','show',DEPENDENCY_SHA+':harness/grasp_act_start_sync.py'],text=True)
    module=ModuleType('pinned_start_sync');exec(compile(raw,'pinned_start_sync.py','exec'),module.__dict__)
    return module.GraspStartSync(('r1','r2'),{'r1':0.,'r2':1.})


def test_close_never_executes_before_both_READY_GO_ACK_and_delay():
    barrier=sync();students={r:StudentBarrier() for r in ('r1','r2')}
    previous={r:command(grip=2000) for r in students}
    proposals={r:command(grip=1500) for r in students}
    for r in students:students[r].propose(proposals[r],False)
    issued={}
    for i in range(15):
        now=i*.1
        permits=barrier.tick({r:s.ready for r,s in students.items()},now)
        for r,s in students.items():
            proposal=None if s.pending else command(now,1500)
            value,_=s.issue(now,previous[r],proposal,False,permits[r])
            if value['pwm']['1']==1500:issued.setdefault(r,now)
            else:
                assert value['pwm']==previous[r]['pwm']
                assert value['wheels']==value['duration_s']==[0.]*4
            previous[r]=value
    assert issued['r1']>=.1 and issued['r2']>=1.
    assert [e['event'] for e in barrier.events[:3]]==['GO','ACK','ACK']
    assert proposals['r1']==command(grip=1500)


def test_pending_proposal_is_exact_and_early_peer_cannot_bypass_barrier():
    barrier=sync();s=StudentBarrier();candidate=command(grip=1749);before=deepcopy(candidate)
    assert s.propose(candidate,False)
    for i in range(20):
        permit=barrier.tick({'r1':True,'r2':False},i*.1)['r1']
        value,done=s.issue(i*.1,command(),None,False,permit)
        assert value['pwm']['1']==2000 and not done
    value,_=s.issue(2.,command(),None,False,True)
    assert value==dict(before,t=2.) and candidate==before
    with pytest.raises(ValueError,match='missing student'):s.issue(2.1,value,None,False,True)


def test_open_endpoint_does_not_claim_ready_and_done_has_no_truth_dependency():
    s=StudentBarrier()
    assert not s.propose(command(grip=1751),False) and not s.ready
    assert s.propose(command(grip=1750),True)
    value,done=s.issue(1.,command(),None,False,False)
    assert not done and value['pwm']['1']==2000
    value,done=s.issue(1.1,command(),None,False,True)
    assert done and s.started


def test_funnel_requires_order_and_counts_rejections_without_success_invention():
    f=Funnel();passed={s:True for s in STAGES};passed['alignment']=False
    f.add(1.,passed)
    assert f.record()['cumulative_run_pass']==dict(approach=1,alignment=0,READY=0,grasp=0,lift_3s=0)
    assert f.record()['frames_rejected']['alignment']==1
    passed['alignment']=True;f.add(2.,passed)
    assert all(f.record()['cumulative_run_pass'].values())


def test_worker_input_rejects_hidden_state_before_inference():
    from harness.grasp_act_rollout import InputAudit
    audit=InputAudit()
    with pytest.raises(ValueError):audit.accept({'teacher_phase':'ready','beam_xyz':[1,2,3]})
    assert audit.record['forbidden_input_fields']==1
