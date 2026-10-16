"""Build a disabled recording handoff; never submit or promote a job."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import shlex

from harness.grasp_act_data import sha256

ROOT = Path(__file__).resolve().parents[1]
RECORD = 'experiments/2026-10-15-act-train'
TEACHER = '1fce11554754d4609470e4fe4b172f9a583bc026'
FLAGS = ('approved', 'enabled', 'ready', 'stage_ready', 'submitted')


def disabled():
    return dict.fromkeys(FLAGS, False)


def build(summary, summary_path, worktree=ROOT):
    if (summary['teacher_source_sha'] != TEACHER or summary['pilot_success'] != 2
            or summary['pilot_N'] != 2 or summary['review_status'] != 'PASS'
            or len(summary['runs']) != 2
            or any(r['audit_status'] != 'PASS' or r['visual_review_status'] != 'PASS'
                   for r in summary['runs'])):
        raise ValueError('two completed inspected ACT11 recording pilots required')
    plan_path = ROOT / RECORD / 'act12-record-plan.json'
    plan = json.loads(plan_path.read_text())
    episodes = plan['episodes']
    if ([e['seed'] for e in episodes] != list(range(86820, 86880))
            or [e['dataset_split'] for e in episodes] != ['train']*45+['validation']*5+['reserve']*10):
        raise ValueError('fixed fresh 45/5 + 10 reserve plan required')
    wrapper = summary['recording_wrapper_source_sha']
    remote = '/home/ugrp/ugrp-sim'
    settings = remote+'/act12rec-1fce1155'
    runs = []
    for index, episode in enumerate(episodes):
        name = f"act12-record-{episode['seed']}-{TEACHER[:8]}"
        args = ['--plan', settings+'/act12-record-plan.json', '--episode', str(index),
                '--dependency-root', '/home/ugrp/ugrp-deps/solo-teacher-6f057f7e',
                '--noise', RECORD+'/act11-noise.json', '--recovery-mode', 'recovery_active_search_v1',
                '--rotation-calibration', 'act8_yaw_gain_v1', '--training-rgb',
                '--gate-receipt', settings+('/pilot-gate-receipt.json' if index < 2 else '/recording-gate-receipt.json'),
                '--cap-s', '90', '--out', remote+'/runs/'+name+'/raw']
        inner = [remote+'/src/'+TEACHER+'/.venv-sim/bin/python',
                 remote+'/src/'+wrapper+'/scripts/run_grasp_act_act12_record.py',
                 '--teacher-source', remote+'/src/'+TEACHER, '--own-review-only-v1', '--', *args]
        command = ['python3', 'scripts/remote_run.py', '--host', 'gcp1', '--detach',
                   '--class', 'dev', '--pr', '504', '--per-run-mb', str(summary['storage']['reserved_per_run_mib']),
                   str(worktree), name, '--', 'bash', '-c',
                   'cd '+shlex.quote(remote+'/src/'+TEACHER)+' && exec '+shlex.join(inner)]
        if index < 2:
            # Preserve the actual executed argv, including its original reservation.
            command = deepcopy(summary['runs'][index]['command'])
        runs.append({**disabled(), 'name': name, 'seed': episode['seed'], 'episode_index': index,
            'dataset_split': episode['dataset_split'], 'source_sha': TEACHER,
            'recording_wrapper_source_sha': wrapper, 'training_rgb': True,
            'command': command, 'training_include': False, 'gate_eligible': False,
            'raw': 'gcp1:'+remote+'/runs/'+name,
            'pilot_evidence': summary['runs'][index]['retrieval_receipt'] if index < 2 else None})
        if index >= 50:
            runs[-1].update(replacement_for_episode_index=None, replacement_split=None)
    return {
        'schema': 'ugrp.vm3_queue.act12_record.v1', **disabled(),
        'status': 'DISABLED_PENDING_INDEPENDENT_RECOUNT_AND_RECORDING_REVIEW',
        'source_sha': TEACHER, 'teacher_source_sha': TEACHER,
        'recording_wrapper_source_sha': wrapper, 'teacher_dependency_sha': summary['teacher_dependency_sha'],
        'branch': 'claude/act-train', 'pr': 504, 'class': 'dev', 'project': 'ugrp-act-train-1014',
        'host': 'gcp1', 'machine_type': 'n4-highcpu-64', 'max_parallel': 16,
        'global_max_parallel': 40, 'pilot_max_parallel': 4,
        'training_rgb': True, 'top_camera': False, 'weld': 'off',
        'remote_execution_started': False, 'training_include': False,
        'gate_promotion_authorized_if_all_conditions_pass': False, 'automatic_promotion': False,
        'coordinator_approval': disabled(), 'independent_recount_approved': False,
        'gate_report': deepcopy(summary['gate_report']),
        'pilot_only_gate_receipt': deepcopy(summary['pilot_gate_receipt']),
        'bulk_gate_receipt': {'path': settings+'/recording-gate-receipt.json', 'sha256': None, 'approved': False},
        'plan': {'path': str(plan_path), 'remote': settings+'/act12-record-plan.json', 'sha256': sha256(plan_path)},
        'noise': {'path': RECORD+'/act11-noise.json', 'sha256': plan['noise_sha256']},
        'recovery_mode': 'recovery_active_search_v1', 'rotation_calibration': 'act8_yaw_gain_v1',
        'yaw_gain': .6790684337506349, 'camera': deepcopy(summary['runs'][0]['camera']),
        'pilot_summary': {'path': str(summary_path), 'sha256': sha256(summary_path)},
        'jobs': [
            {**disabled(), 'stage': 'pilot2', 'max_parallel': 4, 'training_rgb': True,
             'instruction': 'reuse the two inspected results; do not resubmit them', 'runs': runs[:2]},
            {**disabled(), 'stage': 'remaining48', 'max_parallel': 16, 'training_rgb': True,
             'depends_on': ['independent-recount', 'pilot2-review', 'bulk-gate-receipt', 'live-preflight'], 'runs': runs[2:50]},
            {**disabled(), 'stage': 'reserve10', 'max_parallel': 16, 'training_rgb': True,
             'instruction': 'ascending seed order, replace failed slots in original slot order; inherit failed split; stop at 45 train + 5 validation successes', 'runs': runs[50:]},
        ],
        'data_admission': {'target_success_episodes': 50, 'train_success_target': 45, 'validation_success_target': 5,
            'attempted': None, 'successful': None, 'failed_excluded': None,
            'successful_recovery_episodes': None, 'minimum_successful_recovery_episodes': 20,
            'failure_rule': 'exclude failed/HOST_ERROR rows from learning, retain every attempt and denominator; a confirmed defect stops affected work before any reserve is used',
            'recovery_definition': 'successful run with >=1 hash-verified probe-attributed lost -> reacquired episode',
            'previous_results_pooling': False, 'cross_host_pooling': False, 'cross_rotation_pooling': False},
        'storage': deepcopy(summary['storage']),
        'training_draft_untouched': '20261015-act-train-ready-9dc44d90.json',
        'training_fields_after_recording': ['data.path', 'data.manifest_sha256', 'data.gate_receipt',
            'data.recovery_episode_count', 'required_gate.source_sha', 'required_gate.noise_sha256',
            'required_gate.recovery_mode', 'required_gate.recovery_coverage_receipt',
            'recording review / complete file hashes / train-only normalization / 45+5 split receipts'],
        'gpu_path_reference_only': RECORD+'/actgpu1.md',
        'required_before_activation': [
            'Independent ACT11 recount and explicit bulk receipt; pilot-only receipt never authorizes remaining48.',
            'Keep exact ACT11+solo source/noise/recovery/rotation/camera; verify wrapper and review-policy hashes. No previous-result pooling.',
            'Under shared admission lock count all live jobs and reservations: <=40 globally; <=16 batch; <=4 owned pilots.',
            'Project ugrp-act-train-1014 only; existing VM only; verify 8h STOP and idle20m, budget-stop ACTIVE and not triggered. Trigger => no new work or host switch.',
            'Recheck free disk minus every approved remaining write and reservations, with GCP floor8GiB / Mac floor20GiB; no credentials on VM.',
            'Raw data remains on GCP persistent disk. Mac fetch-lite plus selected own frames only; no top input or review.',
            'Inspect first30 and >=6 frames; record camera/frame/rate/bytes/student whitelist/input audit 0/0 for every run.',
            'Successful recovery episodes >=20 and 45train+5validation; failure/HOST_ERROR stays in denominator and outside training.',
            'Training/GPU start is outside this recording queue; reuse ACTGPU1 documentation only.',
        ],
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pilot-summary', type=Path, required=True)
    p.add_argument('--output-dir', type=Path, required=True)
    a = p.parse_args()
    summary = json.loads(a.pilot_summary.read_text())
    q = build(summary, a.pilot_summary)
    a.output_dir.mkdir(parents=True, exist_ok=True)
    path = a.output_dir / f"20261015-act12-record-{q['recording_wrapper_source_sha'][:8]}.json"
    with path.open('x') as f:
        f.write(json.dumps(q, indent=2, allow_nan=False)+'\n')
    print(json.dumps({'path': str(path), 'sha256': sha256(path), 'ready': False}))


if __name__ == '__main__':
    main()
