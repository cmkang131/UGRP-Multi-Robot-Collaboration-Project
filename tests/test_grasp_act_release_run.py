"""Real release run/message loop on a clock-only backend; no physics or render."""
import base64
import io
import json
import sys
from types import ModuleType, SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from scripts import run_grasp_act_release as runner


@pytest.fixture
def fake_backend(monkeypatch):
    """Replace only the scene, native I/O, prefix and evaluation owners."""
    def module(name, **members):
        stub = ModuleType(name)
        stub.__dict__.update(members)
        monkeypatch.setitem(sys.modules, name, stub)

    from harness import zone_pair_highpose_contract as contract
    static = contract.resolve('zone_wide_two_doors_final_v3')[0]
    cargo = SimpleNamespace(item_id='beam_1', body='beam')
    scene = SimpleNamespace(config={'static_map': static, 'setup_only': {'objects': {}}},
                            cargo=[cargo], engine_layout=None, manifest={'fake_backend': True},
                            setup=lambda world: None)
    image_bytes = io.BytesIO()
    Image.new('RGB', (640, 480)).save(image_bytes, format='JPEG')
    jpeg = image_bytes.getvalue()
    geometry = SimpleNamespace(name='zone_zone_A', id=0)
    beam = SimpleNamespace(xpos=np.array([4.6, .4, .03]), xmat=np.eye(3).ravel())

    class World:
        def __init__(self):
            self.data = SimpleNamespace(time=0., eq_active=np.array([False]),
                                        body=lambda name: beam,
                                        site=lambda name: SimpleNamespace(xpos=np.array([0., 0., .1])),
                                        cam_xpos=np.zeros((2, 3)),
                                        cam_xmat=np.tile(np.eye(3).ravel(), (2, 1)))
            self.model = SimpleNamespace(ngeom=1, geom=lambda key: geometry)
            self.controllers = {r: SimpleNamespace(robot_cam_cid=i) for i, r in enumerate(('r1', 'r2'))}
            self.scene_xml = '<fake-clock-only/>'
            self.closed = False
            self.steps = 0

        def robot(self, rid):
            return SimpleNamespace(base_xyz=lambda: [0., 0., .03], base_rpy=lambda: [0., 0., 0.])

        def _physics_step_for(self, robot):
            self.steps += 1
            self.data.time += .05     # clock only; no simulator or dynamics

        def render_team_jpeg(self, **kwargs):
            return jpeg              # synthetic blank fixture, no renderer

        def close(self):
            self.closed = True

    world = World()
    ports = {}

    class Port:
        def __init__(self, world, rid, **kwargs):
            # Arm commands from the ff8f11ef crash ledgers, never measured joints.
            self._servo_pulses = {1: 1500, 3: 811, 4: 1905, 5: 2183, 6: 1500}
            self._motor_commands = (0.,)*4
            self.actions = []
            ports[rid] = self

        def apply(self, action, now):
            self.actions.append((now, action))
            if action['kind'] == 'look':
                self._servo_pulses[6] = action['pan_pulse']
            elif action['kind'] == 'arm':
                self._servo_pulses[action['servo_id']] = action['pulse']

        def _set_motors(self, levels):
            self._motor_commands = tuple(levels)

        def stop(self):
            self._set_motors((0.,)*4)

        def tick(self, now):
            pass

        def capture(self):
            return {'image': base64.b64encode(jpeg).decode()}

    class Prefix:
        phase = 'done'
        outcome = 'success'

        def __init__(self, rid, end, pwm, **kwargs):
            self.pwm = pwm

        def step(self, truth, now, **kwargs):
            return runner.command({'t': now, 'drive': [0., 0., 0.], 'duration_s': 0., 'pwm': self.pwm}), None

    class Visibility:
        def __init__(self, model):
            pass

        def measure(self, data, rid, end):
            return {'visible_probes': 0}

        def body_visible(self, data, rid, body):
            return False

    module('sim.grasp_act_scene', make_scene=lambda plan: scene)
    module('sim.masterpi_drive_friction_v7', build_world=lambda *a, **kw: world, PROFILE='fake')
    module('sim.grasp_act_port', ContinuousActPort=Port)
    module('sim.s2_realism_camera_binding', bind_camera=lambda controller: None)
    module('sim.grasp_act_teacher', GraspTeacher=Prefix)
    from sim import zone_cargo
    monkeypatch.setattr(zone_cargo, 'place', lambda *a: None)
    monkeypatch.setattr(zone_cargo, 'CargoInstance', lambda *a: cargo)
    module('harness.render_randomization', draw=lambda *a: None, apply=lambda *a: {'profile': 'off'})
    monkeypatch.setattr(runner.platform, 'system', lambda: 'FakeBackend')
    monkeypatch.setattr(runner.subprocess, 'check_output',
                        lambda args, **kw: '' if 'status' in args else 'fake-committed-source\n')
    from scripts import audit_grasp_act_visibility
    monkeypatch.setattr(audit_grasp_act_visibility, 'BandVisibility', Visibility)
    monkeypatch.setattr(runner.Eyes, 'classify', lambda *a: None)
    monkeypatch.setattr(runner, 'snapshot', lambda *a: {
        'beam': {'min_z': .02}, 'contacts': {r: [1., 1.] for r in ('r1', 'r2')},
        'robots': {r: {'pose': [0., 0., 0.]} for r in ('r1', 'r2', 'r3')}})
    # Keep the real JSON writer, message coordinator, release teachers, localizers and scheduler.
    monkeypatch.setattr(runner, 'compress_logs', lambda out: None)
    return world, ports


@pytest.mark.parametrize('episode', (0, 1, 2))
def test_command_relative_no_evidence_reaches_pair_decision(tmp_path, fake_backend, episode):
    plans = json.loads((runner.ROOT/'experiments/2026-10-14-e2e18-grasp-rootcause/'
                        'release-command-diagnostic-plan.json').read_text())
    out = tmp_path/'release'
    result = runner.run(plans['episodes'][episode], out, cap_s=3., **plans['execution_profile'])
    world, _ = fake_backend
    assert world.closed and world.steps >= 60
    assert result['status'] == 'complete' and result['prefix_held']
    assert result['code_decisions'][0]['evidence'] == ['none', 'none']
    assert result['code_decisions'][0]['action'] == 'lower'   # blind set-down, then look; not acceptance
    assert result['code_decisions'][0]['lo'] is None and result['code_decisions'][0]['hi'] is None
    assert not result['release_success'] and result['release_outcome'] == 'release_timeout'
    for rid in ('r1', 'r2'):
        rows = [json.loads(s) for s in (out/f'teacher-{rid}.jsonl').read_text().splitlines()]
        assert len(rows) >= 15 and any(r['teacher_phase'] == 'lower' for r in rows)
        reports = [r['report'] for r in rows if r['report']]
        assert all(r['kind'] == 'none' and r['margin_m'] is None for r in reports)
        assert not result['teachers'][rid]['map_pose_known']
        assert not result['lookaround_result'][rid]['localizer']['map_pose_known']
    assert result['input_audit']['held_world_reads'] == 0
    assert result['input_audit']['invisible_measurements'] == 0
    assert json.loads((out/'result.json').read_text())['status'] == 'complete'


def test_unknown_evidence_still_searches_after_lookaround(tmp_path, fake_backend):
    plans = json.loads((runner.ROOT/'experiments/2026-10-14-e2e18-grasp-rootcause/'
                        'release-command-diagnostic-plan.json').read_text())
    out = tmp_path/'release-search'
    result = runner.run(plans['episodes'][0], out, cap_s=22., **plans['execution_profile'])
    world, ports = fake_backend
    assert world.closed and result['status'] == 'complete'
    for rid in ('r1', 'r2'):
        phases = [json.loads(s)['teacher_phase'] for s in (out/f'teacher-{rid}.jsonl').read_text().splitlines()]
        assert 'lookaround' in phases and 'observe' in phases
        pans = [a['pan_pulse'] for _, a in ports[rid].actions if a['kind'] == 'look']
        assert all(p in pans for p in (1750, 1250, 2000, 1000))
        localizer = result['lookaround_result'][rid]['localizer']
        assert localizer['decision']['reason'] == 'map_pose_unknown'
        assert not localizer['decision']['accepted']
    assert not result['release_success']   # blank RGB and no zone evidence cannot accept release


def test_rgb_center_blank_stops_after_real_sweep_without_truth_perception(tmp_path, fake_backend, monkeypatch):
    from sim.grasp_act_release_teacher import ReleaseTeacher
    def forbidden(*args, **kwargs):
        raise AssertionError('truth-derived perception entered RGB centering')
    monkeypatch.setattr(runner.Eyes,'classify',forbidden)
    monkeypatch.setattr(runner.Eyes,'visible',forbidden)
    original=ReleaseTeacher.perceive
    def check(self,obs,now):
        assert obs['band'] is None and not obs['scan']
        return original(self,obs,now)
    monkeypatch.setattr(ReleaseTeacher,'perceive',check)
    plans=json.loads((runner.ROOT/'experiments/2026-10-14-e2e18-grasp-rootcause/release-command-diagnostic-plan.json').read_text())
    result=runner.run(plans['episodes'][0],tmp_path/'blank',cap_s=60.,placement='zone_center_rgb_v1',**plans['execution_profile'])
    assert result['release_outcome']=='zone_center_unobserved'
    assert result['shift_steps']==0 and not result['release_success']
    for rid in ('r1','r2'):
        sweeps=result['lookaround_result'][rid]['evaluation']['sweeps']
        assert len(sweeps)==1
        assert len(sweeps[0]['zone_rgb_views'])==6
        assert len({v['servo'][6] for v in sweeps[0]['zone_rgb_views']})==5
        assert not sweeps[0]['zone_center']['accepted']
        assert sweeps[0]['before']['error_frame']=='arbitrary_command_start'
    assert result['input_audit']['held_world_reads']==result['input_audit']['invisible_measurements']==0


def test_rgb_center_reobserve_after_bounded_move_and_count_actual_shifts(tmp_path, fake_backend, monkeypatch):
    from sim.release_zone_servo import ZoneCenterServo
    calls=[]
    def fitted(self,beam):
        # Pair reports are body-relative (opposite signs), never a map location.
        n=len(calls);calls.append(beam)
        shift=(.63 if n%2==0 else -.63) if n<2 else 0.
        self.result={'accepted':True,'shift_body_m':shift,'map_pose_known':False}
        return self.result
    monkeypatch.setattr(ZoneCenterServo,'finalize',fitted)
    plans=json.loads((runner.ROOT/'experiments/2026-10-14-e2e18-grasp-rootcause/release-command-diagnostic-plan.json').read_text())
    result=runner.run(plans['episodes'][0],tmp_path/'move',cap_s=120.,placement='zone_center_rgb_v1',**plans['execution_profile'])
    assert result['release_outcome']=='teacher_done'
    assert result['shift_steps']==1 and len(calls)==4
    assert result['code_decisions'][1]['shift_m']==.5
    for rid in ('r1','r2'):
        assert len(result['lookaround_result'][rid]['evaluation']['sweeps'])==2
        rows=[json.loads(x) for x in (tmp_path/'move'/f'teacher-{rid}.jsonl').read_text().splitlines()]
        assert any(r['teacher_phase']=='shift' for r in rows)
        assert sum(r['teacher_phase']=='lookaround' for r in rows)>60


def test_release_summary_includes_failure_distances_and_missing_runs(tmp_path):
    from scripts.summarize_grasp_act_release import summarize
    plan={'episodes':[{'seed':i} for i in range(40)]};sha='a'*40
    for i in range(39):
        p=tmp_path/f'gate-{i:02d}-{sha[:8]}'/'raw'/'result.json';p.parent.mkdir(parents=True)
        p.write_text(json.dumps({'status':'complete','source_sha':sha,'prefix_held':True,'release_success':i<38,
            'evaluation_position_error':{'center_distance_m':.6 if i==38 else .02},
            'input_audit':{'held_world_reads':0,'invisible_measurements':0}}))
    result=summarize(plan,tmp_path,'gate',sha)
    assert result['release_success']==38 and not result['gate_pass']
    assert result['complete']==39 and result['runs'][-1]['status']=='missing'
    assert result['center_distance_m']['median']==.02 and result['center_distance_m']['max']==.6


def test_global_release_blank_uses_active_sweeps_before_exhaustion(tmp_path,fake_backend,monkeypatch):
    def forbidden(*args,**kwargs):raise AssertionError('truth perception')
    monkeypatch.setattr(runner.Eyes,'classify',forbidden)
    monkeypatch.setattr(runner.Eyes,'visible',forbidden)
    plans=json.loads((runner.ROOT/'experiments/2026-10-14-e2e18-grasp-rootcause/release-command-diagnostic-plan.json').read_text())
    profile={**plans['execution_profile'],'lookaround':'setdown_global_v1','placement':'global_localized_release_v1'}
    result=runner.run(plans['episodes'][0],tmp_path/'global-empty',cap_s=120.,**profile)
    assert result['release_outcome']=='active_observation_exhausted'
    assert result['shift_steps']==0 and not result['release_success']
    for rid in ('r1','r2'):
        actions=[r for r in result['active_observation'] if r['robot']==rid]
        assert [r['stage'] for r in actions]==[1,2,3]
        assert actions[0]['action']=='pan'
        assert all('skipped' in r['action'] for r in actions[1:])
        assert len(result['lookaround_result'][rid]['evaluation']['sweeps'])==4
    assert result['input_audit']['held_world_reads']==result['input_audit']['invisible_measurements']==0


def test_global_release_message_loop_shifts_then_reobserves(tmp_path,fake_backend,monkeypatch):
    from sim import release_global_observation as active
    calls=[]
    def margins(loc,teacher,now):
        n=len(calls);calls.append(teacher.rid)
        margin=(.05 if teacher.rid=='r1' else .75) if n<2 else .4
        return dict(phase='observe',kind='localized_margin',margin_m=margin,
                    expected_slack_m=.8,lateral_clearance_m=.2)
    monkeypatch.setattr(active,'margin_report',margins)
    plans=json.loads((runner.ROOT/'experiments/2026-10-14-e2e18-grasp-rootcause/release-command-diagnostic-plan.json').read_text())
    profile={**plans['execution_profile'],'lookaround':'setdown_global_v1','placement':'global_localized_release_v1'}
    result=runner.run(plans['episodes'][0],tmp_path/'global-move',cap_s=120.,**profile)
    assert result['release_outcome']=='teacher_done' and result['shift_steps']==1
    assert result['code_decisions'][1]['shift_m']==.2 and len(calls)==4
    assert all(len(v['evaluation']['sweeps'])==2 for v in result['lookaround_result'].values())


def test_lateral_recovery_regrasp_pwm_setdown_and_reobserve(tmp_path,fake_backend,monkeypatch):
    import math
    from sim import release_global_observation as active
    calls=[]
    def margins(loc,teacher,now,*,lateral_recovery):
        assert lateral_recovery=='bounded_v1'
        loc.own.x=np.array([4.6,.4,math.pi/2+.12 if teacher.rid=='r1' else -math.pi/2+.10])
        loc.decision={'accepted':True}
        n=len(calls);calls.append(teacher.rid)
        return dict(phase='observe',kind='localized_margin',margin_m=.4,expected_slack_m=.8,
            lateral_clearance_m=.025 if n<2 else .20,lateral_shift_lo_m=.015,lateral_shift_hi_m=.43)
    monkeypatch.setattr(active,'margin_report',margins)
    def forbidden(*a,**kw):raise AssertionError('truth perception')
    monkeypatch.setattr(runner.Eyes,'classify',forbidden)
    plans=json.loads((runner.ROOT/'experiments/2026-10-14-e2e18-grasp-rootcause/release-command-diagnostic-plan.json').read_text())
    profile={**plans['execution_profile'],'lookaround':'setdown_global_v1','placement':'global_localized_release_v1','lateral_recovery':'bounded_v1'}
    result=runner.run(plans['episodes'][0],tmp_path/'side',cap_s=120.,**profile)
    assert result['release_outcome']=='teacher_done' and result['shift_steps']==1
    assert len(calls)==4 and result['code_decisions'][1]['lateral_shift_m']==.1
    assert len(result['lateral_motion_commands'])==1
    assert result['input_audit']['held_world_reads']==result['input_audit']['invisible_measurements']==0
    assert all(len(v['evaluation']['sweeps'])==2 for v in result['lookaround_result'].values())


def test_nbv_runs_after_legacy_budget_then_uses_only_new_own_rgb(tmp_path,fake_backend,monkeypatch):
    from sim.lookaround_localization import LookaroundLocalizer
    from sim import release_nbv_observation as nbv
    original=LookaroundLocalizer.finalize
    counts={}
    def fitted(self):
        count=counts.get(id(self),0)+1;counts[id(self)]=count
        # Do not inspect backend truth. Synthetic ambiguous own-image receipt
        # exercises the real scheduler, camera capture and turn/return path.
        out=original(self)
        self.decision={**out,'alternatives':[dict(pose=[4.6,.4,math.pi/2])]}
        return self.decision
    import math
    monkeypatch.setattr(LookaroundLocalizer,'finalize',fitted)
    def forbidden(*a,**kw):raise AssertionError('truth perception entered NBV')
    monkeypatch.setattr(runner.Eyes,'classify',forbidden)
    monkeypatch.setattr(runner.Eyes,'visible',forbidden)
    plans=json.loads((runner.ROOT/'experiments/2026-10-14-e2e18-grasp-rootcause/release-command-diagnostic-plan.json').read_text())
    profile={**plans['execution_profile'],'lookaround':'setdown_global_v1',
             'placement':'global_localized_release_v1','active_recovery':'map_nbv_v1'}
    result=runner.run(plans['episodes'][0],tmp_path/'nbv',cap_s=180.,**profile)
    assert result['release_outcome']=='active_observation_exhausted'
    assert not result['release_success'] and result['shift_steps']==0
    for rid in ('r1','r2'):
        entries=[r for r in result['active_observation'] if r['robot']==rid]
        assert [r['stage'] for r in entries]==[1,2,3,4,5,6]
        assert all(r['action']=='map_nbv' for r in entries[3:])
        captures=[len(r['views']) for r in entries[3:]]
        assert all(1<=n<=nbv.VIEW_BUDGET for n in captures)
        saved=result['lookaround_result'][rid]['localizer']
        assert len(saved['views'])==33+sum(captures)
        assert not saved['map_pose_known'] and not saved['decision']['accepted']
    assert result['input_audit']['held_world_reads']==result['input_audit']['invisible_measurements']==0


@pytest.mark.parametrize('recover', (False, True))
def test_setdown_panorama_after_open_retrace_then_original_regrasp(tmp_path,fake_backend,monkeypatch,recover):
    import math
    from sim.lookaround_localization import LookaroundLocalizer
    from sim import release_global_observation as active
    from sim.grasp_act_release_teacher import ReleaseTeacher
    original=LookaroundLocalizer.finalize
    def fitted(self):
        result=original(self)   # blank frames must still be rejected
        self.decision={**result,'credible_hypotheses':[dict(pose=[4.7,.7,math.pi/2])]}
        return self.decision
    monkeypatch.setattr(LookaroundLocalizer,'finalize',fitted)
    def forbidden(*a,**kw):raise AssertionError('truth perception in setdown recovery')
    monkeypatch.setattr(runner.Eyes,'classify',forbidden)
    monkeypatch.setattr(runner.Eyes,'visible',forbidden)
    if recover:
        def margins(loc,t,now,**kw):
            count=len(loc.views)
            # Synthetic sensor receipt tests the runner transition only, NOT
            # localization accuracy or new-view detection on a real scene.
            if count<25:return dict(phase='observe',kind='none')
            margin=(.1 if t.rid=='r1' else .7) if count==25 else .4
            return dict(phase='observe',kind='localized_margin',margin_m=margin,
                        expected_slack_m=.8,lateral_clearance_m=.2)
        monkeypatch.setattr(active,'margin_report',margins)
    picks=[];old_pick=ReleaseTeacher.pick_schedule
    def pick(self,now):
        picks.append(self.rid)
        return old_pick(self,now)
    monkeypatch.setattr(ReleaseTeacher,'pick_schedule',pick)
    plans=json.loads((runner.ROOT/'experiments/2026-10-14-e2e18-grasp-rootcause/release6-diagnostic-plan.json').read_text())
    profile={**plans['execution_profile'],'active_recovery':'setdown_lookaround_v1'}
    out=tmp_path/'setdown'
    result=runner.run(plans['episodes'][0],out,cap_s=180.,**profile)
    assert result['release_outcome']==('teacher_done' if recover else 'active_observation_exhausted')
    assert result['legacy_visibility_counts_applicable'] is False
    assert result['final_map_pose_accepted']=={'r1':False,'r2':False}
    assert result['shift_steps']==int(recover)
    assert picks==(['r1','r2'] if recover else [])
    for rid in ('r1','r2'):
        actions=[a for a in result['active_observation'] if a['robot']==rid]
        assert [a['action'] for a in actions]==['pan','setdown_lookaround_v1']
        rows=[json.loads(s) for s in (out/f'teacher-{rid}.jsonl').read_text().splitlines()]
        first_open=next(v['t'] for v in rows if not v['holding_belief'])
        start=actions[1]['t']
        assert first_open<start and all(not v['holding_belief'] for v in rows if start<=v['t'] and v['teacher_phase']=='lookaround')
        sweeps=result['lookaround_result'][rid]['evaluation']['sweeps']
        labels=[s['label'] for sweep in sweeps for s in sweep['script']]
        assert 'setdown_retrace_backoff_0.10m' in labels and 'setdown_turn_return' in labels
        assert len([s for s in labels if s.startswith('setdown_view')])==12
        if not recover:
            assert len(result['lookaround_result'][rid]['localizer']['views'])==25
            assert not result['lookaround_result'][rid]['localizer']['decision']['accepted']
    assert result['input_audit']['held_world_reads']==result['input_audit']['invisible_measurements']==0
