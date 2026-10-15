"""Real teacher / real pinned runner boundary tests; physics/render tripwires."""
from contextlib import contextmanager
from copy import deepcopy
import importlib
import io
import json
import math
import os
from pathlib import Path
import signal
from types import SimpleNamespace

import pytest

from harness.grasp_act_dart import recovery_hooks
from harness.grasp_act_perturb import RecoveryPerturb, recovery_statistics
from harness.grasp_act_search import CommandSearch, SEARCH_MODE, SEARCH_LIMIT_S, command_delta
from harness.grasp_act_data import read_json, sha256
from harness.grasp_act_recovery_gate import verify_gate
from scripts import run_grasp_act_recovery as adapter
from scripts.audit_grasp_act_act11 import fit_gain, predictions
from scripts.queue_grasp_act_act11 import build_queue, SEEDS, start_bearing
from tests.test_grasp_act_act7 import archive, archived_dependency
from tests.test_grasp_act_act6 import gate_fixture
from tests.test_grasp_act_act9 import ledger
from tests.test_grasp_act_act10 import hold, gaze, slew

ROOT=Path(__file__).resolve().parents[1]
RECORD=ROOT/'experiments/2026-10-15-act-train'


def block_world(monkeypatch):
    def forbidden(*args,**kwargs):pytest.fail('physics/render forbidden')
    world=importlib.import_module('sim.masterpi_drive_friction_v7')
    monkeypatch.setattr(world,'build_world',forbidden)
    mujoco=importlib.import_module('mujoco')
    for name in ('mj_step','mj_forward','Renderer'):monkeypatch.setattr(mujoco,name,forbidden)


@pytest.mark.parametrize('bearing_deg',[24.,-24.8])
@pytest.mark.parametrize('reacquire_t',[None,4.3])
def test_real_teacher_initial_unseen_keeps_parent_scan(archived_dependency,monkeypatch,bearing_deg,reacquire_t):
    """Synthetic own observations at the requested bearings, no FOV/physics claim.

    The teacher has no absolute starting-yaw input. Until reacquisition both
    scenes correctly supply None; bearing appears only in the visible sample.
    """
    model=read_json(RECORD/'act11-noise.json')
    with adapter.dependency_modules(archived_dependency):
        block_world(monkeypatch)
        tm=importlib.import_module('sim.grasp_act_solo_teacher')
        rm=importlib.import_module('harness.grasp_act_solo_recording')
        ops=tm.primitives();original=tm.SoloTeacher
        def make(cls):return cls('cyan','west',ops.folded,profile=tm.PROFILE,
            held_object_hidden_v1=True,ops=ops,teacher_stability='align_relook_v1')
        parent=make(original);noise=RecoveryPerturb(model,seed=1,mode=SEARCH_MODE)
        noise.injections=1  # exercise initial search, without a later yaw probe
        pans=set();stream=io.StringIO()
        with recovery_hooks(tm,rm,noise,stream):
            teacher=make(tm.SoloTeacher)
            for tick in range(121):
                now=tick*.1
                angle=math.radians(bearing_deg)
                measurement=({'xyz':[.8*math.cos(angle),.8*math.sin(angle),.024],'yaw':0.}
                    if reacquire_t is not None and now>=reacquire_t else None)
                expected,done=parent.step(now,measurement=measurement)
                actual,complete=teacher.step(now,measurement=measurement)
                assert actual==expected and complete==done
                assert teacher.result is None and teacher.phase in ('fold','approach','align')
                pans.add(actual['pwm']['6'])
                if measurement is None:
                    assert teacher.recovery_search.seen_t is None
                    assert teacher.search_diagnostic is None
                else:assert teacher.recovery_search.seen_t==now
            assert len(pans)>3  # actual issued pan changes, no fabricated RGB
            assert not any(r.get('active_search') for r in map(json.loads,stream.getvalue().splitlines()))


@pytest.mark.parametrize('trigger',['signal','marker'])
@pytest.mark.parametrize('writer_fails',[False,True])
@pytest.mark.parametrize('partial_ledger',[False,True])
def test_real_runner_repeated_sigint_still_atomically_writes_audit(archived_dependency,monkeypatch,tmp_path,trigger,writer_fails,partial_ledger):
    original=adapter.dependency_modules;out=tmp_path/'run/raw';seen=[]
    before_handler=signal.getsignal(signal.SIGINT)
    @contextmanager
    def scoped(root):
        with original(root):
            block_world(monkeypatch)
            host=importlib.import_module('scripts.grasp_act_host')
            monkeypatch.setattr(host,'identity',lambda _: {'instance':'ugrp-sim-gcp1','machine_type':'n4-highcpu-64'})
            monkeypatch.setattr(host,'require_run_root',lambda _:None)
            runner=importlib.import_module('scripts.run_solo_grasp_act_teacher')
            def git(args,**kwargs):
                assert kwargs['cwd']==root
                return adapter.TEACHER_SHA+'\n' if args==['git','rev-parse','HEAD'] else b''
            monkeypatch.setattr(runner,'subprocess',SimpleNamespace(check_output=git))
            writer=importlib.import_module('scripts.run_grasp_act_teacher');write=writer.write
            def failing_write(path,value):
                if writer_fails and path.name=='result.json' and value['status']!='running':
                    raise OSError('injected pinned except writer failure')
                write(path,value)
            monkeypatch.setattr(writer,'write',failing_write)
            monkeypatch.setattr(writer,'compress_logs',lambda _:None)
            tm=importlib.import_module('sim.grasp_act_solo_teacher');record=tm.InputAudit.record
            def interrupt_during_record(audit):
                assert signal.getsignal(signal.SIGINT)==signal.SIG_IGN
                # Simulate marker + repeated operator interrupts inside the
                # pinned runner's except block and adapter's finally snapshot.
                os.kill(os.getpid(),signal.SIGINT);os.kill(os.getpid(),signal.SIGINT)
                seen.append(True)
                audit.blocked_hidden+=1
                return record(audit)
            monkeypatch.setattr(tm.InputAudit,'record',interrupt_during_record)
            def stop_before_world(*args,**kwargs):
                # The actual audit was instantiated before this boundary.
                if partial_ledger:(out.parent/'recovery-commands.jsonl').write_text('{partial')
                if trigger=='marker':
                    (out/'SUPERVISOR_STOP.json').write_text('{}')
                    raise runner.KeyboardInterrupt('supervisor stopped this run')
                os.kill(os.getpid(),signal.SIGINT)
                pytest.fail('first SIGINT did not interrupt')
            monkeypatch.setattr(importlib.import_module('sim.masterpi_drive_friction_v7'),'build_world',stop_before_world)
            yield
    monkeypatch.setattr(adapter,'dependency_modules',scoped)
    monkeypatch.setattr(adapter.platform,'system',lambda:'Linux')
    monkeypatch.setattr(adapter,'source_sha',lambda:'a'*40)
    plan=read_json(RECORD/'act11-gate-plan.json')['episodes'][0]
    with pytest.raises((KeyboardInterrupt,OSError)):
        adapter.run(plan,out,dependency_root=archived_dependency,noise_path=RECORD/'act11-noise.json',mode=SEARCH_MODE)
    assert signal.getsignal(signal.SIGINT)==before_handler
    report=read_json(out/'result.json')
    assert seen and report['status']=='interrupted' and report['input_audit_available']
    assert report['input_audit']['held_world_reads']==report['input_audit']['invisible_measurements']==0
    assert report['input_audit']['blocked_hidden']==len(seen)>=2
    assert report['physical_success'] is None and report['data_admitted'] is False
    if partial_ledger:assert report['recovery_finalization_error']['type']=='JSONDecodeError'
    else:assert report['recovery']['audit']['command_ticks']==0
    assert not (out/'result.json.tmp').exists()
    assert report['source_sha']=='a'*40


def test_compressed_terminal_result_is_atomic(tmp_path):
    p=tmp_path/'result.json.zst';p.write_bytes(b'previous')
    adapter.atomic_result(p,{'status':'interrupted','input_audit':{'blocked_hidden':17}})
    assert read_json(p)['input_audit']['blocked_hidden']==17
    assert not p.with_suffix('.zst.tmp').exists()


def test_calibration_only_scales_yaw_and_is_default_off():
    turn={**hold(0.),'wheels':[-.35,.35,-.35,.35],'duration_s':[.1]*4}
    nominal=command_delta(turn,.1);scaled=command_delta(turn,.1,.7)
    assert scaled[:2]==nominal[:2] and scaled[2]==pytest.approx(.7*nominal[2])
    assert adapter.rotation_gain(None,'off','off')==1.
    with pytest.raises(ValueError):adapter.rotation_gain({},adapter.CALIBRATION_MODE,SEARCH_MODE)
    noise=read_json(RECORD/'act11-noise.json')
    with pytest.raises(ValueError):adapter.rotation_gain(noise,adapter.CALIBRATION_MODE,'off')
    assert fit_gain([{'nominal_rad':1.,'actual_rad':.7},{'nominal_rad':-2.,'actual_rad':-1.4}])==pytest.approx(.7)
    # predictions accepts only saved visible measurements/commands, no evaluator.
    rows={'commands':[{'t':0.,'phase_before':'approach','applied_command':turn},
                      {'t':.1,'phase_before':'approach','applied_command':hold(.1)}],
          'teacher':[{'visible_target':{'xyz':[1.,0.,.02],'yaw':0.}},{'visible_target':None}]}
    assert predictions(rows,.7)[-1]!=predictions(rows,1.)[-1]


def test_search_memory_is_direction_only_and_still_has_24s_deadline():
    s=CommandSearch(yaw_gain=.7);s.observe(0.,{'xyz':[.7,.3,.024],'yaw':0.},None)
    previous=hold(0.)
    for i in range(241):
        now=i*.1
        if i:s.observe(now,None,previous)
        previous,exhausted,diag=s.action(now,hold(now),gaze,slew)
        # No translation to a remembered invisible target, even after 5.2 s.
        assert command_delta(previous,.1)[:2]==(0.,0.)
        if exhausted:break
    assert now<=SEARCH_LIMIT_S and exhausted and diag['memory_age_s']==pytest.approx(now)
    assert now>5.2 and not any(previous['wheels'])


def test_paired_queue_same_fresh40_early_large_bearing_and_disabled_flags():
    q=build_queue('a'*40);assert len(q['jobs'])==2
    plan=read_json(RECORD/'act11-gate-plan.json')
    assert any(abs(start_bearing(e))>20 for e in plan['episodes'][:2])
    assert len(SEEDS)==len(set(SEEDS))==40 and not set(SEEDS)&set(range(8316800,8317040))
    def walk(value):
        if isinstance(value,dict):
            for k,v in value.items():
                if k in ('approved','enabled','ready','stage_ready','submitted','remote_execution_started',
                         'automatic_promotion','gate_promotion_authorized_if_all_conditions_pass'):assert v is False
                walk(v)
        elif isinstance(value,list):
            for v in value:walk(v)
    walk(q)
    assert [r['seed'] for r in q['jobs'][0]['runs']]==[r['seed'] for r in q['jobs'][1]['runs']]
    for job in q['jobs']:
        assert job['minimum_success']==38 and job['minimum_recovery_runs']==20
        assert job['first_two_seeds']==[e['seed'] for e in plan['episodes'][:2]]
        for r in job['runs']:
            assert r['approved'] is False and r['training_rgb'] is False and '--training-rgb' not in r['command']
            assert r['source_sha']==r['SOURCE_SHA_file']=='a'*40
            assert r['command'][r['command'].index('--rotation-calibration')+1]==job['rotation_calibration']


@pytest.mark.parametrize('corrupt',['none','candidate','mixed','gain'])
def test_gate_cannot_mix_paired_calibration_candidates(tmp_path,corrupt):
    receipt,proof,args=gate_fixture(tmp_path)
    qp=Path(proof['queue']['path']);q=read_json(qp)
    off={**q['jobs'][0],'candidate_id':'rotation-off','rotation_calibration':'off','yaw_gain':1.}
    on={**deepcopy(off),'candidate_id':'rotation-on','rotation_calibration':adapter.CALIBRATION_MODE,'yaw_gain':.7}
    q['jobs']=[off,on];qp.write_text(json.dumps(q));proof['queue']['sha256']=sha256(qp)
    proof['candidate_id']='rotation-on' if corrupt!='candidate' else 'absent'
    for i,item in enumerate(proof['runs']):
        r=read_json(item['path']);folder=tmp_path/f'paired-{i}';(folder/'raw').mkdir(parents=True)
        lp=folder/'recovery-commands.jsonl';rows=ledger()
        lp.write_text(''.join(json.dumps(row)+'\n' for row in rows))
        r['recovery'].update(mode=SEARCH_MODE,rotation_calibration=adapter.CALIBRATION_MODE,
            yaw_gain=1. if corrupt=='mixed' and i==3 else .7,ledger=str(lp),sha256=sha256(lp),
            audit=recovery_statistics(rows),perturbation_targets_excluded=True)
        path=folder/'raw/result.json';path.write_text(json.dumps(r));item.update(path=str(path),sha256=sha256(path))
    receipt.write_text(json.dumps(proof))
    kwargs={**args,'recovery_mode':SEARCH_MODE,'rotation_calibration':adapter.CALIBRATION_MODE,
            'yaw_gain':.8 if corrupt=='gain' else .7}
    if corrupt=='none':assert verify_gate(receipt,**kwargs)['recovery_runs']==38
    else:
        with pytest.raises(ValueError):verify_gate(receipt,**kwargs)
