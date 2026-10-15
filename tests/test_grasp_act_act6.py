"""ACT6 boundary and sparse-horizon checks; no simulation or model execution."""
from collections import deque
from copy import deepcopy
import io
import json
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest

from harness import grasp_act_contract as c
from harness.grasp_act_data import sha256
from harness.grasp_act_dart import MODE, WheelNoise, fit_diagonal, recovery_hooks
from harness.grasp_act_policy import ChunkExecutor
from harness.grasp_act_recovery_gate import verify_gate
from scripts.queue_grasp_act_act6 import build_queue
from tests.test_grasp_act_act4 import observation


def cmd():return {'t':0.,'wheels':[.35]*4,'duration_s':[.05]*4,'pwm':{str(s):1500 for s in c.SERVOS}}


def noise_model():
    return fit_diagonal([{'sample_id':str(i),'metadata':{'skill':'grasp'},'first_action':{
        'valid_actions':1,'mae_per_action_dimension':[.3]*8+[0.]*6}} for i in range(3)])


def test_diagonal_mle_retains_bias_energy_and_does_not_invent_cross_covariance():
    m=noise_model()
    assert np.allclose(m['covariance'],np.eye(8)*.09)
    assert m['dart_scale_alpha_per_tick']==pytest.approx(.72)
    rows=[{'sample_id':'a','metadata':{'skill':'grasp'},'first_action':{
        'valid_actions':1,'mae_per_action_dimension':[.3]*14}}]*2
    with pytest.raises(ValueError,match='duplicate'):fit_diagonal(rows)
    with pytest.raises(ValueError):WheelNoise({**m,'covariance':(-np.eye(8)).tolist()},mode=MODE)


def test_noise_default_and_held_terminal_are_unchanged_and_seeded():
    clean=cmd();off=WheelNoise()
    assert off.apply(clean,phase_before='approach',phase_after='approach',holding=False)==(clean,None)
    a=WheelNoise(noise_model(),mode=MODE,seed=17);b=WheelNoise(noise_model(),mode=MODE,seed=17)
    for phase,held in [('close',False),('align',True),('hold',True)]:
        assert a.apply(clean,phase_before=phase,phase_after=phase,holding=held)==(clean,None)
    actual,diag=a.apply(clean,phase_before='align',phase_after='align',holding=False)
    assert (actual,diag)==b.apply(clean,phase_before='align',phase_after='align',holding=False)
    assert actual['pwm']==clean['pwm'] and actual!=clean and c.command(actual)==actual
    assert clean==cmd()


def test_clean_current_state_label_and_applied_history_cannot_be_swapped():
    class Teacher:
        def __init__(self):self.phase='align';self.holding=False;self.previous=None
        def step(self,now,**kwargs):
            # Label changes with observation; not a pre-recorded clean trajectory.
            self.clean=cmd();self.clean['t']=now;self.clean['duration_s']=[kwargs['measurement']]*4
            return deepcopy(self.clean),False
        def remember_applied(self,v):self.previous=deepcopy(v)
    class Recorder:
        def __init__(self):self.history=deque();self.labels=[]
        def target(self,v,**kwargs):self.labels.append(deepcopy(v));self.history.append(deepcopy(v))
    tm,rm=SimpleNamespace(SoloTeacher=Teacher),SimpleNamespace(SoloRecorder=Recorder)
    stream=io.StringIO()
    with recovery_hooks(tm,rm,WheelNoise(noise_model(),seed=9,mode=MODE),stream):
        t=tm.SoloTeacher();r=rm.SoloRecorder()
        for now,m in [(0.,.03),(.1,.08)]:
            applied,done=t.step(now,measurement=m);r.target(applied)
            assert r.labels[-1]==t.clean and r.history[-1]==applied==t.previous
            assert r.labels[-1]!=applied
    assert tm.SoloTeacher is Teacher and rm.SoloRecorder is Recorder
    assert len(stream.getvalue().splitlines())==2


@pytest.mark.parametrize('stride',[1,2,3,4])
def test_strided_te_horizon_alignment_and_refresh_count(stride):
    rng=np.random.default_rng(7);chunks=rng.uniform(.2,.4,(16,8,14));chunks[:,:,4:8]=.5;chunks[:,:,-1]=0.
    calls=[]
    def predict(*args):calls.append(len(calls));return chunks[len(calls)-1]
    ex=ChunkExecutor(predict,n_action_steps=stride,temporal_ensemble_coeff=.01)
    obs,jpgs=observation();issued=[]
    for tick in range(16):
        obs['t']=tick*.1
        for ref in obs['rgb']:ref['t']=obs['t']
        actual,_=ex.step(obs,jpgs)
        starts=list(range(0,tick+1,stride));starts=[s for s in starts if tick-s<8]
        values=[chunks[s//stride,tick-s] for s in starts]
        avg=np.average(values,axis=0,weights=np.exp(-.01*np.arange(len(starts))))
        expected=c.decode_action(avg)
        assert actual['wheels']==pytest.approx(expected['wheels'])
        assert actual['duration_s']==pytest.approx(expected['duration_s'])
    assert len(calls)==(15//stride+1)


def gate_fixture(tmp_path):
    host={'instance':'gcp1'};expected={'source_sha':'a'*40,'teacher_dependency_sha':'b'*40,'noise_sha256':'c'*64}
    proof={'approved':True,'gate_promotion_authorized_if_all_conditions_pass':False,**expected,
           'seed_inventory_sha256':'d'*64,'fresh_seeds':list(range(40)),'runs':[]}
    queue=tmp_path/'queue.json'
    queue.write_text(json.dumps({'source_sha':expected['source_sha'],
        'jobs':[{'N':40,'training_rgb':False,'runs':[{'seed':i} for i in range(40)]}]}))
    proof['queue']={'path':str(queue),'sha256':sha256(queue)}
    for seed in range(40):
        r={'status':'complete','training_rgb':False,'recording_mode':'success_measurement','weld':'off',
           'student_execution':False,'execution_host':host,'gate_eligible':True,**expected,
           'recovery':{'seed':seed,'mode':MODE},'input_audit':{'held_world_reads':0,'invisible_measurements':0},
           'teacher':{'held_object_hidden_v1':True},'solo_truth_free_lookaround_v1':True,'physical_success':seed>=2}
        p=tmp_path/f'{seed}.json';p.write_text(json.dumps(r));proof['runs'].append({'path':str(p),'sha256':sha256(p)})
    receipt=tmp_path/'gate.json';receipt.write_text(json.dumps(proof))
    args=dict(source='a'*40,dependency='b'*40,noise_hash='c'*64,host=host,recording_seeds=[100])
    return receipt,proof,args


@pytest.mark.parametrize('failure',['none','rgb','source','audit','duplicate','missing','overlap','unapproved','37'])
def test_recording_gate_reads_hashed_results_and_rejects_invalid_evidence(tmp_path,failure):
    p,proof,kwargs=gate_fixture(tmp_path)
    if failure=='duplicate':proof['runs'][-1]=proof['runs'][0]
    elif failure=='missing':proof['runs'].pop()
    elif failure=='unapproved':proof['approved']=False
    elif failure=='overlap':kwargs['recording_seeds']=[0]
    elif failure in ('rgb','source','audit','37'):
        item=proof['runs'][2];path=Path(item['path']);row=json.loads(path.read_text())
        if failure=='rgb':row['training_rgb']=True
        if failure=='source':row['source_sha']='z'*40
        if failure=='audit':row['input_audit']['held_world_reads']=1
        if failure=='37':row['physical_success']=False
        path.write_text(json.dumps(row));item['sha256']=sha256(path)
    p.write_text(json.dumps(proof))
    if failure=='none':assert verify_gate(p,**kwargs)['n']==38
    else:
        with pytest.raises(ValueError):verify_gate(p,**kwargs)


def test_queue_is_entirely_disabled_and_closed_loop_is_one_pending_run():
    q=build_queue('a'*40)
    def walk(x):
        if isinstance(x,dict):
            for k,v in x.items():
                if k in ('approved','enabled','ready','stage_ready','submitted'):assert v is False
                walk(v)
        elif isinstance(x,list):
            for v in x:walk(v)
    walk(q)
    assert len(q['jobs'][0]['runs'])==40 and not q['jobs'][0]['training_rgb']
    assert len(q['jobs'][1]['runs'])==50 and q['jobs'][1]['training_rgb']
    closed=q['jobs'][-1];assert closed['max_runs']==1 and closed['cap_sim_s']==90 and closed['command'] is None
    assert q['materialize_protocol']['value']['teacher_sha']=='a'*40
    assert len(q['materialize_protocol']['value']['validation_seeds'])==5


def test_mac_recovery_rejected_before_dependency_or_metadata(monkeypatch,tmp_path):
    from scripts.run_grasp_act_recovery import run
    monkeypatch.setattr('scripts.run_grasp_act_recovery.platform.system',lambda:'Darwin')
    with pytest.raises(RuntimeError,match='GCP Linux only'):
        run({},tmp_path/'out',dependency_root=tmp_path,noise_path=tmp_path/'missing')
    assert not (tmp_path/'out').exists()


def test_static_student_plan_matches_allowed_scope():
    from scripts.run_grasp_act_student import validate_plan
    root=Path(__file__).resolve().parents[1]/'experiments/2026-10-15-act-train'
    plan=json.loads((root/'act6-student-plan.json').read_text())
    validate_plan(plan,build_queue('a'*40)['materialize_protocol']['value'])


def test_composition_excludes_calibration_and_refits_train_only(tmp_path):
    from tests.test_grasp_act_data import episode
    from harness.grasp_act_data import convert, GraspDataset
    from scripts.merge_grasp_act_recovery_data import merge
    raw=tmp_path/'runs'
    for seed,pwm in [(1,1300),(2,2300),(3,1700),(4,500)]:
        episode(raw,seed,pwm=pwm)
        p=raw/f'run-{seed}/raw/result.json';r=json.loads(p.read_text())
        r['execution_host']={'instance':'ugrp-sim-gcp1','machine_type':'n4-highcpu-64'}
        p.write_text(json.dumps(r))
    def protocol(train,validation):return {'teacher_sha':'a'*40,'run_pattern':'run-{seed}',
        'train_seeds':[train],'validation_seeds':[validation],'done_label':'last_local_row_v1'}
    convert(raw,protocol(1,2),tmp_path/'old');convert(raw,protocol(3,4),tmp_path/'new')
    m=merge(tmp_path/'old',tmp_path/'new',tmp_path/'merged')
    assert m['protocol']['train_seeds']==[1,3] and m['protocol']['validation_seeds']==[4]
    assert m['excluded_calibration_seeds']==[2]
    data=GraspDataset(tmp_path/'merged','train')
    assert data.stats['action_mean'][8:13]==pytest.approx([0.]*5,abs=1e-7)
    assert len(GraspDataset(tmp_path/'merged','validation'))==4
    p=raw/'run-3/raw/result.json';r=json.loads(p.read_text());r['execution_host']['machine_type']='other'
    p.write_text(json.dumps(r))
    with pytest.raises(ValueError,match='mixed simulation'):
        merge(tmp_path/'old',tmp_path/'new',tmp_path/'mixed-host')
    item=m['episodes'][0];path=tmp_path/'merged'/item['path']/'samples.json'
    path.write_text('[]')
    with pytest.raises(ValueError,match='hash'):GraspDataset(tmp_path/'merged','train')


def test_recovery_conversion_requires_actual_qualified_recording(tmp_path):
    from tests.test_grasp_act_data import episode
    from harness.grasp_act_data import convert
    raw=tmp_path/'runs';episode(raw,1)
    protocol={'teacher_sha':'a'*40,'run_pattern':'run-{seed}','train_seeds':[1],
        'validation_seeds':[],'done_label':'last_local_row_v1','recovery_mode':MODE,'noise_sha256':'n'*64}
    with pytest.raises(ValueError,match='unqualified recovery'):
        convert(raw,protocol,tmp_path/'rejected')
    p=raw/'run-1/raw/result.json';r=json.loads(p.read_text());r.update(recovery={'mode':MODE},
        noise_sha256='n'*64,training_candidate=True,recovery_gate={'sha256':'g'*64},
        input_audit={'held_world_reads':0,'invisible_measurements':0});p.write_text(json.dumps(r))
    assert convert(raw,protocol,tmp_path/'accepted')['complete']
