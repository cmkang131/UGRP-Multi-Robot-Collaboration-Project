"""Managed S2 runner on a fake backend; static Scene resolution only, no render/physics."""
import copy
import json
from types import SimpleNamespace

import numpy as np
import pytest

from scripts import run_solo_cyan as runner
from harness import zone_solo_cyan_contract_v106 as c
from harness import zone_solo_cyan_v106 as rt
from sim.solo_cyan_v106 import make_scene, evaluate
from sim.session_scenes import Scene


def small_bundle():
    return {'source_sha': 'a'*40, 'task': {'seed': 911, 'robot_id': 'r3', 'pickup_slot': 'P1-2',
        'destination': 'B', 'passage_id': 'door_1'}, 'map_id': c.MAP_ID, 'contact_profile': 'cargo_noslip_v1',
        'case_cap_s': 4., 'tick_s': .05, 'check': 'solo-cyan-dev'}


def test_standard_scene_final_geometry_only_and_one_cyan():
    scene = make_scene(small_bundle(), 911)
    assert isinstance(scene, Scene)
    assert scene.config['robot_model'] == 'masterpi_v3'
    assert scene.config['static_map'] == c.hp.resolve(c.MAP_ID)[0]
    assert 'landmarks' not in scene.config['static_map']
    assert set(scene.config['setup_only']['spawns']) == {'r1', 'r2', 'r3'}
    objects = scene.config['setup_only']['objects']
    assert len(objects) == 1 and next(iter(objects.values()))['kind'] == 'cyan'
    assert scene._nearclip_id == 'floor_light_nearclip_v1'


def test_all_commanded_camera_postures_have_admitted_keys():
    cal = c.hp.student_calibration(c.hp.calibration_for(c.hp.DEV_PILOT, c.ROOT/c.CALIBRATION,
                                                      c.CALIBRATION_SHA, c.MAP_ID))
    for p in [*[rt.pose_of(k) for k in ('search', 'p45', 'inspect')],
              *[{**rt.LOOK_P20, 6: pan} for pan in rt.LOOK_PANS], rt.grasp_postures()[0], rt.grasp_postures()[1][-1]]:
        c.hp.camera_record(cal, 'unloaded', p)
    c.hp.camera_record(cal, 'loaded', rt.high.HIGH)


def test_bundle_closure_and_workflow_discovery():
    from sim.workflow_manager import catalog
    bundle = c.bundle('a'*40)
    assert bundle['dev_light'] and not bundle['research_result']
    assert bundle['stage_probe'] == 'place' and bundle['speedups'] == 'v98-exact-v6'
    assert bundle['in_run_drop_tilt_contact_detection'] is False
    other = c.bundle('a'*40, stage_probe='pick', speedups='none')
    assert c.hp.base.digest(bundle) != c.hp.base.digest(other)
    hashes = bundle['source_sha256']
    for p in ('harness/zone_solo_cyan_vision_v106.py', 'harness/zone_pair_highpose_partial_fix.py',
              'harness/opencv_wall_observation.py', 'sim/solo_cyan_v106.py', c.CALIBRATION):
        assert hashes[p] == c.hp.base.sha(c.ROOT/p)
    assert 'sim/session_scenes.py' in hashes
    rows = catalog(c.ROOT)[0]['workflows']
    assert next(r for r in rows if r['id'] == c.BUNDLE_ID)['version'] == c.WORKFLOW_VERSION


def test_default_speedups_and_dry_plan_do_not_construct_physics(monkeypatch, capsys, tmp_path):
    args = runner.parser().parse_args(['--expected-source-sha', 'a'*40, '--output', str(tmp_path/'out')])
    assert args.speedups == 'v98-exact-v6'
    monkeypatch.setattr(runner, 'run', lambda *a, **kw: pytest.fail('physics called in plan'))
    assert runner.main(['--expected-source-sha', 'a'*40, '--output', str(tmp_path/'out')]) == 0
    assert json.loads(capsys.readouterr().out)['execution_started'] is False
    assert not (tmp_path/'out').exists()


def test_formal_wrong_passage_and_reserved_seed_are_refused():
    params = dict(robot_id='r3', pickup_slot='P1-2', destination='B', passage_id='door_1', seed=911)
    for changes in ({'admission': 'measured-sim'}, {'passage_id': 'does-not-exist'}, {'seed': 941}):
        with pytest.raises(ValueError):
            c.validate(**{**params, **changes})


def row(t, xyz):
    return {'t': t, 'cyan_xyz_m': list(xyz), 'cyan_rotation': np.eye(3).ravel().tolist(),
            'box_half_m': [.017, .02, .016]}


def test_post_run_judge_rejects_ground_push_and_edge_overhang():
    static = c.hp.resolve(c.MAP_ID)[0]
    dest = static['regions']['zone_B']
    x, y = dest['center_m']
    floor = [row(1+i*.05, [x, y, .016]) for i in range(61)]
    assert not evaluate(floor, static, 'B')['success']  # in-zone without lifting is not pick/carry/place
    assert evaluate([row(0, [1., 0., .15]), *floor], static, 'B')['success']
    overhang = [row(1+i*.05, [x+dest['half_extents_m'][0]-.005, y, .016]) for i in range(61)]
    assert not evaluate([row(0, [1., 0., .15]), *overhang], static, 'B')['success']
    assert not evaluate([row(0, [1., 0., .15]), row(1, [x, y, .016])], static, 'B')['success']


class FakeBackend:
    def __init__(self, bundle, out, seed):
        self.now, self.eval_rows, self.issued = 0., [], []
        self.commands = {'r3': {1: 2000, **rt.pose_of('search')}, 'r1': {'forbidden_foreign_history': True}}
        self.closed = False

    def reset(self, cap):
        return self.now

    def set_deadline(self, deadline):
        self.deadline = deadline

    def advance_to(self, t):
        self.now = t

    def eval_sample(self):
        self.eval_rows.append(row(self.now, [1., 0., .016]))
        # Deliberately malicious eval return: loop must never feed it to control.
        return {'gt_robot_pose': [5, 5, 5], 'success': True}

    def capture(self):
        return {'r3': ({'own_only': True}, None)}

    def issue(self, rid, action):
        self.issued.append((rid, copy.deepcopy(action)))

    def close(self):
        self.closed = True


class FakeRuntime:
    def __init__(self, static, calibration, sha, **task):
        self.state, self.failure, self.robot_id = 'carry', None, 'r3'
        self.events, self.route_i = [], 0
        self.inputs, self.feedback = [], []
        self.closed = False

    @property
    def terminal(self):
        return self.state == 'done'

    def initial_commands(self, now, commands):
        assert set(commands) == {'r3'}

    def on_frames(self, now, frames):
        assert frames == {'r3': ({'own_only': True}, None)}
        self.inputs.append(frames)

    def step(self, now):
        self.state = 'done'
        return [('r3', {'kind': 'hold'})]

    def on_command(self, rid, now, action):
        self.feedback.append((rid, action))

    def record(self):
        return {'state': self.state, 'physical_success': None}

    def close(self):
        self.closed = True


def test_bounded_host_has_no_evaluation_return_channel_and_keeps_artifacts(tmp_path):
    owners = []
    def backend(*a, **kw):
        got = FakeBackend(*a, **kw)
        owners.append(got)
        return got
    def runtime(*a, **kw):
        got = FakeRuntime(*a, **kw)
        owners.append(got)
        return got
    result = runner.run(small_bundle(), tmp_path/'run', backend_factory=backend, runtime_factory=runtime)
    assert result['status'] == 'STAGE_REACHED_UNQUALIFIED'
    assert result['physical_success'] is None and result['evaluation']['success'] is False
    assert result['check_sim_s'] == pytest.approx(3.)
    assert all(o.closed for o in owners)
    assert result['commands_issued'] == 2
    hashes = json.loads((tmp_path/'run/artifacts.sha256.json').read_text())
    assert {'result.json', 'bundle.json', 'student_record.json'} <= hashes.keys()


def test_host_error_retains_failure_record_and_closes_backend(tmp_path):
    b = FakeBackend(None, None, 911)
    def broken(*a, **kw):
        raise OSError(28, 'test ENOSPC')
    result = runner.run(small_bundle(), tmp_path/'error', backend_factory=lambda *a, **kw: b, runtime_factory=broken)
    assert result['status'] == 'HOST_ERROR' and result['failure']['class'] == 'ENOSPC'
    assert b.closed and (tmp_path/'error/result.json').is_file()
