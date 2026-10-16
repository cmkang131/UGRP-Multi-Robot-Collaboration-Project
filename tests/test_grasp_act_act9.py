"""ACT9 command, recorder and gate tests only; no world construction."""
import ast
from collections import deque
from copy import deepcopy
import io
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

from harness import grasp_act_contract as c
from harness.grasp_act_data import paired_segments, sha256
from harness.grasp_act_dart import MODE, PULSE_MODE, recovery_hooks
from harness.grasp_act_perturb import (PERTURB_MODE, RecoveryPerturb, annotate_label,
                                     recovery_statistics, validate_recorded_labels)
from harness.grasp_act_recovery_gate import verify_gate
from scripts.queue_grasp_act_act9 import build_queue, SEEDS, seed_inventory
from tests.test_grasp_act_act6 import cmd, gate_fixture
from tests.test_grasp_act_act4 import observation

ROOT = Path(__file__).resolve().parents[1]
RECORD = ROOT/'experiments/2026-10-15-act-train'


def model(): return json.loads((RECORD/'act9-noise.json').read_text())


def probe(**overrides): return RecoveryPerturb({**model(), **overrides}, seed=71)


def apply(noise, t, *, phase='approach', holding=False, visible=True):
    return noise.apply({**cmd(), 't': t}, phase_before=phase, phase_after=phase,
                       holding=holding, visible=visible)


def test_seeded_single_probe_robot_only_fixed_size_and_phase_boundaries():
    a, b = probe(), probe()
    rows = []
    for tick in range(300):
        clean = {**cmd(), 't': tick*.1}
        actual, diagnostic = apply(a, tick*.1)
        assert (actual, diagnostic) == apply(b, tick*.1)
        assert actual['pwm'] == clean['pwm']
        c.command(actual)
        if diagnostic:
            assert diagnostic['training_target'] is False
            assert actual['duration_s'] == [.1]*4
            assert actual['wheels'] in ([-.35,.35,-.35,.35], [.35,-.35,.35,-.35])
        else: assert actual == clean
        rows.append(diagnostic)
    assert [r['tick'] for r in rows if r] == list(range(1,10))
    for phase, holding, visible in [('approach',True,True), ('hover',False,True),
                                  ('approach',False,False)]:
        noise = probe(probability_per_eligible_tick=1, minimum_eligible_ticks=1)
        assert apply(noise, 0., phase=phase, holding=holding, visible=visible) == (cmd(), None)
    stop = {**cmd(), 'wheels':[0.]*4, 'duration_s':[0.]*4}
    assert probe().apply(stop,phase_before='align',phase_after='align',holding=False,visible=True) == (stop,None)


@pytest.mark.parametrize('change', [{'probability_per_eligible_tick':float('nan')},
    {'burst_ticks':13}, {'held_noise':True}, {'pulse_s':.15}])
def test_invalid_probe_cannot_change_the_robot_only_contract(change):
    with pytest.raises(ValueError): probe(**change)


def ledger(recovered=True, lost=True):
    rows = []
    for i in range(7):
        injection = i in (1,2)
        rows.append({'t':i*.1, 'phase_after':'approach',
            'target_visible': not lost or i<2 or (recovered and i>=4),
            'perturbation_interval':injection,
            'disturbance': {'mode':PERTURB_MODE,'tick':i,'episode_id':1} if injection else None})
    return rows


def test_actual_visibility_loss_required_and_unresolved_failures_count_once():
    audit = recovery_statistics(ledger())
    assert (audit['lost_N'],audit['recovery_scene_N'],audit['recovery_failure_N']) == (1,1,0)
    assert audit['perturbation_fraction'] == pytest.approx(2/7)
    assert audit['episodes'][0]['lost_t'] == pytest.approx(.2)
    assert audit['episodes'][0]['reacquired_t'] == pytest.approx(.4)
    assert recovery_statistics(ledger(recovered=False))['recovery_failure_N'] == 1
    no_loss = recovery_statistics(ledger(lost=False))
    assert no_loss['recovery_scene_N'] == 0 and no_loss['perturbation_no_loss_N'] == 1
    rows = ledger(); rows[3].update(phase_after='hover',target_visible=False)
    assert recovery_statistics(rows)['recovery_failure_N'] == 1


def test_hook_uses_real_pinned_recorder_target_and_preserves_actual_history():
    # Extract only pure recorder methods: never import a sim runner or create a
    # world. This verifies the exact dependency's serialized teacher labels.
    source = subprocess.check_output(['git','show','6f057f7e:harness/grasp_act_solo_recording.py'],cwd=ROOT,text=True)
    tree = ast.parse(source)
    segment = next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='segment')
    cls = next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='SoloRecorder')
    target = next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='target')
    namespace = {'command':c.command,'deepcopy':deepcopy,'json':json}
    exec(compile(ast.Module(body=[segment,target],type_ignores=[]),'pinned-recorder','exec'),namespace)
    class Recorder:
        target = namespace['target']
        def __init__(self):
            self.history=deque();self.label_file=io.StringIO();self.local_started=True
            self.pending=None;self.rows=0
    class Teacher:
        def __init__(self):
            self.phase='approach';self.holding=False;self.measurements=[]
            self.sink=SimpleNamespace(pwm={s:1500 for s in c.SERVOS})
            self.arm=SimpleNamespace(commanded={});self.target=None
        def step(self,now,**kwargs):
            self.measurements.append(kwargs['measurement'])
            return {**cmd(),'t':now},False
        def remember_applied(self,value):self.previous=deepcopy(value)
        def _reset_alignment(self):pass
    tm, rm = SimpleNamespace(SoloTeacher=Teacher), SimpleNamespace(SoloRecorder=Recorder)
    stream = io.StringIO(); obs, _ = observation()
    observations = []; labels = []; actuals = []
    with recovery_hooks(tm,rm,probe(probability_per_eligible_tick=1,minimum_eligible_ticks=3,burst_ticks=2),stream):
        teacher, recorder = tm.SoloTeacher(), rm.SoloRecorder()
        for i in range(7):
            now=i*.1; o=deepcopy(obs);o.update(t=now,sample_id=f'probe:{i}:r1')
            for ref in o['rgb']:ref['t']=now
            recorder.pending=(o,'approach',.5)
            actual,_=teacher.step(now,measurement={'xyz':[.5,0,0],'yaw':0.})
            recorder.target(actual,skill_after='grasp',phase_after='approach',complete=False)
            observations.append(o);actuals.append(actual)
            assert teacher.previous == recorder.history[-1] == actual
        labels=[json.loads(line) for line in recorder.label_file.getvalue().splitlines()]
        assert teacher.measurements[2] is not None and teacher.measurements[3] is None
    assert tm.SoloTeacher is Teacher and rm.SoloRecorder is Recorder
    assert [l['local_skill_sample'] for l in labels] == [True,True,False,False,True,True,True]
    assert [l['perturbation_interval'] for l in labels] == [False,False,True,True,False,False,False]
    audit = recovery_statistics([json.loads(line) for line in stream.getvalue().splitlines()])
    # Suppressing the teacher's location input during the burst must never
    # fabricate an own-camera loss or count a recovery scene.
    assert audit['lost_N'] == audit['recovery_scene_N'] == 0
    validate_recorded_labels(labels,audit)
    with pytest.raises(ValueError,match='mask'):
        validate_recorded_labels([{k:v for k,v in label.items() if k!='perturbation_interval'} for label in labels],audit)
    assert all(l['clean_teacher_command'] != a for l,a in zip(labels[2:4],actuals[2:4]))
    groups=paired_segments(observations,labels)
    assert list(map(len,groups)) == [2,3]
    labels[2]['local_skill_sample']=True
    with pytest.raises(ValueError,match='perturbation'):paired_segments(observations,labels)


@pytest.mark.parametrize('mode',[MODE,PULSE_MODE,PERTURB_MODE])
def test_legacy_act8_and_new_gate_modes_are_accepted_without_weakening_old_checks(tmp_path,mode):
    receipt,proof,args=gate_fixture(tmp_path)
    for i,item in enumerate(proof['runs']):
        path=Path(item['path']); r=json.loads(path.read_text());r['recovery']['mode']=mode
        if mode==PERTURB_MODE:
            # Mirror the runner's raw/result and sibling ledger structure.
            folder=tmp_path/f'run-{i}';(folder/'raw').mkdir(parents=True)
            path=folder/'raw/result.json';ledger_path=folder/'recovery-commands.jsonl'
            rows=ledger(recovered=i<22)
            ledger_path.write_text(''.join(json.dumps(row)+'\n' for row in rows))
            r['recovery'].update(ledger=str(ledger_path),sha256=sha256(ledger_path),
                audit=recovery_statistics(rows),perturbation_targets_excluded=True)
            item['path']=str(path)
        path.write_text(json.dumps(r));item['sha256']=sha256(path)
    receipt.write_text(json.dumps(proof))
    result=verify_gate(receipt,**args,recovery_mode=mode)
    assert result['n']==38
    if mode==PERTURB_MODE:
        assert result['recovery_runs']==20
        item=proof['runs'][2];path=Path(item['path']);r=json.loads(path.read_text())
        rows=ledger(recovered=False);lp=Path(r['recovery']['ledger'])
        lp.write_text(''.join(json.dumps(row)+'\n' for row in rows))
        r['recovery'].update(sha256=sha256(lp),audit=recovery_statistics(rows))
        path.write_text(json.dumps(r));item['sha256']=sha256(path);receipt.write_text(json.dumps(proof))
        with pytest.raises(ValueError,match='20/40'):verify_gate(receipt,**args)
    else:
        with pytest.raises(ValueError,match='mixed'):verify_gate(receipt,**args,recovery_mode=PERTURB_MODE)


def test_queue_fresh40_disabled_and_prior_inventory_hashes(tmp_path):
    q=build_queue('b'*40)
    def walk(value):
        if isinstance(value,dict):
            for k,v in value.items():
                if k in ('approved','enabled','ready','stage_ready','submitted','remote_execution_started',
                         'gate_promotion_authorized_if_all_conditions_pass','automatic_promotion'):assert v is False
                walk(v)
        elif isinstance(value,list):
            for v in value:walk(v)
    walk(q)
    gate=q['jobs'][0];assert gate['minimum_recovery_runs']==20 and gate['minimum_success']==38
    assert [r['seed'] for r in gate['runs']]==SEEDS and len(SEEDS)==40
    plan=json.loads((RECORD/'act9-gate-plan.json').read_text())
    assert [e['seed'] for e in plan['episodes']]==SEEDS
    assert plan['kinds']==dict.fromkeys(('cyan','red','green','yellow'),10)
    for run in gate['runs']:
        command=run['command'];assert command[command.index('--recovery-mode')+1]==PERTURB_MODE
        assert '--training-rgb' not in command and not run['training_rgb']
        assert command[command.index('--out')+1].endswith(run['name']+'/raw')
    (tmp_path/'old-queue.json').write_text(json.dumps({'seed':SEEDS[0]}))
    with pytest.raises(ValueError,match='already'):seed_inventory(tmp_path)


def test_mac_recovery_probe_is_blocked_before_reading_any_dependency(monkeypatch,tmp_path):
    from scripts.run_grasp_act_recovery import run
    monkeypatch.setattr('scripts.run_grasp_act_recovery.platform.system',lambda:'Darwin')
    with pytest.raises(RuntimeError,match='GCP Linux only'):
        run({},tmp_path/'absent',dependency_root=tmp_path,noise_path=tmp_path/'missing',mode=PERTURB_MODE)
