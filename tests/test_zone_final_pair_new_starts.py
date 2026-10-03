"""V94 fake-physics admission, schedule/support and precheck isolation."""
import copy
import json
from types import SimpleNamespace

import numpy as np
import pytest

from harness import zone_final_pair_new_starts as v
from scripts import precheck_heldout_v94 as checker
from scripts import run_final_pair_new_starts as runner
from tests.test_zone_final_pair_v3 import FakePhysics


def bundle(mid=v.MAPS[0]):
    return {**v.bundle(mid), 'case': v.cases(v.CHECK, mid)[0], 'source_sha': 'a'*40}


@pytest.mark.parametrize('mid', v.MAPS)
def test_four_new_starts_and_every_supported_cell(mid):
    result = checker.support(mid)
    assert result['cell_count'] == 288
    assert all(c['complete_windows'] > 0 for c in result['cells'])
    assert {r['robot_id'] for r in result['cells']} == {'r1', 'r2'}
    assert {r['horizon_s'] for r in result['cells']} == {.2, .5, 1., 2., 3., 3.2}
    assert len({tuple(p) for starts in v.STARTS.values() for p in starts.values()}) == 4
    from sim.final_pair_new_starts import make_scene
    scene = make_scene(bundle(mid), 911)
    from sim.session_scenes import Scene
    assert isinstance(scene, Scene)
    for rid, xy_yaw in v.STARTS[mid].items():
        p = scene.config['setup_only']['spawns'][rid]
        assert [p[0], p[1], p[3]] == xy_yaw
    assert v.path_preflight(v.CHECK, mid)['admitted']


@pytest.mark.parametrize('precheck', [True, False])
def test_same_command_timeline_headless_or_collection(tmp_path, precheck):
    made = []
    class Backend(FakePhysics):
        minimum_wall_clearance_m = {'r1': .7, 'r2': .8}
        def kinematic_sample(self):
            self.eval_sample()
    def factory(*a, **kw):
        obj = Backend(*a, **kw)
        made.append(obj)
        return obj
    result = runner.run_case(bundle(), tmp_path/'case', seed=911, backend_factory=factory, precheck=precheck)
    obj = made[0]
    assert result['status'] == ('PRECHECK_ONLY' if precheck else 'COLLECTED_UNQUALIFIED')
    assert result['collection_role'] == ('PRECHECK_NOT_COLLECTION' if precheck else 'HELD_OUT_VALIDATION')
    assert len(obj.samples) == 7401
    assert len(obj.frames) == (0 if precheck else 1851)
    assert len(obj.actions) == len(v.schedule())
    assert {a['robot_id'] for a in v.schedule()} == {'r1', 'r2'}


@pytest.mark.parametrize('fault', ['start', 'r2_plan', 'timing', 'model', 'weld', 'seed', 'interlock'])
def test_mutations_stop_before_backend_and_output(tmp_path, fault):
    b = bundle()
    if fault == 'start': b['start_xy_yaw']['r2'][0] = 3.25
    if fault == 'r2_plan': b['measurement_by_robot']['r2']['segments'] = []
    if fault == 'timing': b['timing']['scheduler_period_s'] = .2
    if fault == 'model': b['robot_model'] = 'masterpi_v2'
    if fault == 'weld': b['weld'] = 'on'
    if fault == 'seed': b['seed'] = 912
    if fault == 'interlock': b['runtime_interlock']['required'] = False
    with pytest.raises(ValueError):
        runner.run_case(b, tmp_path/'forbidden', seed=911,
                        backend_factory=lambda *a, **kw: pytest.fail('backend reached'))
    assert not (tmp_path/'forbidden').exists()


def test_missing_signed_level_or_long_horizon_rejected(monkeypatch):
    old = v.design
    def bad(check, mid, rid='r1'):
        plan = old(check, mid, rid)
        for s in plan['segments']:
            if s['phase'] == 'step' and s['value'] == -.03:
                s['value'] = -.02
        return plan
    monkeypatch.setattr(v, 'design', bad)
    with pytest.raises(ValueError, match='unsupported B cell'):
        checker.support(v.MAPS[0])


def test_headless_capture_is_impossible():
    from sim.final_pair_new_starts import PhysicsBackend
    obj = PhysicsBackend.__new__(PhysicsBackend)
    obj.render_enabled = False
    with pytest.raises(RuntimeError, match='MUST_NOT_CAPTURE'):
        obj.capture()


def test_r2_geometry_has_the_same_mandatory_guard(monkeypatch):
    from tests.test_zone_final_pair_review_fixes import fake_guard
    from sim.final_pair_new_starts import PhysicsBackend
    old = fake_guard(monkeypatch)
    obj = PhysicsBackend.__new__(PhysicsBackend)
    obj.__dict__ = copy.copy(old.__dict__)
    obj.bundle = bundle()
    obj.minimum_wall_clearance_m = dict.fromkeys(v.ROBOTS, float('inf'))
    obj.scene.config['static_map'] = v.previous.resolve(v.MAPS[0])[0]
    # Fixture has two carrier geometries; the unloaded v91 guard checked only r1.
    obj.collection_guard()
    obj.world.data.geom_xpos[1, 0] = 2.4
    with pytest.raises(ValueError):
        obj.collection_guard()
    assert obj.held


def test_workflow_routes_new_runner_and_binding_includes_all_gates():
    from sim import workflow_manager as wm
    row, _ = wm._row(v.previous.ROOT, v.WORKFLOW_ID)
    assert row['runner'] == 'scripts.run_final_pair_new_starts'
    assert row['version'] == '3.6.0'
    b = checker.binding()
    for path in ('harness/kinematic_overlap.py', 'scripts/precheck_heldout_v94.py',
                 'scripts/validate_consumer_criterion_b_v94.py', 'sim/final_pair_new_starts.py'):
        assert b['source_sha256'][path] == checker.sha(v.previous.ROOT/path)


@pytest.mark.parametrize('fault', ['edited', 'other_issue', 'missing_hash', 'future'])
def test_public_commitment_fails_closed(monkeypatch, tmp_path, fault):
    remote = {'id': 123, 'issue_url': 'https://api.github.com/repos/a/b/issues/219',
              'html_url': 'https://github.com/a/b/issues/219#issuecomment-123',
              'created_at': '2026-01-01T00:00:00Z', 'updated_at': '2026-01-01T00:00:00Z',
              'body': 'V94_PRE_COLLECTION_COMMITMENT '+('a'*64)}
    if fault == 'edited': remote['updated_at'] = '2026-01-02T00:00:00Z'
    if fault == 'other_issue': remote['issue_url'] = remote['issue_url'].replace('219', '218')
    if fault == 'missing_hash': remote['body'] = 'V94_PRE_COLLECTION_COMMITMENT'
    if fault == 'future': remote['created_at'] = remote['updated_at'] = '2999-01-01T00:00:00Z'
    monkeypatch.setattr(checker, 'commitment_hashes', lambda _: {'receipt': 'a'*64})
    monkeypatch.setattr(checker.subprocess, 'check_output', lambda *a, **kw: json.dumps(remote))
    with pytest.raises(ValueError):
        checker.verify_public_commitment(123, tmp_path, {})
