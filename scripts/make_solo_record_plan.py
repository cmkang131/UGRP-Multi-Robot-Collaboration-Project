"""Offline 50-episode record plan. Does not connect to or start any host."""
import argparse
from collections import Counter
import json
import hashlib
import subprocess
from pathlib import Path
from harness.grasp_act_seed_splits import check_range
from harness.grasp_act_solo_recording import camera_config
from scripts.make_solo_teacher_plan import episode
from sim.grasp_act_solo_teacher import BOX_KINDS

SEED0 = 86000
ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = 'experiments/2026-10-14-act-solo-teacher/solo-record-plan.json'


def make_queue(plan, sha):
    runs = []
    approval_path = '/home/ugrp/ugrp-sim/approvals/solo-record-'+sha[:8]+'.json'
    for i, e in enumerate(plan['episodes']):
        name = f"solo-record-{e['seed']}-{sha[:8]}"
        cmd = ['python3', 'scripts/remote_run.py', '--host', 'gcp1', '--detach', '--class', 'dev',
            '--pr', '502', '--per-run-mb', '1024', str(ROOT), name, '--', '.venv-sim/bin/python',
            '-m', 'scripts.run_solo_grasp_act_teacher', '--execution-host', 'gcp1', '--teacher-profile',
            'solo_visible_only_v1', '--held-object-hidden-v1', '--setdown-lookaround-v1',
            '--teacher-stability', 'align_relook_v1', '--reach-mode', 'pad_window_v2',
            '--rgb-lift-mode', 'solo_lift_lookback_v1', '--solo-lift-lookback-margin-v1',
            '--solo-truth-free-lookaround-v1', '--training-rgb', '--recording-stage', e['recording_stage'],
            '--plan', PLAN_PATH, '--episode', str(i), '--cap-s', '90',
            '--out', f'/home/ugrp/ugrp-sim/runs/{name}/raw']
        if i >= 2:
            cmd.extend(['--recording-approval', approval_path])
        runs.append({'stage': e['recording_stage'], 'name': name, 'seed': e['seed'], 'kind': e['kind'],
            'source_sha': sha, 'enabled': False, 'requires_coordinator_approval': i >= 2,
            'depends_on': [f"solo-record-{x['seed']}-{sha[:8]}" for x in plan['episodes'][:2]] if i >= 2 else [],
            'max_parallel': 2 if i < 2 else 6, 'training_include': False, 'gate_eligible': False,
            'command': cmd})
    return {'schema': 'ugrp.grasp_act.solo_record_queue.v1', 'branch': 'claude/act-solo-teacher',
        'pr': 502, 'sha': sha, 'host': 'gcp1', 'machine_type': 'n4-highcpu-64',
        'project': 'ugrp-act-train-1014', 'source_worktree': str(ROOT),
        'runner_cwd': '/Users/changmin/projects/ugrp', 'runner_note': 'Use primary standard GCP remote_run.py; frozen source_worktree snapshot only',
        'status': 'prepared_not_submitted', 'ready': False, 'runs_enabled': False,
        'stage_counts': {'pilot': 2, 'batch': 48}, 'run_count': 50,
        'gate_promotion_authorized_if_all_conditions_pass': False,
        'coordinator_approval': {'approved': False, 'path': approval_path},
        'training_rgb': True, 'weld': 'off', 'kinds': plan['distribution'],
        'camera': plan['camera'], 'plan_sha256': hashlib.sha256((ROOT/PLAN_PATH).read_bytes()).hexdigest(),
        'seed_reservation': {'split': 'train', 'range': [SEED0, SEED0+49],
                             'live_remote_unused_check': 'pending; no remote access in preparation'},
        'storage_budget_mib': {'expected_per_episode': 96, 'expected_total': 4800,
            'reserved_per_episode': 1024, 'reserved_total': 51200,
            'basis': '90 SIM s x10 Hz; JPEG estimate unmeasured; reserve native RGB-equivalent plus logs',
            'raw_location': '/home/ugrp/ugrp-sim/runs/solo-record-<seed>-'+sha[:8]+'/raw',
            'preservation': 'GCP persistent disk only; ARM backup not implemented; no raw retrieval performed'},
        'first_30s_check_command': '.venv-sim/bin/python -m scripts.check_solo_recording <RAW> --out <CHECK.json>',
        'preconditions': [
            'Pushed SHA must match clean source_worktree and each snapshot; confirm live unused seeds before submission.',
            'gcp1 project/instance/machine admission, budget-stop enabled, 8h STOP and 20min idle guard; no bypass or host switch.',
            'Run storage_budget.py --all-hosts with 51200 MiB plus other reserved writes; no remote check done in this preparation.',
            'Pilot two raw recordings only; inspect first 30 SIM seconds: actual sizes, unique frames, 10 Hz, 640x480, K/D/mount, previous issued history alignment.',
            'Inspect >=6 frames through each pilot and commanded versus observed displacement; read full result/eval separately.',
            'Truth-free scan changes teacher behavior: c35e2ff2 40/40 is reference only. Require corrected-source same-machine gate >=38/40 before bulk/data admission.',
            'Bulk 48 requires explicit coordinator approval with corrected gate and two hashed passed pilot checks; never auto-promote.',
            'Pilot concurrency2 and bulk concurrency6 must each pass a same-machine first30 speed gate median wall/SIM <=3.5 before expansion; combined concurrency<=40.',
            'Check endpoint alert state immediately before stage (no LLM used); record load/memory and stop confirmed shared defects.',
            'Retain failure/HOST_ERROR originals; training_include stays false until independent dataset admission; verify manifests and stopped VM after execution.'],
        'runs': runs}


def prepare():
    check_range('train', SEED0, 50)
    kinds = list(BOX_KINDS)*12+list(BOX_KINDS[:2])
    counts, rows = Counter(), []
    for n, kind in enumerate(kinds):
        row = episode(counts[kind], kind, SEED0+n, 'train')
        row.update(pr=502, negative_probe=False, gate_eligible=False, training_eligible=True,
                   recording_stage='pilot' if n < 2 else 'batch', destination='pickup_site')
        rows.append(row)
        counts[kind] += 1
    return {'schema': 'ugrp.grasp_act.solo_record_plan.v1', 'episodes': rows,
        'distribution': dict(counts), 'balance_note': '50 cannot divide equally by 4: 13/13/12/12; bulk 48 is 12 each',
        'camera': camera_config(), 'student_execution': False, 'weld': 'off', 'training_rgb': True,
        'gate_promotion_authorized_if_all_conditions_pass': False}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--queue-out', type=Path)
    a = p.parse_args()
    plan = prepare()
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(plan, indent=2)+'\n')
    if a.queue_out is not None:
        sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
        if subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=no'], cwd=ROOT):
            raise ValueError('commit plan and source before generating a pinned queue')
        q = make_queue(plan, sha)
        a.queue_out.parent.mkdir(parents=True, exist_ok=True)
        with a.queue_out.open('x') as stream:
            stream.write(json.dumps(q, indent=2)+'\n')
    print(json.dumps({'N': len(plan['episodes']), 'kinds': plan['distribution']}))


if __name__ == '__main__':
    main()
