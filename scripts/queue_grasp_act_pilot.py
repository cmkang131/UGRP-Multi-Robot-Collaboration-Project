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


def build_main_eval_queue(sha, pricing):
    """Coordinator-approved, one RGB main fit; existing blank control stays off."""
    q = build_queue(sha, pricing)
    run = '/mnt/act-source/act-main-' + sha[:8]
    old_run = '/mnt/act-source/act-pilot1'
    protocol = 'experiments/2026-10-15-act-train/protocol.json'
    q.update(status='approved_main_eval_pending_worker_preflight',
        purpose='solo-only training/closed-loop plumbing pilot; not final model or gate promotion',
        prior_smoke={'source_sha': '7caf99447c5d7543b087722957d4d9987c22cbee',
            'report': '/Users/changmin/projects/ugrp/outputs/e2e18-admin/gcp-reports/act-smoke-7caf9944.json',
            'evidence_scope': 'operations worker/coordinator report; no independent remote verification',
            'resume_allowed': False, 'reason': 'source, labels, manifest and normalization changed'},
        coordinator_approval={'approved': True, 'stage': 'main+eval', 'steps': 10000,
            'source_sha': sha, 'blank_images': False, 'main_training_runs': 1,
            'basis': '2026-10-15 user relayed coordinator approval for solo-only main and evaluation',
            'gate_promotion_authorized_if_all_conditions_pass': False})
    q['machine'].update(reuse_existing=True, expected_state_before_start='TERMINATED',
        operation='restart existing instance only; no create, clone, snapshot or disk replacement',
        state_evidence='user/coordinator report; worker must verify current state',
        boot_disk_gib=100, data_disk_gib=0,
        data_disk_source='existing 100 GB boot disk with source recordings and old smoke preserved')
    q['preflight_required'] = [
        'Verify existing ugrp-act-l4-pilot1 is TERMINATED with its original disk/data; restart it only after budget/credit checks',
        'Confirm project ugrp-act-train-1014 and remaining credit; no budget-stop activation; stop/report on activation, no bypass or host switch',
        'Verify budget-stop, max-run-duration=8h STOP and this SHA idle guard (1200s); no billing changes, keys or service-account changes',
        'Verify current official regional VM/disk/network prices; stored pricing is historical estimate, credit balance is unverified',
        'Keep all 50 recordings, prior datasets/checkpoints and raw reports; >=40 GiB free before conversion; stop on insufficient space',
        'Verify GCS archive sha256 2917caf7ff8c8c4a429a5b840ac2223c6d4c784eaa95e0e99a11267ea64b00f8 and all source files; only documented RUN_META milestone-update exceptions allowed',
        'Reuse Python 3.12 environment with requirements-reference-act.txt pinned upstream; no credentials or model keys on VM',
        'Clean checkout at source_sha; fresh output root; do not resume 7caf9944 weights or use its old normalization',
        'After every stage retrieve strict JSON summaries/raw hashes, stop owned VM(s), and verify TERMINATED; restart same VM for next stage']
    q['transfer'] = {
        'method': 'reuse already extracted, verified recordings on retained pilot1 disk; no new snapshot',
        'restored_runs_root': '/mnt/act-source/home/ugrp/ugrp-sim/runs',
        'fallback_archive': 'gs://ugrp-act-train-1014-runs/solo-record-6f057f7e/solo-record-6f057f7e-milestone.tar',
        'archive_sha256': '2917caf7ff8c8c4a429a5b840ac2223c6d4c784eaa95e0e99a11267ea64b00f8',
        'verified_transfer': False, 'credentials_copied': False,
        'gcloud_project_flag_required': '--project=' + PROJECT}
    for job in q['jobs']:
        if 'command' in job:
            job['command'] = [x.replace(old_run, run) for x in job['command']]
    jobs = {j['stage']: j for j in q['jobs']}
    jobs['convert']['required_receipt'] = {'done_label': 'last_local_row_v1', 'episodes': 50,
        'split': {'train': 45, 'validation': 5}, 'skill_episodes': {'grasp': 50, 'release': 50},
        'skill_done': {'grasp': 50, 'release': 50},
        'skill_missing_done_episodes': {'grasp': 0, 'release': 0}, 'input_audit': [0, 0],
        'per_episode_done_required': {'grasp': 1, 'release': 1},
        'instruction': 'Inspect manifest skill_counts/done_counts/missing_done_skills for all 50 episodes; stop before smoke on any mismatch'}
    jobs['main'].update(enabled=True, depends_on=['convert', 'smoke', 'offline-smoke'],
        approval_materialization={'path': run + '/approvals/main.json',
            'authorized_by': 'coordinator_approval; no further approval required within these bounds',
            'template': {'approved': True, 'stage': 'main', 'source_sha': sha,
                'dataset_manifest_sha256': None, 'smoke_summary_sha256': None,
                'steps': 10000, 'blank_images': False,
                'gate_promotion_authorized_if_all_conditions_pass': False},
            'fill_hashes_from': [run + '/dataset/manifest.json', run + '/smoke/summary.json'],
            'instruction': 'Fill exact hashes only after matching new-source convert/smoke receipts pass; authorize_main validates them'},
        hyperparameters={'optimizer': 'AdamW', 'lr': 1e-5, 'backbone_lr': 1e-5,
            'weight_decay': 1e-4, 'batch_size': 8, 'grad_norm_clip': 1., 'kl_weight': 10.,
            'chunk_size': 8, 'n_action_steps': 8, 'temporal_ensemble_coeff': None,
            'backbone': 'ResNet18 ImageNet1K V1, fine tuned',
            'initialization': 'fresh matching smoke 300 steps, then resume to total 10000 (not 10300)',
            'selection': 'fixed final step; heldout never selects checkpoint',
            'research_basis': 'experiments/2026-10-15-act-train/pilot1.md#참고-자료와-선택'})
    jobs['blank-image-control'].update(enabled=False,
        instruction='Existing plan stays disabled; no blank training authorized in this one-RGB-main pilot; required before later data expansion')
    offline = {'stage': 'offline-main', 'enabled': True, 'depends_on': ['main'],
        'command': jobs['offline-smoke']['command'].copy(), 'validation_seeds': list(range(86045, 86050)),
        'report_required': ['action MAE before/after decoding by seed/skill/task',
            'done TP/FP/FN, positive/predicted/negative denominators, precision and recall (null if denominator=0)',
            'first_action unique rows separate from overlapping all_horizons; no physical success claim',
            'checkpoint full inventory sha256, fixed step10000 and successful weight reload']}
    offline['command'] = [x.replace('/smoke/step-000300/', '/main/step-010000/').replace('/offline-smoke', '/offline-main')
                          for x in offline['command']]
    closed = jobs['closed-loop']
    closed.update(enabled=True, depends_on=['offline-main'], seeds=list(range(91100, 91110)),
        skill='grasp_release', object_kind_counts={'cyan': 3, 'red': 3, 'green': 2, 'yellow': 2},
        balance_note='10 is not divisible by four; counts differ by at most one',
        seed_inventory_verified=False,
        operator_preflight=['Check all simulation/teacher/train/validation seed inventories; these 10 are proposed unused reservations only',
            'Validate each plan static spawn/obstacle/cargo collision; stop and return replacement seed/plan inventory if occupied',
            'Use this exact SHA on gcp1; no main merge or scenario/physics replacement during cohort',
            'First seed: inspect first 30 SIM seconds inputs/commands and CPU inference; measure max_parallel=1 speed before remaining seeds',
            'Use machine-specific measured speed gate; Azure numbers are not applicable',
            'Review at least six evenly spaced frames per run (and >=1/60 SIM seconds); identify actual control/physical defect before attribution; stop affected queued/running jobs immediately on confirmed defect'],
        inference={'method': 'copy step-010000/actor to gcp1, isolated local CPU worker over stdin/stdout',
            'verify': 'copy config.json, adapter.json, model.safetensors, SHA256.json; verify full inventory hashes and CPU model load before runs',
            'environment': 'reuse/pin requirements-reference-act.txt on gcp1; no GPU inference service or cross-VM RPC',
            'latency': 'record n, median and p95 wall seconds per chunk; include CPU in wall/SIM measurement'},
        success='physical_success: stable grasp/lift then stable setdown at pickup_site, weld off; truth is scoring only',
        success_criteria={'lift': '>=12mm clearance, <=10deg tilt, each finger >=0.5N for 3 SIM seconds',
            'release': '-5..6mm clearance, <=10deg tilt, each finger <0.1N, linear speed <=0.02m/s for 3 SIM seconds after release instruction; observed airborne unloaded drop is a latched failure'},
        transition='student grasp done -> fixed 3.1 SIM seconds -> ACT release instruction -> student release done -> fixed 3.1 SIM seconds; no truth/teacher correction',
        report_required=['all 10 starts including failures/HOST_ERROR; overall and per-kind n/N',
            'failure_reason counts and HOST_ERROR separately; physical success distinct from model done',
            'input audit forbidden/teacher=0/0 for all runs; requests and raw inputs/commands/eval-only hashes',
            'retrieval status, actual frames/timestamps reviewed, per-run inference latency, wall/SIM; sampled drop detector is not proof of no drop: review video, record any missed drop as failure',
            'stop owned gcp1 and training VM; verify both TERMINATED after evaluation'])
    closed['command_template'] = ['90' if x == '60' else x.replace('closed-loop-plans/', 'closed-loop-main-plans/')
                                  for x in closed['command_template']]
    q['jobs'] = [jobs[k] for k in ('convert', 'smoke', 'offline-smoke', 'main', 'blank-image-control')] + [offline, closed]
    q['after_each_stage'] = [
        'Use harness.grasp_act_data.write_summary (nonfinite report metrics -> null) for every report; retain all failures/HOST_ERROR with raw locations and sha256',
        'Retrieve summaries, checkpoint inventories and raw hashes before complete reporting; do not mark unretrieved artifacts complete',
        'Stop owned VM after every stage, verify TERMINATED, record name/state/time; restart the same retained VM only for its next stage',
        'Preserve selected and reported comparison/failure checkpoints as new GitHub Release assets per docs/model_artifacts.md; redownload/hash/load verification required; no gate promotion']
    return q


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output-dir', type=Path, required=True)
    p.add_argument('--mode', choices=('prepare', 'main-eval'), default='prepare')
    a = p.parse_args()
    sha = source_sha()
    pricing = json.loads((ROOT / 'experiments/2026-10-15-act-train/pricing.json').read_text())
    queue = (build_main_eval_queue if a.mode == 'main-eval' else build_queue)(sha, pricing)
    queue['protocol_sha256'] = sha256(ROOT / 'experiments/2026-10-15-act-train/protocol.json')
    path = a.output_dir / f'20261015-act-train-{sha[:8]}.json'
    if path.exists():
        raise FileExistsError(path)
    a.output_dir.mkdir(parents=True, exist_ok=True)
    write_json(path, queue)
    print(json.dumps({'path': str(path), 'sha256': sha256(path), 'source_sha': sha}))


if __name__ == '__main__':
    main()
