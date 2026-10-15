"""Replay ACT9 command selection/label exclusion on stored ACT8 gate ledgers.

No simulator, renderer, training, network or counterfactual visibility model.
The stored visibility belongs to ACT8; this replay cannot prove ACT9 recovery.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

from harness.grasp_act_data import read_json, read_rows, sha256, write_json
from harness.grasp_act_perturb import RecoveryPerturb, annotate_label, recovery_statistics
from harness.grasp_act_recovery_gate import verify_gate


def act8_verifier_fixture(source):
    """Exercise real retrieved results; never save an approval receipt."""
    first = read_json(source['runs'][0]['result_file'])
    expected = {k: first[k] for k in ('source_sha','teacher_dependency_sha','noise_sha256')}
    proof = {'approved': True, 'gate_promotion_authorized_if_all_conditions_pass': False,
        **expected, 'fresh_seeds': [r['seed'] for r in source['runs']],
        'seed_inventory_sha256': source['gate_plan']['sha256'],
        'runs': [{'path':r['result_file'],'sha256':r['result_sha256']} for r in source['runs']]}
    with tempfile.TemporaryDirectory(prefix='act9-act8-verifier-fixture-') as folder:
        receipt = Path(folder)/'temporary-test-fixture.json'
        receipt.write_text(json.dumps(proof))
        result = verify_gate(receipt, source=expected['source_sha'],
            dependency=expected['teacher_dependency_sha'], noise_hash=expected['noise_sha256'],
            host=first['execution_host'], recording_seeds=[])
    return {'n':result['n'], 'N':result['N'],
        'scope':'temporary verifier test fixture, not a gate review or recording approval'}


def replay(summary_path, model_path, output):
    summary_path, model_path, output = map(Path, (summary_path, model_path, output))
    output.mkdir(parents=True, exist_ok=False)
    source = read_json(summary_path); model = read_json(model_path)
    verifier_fixture = act8_verifier_fixture(source)
    runs = []
    for entry in source['runs']:
        result_path = Path(entry['result_file'])
        if sha256(result_path) != entry['result_sha256']: raise ValueError('ACT8 result hash mismatch')
        result = read_json(result_path); root = result_path.parent
        ledger_path = root.parent/'recovery-commands.jsonl.zst'
        decoded = subprocess.check_output(['zstd', '-dc', str(ledger_path)])
        if hashlib.sha256(decoded).hexdigest() != result['recovery']['sha256']:
            raise ValueError('ACT8 command ledger hash mismatch')
        commands = [json.loads(line) for line in decoded.splitlines()]
        teachers = read_rows(root/'teacher-commands.jsonl.zst')
        if len(commands) != len(teachers): raise ValueError('ACT8 command/visibility row mismatch')
        probe = RecoveryPerturb(model, seed=entry['seed'])
        generated = []; excluded = 0
        for row, teacher in zip(commands, teachers):
            if row['t'] != teacher['t']: raise ValueError('ACT8 clock mismatch')
            applied, diagnostic = probe.apply(row['clean_teacher_command'],
                phase_before=row['phase_before'], phase_after=row['phase_after'],
                holding=teacher['phase'] not in ('approach','align','relook'),
                visible=teacher['visible_target'] is not None)
            interval = diagnostic is not None
            # A teacher-label proxy exercises the same annotation as the real
            # recorder. There are no native training RGB labels in this gate.
            label = annotate_label({'local_skill_sample': teacher['student_context']['local_skill_sample'],
                'done': False, 'terminal_reason': None, 'clean_teacher_command': row['clean_teacher_command']},
                perturbation_interval=interval)
            if interval and (label['local_skill_sample'] or label['training_target']):
                raise ValueError('perturbation leaked to targets')
            excluded += interval
            generated.append({**row, 'applied_command': applied, 'disturbance': diagnostic,
                'target_visible': teacher['visible_target'] is not None, 'perturbation_interval': interval,
                'teacher_label_proxy': label})
        target = output/f"{entry['run']}-command-replay.jsonl"
        target.write_text(''.join(json.dumps(r, allow_nan=False)+'\n' for r in generated))
        audit = recovery_statistics(generated)
        runs.append({'seed': entry['seed'], 'baseline_run': entry['run'],
            'baseline_result': str(result_path), 'baseline_result_sha256': sha256(result_path),
            'baseline_ledger': str(ledger_path), 'baseline_ledger_sha256': sha256(ledger_path),
            'baseline_visibility': str(root/'teacher-commands.jsonl.zst'),
            'baseline_visibility_sha256': sha256(root/'teacher-commands.jsonl.zst'),
            'replay': str(target), 'replay_sha256': sha256(target),
            'injected_ticks': audit['perturbation_ticks'], 'excluded_proxy_labels': excluded,
            'stored_visibility_recovery_scene_N': audit['recovery_scene_N'],
            'physical_success': None})
    report = {'schema': 'ugrp.act9.saved_ledger_replay.v1', 'baseline_summary': str(summary_path),
        'baseline_summary_sha256': sha256(summary_path), 'noise_sha256': sha256(model_path),
        'runs_N': len(runs), 'injected_runs_N': sum(r['injected_ticks'] > 0 for r in runs),
        'injected_ticks': sum(r['injected_ticks'] for r in runs),
        'excluded_proxy_labels': sum(r['excluded_proxy_labels'] for r in runs),
        'act8_verifier_fixture': verifier_fixture,
        'act9_physical_runs_N': 0, 'training_rgb': False, 'data_admitted': False,
        'scope': 'command-only replay of ACT8 clean decisions and fixed ACT8 visibility; not ACT9 teacher/physical replay',
        'runs': runs}
    write_json(output/'summary.json', report)
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--summary', type=Path, required=True)
    p.add_argument('--noise', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args(); report = replay(a.summary, a.noise, a.output)
    print(json.dumps({k: report[k] for k in ('runs_N','injected_runs_N','injected_ticks',
        'excluded_proxy_labels','act9_physical_runs_N')}))


if __name__ == '__main__': main()
