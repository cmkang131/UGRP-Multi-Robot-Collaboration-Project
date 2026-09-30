"""Static registration and fake native lifecycle checks; no Scene/World/render."""
import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from harness.zone_study_contract import digest
from scripts import run_zone_target_checks as runner
from scripts import zone_target_bundle as registry
from sim.workflow_manager import plan

ROOT = Path(__file__).resolve().parents[1]


def test_bundle_freezes_all_new_control_files_config_assets_and_verifies_drift(monkeypatch):
    bundle, sha = registry.verify_bundle()
    assert sha == digest(bundle)
    required = {'harness/zone_target_executor.py', 'harness/zone_target_rgb.py',
                'harness/zone_target_identity.py', 'harness/zone_target_actor.py',
                'scripts/run_zone_target_checks.py', 'scripts/zone_target_host.py',
                'sim/zone_target_scene.py', 'configs/t13_target_checks.json',
                'harness/vision_pose_source.py', 'configs/vision_loc_worker.json',
                'sim/masterpi_scene_v2.xml'}
    assert required <= bundle['sources'].keys()
    for path in required:
        assert bundle['sources'][path] == hashlib.sha256((ROOT/path).read_bytes()).hexdigest()
    assert bundle['verification']['physics'] == 'not_run'
    changed = copy.deepcopy(bundle)
    changed['sources']['harness/zone_target_rgb.py'] = '0'*64
    monkeypatch.setattr(registry, 'candidate_bundle', lambda root: changed)
    with pytest.raises(ValueError, match='bundle/source mismatch'): registry.verify_bundle()


def test_original_s5_setup_events_orders_and_caps_are_preserved_across_conditions():
    cfg = registry.load_config()
    old = json.loads((ROOT/'configs/zone_study_scenarios_v2/s5_moved_dropped_item_v2.json').read_text())
    assert cfg['setup_only'] == old['eval']['setup']
    assert cfg['public_orders'] == old['orders']
    assert cfg['hidden_events'] == old['eval']['hidden_events']
    hashes = set()
    for condition in cfg['conditions']:
        for group, count in [('t13a', 2), ('t13b', 4)]:
            args = runner.parser().parse_args(['--group', group, '--condition', condition])
            selected = runner.selection(cfg, args)
            hashes.add(selected['controller_config_sha256'])
            assert selected['sim_cap_s'] == 900*count and len(selected['cells']) == count
    assert len(hashes) == 1
    for name in cfg['cells']:
        cell, spec, hidden = registry.cell_inputs(cfg, name)
        assert hidden['eval']['hidden_events'][:2] == cfg['hidden_events']
        assert spec['target_placements'][:4] == cfg['setup_only']['placements']
        assert set(spec['pose_priors']) == {'r1', 'r2', 'r3'}
    _, ambiguous, _ = registry.cell_inputs(cfg, 'I2')
    assert len(ambiguous['target_placements']) == 5
    assert len(ambiguous['visual_catalogue']['objects']) == 5


def test_workflow_plan_is_runnable_module_with_explicit_registration(tmp_path):
    p = plan(ROOT, 'zone-target-checks', ['--group', 't13a', '--condition', 'no_comm',
                                          '--output', str(tmp_path/'new')])
    assert p['workflow_version'] == '3.1.0'
    assert 'scripts.run_zone_target_checks' in p['command']
    assert p['runner'] == 'scripts.run_zone_target_checks' and p['execution_started'] is False


def test_setup_box_inventory_restores_all_three_original_cubes_without_native_scene():
    from sim.zone_target_scene import box_inventory
    cfg = registry.load_config()
    result = box_inventory(cfg['setup_only']['placements'])
    assert set(result) == {'cyan_1', 'red_1', 'red_2'}
    assert result['red_2']['position_m'] == [1.6, -2.45, .016]
    assert result['cyan_1']['half_extents_m'] == [.017, .02, .016]


def fake_native(monkeypatch, *, fail_advance=False, fail_close=False):
    from scripts import zone_target_host
    from harness import zone_study_integration, zone_study_referee, zone_target_actor
    from sim import render_profile
    hosts, actors = [], []
    bundle = registry.candidate_bundle()

    class Host:
        def __init__(self, spec, student, **kwargs):
            self.spec, self.hidden = spec, kwargs['hidden']
            self.world = SimpleNamespace(data=SimpleNamespace(time=0.), model=object())
            self.contact_record, self.static = bundle['contact'], {}
            self.eval_only, self.hidden_log = {'max_eq_active': 0}, []
            self.closed = False
            self.robots = {}
            for rid in ('r1', 'r2', 'r3'):
                ex = SimpleNamespace(jobs=SimpleNamespace(claim=lambda oid: {'state': 'unknown'}),
                                     target_log=[], recognizer=SimpleNamespace(log=[]),
                                     pose=SimpleNamespace(provider=SimpleNamespace(record=lambda: {}), timing=[]),
                                     jobs_done=[], _summaries=[])
                self.robots[rid] = SimpleNamespace(executor=ex, commands=[], frames=[],
                                                  cancellations=[], decisions=[], exception=None)
            hosts.append(self)
        def referee_truth(self):
            return {p['item_id']: {'kind': p['kind'], 'x': p['pose_m'][0], 'y': p['pose_m'][1]}
                    for p in self.spec['target_placements']}
        def settle(self, t): self.world.data.time = t; return t
        def advance_to(self, t):
            if fail_advance: raise OSError(28, 'fake ENOSPC')
            self.world.data.time = t
        def close_episode(self, reason):
            if fail_close: raise RuntimeError('fake collection failure')
        def close(self): self.closed = True

    class Actor:
        def __init__(self, executor, **kw): self.actions = []; actors.append(kw)
        def tick(self, t): self.actions.append({'sim_s': t})

    class Referee:
        def __init__(self, *args): pass
        def observe(self, *args): pass
        def record(self): return {'evaluation_only': True}

    monkeypatch.setattr(zone_target_host, 'TargetStudyHost', Host)
    monkeypatch.setattr(zone_target_actor, 'TargetActor', Actor)
    monkeypatch.setattr(zone_study_referee, 'Referee', Referee)
    monkeypatch.setattr(zone_study_integration, 'pose_provider_spec', lambda *a, **kw: {})
    monkeypatch.setattr(render_profile, 'verify_model', lambda *a: {'fake': True})
    return hosts, actors, bundle


def test_fake_run_keeps_900_cap_truth_separate_and_writes_verifiable_artifacts(monkeypatch, tmp_path):
    hosts, actors, bundle = fake_native(monkeypatch)
    out = tmp_path/'run'
    result = runner.execute_cell(registry.load_config(), 'M-U', 'no_comm', out, bundle, digest(bundle))
    assert result['terminal'] == 'CAP' and result['sim_s'] == 900
    assert result['physical_success'] is None and result['llm_calls'] == 0
    assert hosts[0].closed
    assert actors == [{'order_id': 'order-1', 'start_after_s': 70.}]
    public = json.loads((out/'inputs.json').read_text())
    assert not {'events', 'placements', 'focal'} & public.keys()
    assert (out/'eval_only/truth.jsonl').is_file()
    receipts = json.loads((out/'artifacts.sha256.json').read_text())
    for path, receipt in receipts.items():
        assert receipt['sha256'] == hashlib.sha256((out/path).read_bytes()).hexdigest()


@pytest.mark.parametrize('fault', ['advance', 'close'])
def test_fake_host_failures_keep_failure_record_and_close(monkeypatch, tmp_path, fault):
    hosts, actors, bundle = fake_native(monkeypatch, fail_advance=fault == 'advance', fail_close=fault == 'close')
    out = tmp_path/'run'
    result = runner.execute_cell(registry.load_config(), 'D-H', 'no_comm', out, bundle, digest(bundle))
    assert result['terminal'] == 'HOST_ERROR' and result['physical_success'] is None
    assert hosts[0].closed
    assert json.loads((out/'result.json').read_text())['terminal'] == 'HOST_ERROR'
    if fault == 'advance': assert result['error']['errno'] == 28


def test_runner_plan_and_dirty_execution_gate_never_construct_native_host(monkeypatch, capsys, tmp_path):
    import sim.workflow_manager as wm
    monkeypatch.setattr(runner, 'execute_cell', lambda *a: pytest.fail('native path reached'))
    assert runner.main(['--group', 't13a']) == 0
    assert json.loads(capsys.readouterr().out)['physics_run'] is False
    monkeypatch.setattr(wm, 'git_identity', lambda root: {'source_sha': 'a'*40, 'source_dirty': True})
    with pytest.raises(SystemExit, match='clean committed source'):
        runner.main(['--group', 't13a', '--execute', '--expected-source-sha', 'a'*40,
                     '--output', str(tmp_path/'abs')])
