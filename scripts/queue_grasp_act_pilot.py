"""Write a source-pinned operations request; never executes remote/cloud actions."""
import argparse
import json
from pathlib import Path

import sys

if str(Path(__file__).resolve().parents[1]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.grasp_act_data import sha256, write_json
from scripts.grasp_act_training_guard import PROJECT, ROOT, source_sha


def build_queue(sha, pricing):
    run = '/mnt/act-source/act-pilot1'
    protocol = 'experiments/2026-10-15-act-train/protocol.json'
    python = '/home/ugrp/ugrp-act-env/bin/python'
    return {'schema': 'ugrp.act_training.queue.v1', 'source_sha': sha,
        'branch': 'claude/act-train', 'project': PROJECT,
        'status': 'prepared_for_worker_preflight', 'remote_execution_started': False,
        'gate_promotion_authorized_if_all_conditions_pass': False,
        'record': 'experiments/2026-10-15-act-train/pilot1.md',
        'machine': {'name': 'ugrp-act-l4-pilot1', 'machine_type': 'g2-standard-4',
            'zone': 'asia-northeast3-a', 'gpu': '1 x NVIDIA L4 24 GiB',
            'boot_disk_gib': 60, 'boot_disk_type': 'pd-balanced',
            'data_disk_gib': 250, 'data_disk_type': 'pd-balanced',
            'data_disk_source': 'snapshot clone of gcp1 disk; original disk retained',
            'max_run_duration': '8h', 'instance_termination_action': 'STOP',
            'idle_shutdown_s': 1200, 'no_service_account': True, 'no_scopes': True,
            'model_keys_on_vm': False, 'budget_stop': 'keep existing; no billing changes',
            'pricing': pricing},
        'preflight_required': [
            'Confirm project ugrp-act-train-1014, current credit remaining, no budget-stop activation; never bypass or switch host on activation',
            'Verify existing budget-stop subscription/function and 8h STOP; install this SHA idle guard, verify timer and idle 1200s; do not alter billing',
            'Verify L4 quota/zone availability and official current regional VM/disk/snapshot/network prices; recorded price is an estimate, not remaining credits',
            'Record exact gcp1 source disk name and snapshot/clone resource IDs; no snapshot of active writes; do not delete originals',
            'Verify 50/50 completed source runs and source SHA; hash every transferred file against source SHA256SUMS before conversion',
            'Training disk >=40 GiB free after clone; account for snapshot and stopped disk costs; no raw deletion',
            'Python 3.12 + requirements-reference-act.txt pinned SHA; publicly downloaded pretrained ResNet18, no model/account keys',
            'Keep source clean and fixed at source_sha; run only smoke before coordinator approval'],
        'transfer': {'method': 'GCP snapshot and restored persistent disk, within project only',
            'source_instance': 'ugrp-sim-gcp1', 'source_zone': 'asia-northeast3-a',
            'source_runs': '/home/ugrp/ugrp-sim/runs/solo-record-860{00..49}-6f057f7e',
            'restored_disk_mount': '/mnt/act-source',
            'restored_runs_root': '/mnt/act-source/home/ugrp/ugrp-sim/runs',
            'gcloud_project_flag_required': '--project=' + PROJECT,
            'source_disk_name': None, 'snapshot_name': None,
            'verified_transfer': False, 'credentials_copied': False},
        'jobs': [
            {'stage': 'convert', 'enabled': True, 'requires_preflight': True,
             'command': [python, '-m', 'scripts.prepare_grasp_act_data', '--runs-root',
                 '/mnt/act-source/home/ugrp/ugrp-sim/runs', '--protocol', protocol, '--output', run + '/dataset']},
            {'stage': 'smoke', 'enabled': True, 'requires_preflight': True, 'depends_on': ['convert'],
             'command': [python, '-m', 'scripts.train_grasp_act', '--dataset', run + '/dataset',
                 '--output', run + '/smoke', '--stage', 'smoke', '--steps', '300', '--max-wall-s', '1800']},
            {'stage': 'offline-smoke', 'enabled': True, 'depends_on': ['smoke'],
             'command': [python, '-m', 'scripts.evaluate_grasp_act_offline', '--dataset', run + '/dataset',
                 '--model', run + '/smoke/step-000300/actor', '--output', run + '/offline-smoke']},
            {'stage': 'main', 'enabled': False, 'requires_coordinator_approval': True,
             'depends_on': ['smoke', 'offline-smoke'],
             'command': [python, '-m', 'scripts.train_grasp_act', '--dataset', run + '/dataset',
                 '--output', run + '/main', '--stage', 'main', '--steps', '10000', '--max-wall-s', '21600',
                 '--resume', run + '/smoke/step-000300', '--smoke-summary', run + '/smoke/summary.json',
                 '--approval', run + '/approvals/main.json']},
            {'stage': 'blank-image-control', 'enabled': False, 'requires_coordinator_approval': True,
             'instruction': 'Separate fresh blank smoke then equal-step approved main with --blank-images; do not resume RGB checkpoint'},
            {'stage': 'closed-loop', 'enabled': False, 'requires_coordinator_approval': True,
             'host': 'gcp1', 'machine_type': 'n4-highcpu-64', 'max_parallel': 1,
             'seeds': list(range(91050, 91070)), 'input_audit_required': [0, 0],
             'first_30_sim_s_review_required': True, 'unused_seed_and_static_collision_check_required': True,
             'command_template': ['.venv-sim/bin/python', '-m', 'scripts.sim_cli', 'workflow', 'run',
                 'grasp-act-student-pilot', '--', '--plan', 'experiments/2026-10-15-act-train/closed-loop-plans/{seed}.json',
                 '--protocol', protocol, '--model', '{verified_actor_dir_on_gcp1}',
                 '--actor-python', '{pinned_act_python_on_gcp1}', '--cap-s', '60', '--output', '{fresh_run_dir}']}
        ],
        'after_each_stage': ['Write JSON summary including failures/HOST_ERROR and artifact sha256; retrieve and verify before reporting complete',
            'Stop this VM after smoke and await approval; verify TERMINATED; do not keep GPU running during review',
            'After approved final/control results, preserve selected and comparison checkpoints as versioned GitHub Release assets per docs/model_artifacts.md; redownload/hash/load verification required'],
        'main_approval_fields': ['approved=true', 'stage=main', 'source_sha', 'dataset_manifest_sha256',
            'smoke_summary_sha256', 'steps=10000', 'blank_images', 'gate_promotion_authorized_if_all_conditions_pass=false']}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output-dir', type=Path, required=True)
    a = p.parse_args()
    sha = source_sha()
    pricing = json.loads((ROOT / 'experiments/2026-10-15-act-train/pricing.json').read_text())
    queue = build_queue(sha, pricing)
    queue['protocol_sha256'] = sha256(ROOT / 'experiments/2026-10-15-act-train/protocol.json')
    path = a.output_dir / f'20261015-act-train-{sha[:8]}.json'
    if path.exists():
        raise FileExistsError(path)
    a.output_dir.mkdir(parents=True, exist_ok=True)
    write_json(path, queue)
    print(json.dumps({'path': str(path), 'sha256': sha256(path), 'source_sha': sha}))


if __name__ == '__main__':
    main()
