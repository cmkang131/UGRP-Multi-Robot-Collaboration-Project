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
    for r in students:students[r].propose(proposals[r],False,previous[r])
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
    assert s.propose(candidate,False,command())
    for i in range(20):
        permit=barrier.tick({'r1':True,'r2':False},i*.1)['r1']
        value,done=s.issue(i*.1,command(),None,False,permit)
        assert value['pwm']['1']==2000 and not done
    value,_=s.issue(2.,command(),None,False,True)
    assert value==dict(before,t=2.) and candidate==before
    with pytest.raises(ValueError,match='missing student'):s.issue(2.1,value,None,False,True)


def test_even_one_PWM_close_waits_and_open_hold_does_not_claim_ready():
    s=StudentBarrier()
    assert not s.propose(command(grip=2000),False,command()) and not s.ready
    assert not s.propose(command(grip=2000),False,command(grip=1900)) and not s.ready
    assert s.propose(command(grip=1999),True,command())
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


def test_evaluator_cannot_count_wrong_end_or_center_contacts_as_assigned_grasp():
    from harness.beamact_pair_score import assigned_forces
    ends={'teal':[-.27,0.,.024],'blue':[.27,0.,.024]};roles={'r1':'teal','r2':'blue'}
    contacts=[dict(robot=r,finger=i,position_xyz=ends[role],normal_force_n=.5)
        for r,role in roles.items() for i in range(2)]
    before=deepcopy(contacts)
    assert assigned_forces(contacts,ends,roles)=={'r1':[.5,.5],'r2':[.5,.5]}
    assert contacts==before
    for row in contacts:row['position_xyz']=ends['blue' if roles[row['robot']]=='teal' else 'teal']
    assert assigned_forces(contacts,ends,roles)=={'r1':[0.,0.],'r2':[0.,0.]}
    for row in contacts:row['position_xyz']=[0.,0.,.024]
    assert assigned_forces(contacts,ends,roles)=={'r1':[0.,0.],'r2':[0.,0.]}


def test_raw_recount_preserves_all_HOST_ERROR_runs_without_fabricating_completed_trials(tmp_path,monkeypatch):
    import json
    import sys
    import scripts.analyze_beamact2 as analyze
    (tmp_path/'queue.json').write_text(json.dumps(dict(source_sha='rollout',model_sha256='model')))
    for seed in range(8329000,8329020):
        run=tmp_path/f'seed-{seed}';run.mkdir()
        (run/'result.json').write_text(json.dumps(dict(status='HOST_ERROR',complete=False,cap_end=False)))
    monkeypatch.setattr(analyze,'require_gcp2',lambda **kw:{'scope':'unit fixture'})
    monkeypatch.setattr(analyze,'source_sha',lambda:'analysis')
    monkeypatch.setattr(sys,'argv',['analyze','--root',str(tmp_path)])
    analyze.main()
    value=json.loads((tmp_path/'summary.json').read_text())
    assert value['N']==value['attempted']==20 and value['n']==value['completed']==0
    assert not value['complete'] and value['reason_distribution']=={'HOST_ERROR':20}
    assert value['analysis_source_sha']=='analysis'


def test_resource_admission_counts_orphan_runs_and_excludes_own_descendants_and_wrappers():
    from harness.beamact_resources import other_run_pids
    text='''PID PPID COMMAND
10 1 /env/bin/python -m scripts.sim_cli workflow run beamact2-student
11 10 /env/bin/python -m scripts.run_beamact2_student --plan example
12 11 /env/bin/python -m scripts.beamact2_worker --model example
20 1 /env/bin/python /src/experiments/reloc/run_round.py --worker case.json
21 1 /env/bin/python -m scripts.run_beampair1 --plan case.json
22 1 timeout 8h /env/bin/python -m scripts.run_beampair1 --plan case.json
23 1 bash -c /env/bin/python -m scripts.run_beampair1 --plan case.json
24 1 /usr/bin/python3 /usr/bin/networkd-dispatcher
30 1 /env/bin/python -m scripts.run_grasp_act_student --plan case.json
'''
    assert other_run_pids(text,[10])==[20,21,30]


def test_raw_replay_detects_one_PWM_or_issued_history_tampering():
    import numpy as np
    from harness import grasp_act_contract as c
    from harness.grasp_act_rollout import OwnHistory
    from harness.grasp_act_policy import ChunkExecutor
    from harness.beamact_replay import replay
    initial={r:command(grip=2000) for r in ('r1','r2')}
    histories={r:OwnHistory(r,'replay',v) for r,v in initial.items()}
    students={r:StudentBarrier() for r in initial}
    previous=deepcopy(initial);predictions=[];inputs=[];commands=[];barrier=sync()
    def predict(obs,pictures):
        chunk=np.tile(c.encode_action(command(grip=1500)),(c.CHUNK,1)).tolist()
        predictions.append(dict(t=obs['t'],robot=obs['robot_id'],chunk=chunk))
        return chunk
    executors={r:ChunkExecutor(predict) for r in initial}
    for i in range(16):
        now=i*.1;permits=barrier.tick({r:s.ready for r,s in students.items()},now)
        for rid in initial:
            s=students[rid];waiting=s.pending is not None and not permits[rid]
            obs,pictures,_=histories[rid].observe(now,b'no image decoding in command replay',
                skill='wait' if waiting else 'grasp',object_kind='long_beam',role='teal' if rid=='r1' else 'blue')
            inputs.append(obs);value=None;done=False
            if s.pending is None:
                value,done=executors[rid].step(obs,pictures);s.propose(value,done,previous[rid])
            value,done=s.issue(now,previous[rid],value,done,permits[rid])
            commands.append(dict(t=now,robot=rid,command=value,done=done,ready=s.ready,permit=permits[rid],waiting=waiting))
            histories[rid].issue(value);previous[rid]=value
    protocol=dict(events=barrier.events,own_events={r:s.events for r,s in students.items()},delays_s=barrier.delays)
    assert replay(inputs,commands,predictions,initial,protocol)['command_mismatches']==0
    changed=deepcopy(commands);changed[-1]['command']['pwm']['3']+=1
    with pytest.raises(ValueError,match='command replay'):replay(inputs,changed,predictions,initial,protocol)
    changed=deepcopy(inputs);changed[-1]['issued'][-1]['pwm']['3']+=1
    with pytest.raises(ValueError,match='issued history'):replay(changed,commands,predictions,initial,protocol)
