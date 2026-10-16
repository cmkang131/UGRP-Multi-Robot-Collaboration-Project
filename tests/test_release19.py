"""Scheduler/clock-only regressions; no MuJoCo physics, renderer or network."""
import ast
import copy
import inspect
import json
import subprocess
from types import SimpleNamespace

import pytest

from sim import release18, release19
from sim.lookaround_localization import ScriptRunner
from scripts import run_grasp_act_release as runner
from scripts.prepare_release_gate40_queue import build, verify
from tests.test_grasp_act_release_run import fake_backend as _fake_backend

fake_backend = _fake_backend


def drive(cls, *, holding=False, busy=False, stale=False, changed=False, wheel_step=False):
    teacher=SimpleNamespace(pwm={1:2000,3:100,4:200,5:300,6:1500},holding=holding)
    history=release18.CommandHistory();history.observe(teacher.pwm,-2.)
    left={**teacher.pwm,6:800};right={**left,6:2200}
    steps=[dict(servo=left,wait=1.,capture=False,label='arm'),
           dict(servo=left,wait=.8,capture=True,label='view_first'),
           dict(servo=right,wait=.8,capture=True,label='view_second')]
    if wheel_step:steps.insert(1,dict(wheels=[([.35]*4,[.1]*4)],wait=.3,capture=False,label='base'))
    args=dict(teacher=teacher,command_history=history,idle=lambda:not busy) if cls==release19.ScriptRunner else {}
    a=cls(steps,0.,**args);captures=[];commands=[]
    def set_servo(pose,now):
        teacher.pwm.update(pose);commands.append((now,copy.deepcopy(pose)))
        if not stale:history.observe(teacher.pwm,now)
    for k in range(100):
        now=k*.1
        if changed and k==10:teacher.pwm[3]+=1
        if not stale:history.observe(teacher.pwm,now)
        a.tick(now,set_servo=set_servo,set_wheels=lambda *v:None,wheels_idle=lambda:True,
               capture=lambda t:captures.append(t))
        if a.done:return a,captures,commands
    raise AssertionError('finite scheduler did not finish')


def test_reuses_only_identical_completed_wait_keeps_fresh_view_order():
    old,old_images,old_commands=drive(ScriptRunner)
    new,new_images,new_commands=drive(release19.ScriptRunner)
    assert round(old.end-new.end,6)==.8
    assert [p for _,p in old_commands]==[p for _,p in new_commands]
    assert len(old_images)==len(new_images)==2
    assert new_images[1]-new_images[0]>=.8-1e-9  # new pan keeps its full original wait
    assert len(new.reused_waits)==1 and new.reused_waits[0]['command_age_s']>=1.


@pytest.mark.parametrize('opts',[dict(holding=True),dict(busy=True),dict(stale=True),dict(changed=True)])
def test_unknown_busy_holding_or_changed_history_retains_exact_old_timing(opts):
    old,images,commands=drive(ScriptRunner,**opts)
    new,actual,issued=drive(release19.ScriptRunner,**opts)
    assert actual==images and issued==commands and new.end==old.end
    assert not new.reused_waits


def test_wheel_step_dwell_and_command_order_unchanged():
    old,images,commands=drive(ScriptRunner,wheel_step=True)
    new,actual,issued=drive(release19.ScriptRunner,wheel_step=True)
    assert [e['label'] for e in old.log]==[e['label'] for e in new.log]
    assert old.end==new.end and images==actual and commands==issued
    assert not new.reused_waits  # wheel/body settling cannot borrow servo age
    assert next(e['t'] for e in new.log if e['label']=='view_first')>=1.3


def test_top_reads_are_counted_and_refused_before_access():
    calls=[];world=SimpleNamespace(render_team_jpeg=lambda **kw:calls.append(kw) or b'eval')
    audit=release19.TopCameraAudit();audit.install(world)
    with pytest.raises(RuntimeError,match='CONTROL_TOP_CAMERA_FORBIDDEN'):world.render_team_jpeg(camera='top')
    assert not calls and audit.record()['control_top_camera_reads']==1
    assert audit.evaluation_jpeg(world,camera='top')==b'eval'
    assert audit.record()['evaluation_top_camera_reads']==1
    with pytest.raises(RuntimeError):world.render_team_jpeg()
    assert audit.record()['control_top_camera_reads']==2


def test_default_profile_and_validation_keep_all_release18_guards():
    assert inspect.signature(runner.run).parameters['release_profile'].default=='off'
    plan=json.loads((runner.ROOT/'experiments/2026-10-14-e2e18-grasp-rootcause/release18-diagnostic-plan.json').read_text())
    opts=plan['execution_profile']
    release19.validate(release19.PROFILE,False,opts,plan['episodes'][0])
    for key,bad in [('held_object','visible_v0'),('own_pose_source','truth'),('lookaround','off'),('pose_anchor','legacy_truth_v0')]:
        with pytest.raises(ValueError):release19.validate(release19.PROFILE,False,{**opts,key:bad},plan['episodes'][0])
    with pytest.raises(ValueError):release19.validate(release19.PROFILE,True,opts,plan['episodes'][0])


def test_queue_pair_same40_separate_sha_and_all_flags_false():
    q=build('1'*40);verify(q)
    assert len(q['candidates'])==2 and q['run_count']==80
    assert q['candidates'][0]['execution_profile']['release_profile']=='release18_v1'
    assert q['candidates'][1]['execution_profile']['release_profile']=='release19_v1'
    q['runs'][0]['enabled']=True
    with pytest.raises(AssertionError):verify(q)


def test_disabled_release19_matches_a3bbc90e_teacher_and_actuator_trace(tmp_path,fake_backend):
    """Execute original a3 run() and new release18 path on the same clock stub."""
    original=subprocess.run(['git','show','a3bbc90e:scripts/run_grasp_act_release.py'],text=True,cwd=runner.ROOT,check=True,stdout=subprocess.PIPE).stdout
    function=next(n for n in ast.parse(original).body if isinstance(n,ast.FunctionDef) and n.name=='run')
    namespace=runner.__dict__.copy()
    exec(compile(ast.Module(body=[function],type_ignores=[]),'<a3bbc90e-run>','exec'),namespace)
    plan=json.loads((runner.ROOT/'experiments/2026-10-14-e2e18-grasp-rootcause/release18-diagnostic-plan.json').read_text())
    old=namespace['run'](plan['episodes'][0],tmp_path/'old',cap_s=25.,**plan['execution_profile'])
    world,ports=fake_backend
    actions={r:copy.deepcopy(p.actions) for r,p in ports.items()}
    world.data.time=0.;world.steps=0;world.closed=False;ports.clear()
    new=runner.run(plan['episodes'][0],tmp_path/'new',cap_s=25.,**plan['execution_profile'])
    assert actions=={r:p.actions for r,p in ports.items()}
    for rid in ('r1','r2'):
        assert (tmp_path/'old'/f'teacher-{rid}.jsonl').read_bytes()==(tmp_path/'new'/f'teacher-{rid}.jsonl').read_bytes()
    for key in ('code_decisions','line_rechecks','map_backoff_checks','release_outcome'):
        assert old[key]==new[key]
    assert new['input_audit']['control_top_camera_reads']==0
    assert new['input_audit']['evaluation_top_camera_reads']>0


def test_release19_runner_records_reused_waits_and_zero_top_control(tmp_path,fake_backend,monkeypatch):
    from tests import test_release15 as existing
    run=runner.run;results=[]
    def selected(*args,**kwargs):
        kwargs.update(release_profile=release19.PROFILE,command_motion='yaw_cal_v1',
                      release_fov_step='release_fov_step_pulse_v1',
                      release_settle_reuse=release18.REUSE,release_goal_region=release18.GOAL_REGION)
        value=run(*args,**kwargs);results.append(value);return value
    monkeypatch.setattr(runner,'run',selected)
    existing.test_runner_real_map_near_wall_and_actual_pixel_barrier(tmp_path,fake_backend,monkeypatch)
    result=results[0]
    assert result['input_audit']['control_top_camera_reads']==0
    assert result['input_audit']['held_world_reads']==0
    assert result['input_audit']['invisible_measurements']==0
    waits=[w for v in result['lookaround_result'].values() for s in v['evaluation']['sweeps'] for w in s['reused_command_waits']]
    assert waits and all(w['omitted_wait_s']==.8 and w['command_age_s']>=.8 for w in waits)
