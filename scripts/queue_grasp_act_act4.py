"""Write a non-approved ACT4 operator handoff; never contact/start cloud VMs."""
import argparse
import json
from pathlib import Path
import sys

if str(Path(__file__).resolve().parents[1]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.grasp_act_data import sha256, write_json
from scripts.grasp_act_training_guard import ROOT, source_sha


def build_queue(source):
    base = f'/mnt/act-source/act4-{source[:8]}'
    data = '/mnt/act-source/act-main-f609979c/dataset'
    cpu_model = f'/home/ugrp/act4-models-{source[:8]}/actor'
    py = '/home/ugrp/ugrp-act-env/bin/python'
    def job(stage, command, depends=()):
        return {'stage': stage, 'approved': False, 'enabled': False, 'depends_on': list(depends), 'command': command}
    training = [py, '-m', 'scripts.train_grasp_act', '--dataset', data,
                '--done-loss', 'balanced_bce_v1', '--done-loss-weight', '1']
    jobs = [
        job('saved-baseline-analysis', [py, '-m', 'scripts.analyze_grasp_act_predictions',
            '--predictions', '/mnt/act-source/act-main-f609979c/offline-main/predictions.jsonl',
            '--manifest', data+'/manifest.json', '--output', base+'/baseline-analysis']),
        job('smoke', training+['--output', base+'/smoke', '--stage', 'smoke', '--steps', '300',
                              '--max-wall-s', '1800'], ['saved-baseline-analysis', 'measurement-receipt']),
        job('main', training+['--output', base+'/main', '--stage', 'main', '--steps', '10000',
            '--max-wall-s', '21600', '--resume', base+'/smoke/step-000300',
            '--smoke-summary', base+'/smoke/summary.json', '--approval', base+'/approval-main.json'], ['smoke']),
        job('offline-candidate', [py, '-m', 'scripts.evaluate_grasp_act_offline', '--dataset', data,
            '--model', base+'/main/step-010000/actor', '--output', base+'/offline-candidate'], ['main']),
        job('candidate-analysis', [py, '-m', 'scripts.analyze_grasp_act_predictions',
            '--predictions', base+'/offline-candidate/predictions.jsonl', '--manifest', data+'/manifest.json',
            '--output', base+'/candidate-analysis'], ['offline-candidate']),
    ]
    jobs.append({'stage': 'closed-loop', 'approved': False, 'enabled': False,
        'depends_on': ['candidate-analysis', 'offline-review-receipt', 'fresh-plan-receipt', 'gcp1-speed-receipt'],
        'max_runs': 1, 'cap_sim_s': 90, 'release_followup_seeds_only_after_first_run_review': True,
        'proposed_seed': 91101,
        'inference_options': {'n_action_steps': 1, 'temporal_ensemble_coeff': .01},
        'command': ['.venv-sim/bin/python', '-m', 'scripts.sim_cli', 'workflow', 'run',
            'grasp-act-student-pilot', '--', '--plan', 'experiments/2026-10-15-act-train/closed-loop-main-plans/91101.json',
            '--protocol', 'experiments/2026-10-15-act-train/protocol.json',
            '--model', cpu_model, '--actor-python', '/home/ugrp/ugrp-act-env/bin/python',
            '--output', f'outputs/act4-{source[:8]}-s91101/raw', '--cap-s', '90',
            '--n-action-steps', '1', '--temporal-ensemble-coeff', '.01'],
        'seed_inventory_verified': False,
        'model_transfer': {'source': base+'/main/step-010000/actor', 'destination': cpu_model,
            'full_hash_and_cpu_load_verification_required': True},
        'note': '91101 was unsubmitted in old-model cohort, but operator must recheck unused status/static setup; NEW candidate only, no old-model retry'})
    return {'schema': 'ugrp.vm3_queue.act4.v1', 'approved': False, 'enabled': False,
        'source_sha': source, 'project': 'ugrp-act-train-1014', 'branch': 'claude/act-train', 'pr': 504,
        'remote_execution_started': False, 'gate_promotion_authorized_if_all_conditions_pass': False,
        'status': 'BLOCKED_PENDING_MEASUREMENTS_AND_APPROVAL',
        'source_dataset_manifest_sha256': 'da651587d3cbe51f418f63fda55642b53e985a1fe1551db98909517065ba058b',
        'baseline_model_sha256': '9f5e469439e1ea8bc7ada73dc558b6f5e7aa48edf71cc416b64b9f7b6929576a',
        'machine': {'training_type': 'g2-standard-4', 'gpu': 'NVIDIA L4',
            'simulation_instance': 'ugrp-sim-gcp1', 'simulation_type': 'n4-highcpu-64',
            'reuse_retained_resources_only': True, 'max_run_duration': '8h',
            'instance_termination_action': 'STOP', 'idle_shutdown_s': 1200},
        'budgets': {'training_max_wall_s': 23400, 'simulation_max_wall_s': 1800,
            'minimum_free_training_disk_gib': 40, 'new_checkpoint_budget_gib': 16,
            'new_simulation_raw_budget_gib': 1, 'cost_estimate': 'refresh official price and actual credit balance before approval'},
        'required_before_start': [
            'No authorization inherited from f609979c; every stage requires new explicit approval',
            'Check actual credits, active budget-stop alerts and budget-stop function; never bypass or switch hosts',
            'Every gcloud resource command must include --project=ugrp-act-train-1014',
            'Confirm free disk including other approved jobs; preserve original datasets/checkpoints/runs',
            'Verify clean exact source SHA, pinned LeRobot and full dataset/normalization hashes',
            'measurement-receipt: analyze all 1833 held-out unique timesteps incl. per-skill done score quantiles and lateral/yaw signs',
            'measurement-receipt: count edge/lost-to-recovery intervals on all 50 teacher episodes; distinguish blind terminal segment',
            'measurement-receipt: retrieve only first 30 SIM-second 91100 input RGB refs needed for offline input/output comparison; no physics replay',
            'offline-review-receipt: first-action grasp/release done recall and false positives reviewed at fixed threshold .65, no test-set threshold tuning',
            'gcp1-speed-receipt: measure at planned concurrency 1 with per-tick inference; previous 0.323s/call does not meet 0.1s wall period',
            'If a known defect persists, stop before more runs; preserve all failures and HOST_ERROR'],
        'main_approval_template': {'approved': False, 'stage': 'main', 'source_sha': source,
            'dataset_manifest_sha256': 'da651587d3cbe51f418f63fda55642b53e985a1fe1551db98909517065ba058b',
            'smoke_summary_sha256': None, 'steps': 10000, 'blank_images': False,
            'done_loss': 'balanced_bce_v1', 'done_loss_weight': 1.,
            'gate_promotion_authorized_if_all_conditions_pass': False},
        'jobs': jobs,
        'dart': {'approved': False, 'implemented': False, 'reason': 'full recovery census and residual covariance unavailable; do not invent noise scale or run teacher'},
        'after_each_stage': ['retrieve summary/errors/hash inventory, then verify owned VM TERMINATED',
            'preserve selected/report-used candidate model as new GitHub Release asset; re-download/hash/load before complete',
            'retain raw paths and sha256; do not combine hosts, model variants, or training diagnostics with physical success']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    source = source_sha()
    queue = build_queue(source)
    queue['analysis_summary_sha256'] = sha256(ROOT/'experiments/2026-10-15-act-train/act4-summary.json')
    args.output_dir.mkdir(parents=True, exist_ok=True)
    path = args.output_dir / f'20261015-act4-{source[:8]}.json'
    if path.exists(): raise FileExistsError(path)
    write_json(path, queue)
    print(json.dumps({'path': str(path), 'sha256': sha256(path), 'approved': False, 'source_sha': source}))


if __name__ == '__main__':
    main()
