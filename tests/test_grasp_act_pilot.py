import ast
import json
from pathlib import Path

import numpy as np
import pytest

from harness.grasp_act_data import write_json, write_summary
from scripts.evaluate_grasp_act_offline import action_metrics
from scripts.grasp_act_training_guard import authorize_main, require_gcp
from scripts.run_grasp_act_student import validate_plan

ROOT = Path(__file__).resolve().parents[1]


def test_mac_guard_precedes_training_or_physics(monkeypatch):
    monkeypatch.setattr('scripts.grasp_act_training_guard.platform.system', lambda: 'Darwin')
    for training in (True, False):
        with pytest.raises(RuntimeError, match='forbidden'):
            require_gcp(training=training)


def test_main_requires_exact_coordinator_approval(tmp_path):
    kwargs = dict(source='source', dataset_hash='data', smoke_hash='smoke', steps=10000, blank=False)
    with pytest.raises(ValueError, match='coordinator approval'):
        authorize_main(None, **kwargs)
    p = tmp_path / 'approval.json'
    d = {'approved': True, 'stage': 'main', 'source_sha': 'source',
         'dataset_manifest_sha256': 'data', 'smoke_summary_sha256': 'smoke', 'steps': 10000,
         'blank_images': False, 'gate_promotion_authorized_if_all_conditions_pass': False}
    write_json(p, d); authorize_main(p, **kwargs)
    d['gate_promotion_authorized_if_all_conditions_pass'] = True; write_json(p, d)
    with pytest.raises(ValueError):
        authorize_main(p, **kwargs)


def test_metrics_padding_and_missing_completion_denominator():
    target = np.zeros((1, 8, 14))
    prediction = target.copy(); prediction[0, 0, 8] = .1
    pad = np.ones((1, 8), bool); pad[0, 0] = False
    prediction[0, 1:] = 999.
    m = action_metrics(prediction, target, pad)
    assert m['valid_actions'] == 1 and m['done_positive_N'] == 0
    assert m['pwm_mae'] == pytest.approx(20.)
    assert m['done_precision'] is None and m['done_recall'] is None


def test_summary_nulls_nested_nonfinite_metrics_without_relaxing_contracts(tmp_path):
    value = {'metrics': [float('nan'), {'bounds': (float('inf'), -float('inf'))}],
             'numpy': np.array([1.25, np.nan]), 'scalar': np.float32(np.inf),
             'ok': True, 'text': 'NaN/Infinity are literal text', 'absent': None}
    path = tmp_path / 'summary.json'
    write_summary(path, value)
    def reject(token):
        pytest.fail('nonstandard JSON token: ' + token)
    parsed = json.loads(path.read_text(), parse_constant=reject)
    assert parsed == {'metrics': [None, {'bounds': [None, None]}], 'numpy': [1.25, None],
                      'scalar': None, 'ok': True, 'text': value['text'], 'absent': None}
    assert np.isnan(value['metrics'][0]) and np.isinf(value['scalar'])
    with pytest.raises(ValueError):
        write_json(path, {'input': float('nan')})
    assert json.loads(path.read_text()) == parsed  # failed strict write is atomic


def test_done_precision_recall_denominators_exclude_padding():
    y = np.zeros((1, 8, 14)); p = y.copy()
    y[0, :2, -1] = 1.
    p[0, [0, 2], -1] = .7
    pad = np.zeros((1, 8), bool); pad[0, 4:] = True
    p[0, 4:] = 999.
    m = action_metrics(p, y, pad)
    assert m['valid_actions'] == 4 and m['done_positive_N'] == 2
    assert m['done_true_positive_n'] == 1 and m['done_false_positive_n'] == 1
    assert m['done_missed_n'] == 1 and m['done_predicted_positive_N'] == 2
    assert m['done_precision'] == .5 and m['done_recall'] == .5


def test_eval_fresh_seeds_and_nearfield_only():
    p = {'seed': 91050, 'skill': 'grasp', 'object_kind': 'cyan', 'role': 'west', 'robot_id': 'r1',
         'target_setup_xy': [0., 0.], 'spawns': {'r1': [-.55, 0., .03, 0.]}}
    protocol = {'closed_loop_seeds': [91050], 'train_seeds': [86000], 'validation_seeds': [86045]}
    validate_plan(p, protocol)
    protocol['train_seeds'].append(91050)
    with pytest.raises(ValueError, match='leak'):
        validate_plan(p, protocol)


def test_student_worker_has_no_teacher_or_simulator_import():
    for name in ('scripts/grasp_act_student_worker.py', 'harness/grasp_act_policy.py',
                 'harness/grasp_act_contract.py'):
        tree = ast.parse((ROOT / name).read_text())
        imported = []
        for n in ast.walk(tree):
            if isinstance(n, ast.ImportFrom):
                imported.append(n.module or '')
            if isinstance(n, ast.Import):
                imported.extend(a.name for a in n.names)
        assert not any(x.startswith('sim') or 'teacher' in x or 'mujoco' in x for x in imported)


def test_checked_in_protocol_has_no_promotion():
    p = json.loads((ROOT / 'experiments/2026-10-15-act-train/protocol.json').read_text())
    assert p['done_label'] == 'last_local_row_v1'
    assert p['train_seeds'] == list(range(86000, 86045))
    assert p['validation_seeds'] == list(range(86045, 86050))
    assert not p['gate_promotion_authorized_if_all_conditions_pass']
    assert not set(p['closed_loop_seeds']) & set(p['train_seeds'] + p['validation_seeds'])
    from scripts.queue_grasp_act_pilot import build_queue
    q = build_queue('a' * 40, {})
    assert not q['gate_promotion_authorized_if_all_conditions_pass']
    assert q['project'] == 'ugrp-act-train-1014'
    assert q['machine']['max_run_duration'] == '8h'
    assert q['machine']['idle_shutdown_s'] == 1200
    assert not next(j for j in q['jobs'] if j['stage'] == 'main')['enabled']
    assert not next(j for j in q['jobs'] if j['stage'] == 'closed-loop')['enabled']


def test_approved_main_eval_queue_reuses_vm_and_matches_fresh_sources():
    from scripts.queue_grasp_act_pilot import build_main_eval_queue
    q = build_main_eval_queue('b' * 40, {})
    assert q['coordinator_approval']['approved']
    assert q['coordinator_approval']['stage'] == 'main+eval'
    assert q['coordinator_approval']['steps'] == 10000
    assert not q['gate_promotion_authorized_if_all_conditions_pass']
    assert not q['remote_execution_started']
    assert q['machine']['reuse_existing'] and q['machine']['expected_state_before_start'] == 'TERMINATED'
    jobs = {j['stage']: j for j in q['jobs']}
    assert not jobs['blank-image-control']['enabled']
    for name in ('convert', 'smoke', 'offline-smoke', 'main', 'offline-main', 'closed-loop'):
        assert jobs[name]['enabled']
    assert jobs['convert']['required_receipt']['skill_done'] == {'grasp': 50, 'release': 50}
    main = jobs['main']['command']
    assert main[main.index('--steps') + 1] == '10000'
    assert main[main.index('--resume') + 1] == '/mnt/act-source/act-main-bbbbbbbb/smoke/step-000300'
    template = jobs['main']['approval_materialization']['template']
    assert template['stage'] == 'main' and template['source_sha'] == 'b' * 40
    assert template['dataset_manifest_sha256'] is None and template['smoke_summary_sha256'] is None
    offline = jobs['offline-main']['command']
    assert offline[offline.index('--model') + 1].endswith('/main/step-010000/actor')
    closed = jobs['closed-loop']
    assert 'command' not in closed and closed['command_template']
    assert closed['depends_on'] == ['offline-main'] and len(closed['seeds']) == 10
    assert sum(closed['object_kind_counts'].values()) == 10 and not closed['seed_inventory_verified']
    protocol = json.loads((ROOT / 'experiments/2026-10-15-act-train/protocol.json').read_text())
    assert closed['seeds'] == protocol['closed_loop_seeds']
    counts = {}
    for seed in closed['seeds']:
        plan = json.loads((ROOT / f'experiments/2026-10-15-act-train/closed-loop-main-plans/{seed}.json').read_text())
        validate_plan(plan, protocol)
        assert plan['skill'] == 'grasp_release'
        scene = ROOT / f'configs/zone_study_scenarios_v4/{plan["scenario_id"]}.json'
        from harness.grasp_act_data import sha256
        assert sha256(scene) == plan['setup_source_sha256']
        obj = next(x for x in json.loads(scene.read_text())['eval']['setup']['placements'] if x['item_id'] == plan['item_id'])
        assert obj['kind'] == plan['object_kind'] and obj['pose_m'][:2] == plan['target_setup_xy']
        counts[obj['kind']] = counts.get(obj['kind'], 0) + 1
    assert counts == closed['object_kind_counts']
