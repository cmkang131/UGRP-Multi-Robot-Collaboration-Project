"""S3 bundle, production host loop and post-run referee, without MuJoCo."""
import copy
import json
import sys
from types import SimpleNamespace

import pytest

from harness import zone_s3_contract as c
from harness import zone_s3_host as host
from scripts import run_s3_host as runner
from sim.zone_s3_host import make_scene, PhysicsBackend
from sim.zone_scenario_scene import ScenarioFinalV3Scene
from tests.test_s3_host import FakePair, FakeSolo, frames


@pytest.fixture(autouse=True)
def no_physics(monkeypatch):
    monkeypatch.setitem(sys.modules, 'mujoco', None)
    monkeypatch.setitem(sys.modules, 'sim.multi_masterpi_production', None)


def test_bundle_reuses_source_closure_and_registered_workflow():
    from sim.workflow_manager import catalog
    b = c.bundle('a'*40)
    assert b['seed'] == 601 and b['model_calls'] == 0 and b['referee_feedback'] is False
    assert b['case_cap_s'] == 1800. and b['tick_s'] == .05
    assert b['parent_bundles'] == ['zone-solo-cyan-v106', 'zone-final-pair-highpose-v98']
    for path in ('harness/zone_pair_highpose_runtime.py', 'harness/zone_solo_cyan_v106.py',
                 'harness/opencv_wall_observation.py', 'harness/zone_study_referee.py',
                 'sim/zone_scenario_scene.py', c.SCENARIO_PATH, c.LAUNCH, c.solo.CALIBRATION):
        assert b['source_sha256'][path] == c.hp.base.sha(c.ROOT/path)
    assert next(r for r in catalog(c.ROOT)[0]['workflows'] if r['id'] == c.BUNDLE_ID)['version'] == '3.14.0'
    b['seed'] = 941
    with pytest.raises(ValueError, match='unregistered'):
        c.verify(b)


@pytest.mark.parametrize('key,value', [('tick_s', .1), ('weld', 'on'), ('model_calls', 1), ('case_cap_s', 3600.)])
def test_tampered_bundle_rejected_before_backend(key, value, tmp_path):
    b = c.bundle('a'*40)
    b[key] = value
    with pytest.raises(ValueError, match='mismatch'):
        runner.run(b, tmp_path/'unused', backend_factory=lambda *a, **k: pytest.fail('backend'))
    assert not (tmp_path/'unused').exists()


def test_actual_scenario_factory_mixed_v3_scene_without_reset():
    scene = make_scene({'scenario_id': 'dev_s1lite'}, 601)
    assert isinstance(scene, ScenarioFinalV3Scene)
    assert set(scene.inventory) == {'cyan_1', 'beam_1'}
    assert set(scene.config['setup_only']['spawns']) == set(host.ROBOTS)
    assert scene._nearclip_id == 'floor_light_nearclip_v1'
    assert scene.config['robot_model'] == 'masterpi_v3'


def test_dry_plan_no_output_physics_or_model(capsys, tmp_path, monkeypatch):
    monkeypatch.setattr(runner, 'run', lambda *a, **kw: pytest.fail('execution in dry plan'))
    assert runner.main(['--expected-source-sha', 'a'*40, '--output', str(tmp_path/'plan')]) == 0
    assert json.loads(capsys.readouterr().out)['execution_started'] is False
    assert not (tmp_path/'plan').exists()


def test_execute_needs_release_even_if_lock_were_free(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, 'check_source', lambda *a: pytest.fail('must refuse reservation first'))
    with pytest.raises(ValueError, match='PR393'):
        runner.main(['--execute', '--expected-source-sha', 'a'*40, '--output', str(tmp_path/'run')])


class Backend:
    def __init__(self, b, out, *, seed):
        self.now, self.commands, self.issued = 0., {r: {'owner': r} for r in host.ROBOTS}, []
        self.closed, self.sampled, self.evaluated = False, [], False
        self.bundle, self.out = b, out

    def reset(self, cap):
        return 0.

    def set_deadline(self, t):
        self.deadline = t

    def eval_sample(self):
        self.sampled.append(self.now)
        return {'success': True, 'gt_robot_pose': [9, 9, 9]}  # forbidden feedback sentinel

    def capture(self):
        assert not self.evaluated
        return frames(self.now)

    def advance_to(self, t):
        assert not self.evaluated
        self.now = t

    def issue(self, r, cmd):
        assert not self.evaluated
        self.issued.append((r, self.now, copy.deepcopy(cmd)))

    def evaluate(self, orders, static):
        self.evaluated = True
        return {'orders_complete': self.verdict, 'orders': {o['order_id']: {} for o in orders}}

    def close(self):
        self.closed = True


def execute_fake(tmp_path, monkeypatch, *, verdict=False, failure=False):
    monkeypatch.setattr(c, 'CAP_S', 4.)
    made, runtimes = [], []
    def backend(*a, **kw):
        obj = Backend(*a, **kw)
        obj.verdict = verdict
        made.append(obj)
        return obj
    def runtime(*a, **kw):
        obj = host.Runtime(*a, **kw, pair_factory=FakePair, solo_factory=FakeSolo)
        step = obj.step
        def progress(now):
            rows = step(now)
            if now >= .1:
                for own in obj.pair.actors.values():
                    own.jobs_done.append({'kind': 'pair_carry', 'confirmation': 'unconfirmed'})
                obj.solo.terminal = True
                obj.solo.failure = 'TEST_FAILURE' if failure else None
            return rows
        obj.step = progress
        runtimes.append(obj)
        return obj
    b = c.bundle('a'*40)
    result = runner.run(b, tmp_path, runtime_factory=runtime, backend_factory=backend)
    return result, made[0], runtimes[0]


def test_real_loop_completion_is_not_delivery_eval_cannot_steer(tmp_path, monkeypatch):
    result, backend, rt = execute_fake(tmp_path/'fail', monkeypatch, verdict=False)
    assert result['status'] == 'DEV_NOT_DELIVERED' and result['commands_complete']
    assert result['evaluation']['orders_complete'] is False
    assert result['check_sim_s'] == pytest.approx(3.1)
    passed, other, _ = execute_fake(tmp_path/'pass', monkeypatch, verdict=True)
    assert passed['status'] == 'DEV_DELIVERED'
    assert other.issued == backend.issued  # only evaluation changed, never actions
    assert backend.closed and rt.solo.closed and rt.pair.closed
    report = json.loads((tmp_path/'fail/trial.json').read_text())
    assert report['http_attempts'] == report['model_calls'] == 0
    manifest = json.loads((tmp_path/'fail/artifacts.sha256.json').read_text())
    assert all(c.hp.base.sha(tmp_path/'fail'/p) == sha for p, sha in manifest.items())


def test_controller_failure_cannot_be_relabelled_by_positive_judge(tmp_path, monkeypatch):
    result, backend, rt = execute_fake(tmp_path/'out', monkeypatch, verdict=True, failure=True)
    assert result['status'] == 'DEV_NOT_DELIVERED' and not result['commands_complete']
    assert result['controller_failures'] == {'r3': 'TEST_FAILURE'}


def test_backend_error_closes_runtime_and_records_host_error(tmp_path, monkeypatch):
    def broken(self, r, cmd):
        raise OSError(28, 'disk full')
    monkeypatch.setattr(Backend, 'issue', broken)
    result, backend, rt = execute_fake(tmp_path/'out', monkeypatch)
    assert result['status'] == 'HOST_ERROR' and result['failure']['class'] == 'ENOSPC'
    assert backend.closed and rt.solo.closed and rt.pair.closed
    assert (tmp_path/'out/result.json').is_file()


def judge(tmp_path, rows):
    b = {'seed': 601, 'source_sha': 'a'*40}
    owner = SimpleNamespace(bundle=b, out=tmp_path)
    (tmp_path/'eval_only').mkdir()
    (tmp_path/'eval_only/referee_truth.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
    return PhysicsBackend.evaluate(owner, c.inputs()[2]['orders'], c.hp.resolve(c.solo.MAP_ID)[0])


@pytest.mark.parametrize('defect', [None, 'held', 'overhang', 'missing', 'departed'])
def test_post_run_existing_referee_requires_both_orders_and_final_standing(tmp_path, defect):
    static = c.hp.resolve(c.solo.MAP_ID)[0]
    a, b = [static['regions']['zone_'+z]['center_m'] for z in ('A', 'B')]
    items = {'cyan_1': {'kind': 'cyan', 'x': a[0], 'y': a[1], 'z': .016, 'yaw': 0., 'held': False, 'speed': 0.},
             'beam_1': {'kind': 'long_beam', 'x': b[0], 'y': b[1], 'z': .02, 'yaw': 0., 'held': False, 'speed': 0.}}
    if defect == 'held':
        items['cyan_1']['held'] = True
    if defect == 'overhang':
        items['beam_1']['x'] += .7
    if defect == 'missing':
        del items['beam_1']
    rows = [{'t': t, 'items': copy.deepcopy(items)} for t in (0., 1., 2., 3.)]
    if defect == 'departed':
        rows[-1]['items']['beam_1']['x'] = -1.
    result = judge(tmp_path, rows)
    assert result['orders_complete'] == (defect is None)
    assert result['feedback_to_controller'] is False
