import ast
import json
from pathlib import Path

import numpy as np
import pytest

from harness.grasp_act_data import write_json
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
