"""Combine ACT4 and ACT5 comparison in an unapproved local operator queue."""
import argparse
import copy
import json
from pathlib import Path
import sys

if str(Path(__file__).resolve().parents[1]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.grasp_act_data import sha256, write_json
from scripts.grasp_act_training_guard import ROOT, source_sha
from scripts.queue_grasp_act_act4 import build_queue as act4_queue


def build_queue(source):
    queue = act4_queue(source)
    original = queue.pop('jobs')
    old_base = f'/mnt/act-source/act4-{source[:8]}'
    base = f'/mnt/act-source/act5-{source[:8]}'
    queue.update(schema='ugrp.vm3_queue.act5.v1',
        status='BLOCKED_PENDING_FULL_HELDOUT_MEMORY_MEASUREMENTS_AND_APPROVAL',
        combines_act4=True, replaces_unstarted_act4_only_after_operator_approval=True,
        prior_queue='20261015-act4-40a21045.json',
        candidate={'command_history_dropout': .2, 'default': 0.,
            'fill': 'normalized zero = training mean, all 16x14 issued history fields',
            'inference': 'full real issued history; no dropout',
            'selection_basis': '11.2s mean-history intervention is influential; late raw-zero effect is OOD, global copycat not established',
            'probability_status': 'exploratory design value, not measured optimum'},
        deferred_candidates={'explicit_target_memory': 'not implemented: target remains partly visible in most 91100 frames',
            'full_resolution_current': 'not implemented: 320x240 loss of useful position information unproven'})
    py = '/home/ugrp/ugrp-act-env/bin/python'
    data = '/mnt/act-source/act-main-f609979c/dataset'
    baseline_model = '/mnt/act-source/act-main-f609979c/main/step-010000/actor'
    jobs = [copy.deepcopy(original[0]), {'stage': 'memory-baseline-analysis', 'approved': False, 'enabled': False,
        'depends_on': ['saved-baseline-analysis'], 'command': [py, '-m', 'scripts.evaluate_grasp_act_memory',
            '--dataset', data, '--model', baseline_model, '--output', base+'/memory-baseline'],
        'runtime_path_verification_required': True}]
    jobs[0]['command'][-1] = base+'/baseline-analysis'
    templates = {}
    # Matching BCE/seed/sampler/budget controls isolate the input regularizer.
    for arm, probability in (('act4-control', 0.), ('act5-dropout', .2)):
        names = {job['stage']: arm+'/'+job['stage'] for job in original[1:]}
        for source_job in original[1:]:
            job = copy.deepcopy(source_job)
            stage = job['stage']
            job['stage'] = names[stage]
            job['depends_on'] = [names.get(d, d) for d in job['depends_on']]
            job['command'] = [s.replace(old_base, base+'/'+arm).replace(
                f'act4-models-{source[:8]}', f'act5-{arm}-models-{source[:8]}').replace(
                f'outputs/act4-{source[:8]}', f'outputs/act5-{arm}-{source[:8]}') for s in job['command']]
            if stage in ('smoke', 'main'):
                job['command'] += ['--command-history-dropout', str(probability)]
            if stage == 'smoke':
                job['depends_on'] += ['memory-baseline-analysis', 'memory-review-receipt']
            if stage == 'closed-loop':
                # Do not run both arms from the same old plan/seed automatically.
                job['depends_on'] += ['paired-fresh-plans-receipt', 'both-arms-offline-review-receipt']
                job['proposed_seed'] = None
                job['command'] = None
                job['status'] = 'BLOCKED_FRESH_UNUSED_MATCHED_PLANS_REQUIRED'
                job['model_transfer'] = {'source': base+'/'+arm+'/main/step-010000/actor',
                    'destination': f'/home/ugrp/act5-{arm}-models-{source[:8]}/actor',
                    'full_hash_and_cpu_load_verification_required': True}
            jobs.append(job)
        template = copy.deepcopy(queue['main_approval_template'])
        template['command_history_dropout'] = probability
        templates[arm] = template
    queue.pop('main_approval_template')
    queue['main_approval_templates'] = templates
    queue['jobs'] = jobs
    queue['budgets'].update(training_max_wall_s_per_arm=23400,
        training_max_wall_s_total=46800, offline_memory_analysis_max_wall_s=1800,
        stages_must_run_in_separate_8h_vm_windows=True, new_checkpoint_budget_gib=32,
        minimum_free_training_disk_gib=56)
    queue['budgets'].pop('training_max_wall_s')
    queue['required_before_start'] += [
        'memory-review-receipt: full 5 heldout episodes/1833 rows, all six variants, first-action MAE/signs and all-valid-horizon sensitivity',
        'Sparse CPU diagnostics are not full heldout coverage and cannot satisfy memory-review-receipt',
        'Confirm command sensitivity in relevant grasp phases before authorizing dropout training; cancel candidate if unsupported',
        'Run matched act4-control and act5-dropout with same data/seed/steps; do not attribute BCE or ensembling improvement to dropout',
        'Refresh total two-arm credit/disk/time budget and enforce stop at credit guard; do not run old act4 queue as well',
        'Physical comparison requires separate approval and fresh unused matched plans; no old-model resume']
    return queue


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output-dir', type=Path, required=True)
    a = p.parse_args()
    source = source_sha()
    queue = build_queue(source)
    queue['analysis_summary_sha256'] = sha256(ROOT/'experiments/2026-10-15-act-train/act5-summary.json')
    a.output_dir.mkdir(parents=True, exist_ok=True)
    path = a.output_dir/f'20261015-act5-{source[:8]}.json'
    if path.exists():
        raise FileExistsError(path)
    write_json(path, queue)
    print(json.dumps({'path': str(path), 'sha256': sha256(path), 'source_sha': source, 'approved': False}))


if __name__ == '__main__':
    main()
