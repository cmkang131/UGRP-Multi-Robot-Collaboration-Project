"""Saved own-RGB/issued-command regression and finite scheduler stubs; no physics."""
import ast
import copy
import json
from pathlib import Path
import subprocess

import numpy as np
import pytest

from sim import release14, release17, release18, release19, release20, release21
from sim.lookaround_localization import Camera
from tests.test_release_regrasp import teachers
from tests.test_grasp_act_release_run import fake_backend  # noqa: F401
from scripts import run_grasp_act_release as runner

FIXTURE = Path(__file__).parent/'fixtures/release21_fov_110618.json'


def setup(cls=release21.LineAlign):
    saved = json.loads(FIXTURE.read_text())
    t = teachers()['r1']
    t.pwm = {int(k):v for k,v in saved['pwm'].items()}
    t.odometry_profile = 'yaw_cal_v1'
    issued, scheduled = [], []
    a = cls(t, saved['t'], camera=Camera(), undistort=lambda f:f,
            wheel_command=lambda *v:issued.append(v), clearance=lambda *v:True,
            fov_step=release17.FOV_STEP)
    a.state = 'align'
    a.expected = dict(t.pwm)
    a.command_history = release18.CommandHistory()
    a.command_history.observe(t.pwm, saved['t'])
    a.features = lambda frame:saved['feature']
    return a, t, saved, issued, scheduled


def test_saved_110618_reproduces_old_failure_and_starts_stationary_recenter():
    old, _, saved, _, _ = setup(release20.LineAlign)
    assert old.choose_step(saved['feature'], .1, saved['t'])['kind'] == 'fov_blocked'
    a, t, saved, issued, scheduled = setup()
    assert a.tick(saved['t'], lambda *v:None, lambda *v:scheduled.append(v)) == 'pending'
    assert a.failure is None and a.view_state['phase'] == 'view'
    assert not any(issued[-1][2]) and a.alternatives == dict(recenter=1, backoff=0, reverse=0)
    assert scheduled and a.stable is None
    target = a.view_state['target']
    assert target[1] == 2000 and all(target[k] == t.pwm[k] for k in (4,5))
    projected = release21.reproject(saved['feature']['points'], a.camera, t.pwm, target)
    assert release21.margin(projected) > release21.margin(saved['feature']['points'])+4.


@pytest.mark.parametrize('yaw_sign',[1,-1])
def test_recenter_checks_same_camera_yaw_before_restore_and_cannot_certify_alignment(yaw_sign):
    a,t,saved,issued,scheduled = setup()
    at=saved['t']
    a.tick(at, lambda *v:None, lambda *v:scheduled.append(v))
    view = a.view_state
    t.pwm = dict(view['target'])
    a.command_history.observe(t.pwm,at+.1)  # scheduler issues on its next tick
    # The fresh camera frame is represented by reprojected own pixels here;
    # this tests scheduling, not a physical prediction or a new observation.
    f=copy.deepcopy(saved['feature'])
    f['points']=release21.reproject(f['points'], a.camera, view['home'], t.pwm).tolist()
    f['fov_safe']=True
    a.features=lambda image:f
    captured=[]
    assert a.tick(at+.7, lambda *v:pytest.fail('unsettled camera'), lambda *v:None)=='pending'
    a.command_history.observe(t.pwm,at+.8)
    assert a.tick(at+.8,lambda *v:pytest.fail('command age only .7'),lambda *v:None)=='pending'
    a.command_history.observe(t.pwm,at+.9)
    assert a.tick(at+.9, lambda *v:captured.append(v), lambda *v:scheduled.append(v))=='pending'
    assert captured and a.view_state['phase']=='verify'
    assert any(e['event']=='release21_pulse' for e in a.records)
    assert a.stable is None and a.state!='done'
    assert a.sign_pending is not None and len(scheduled)==1  # no restore before new RGB
    expected=a.sign_pending['expected_px']
    after={**f,'center_error':f['center_error']+yaw_sign*expected/640}
    a.features=lambda image:after
    a.command_history.observe(t.pwm,at+1.1)
    assert a.tick(at+1.1,lambda *v:captured.append(v),lambda *v:scheduled.append(v))=='pending'
    assert a.sign_state==('verified' if yaw_sign==1 else 'mismatch')
    assert a.view_state['phase']=='restore'
    assert scheduled[-1][1][-1][1] == {3:view['home'][3],6:view['home'][6]}
    t.pwm=dict(view['home']);a.command_history.observe(t.pwm,at+1.2)
    a.command_history.observe(t.pwm,at+1.9)
    assert a.tick(at+1.9,lambda *v:pytest.fail('restore age only .7'),lambda *v:None)=='pending'
    if yaw_sign==-1:
        a.command_history.observe(t.pwm,at+2.)
        assert a.tick(at+2.,lambda *v:pytest.fail('yaw mismatch'),lambda *v:None)=='failed'
        assert a.failure=='release17_yaw_cal_sign_mismatch'
    assert a.started == at  # original 16 s cap remains


def test_alternatives_order_lifetime_bounds_and_map_rejection(monkeypatch):
    a,t,saved,issued,scheduled=setup()
    monkeypatch.setattr(a,'camera_candidate',lambda *v:None)
    a.clearance=lambda *v:False
    assert a.tick(saved['t'],lambda *v:None,lambda *v:scheduled.append(v))=='failed'
    assert not issued and not scheduled
    assert a.alternatives==dict(recenter=2,backoff=2,reverse=2)
    actions=[e['action'] for e in a.records if e['event']=='release21_alternative']
    assert actions==['recenter']*2+['backoff']*2+['reverse']*2
    assert a.records[-1]['event']=='release21_exhausted'
    a.tick(saved['t']+.2,lambda *v:pytest.fail('already failed'),lambda *v:None)
    assert a.alternatives==dict(recenter=2,backoff=2,reverse=2)


def test_recovery_preserves_motion_caps_and_resets_quantum_history():
    a,t,saved,issued,_=setup()
    f=saved['feature']
    a.settlers[0].issued(.1)
    a.motion=np.array([.10,.10,np.deg2rad(18)])
    assert not a.issue(f,(0.,.004,0.),saved['t'],'reverse')
    assert not issued
    a.reset_settling()
    assert a.stable is None and all(s.pulses==s.total_reversals==0 for s in a.settlers)


def test_reprojection_identity_matches_existing_motion_model():
    a,t,saved,_,_=setup()
    p=saved['feature']['points']
    for motion in ((0.,0.,0.),(.01,-.002,.01)):
        assert np.allclose(release21.reproject(p,a.camera,t.pwm,t.pwm,motion),
                           release21.release15.project_motion(p,a.camera,t.pwm,motion))


@pytest.mark.parametrize('profile',[release18.PROFILE,release19.PROFILE])
def test_toggle_requires_quantum_settle_and_safe_profile(profile):
    opts={**release14.SAFE,'command_motion':'yaw_cal_v1','release20_settle':release20.SETTLE,'release21':release21.MODE}
    ep=dict(end_color_scene='grasp_act_teal_blue_v1')
    release21.validate(profile,False,opts,ep)
    for key,bad in (('release21','bad'),('release20_settle','off'),('command_motion','off')):
        with pytest.raises(ValueError):release21.validate(profile,False,{**opts,key:bad},ep)
    with pytest.raises(ValueError):release21.validate(profile,True,opts,ep)


def test_release21_off_matches_e897b0c2_trace_and_results(tmp_path,fake_backend):
    original=subprocess.run(['git','show','e897b0c2:scripts/run_grasp_act_release.py'],text=True,
                            cwd=runner.ROOT,check=True,stdout=subprocess.PIPE).stdout
    function=next(n for n in ast.parse(original).body if isinstance(n,ast.FunctionDef) and n.name=='run')
    ns=runner.__dict__.copy()
    exec(compile(ast.Module(body=[function],type_ignores=[]),'<e897b0c2-run>','exec'),ns)
    plan=json.loads((runner.ROOT/'experiments/2026-10-14-e2e18-grasp-rootcause/release20-dev4-round2-plan.json').read_text())
    world,ports=fake_backend
    original_top=world.render_team_jpeg
    old=ns['run'](plan['episodes'][0],tmp_path/'old',cap_s=25.,**plan['execution_profile'])
    actions={r:copy.deepcopy(p.actions) for r,p in ports.items()}
    world.data.time=0.;world.steps=0;world.closed=False;ports.clear()
    world.render_team_jpeg=original_top
    new=runner.run(plan['episodes'][0],tmp_path/'new',cap_s=25.,release21='off',**plan['execution_profile'])
    assert actions=={r:p.actions for r,p in ports.items()}
    for rid in ('r1','r2'):
        assert (tmp_path/'old'/f'teacher-{rid}.jsonl').read_bytes()==(tmp_path/'new'/f'teacher-{rid}.jsonl').read_bytes()
    for k in ('code_decisions','line_rechecks','map_backoff_checks','release_outcome','input_audit'):
        assert old[k]==new[k]
    assert 'release21' not in new


def test_top_review_off_reads_no_top_camera(tmp_path,fake_backend):
    plan=json.loads((runner.ROOT/'experiments/2026-10-14-e2e18-grasp-rootcause/release20-dev4-round2-plan.json').read_text())
    result=runner.run(plan['episodes'][0],tmp_path/'off',cap_s=25.,release21=release21.MODE,review_top='off',**plan['execution_profile'])
    assert result['input_audit']['evaluation_top_camera_reads']==0
    assert result['input_audit']['control_top_camera_reads']==0
    assert not list((tmp_path/'off/eval-overview').glob('*.jpg'))
