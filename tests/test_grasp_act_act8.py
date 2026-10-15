"""ACT8 command projection and saved-log audit only; never create a world."""
import ast
import io
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import numpy as np
import pytest

from harness.grasp_act_dart import WheelNoise, MODE, PULSE_MODE
from harness import grasp_act_contract as c
from scripts.analyze_grasp_act_act8 import relay, stalled_intervals, visibility_events
from scripts.queue_grasp_act_act8 import build_queue, SEEDS

ROOT=Path(__file__).resolve().parents[1]
RECORD=ROOT/'experiments/2026-10-15-act-train'


def command(t=0.):
    # Stored failing run, raw t=24: independent wheel clocks are very short.
    return {'t':t,'wheels':[.35,-.35,.35,.35],
        'duration_s':[.057367701172610856,.010812174051191954,.026330683091665193,.020224844029753705],
        'pwm':{str(s):1500 for s in c.SERVOS}}


def model():return json.loads((RECORD/'act8-noise.json').read_text())


def test_new_mode_preserves_start_margin_and_pulse_floor_after_every_draw():
    noise=WheelNoise(model(),seed=8316627,mode=PULSE_MODE); rows=[]; draws=[]
    for i in range(80):
        clean=command(i*.1); applied,diag=noise.apply(clean,phase_before='approach',phase_after='approach',holding=False)
        c.command(applied)
        assert applied['pwm']==clean['pwm'] and clean==command(i*.1)
        for w,d in zip(applied['wheels'],applied['duration_s']):
            assert (w==d==0.) or (abs(w)==.35 and .04<=d<=.1+1e-12)
        rows.append({'applied':applied});draws.append(diag)
    assert sum(d['new_draw'] for d in draws)==20
    assert all(draws[i]['noise']==draws[i//4*4]['noise'] for i in range(80))
    assert relay(rows,'applied')['blocked_wheel_s']==[0.]*4


def test_off_old_mode_and_held_or_stop_commands_do_not_gain_motion():
    clean=command(); old=WheelNoise(model(),seed=17,mode=MODE)
    # Lock the legacy RNG/projection independently of the new path.
    duplicate=WheelNoise(model(),seed=17,mode=MODE)
    assert old.apply(clean,phase_before='approach',phase_after='approach',holding=False)==duplicate.apply(
        clean,phase_before='approach',phase_after='approach',holding=False)
    new=WheelNoise(model(),seed=17,mode=PULSE_MODE)
    for phase,held in [('approach',True),('close',False),('hold',True)]:
        assert new.apply(clean,phase_before=phase,phase_after=phase,holding=held)==(clean,None)
    stop={**clean,'wheels':[0.]*4,'duration_s':[0.]*4}
    assert new.apply(stop,phase_before='approach',phase_after='align',holding=False)==(stop,None)
    assert WheelNoise().apply(clean,phase_before='approach',phase_after='approach',holding=False)==(clean,None)


def test_fast_saved_relay_matches_pinned_command_step_without_importing_sim():
    source=subprocess.check_output(['git','show','6f057f7e:sim/masterpi_drive_friction_v7.py'],cwd=ROOT,text=True)
    tree=ast.parse(source)
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='DriveParameters')
    method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='command_step')
    namespace={'np':np};exec(compile(ast.Module(body=[method],type_ignores=[]),'pinned-command-step','exec'),namespace)
    parameters=SimpleNamespace(start_fraction=.325,kinetic_fraction=1/12)
    rng=np.random.default_rng(8316627);rows=[]
    for i in range(60):
        w=rng.choice([-.4,-.35,-.31,0.,.31,.35,.4],4);d=rng.choice([0.,.01,.031,.04,.099,.1,.15],4)
        d=np.where(w==0,0.,d);w=np.where(d==0,0.,w)
        rows.append({'command':{'wheels':w.tolist(),'duration_s':d.tolist()}})
    state=np.zeros(4,int); blocked=np.zeros(4);integral=np.zeros(4)
    for row in rows:
        for tick in range(100):
            cmd=row['command'];u=np.where(tick*.001 < np.array(cmd['duration_s'])-1e-9,cmd['wheels'],0.)
            effective,state=namespace['command_step'](parameters,u,state)
            blocked+=((u!=0)&(effective==0))*.001;integral+=effective*.001
    audit=relay(rows,'command')
    assert audit['blocked_wheel_s']==pytest.approx(blocked)
    assert audit['signed_effective_integral_u_s']==pytest.approx(integral)


def test_relook_loss_and_reacquisition_are_counted_without_held_intervals():
    rows=[{'phase':p,'t':i*.1,'visible_target':{'xyz':[.2,0,0]} if seen else None}
        for i,(p,seen) in enumerate([('approach',True),('relook',False),('relook',False),
                                  ('relook',True),('close',False),('hold',False),('backoff',True)])]
    assert visibility_events(rows)==[{'lost_t':.1,'reacquired_t':pytest.approx(.3),'blind_s':pytest.approx(.2)}]


def test_net_stall_metric_keeps_motion_path_distinct_from_net_progress():
    rows=[{'t':i*.1,'phase_before':'approach','phase_after':'approach','clean_teacher_command':command(i*.1)} for i in range(61)]
    evaluation=[{'base_xyz':[.002*(i%2),0,0]} for i in range(61)]
    audit=stalled_intervals(rows,evaluation)
    assert audit['longest_s']==6. and audit['windows_N']==31
    assert stalled_intervals(rows,evaluation,require_motion=True)['longest_s']==6.
    stops=[{**r,'clean_teacher_command':{**r['clean_teacher_command'],'wheels':[0.]*4,'duration_s':[0.]*4}} for r in rows]
    assert stalled_intervals(stops,evaluation,require_motion=True)['longest_s']==0.
    evaluation=[{'base_xyz':[i*.01,0,0]} for i in range(61)]
    assert stalled_intervals(rows,evaluation)['longest_s']==0.


def test_new_queue_has_fresh40_and_all_admission_flags_disabled():
    q=build_queue('b'*40)
    def walk(x):
        if isinstance(x,dict):
            for k,v in x.items():
                if k in ('approved','enabled','ready','stage_ready','submitted'):assert v is False
                walk(v)
        elif isinstance(x,list):
            for v in x:walk(v)
    walk(q);runs=q['jobs'][0]['runs']
    assert len(runs)==40 and [r['seed'] for r in runs]==SEEDS
    assert not set(SEEDS)&set(range(8316600,8316640))
    plan=json.loads((RECORD/'act8-gate-plan.json').read_text())
    assert [r['seed'] for r in plan['episodes']]==SEEDS
    assert plan['kinds']==dict.fromkeys(('cyan','red','green','yellow'),10)
    for i,r in enumerate(runs):
        cmd=r['command'];assert r['source_sha']=='b'*40 and r['SOURCE_SHA_file']=='b'*40
        assert cmd[cmd.index('--episode')+1]==str(i)
        assert cmd[cmd.index('--recovery-mode')+1]==PULSE_MODE
        assert cmd[cmd.index('--out')+1].endswith(r['name']+'/raw')
        assert cmd[cmd.index('--plan')+1].endswith('act8-gate-plan.json')
        assert '--training-rgb' not in cmd
    assert q['gate_promotion_authorized_if_all_conditions_pass'] is False


def test_new_mode_cannot_record_training_rgb(monkeypatch,tmp_path):
    from scripts import run_grasp_act_recovery as adapter
    monkeypatch.setattr(adapter.platform,'system',lambda:'Linux')
    with pytest.raises(ValueError,match='gate-only'):
        adapter.run({},tmp_path/'raw',dependency_root=tmp_path,noise_path=tmp_path/'absent',
                    mode=PULSE_MODE,training_rgb=True)


def test_evaluation_snapshot_is_separate_and_apply_return_is_unchanged(monkeypatch):
    from harness.grasp_act_recovery_audit import evaluation_hook
    mujoco=pytest.importorskip('mujoco')
    calls=[]; result=object()
    def original(*args):calls.append(args);return result
    runner=SimpleNamespace(apply=original); stream=io.StringIO()
    joint_index={f'r1__wheel_{w}_joint':i for i,w in enumerate(('fl','fr','rl','rr'))}
    names=['r1__base','cargo_yellow_1','floor','r2__base']
    model=SimpleNamespace(
        joint=lambda name:SimpleNamespace(qposadr=[joint_index[name]],dofadr=[joint_index[name]]),
        geom=lambda index:SimpleNamespace(name=names[index]))
    data=SimpleNamespace(ncon=2,contact=[SimpleNamespace(geom1=0,geom2=1,dist=-.001),
        SimpleNamespace(geom1=2,geom2=3,dist=0.)],qpos=np.arange(4.),qvel=np.arange(4.)+.5)
    port=SimpleNamespace(robot_id='r1',_world=SimpleNamespace(model=model,data=data),
        _robot=SimpleNamespace(base_xyz=lambda:[1.,2.,3.],base_rpy=lambda:[0.,0.,.2]))
    def force(m,d,i,out):assert i==0;out[0]=2.
    monkeypatch.setattr(mujoco,'mj_contactForce',force)
    def forbidden(*a,**k):pytest.fail('physics or rendering reached')
    for name in ('mj_step','mj_forward','Renderer'):monkeypatch.setattr(mujoco,name,forbidden)
    value=command(); previous=command(-.1)
    with pytest.raises(RuntimeError,match='restore'):
        with evaluation_hook(runner,stream,enabled=True):
            assert runner.apply(port,value,0.,previous) is result
            raise RuntimeError('restore')
    assert runner.apply is original and calls==[(port,value,0.,previous)]
    row=json.loads(stream.getvalue());assert row['wheel_qvel_rad_s']==[.5,1.5,2.5,3.5]
    assert row['contacts']==[{'geoms':['r1__base','cargo_yellow_1'],'distance_m':-.001,'normal_force_N':2.}]
