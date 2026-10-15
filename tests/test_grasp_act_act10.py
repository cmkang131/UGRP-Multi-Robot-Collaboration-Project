"""Targeted command/FK/adapter checks; no simulator, renderer or training."""
import ast
from copy import deepcopy
import io
import json
import math
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

from harness.grasp_act_data import sha256
from harness.grasp_act_dart import recovery_hooks
from harness.grasp_act_perturb import RecoveryPerturb, recovery_statistics, LOSS_ATTRIBUTION_S
from harness.grasp_act_recovery_gate import verify_gate
from harness.grasp_act_search import (CommandSearch, SEARCH_MODE, SEARCH_LIMIT_S,
                                      command_delta, propagate)
from scripts.queue_grasp_act_act10 import build_queue, SEEDS
from scripts.queue_grasp_act_act9 import seed_inventory
from tests.test_grasp_act_act6 import cmd, gate_fixture
from tests.test_grasp_act_act9 import ledger, model

ROOT=Path(__file__).resolve().parents[1]
RECORD=ROOT/'experiments/2026-10-15-act-train'


def hold(t):return {**cmd(),'t':t,'wheels':[0.]*4,'duration_s':[0.]*4}
def gaze(point, pose, *, visible):
    assert not visible
    return {**pose,3:720 if point[0]>.5 else 500}
def slew(pose, target):
    return {k:int(pose[k]+max(-60,min(60,target[k]-pose[k]))) for k in target}


def test_integrates_actual_perturbation_in_body_frame_and_matches_pinned_model():
    source=subprocess.check_output(['git','show','6f057f7e:sim/grasp_act_teacher_v3.py'],cwd=ROOT,text=True)
    fn=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='propagate_owned')
    ns={'math':math};exec(compile(ast.Module(body=[fn],type_ignores=[]),'pinned-propagate','exec'),ns)
    search=CommandSearch(); point=[.7,.2,.024]
    search.observe(0.,{'xyz':point,'yaw':0.},None)
    yaw={**hold(0.),'wheels':[-.35,.35,-.35,.35],'duration_s':[.1]*4}
    for i in range(1,10):
        expected=ns['propagate_owned'](point,yaw,.1);point=expected
        search.observe(i*.1,None,yaw)
        assert search.point==pytest.approx(expected)
    assert math.atan2(search.point[1],search.point[0])<0
    assert command_delta(yaw,.1)[2]>0


def test_orient_range_matched_tilt_full_pan_and_360_search_then_fail():
    search=CommandSearch();search.observe(0.,{'xyz':[.3,-.7,.024],'yaw':0.},None)
    previous=None;pose=hold(0.)['pwm'];stages=set();pans=[]
    for i in range(260):
        now=i*.1
        if i:search.observe(now,None,previous)
        value,exhausted,diag=search.action(now,{**hold(now),'pwm':pose},gaze,slew)
        pose=value['pwm'];stages.add(diag['stage']);pans.append(pose['6'])
        if i==0:
            assert value['wheels']==[.35,-.35,.35,-.35]
            assert pose['3']==1440  # slew toward the far-range 720 pose
        if exhausted:
            assert not any(value['wheels'])
            break
        previous=value
    assert exhausted and now<=SEARCH_LIMIT_S
    assert stages=={'orient','pan_scan','body_scan'}
    assert min(pans)<=520 and max(pans)>=2480
    assert math.degrees(search.scan_yaw)==pytest.approx(360.)


def test_time_cap_without_effective_issued_turn_and_missing_memory_fail_closed():
    s=CommandSearch();s.observe(0.,None,None)
    assert s.action(0.,hold(0.),gaze,slew)[1]
    s.observe(.1,{'xyz':[-1.,0.,.02],'yaw':0.},None)
    s.action(.1,hold(.1),gaze,slew)
    # A relay that applies stop instead of the requested turn cannot extend time.
    for i in range(2,243):
        now=i*.1;s.observe(now,None,hold(now-.1))
        value,exhausted,_=s.action(now,hold(now),gaze,slew)
        if exhausted:break
    assert exhausted and now-.1==pytest.approx(SEARCH_LIMIT_S)
    assert not any(value['wheels'])


def test_reacquisition_resets_search_and_held_or_nonlocal_input_erases_memory():
    s=CommandSearch();m={'xyz':[.8,.3,.02],'yaw':0.}
    s.observe(0.,m,None);s.action(0.,hold(0.),gaze,slew)
    s.observe(.1,m,hold(0.));assert s.started is None and s.point==m['xyz']
    for kwargs in ({'holding':True},{'eligible':False}):
        s.observe(s.previous_t+.1,m,None,**kwargs)
        assert s.point is None and s.seen_t is None and s.stage is None


def test_hook_uses_corrective_clean_labels_resumes_parent_and_fails_without_timeout():
    class Teacher:
        def __init__(self):
            self.phase='approach';self.holding=False;self.previous=None;self.result=None
            self.sink=SimpleNamespace(pwm={int(k):v for k,v in hold(0.)['pwm'].items()})
            self.arm=SimpleNamespace(commanded={});self.ops=SimpleNamespace(gaze=gaze,slew=slew)
            self.target=self.seen_t=self.stable_t=None;self.resumed=0
        def _hold(self,now):return {**hold(now),'pwm':{str(k):v for k,v in self.sink.pwm.items()}}
        def _set(self,phase,now):self.phase=phase
        def _seek(self,measurement,now):self.resumed+=1;return self._hold(now)
        def _relook(self,measurement,now):return self._seek(measurement,now)
        def step(self,now,**kwargs):return self._seek(kwargs['measurement'],now),False
        def _reset_alignment(self):pass
        def remember_applied(self,value):self.previous=deepcopy(value)
    tm=SimpleNamespace(SoloTeacher=Teacher);rm=SimpleNamespace(SoloRecorder=object)
    noise=RecoveryPerturb({**model(),'mode':SEARCH_MODE},seed=1,mode=SEARCH_MODE)
    noise.injections=1 # focus on post-probe recovery
    stream=io.StringIO()
    with recovery_hooks(tm,rm,noise,stream):
        t=tm.SoloTeacher();m={'xyz':[.7,-.5,.02],'yaw':0.}
        t.step(0.,measurement=m);value,_=t.step(.1,measurement=None)
        assert any(value['wheels']) and t.resumed==1
        t.step(.2,measurement=m);assert t.resumed==2 and t.recovery_search.started is None
        for i in range(3,250):
            value,_=t.step(i*.1,measurement=None)
            if t.result:break
        assert t.result=='recovery_search_exhausted' and t.phase=='failed' and not any(value['wheels'])
    rows=[json.loads(s) for s in stream.getvalue().splitlines()]
    assert rows[1]['clean_teacher_command']==rows[1]['applied_command']
    assert rows[1]['active_search']['stage']=='orient'


def test_attribution_window_rejects_late_unrelated_loss_but_keeps_late_reacquisition():
    rows=ledger(lost=False)
    last_probe=max(r['t'] for r in rows if r['perturbation_interval'])
    rows.extend([{**rows[-1],'t':last_probe+LOSS_ATTRIBUTION_S+.1,'target_visible':False},
                 {**rows[-1],'t':last_probe+LOSS_ATTRIBUTION_S+.2}])
    audit=recovery_statistics(rows)
    assert audit['lost_N']==audit['recovery_scene_N']==0
    rows=ledger(recovered=False)
    rows.append({**rows[-1],'t':20.,'target_visible':True})
    assert recovery_statistics(rows)['recovery_scene_N']==1
    for row in rows:
        if row['disturbance']:row['disturbance']['mode']=SEARCH_MODE
    assert recovery_statistics(rows)['recovery_scene_N']==1


@pytest.mark.parametrize('corruption',['none','queue_hash','different_seeds','unbound','no_recovery'])
def test_search_gate_requires_queue_seeds_and_successful_recovery_scenes(tmp_path,corruption):
    receipt,proof,args=gate_fixture(tmp_path)
    for i,item in enumerate(proof['runs']):
        old=Path(item['path']);r=json.loads(old.read_text());old.unlink()
        folder=tmp_path/f'run-{i}';(folder/'raw').mkdir(parents=True)
        path=folder/'raw/result.json';lp=folder/'recovery-commands.jsonl'
        rows=ledger(recovered=i<22 and corruption!='no_recovery')
        for row in rows:
            if row['disturbance']:row['disturbance']['mode']=SEARCH_MODE
        lp.write_text(''.join(json.dumps(r)+'\n' for r in rows))
        r['recovery'].update(mode=SEARCH_MODE,ledger=str(lp),sha256=sha256(lp),
            audit=recovery_statistics(rows),perturbation_targets_excluded=True)
        path.write_text(json.dumps(r));item.update(path=str(path),sha256=sha256(path))
    if corruption=='queue_hash':proof['queue']['sha256']='0'*64
    if corruption=='unbound':proof.pop('queue')
    if corruption=='different_seeds':
        qp=Path(proof['queue']['path']);q=json.loads(qp.read_text())
        q['jobs'][0]['runs'][0]['seed']=900;qp.write_text(json.dumps(q));proof['queue']['sha256']=sha256(qp)
    receipt.write_text(json.dumps(proof))
    if corruption=='none':
        result=verify_gate(receipt,**args,recovery_mode=SEARCH_MODE)
        assert result['n']==38 and result['recovery_runs']==20
    else:
        with pytest.raises(ValueError):verify_gate(receipt,**args,recovery_mode=SEARCH_MODE)


def test_new_queue_all_disabled_fresh40_no_recording_and_correct_source(tmp_path):
    q=build_queue('a'*40)
    def walk(value):
        if isinstance(value,dict):
            for k,v in value.items():
                if k in ('approved','enabled','ready','stage_ready','submitted','remote_execution_started',
                         'automatic_promotion','gate_promotion_authorized_if_all_conditions_pass'):assert v is False
                walk(v)
        elif isinstance(value,list):
            for v in value:walk(v)
    walk(q);gate=q['jobs'][0]
    assert gate['minimum_success']==38 and gate['minimum_recovery_runs']==20
    assert len(SEEDS)==len(set(SEEDS))==40
    assert not set(SEEDS)&set(range(8316800,8316940))
    assert gate['max_parallel']==40
    plan=json.loads((RECORD/'act10-gate-plan.json').read_text())
    assert [r['seed'] for r in plan['episodes']]==SEEDS
    for run,seed in zip(gate['runs'],SEEDS):
        assert run['seed']==seed and run['source_sha']==run['SOURCE_SHA_file']=='a'*40
        command=run['command'];assert command[command.index('--recovery-mode')+1]==SEARCH_MODE
        assert not run['training_rgb'] and '--training-rgb' not in command
        assert command[command.index('--out')+1].endswith(run['name']+'/raw')
    (tmp_path/'prior-act9.json').write_text(json.dumps({'seed':SEEDS[0]}))
    with pytest.raises(ValueError,match='already'):
        seed_inventory(tmp_path,proposed_seeds=SEEDS,exclude_tag='act10')


def test_mac_active_search_stops_before_loading_a_dependency(monkeypatch,tmp_path):
    from scripts.run_grasp_act_recovery import run
    monkeypatch.setattr('scripts.run_grasp_act_recovery.platform.system',lambda:'Darwin')
    with pytest.raises(RuntimeError,match='GCP Linux only'):
        run({},tmp_path/'raw',dependency_root=tmp_path,noise_path=tmp_path/'missing',mode=SEARCH_MODE)
