"""Assigned-side handoff distribution; native checks use only kinematics/rays."""
import json
from pathlib import Path

import pytest

from scripts.make_crate_teacher_plan import prepare
from harness.grasp_act_seed_splits import registry, split_of, check_range

ROOT = Path(__file__).resolve().parents[1]
EXP = ROOT/'experiments/2026-10-14-crate-teacher'


def load(name):
    return json.loads((EXP/name).read_text())


def static_checker(monkeypatch):
    mj = pytest.importorskip('mujoco')
    def forbidden(*args, **kwargs):
        pytest.fail('physics/render called during static start audit')
    for name in ('mj_step', 'mj_step1', 'mj_step2', 'mj_forward', 'Renderer'):
        monkeypatch.setattr(mj, name, forbidden)
    from scripts.audit_crate_start_los import CrateStartLOS
    return CrateStartLOS()


def test_v6_frozen_counts_original_rejection_and_fresh_never_train_seeds():
    plan = load('gate_plan_v6_77200.json')
    audit = plan['start_los_audit']
    assert plan['start_assigned_los'] == 'start_assigned_los_v1'
    assert (audit['minimum_visible_probes'], audit['probe_N']) == (5, 15)
    assert audit['pitches'] == [[820, 2320], [700, 2440], [500, 2500]]
    assert audit['yaw_step_deg'] == 1 and audit['yaw_views_per_pitch'] == 360
    assert audit['accepted']['both_pass'] == audit['accepted']['N'] == 40
    assert audit['original']['both_pass'] == 26
    assert audit['original']['rejected'] == 14 and audit['original']['rejection_rate'] == .35
    assert audit['original']['per_robot']['r1']['rejected'] == 9
    assert audit['original']['per_robot']['r2']['rejected'] == 5
    assert (audit['rejected_los_proposals'], audit['total_los_proposals']) == (30, 70)
    assert audit['mj_step_calls'] == audit['render_calls'] == 0
    assert [e['seed'] for e in plan['episodes']] == list(range(77200, 77240))
    reg = registry()
    assert 'crate_gate_v3' in reg['gate_seeds_never_train']
    check_range('crate_gate_v3', 77200, 40)
    assert all(split_of(e['seed']) == 'crate_gate_v3' for e in plan['episodes'])
    original = prepare(seed=77200, split='crate_gate_v3', scenario_set='v5')
    for before, frozen in zip(original['episodes'], audit['original_starts']):
        for key in ('seed', 'cargo_pose', 'spawns', 'roles', 'initial_pan'):
            assert before[key] == frozen[key]
    # The toggle off keeps the original starts and has no native dependency.
    assert 'start_los_audit' not in original and 'start_assigned_los' not in original
    with pytest.raises(ValueError):
        prepare(start_assigned_los='invalid')


def test_every_frozen_gate_and_six_diagnostics_have_native_los(monkeypatch):
    checker = static_checker(monkeypatch)
    gate = load('gate_plan_v6_77200.json')['episodes']
    reused = load('diag_plan_v5_77920.json')['episodes']
    fresh = load('diag_plan_v6_77930.json')['episodes']
    assert [e['seed'] for e in reused+fresh] == [77920, 77921, 77922, 77930, 77931, 77932]
    assert all(e['seed'] != 77902 for e in gate+reused+fresh)
    for episode in gate+reused+fresh:
        report = checker.check(episode)
        assert report['accepted'], (episode['seed'], report)
        assert report['mj_step_calls'] == report['render_calls'] == 0
        assert episode['roles']['r1'] != episode['roles']['r2']


def test_generated_v6_is_deterministic_and_pins_unfiltered_rejection(monkeypatch):
    static_checker(monkeypatch)
    frozen = load('gate_plan_v6_77200.json')
    actual = prepare(seed=77200, split='crate_gate_v3', scenario_set='v5',
                     start_assigned_los='start_assigned_los_v1')
    for key in ('original', 'accepted', 'rejected_los_proposals', 'total_los_proposals'):
        assert actual['start_los_audit'][key] == frozen['start_los_audit'][key]
    assert actual['rejected_proposals'] == frozen['rejected_proposals']
    # Host-specific XML paths and floating camera coordinates are not a portable
    # fixture. The sampled poses, roles, RNG draws and all counts must match.
    for expected, generated in zip(frozen['episodes'], actual['episodes']):
        for key in ('seed', 'cargo_pose', 'spawns', 'roles', 'initial_pan',
                    'handoff_pose_error', 'proposal_attempts', 'start_los_proposals'):
            assert generated[key] == expected[key]
    first = prepare(count=1, seed=77200, split='crate_gate_v3', scenario_set='v5',
                    start_assigned_los='start_assigned_los_v1')['episodes'][0]
    assert first == actual['episodes'][0]


def test_original_v5_gate_and_relocation_example_remain_rejected(monkeypatch):
    checker = static_checker(monkeypatch)
    rows = [checker.check(e) for e in load('gate_plan_v5_77100.json')['episodes']]
    assert sum(r['accepted'] for r in rows) == 25
    assert sum(all(v['any'] for v in r['robots'].values()) for r in rows) == 30
    episode = next(e for e in load('diag_plan_77900.json')['episodes'] if e['seed'] == 77902)
    report = checker.check(episode, exhaustive=True)
    assert not report['accepted']
    assert max(p['max_seen'] for p in report['robots']['r1']['pitch_results']) == 3
    assert report['robots']['r1']['exhaustive']


def test_start_oracle_is_absent_from_runtime_action_path():
    for name in ('scripts/run_crate_teacher.py', 'sim/crate_grasp_teacher.py',
                 'sim/grasp_act_teacher_v3.py', 'harness/grasp_act_visible_world.py'):
        assert 'audit_crate_start_los' not in (ROOT/name).read_text()
    # Preserve both existing thresholds: start rejection cannot relax exposure.
    assert "v['visible_probes']<5" in (ROOT/'sim/grasp_act_visible_measurements.py').read_text()
    assert "['visible_probes']>=5" in (ROOT/'sim/grasp_act_teacher_v3.py').read_text()
