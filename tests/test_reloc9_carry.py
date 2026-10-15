import copy
import math
import sys
import numpy as np
import pytest
from harness.reloc9_rotation import calibration
from sim.solo_carry_pose import CommandPose, task_start
from harness.zone_final_environment import resolve
from sim.grasp_act_solo_teacher import primitives
from sim.solo_carry9_search import CargoSearch, edge_cue, PANS, RANGE_FACTORS


def pose(**kwargs):
    return CommandPose(task_start(resolve('zone_wide_two_doors_final_v3')[0]),
        drive_model_deadband_v1=True,**kwargs)


def test_rotation_scales_only_pure_turn_once_and_off_is_identical():
    a,b,c=pose(),pose(reloc9_rotation_calibration_v1=False),pose(reloc9_rotation_calibration_v1=True)
    ops=primitives()
    for i,drive in enumerate(([0,0,.065],[0,0,.065],[.1,0,.02],[.1,0,0],[0,0,0])):
        wheels,duration=ops.duty(drive);issued=dict(t=i*.1,wheels=wheels,duration_s=duration)
        for p in (a,b,c):p.issue(issued,.1)
        assert a.record()==b.record()
        from harness.reloc9_rotation import pure_turn
        gain=calibration()['yaw_scale'] if pure_turn(issued) else 1.
        assert c.last_delta[2]==pytest.approx(a.last_delta[2]*gain)
        assert c.cached_delta(issued,.1)==c.last_delta
        assert c.last_delta[:2]==a.last_delta[:2]
    assert c.record()['rotation_error_fraction'] >= .4
    with pytest.raises(ValueError):pose(reloc9_rotation_calibration_v1='on')


def test_plan_same_seeds_layouts_and_disabled_serial_rotation_first_queue():
    from scripts.prepare_reloc9_carry_queue import prepare9,make_queue,CANDIDATES
    from scripts.run_solo_grasp_act_teacher import validate_carry
    p=prepare9();q=make_queue(p,'a'*40)
    assert q['run_count']==34 and q['max_parallel']==1
    assert q['runs'][0]['targets_deg']==[90,-180]
    for i in range(0,33,3):
        group=p['episodes'][i:i+3]
        assert [e['reloc9_candidate'] for e in group]==list(CANDIDATES)
        assert len({e['seed'] for e in group})==1
        assert all(e['spawns']==group[0]['spawns'] and e['cargo_pose_m']==group[0]['cargo_pose_m'] for e in group)
        for e in group:validate_carry(e,enabled=True,training_rgb=False,truth_free=True,lift='solo_lift_lookback_v1',negative=False)
    for obj in [q,q['coordinator_approval'],*q['runs'],*q['execution_stages']]:
        assert all(obj[k] is False for k in ('approved','enabled','ready','stage_ready','execute','submitted'))
    assert all('--execute' not in r['command'] for r in q['runs'])
    for before,after in zip(q['runs'],q['runs'][1:]):assert after['depends_on']==before['name']


def test_search_returns_bearing_then_range_gaze_full_pan_and_body_rotation_only():
    from harness.drive_model import CommandDriveModel
    ops=primitives();goals=[]
    real_gaze=ops.gaze
    ops.gaze=lambda point,pwm,visible=False:(goals.append(list(point)) or real_gaze(point,pwm,visible=visible))
    pwm={1:2000,**ops.folded,6:1500};x=np.array([0.,0.,math.pi])
    s=CargoSearch(x,[.8,0.,.024],0.,pwm,ops,source='issued_setdown_geometry_after_open')
    model=CommandDriveModel();initial_xy=x[:2].copy()
    for i in range(2400):
        turn,pwm=s.tick(i*.1,x,pwm)
        wh,d=ops.duty([0,0,.65*turn]);delta=model.delta(wh,d,.1)
        x[2]+=delta[2]*calibration()['yaw_scale']
        assert delta[:2]==(0.,0.)
        if s.failure:break
    np.testing.assert_array_equal(x[:2],initial_xy)
    assert s.failure=='carry_reacquire_unconfirmed' and i*.1 <= s.deadline+.1
    scans=[e for e in s.events if e['stage']=='pan_scan']
    assert [e['pan'] for e in scans]==list(PANS)*len(RANGE_FACTORS)
    assert {e['range_factor'] for e in scans}==set(RANGE_FACTORS)
    assert s.scan_yaw >= 2*math.pi


def test_left_edge_cue_turns_body_but_never_claims_reacquisition():
    rgb=np.zeros((480,640,3),np.uint8);rgb[200:230,:15]=[255,255,0]
    u=edge_cue(rgb,'yellow');assert u is not None and u < .15
    ops=primitives();pwm={1:2000,**ops.folded,6:1500}
    search=CargoSearch([0,0,0],[1,0,.024],0,pwm,ops,source='previous_own_visible_target')
    search.stage='pan_scan'
    turn,_=search.tick(.1,[0,0,0],pwm,edge_u=u)
    assert turn>0 and search.stage=='edge_orient' and search.failure is None
    search.tick(.2,[0,0,0],pwm,edge_u=u)
    assert search.edge_attempts==1


def test_teacher_search_requires_fresh_measurement_and_off_keeps_legacy():
    from tests.test_solo_carry5 import recovery_teacher
    from sim.solo_carry7 import CargoReacquirer
    t,m,_=recovery_teacher();t.robust_recovery_v1=True
    t.phase='carry_reacquire';t.phase_t=0.;t.skill_started=0.;t.recovery_return='approach'
    t.reloc9_reacquisition_v1=True
    t.reacquirer=CargoSearch(m.loc.pose,[1,0,.024],0,t.sink.pwm,t.ops,source='previous_own_visible_target')
    t.step(0.,own_rgb=lambda:np.zeros((480,640,3),np.uint8))
    assert t.phase=='carry_reacquire'
    t.step(.1,measurement=dict(xyz=[.5,0,.024],yaw=0.),own_rgb=lambda:None)
    assert t.phase=='approach' and t.recovery_world is None
    assert not recovery_teacher()[0].reloc9_reacquisition_v1


def test_rotation_check_prepare_does_not_import_or_run_physics(monkeypatch,capsys):
    from scripts.run_reloc9_rotation_check import main,run
    monkeypatch.setattr(sys,'argv',['check','--plan','missing','--out','missing','--expected-source-sha','a'*40])
    main();assert 'PREPARED_NOT_EXECUTED' in capsys.readouterr().out
    import scripts.run_reloc9_rotation_check as check
    monkeypatch.setattr(check.platform,'system',lambda:'Darwin')
    with pytest.raises(RuntimeError,match='GCP_LINUX_ONLY'):run(None,None,'a'*40)


def test_rotation_check_mock_clock_truth_cannot_change_commands(monkeypatch,tmp_path):
    """No MuJoCo construction/step: adversarial evaluator yaw is output-only."""
    import json
    from types import SimpleNamespace
    import scripts.run_reloc9_rotation_check as check
    import scripts.grasp_act_host as host
    import sim.grasp_act_scene as scene_module
    import types
    drive_module=types.ModuleType('sim.masterpi_drive_friction_v7')
    drive_module.PROFILE='masterpi_drive_friction_v7'
    drive_module.build_world=None
    monkeypatch.setitem(sys.modules,'sim.masterpi_drive_friction_v7',drive_module)
    import sim.grasp_act_port as port_module
    from scripts.prepare_reloc9_carry_queue import PLAN,ROOT
    monkeypatch.setattr(check.platform,'system',lambda:'Linux')
    monkeypatch.setattr(host,'identity',lambda name:None)
    monkeypatch.setattr(host,'require_run_root',lambda path:None)
    monkeypatch.setattr(check,'subprocess',SimpleNamespace(
        check_output=lambda args,**kw:b'' if 'status' in args else 'a'*40))
    evaluator={'yaw':0.}
    class World:
        def __init__(self):self.data=SimpleNamespace(time=0.);self.closed=False
        def robot(self,rid):return SimpleNamespace(base_rpy=lambda:[0.,0.,evaluator['yaw']])
        def _physics_step_for(self,robot):self.data.time+=.01
        def close(self):self.closed=True
    worlds=[]
    def build(*args,**kw):
        assert kw['render'] is False
        w=World();worlds.append(w);return w
    monkeypatch.setattr(drive_module,'build_world',build)
    monkeypatch.setattr(scene_module,'make_scene',lambda p:SimpleNamespace(
        config={'setup_only':{'spawns':{}}},engine_layout={},setup=lambda world:None))
    monkeypatch.setattr(port_module,'DutyActPort',lambda *a,**kw:SimpleNamespace(
        apply=lambda *a:None,tick=lambda *a:None,stop=lambda:None))
    ledgers=[]
    for i,yaw in enumerate((0.,2.9)):
        evaluator['yaw']=yaw
        path=tmp_path/str(i)
        result=check.run(ROOT/PLAN,path,'a'*40)
        assert result['complete'] and not result['rotation_gate_passed']
        # This mock only advances time; it is NOT a physical rotation test.
        ledger=path/'rotation-ledger.jsonl'
        if not ledger.exists():
            import subprocess
            data=subprocess.check_output(['zstd','-dc',str(path/'rotation-ledger.jsonl.zst')])
        else:data=ledger.read_bytes()
        ledgers.append([json.loads(line)['command'] for line in data.splitlines()])
    assert ledgers[0]==ledgers[1] and all(w.closed for w in worlds)
