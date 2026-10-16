#!/usr/bin/env python3
"""Reproduce a preparation report from saved evidence; never launches training."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if __name__ == '__main__':
    sys.path.insert(0, str(ROOT))

from scripts.rlprep_contract import CountBudget, inspect_warp3_marker, stop_event


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment-dir', type=Path,
                        default=ROOT / 'experiments/2026-10-16-rlprep')
    args = parser.parse_args()
    folder = args.experiment_dir.resolve()
    inputs = json.loads((folder / 'inputs.json').read_text())
    marker = inspect_warp3_marker(folder / 'warp3-record-api-ready.json')
    candidates = inputs['base_candidates']
    stages, rejection_counts = [], {}
    remaining = len(candidates)
    stages.append(dict(gate='warp3_marker_metadata_only', input=remaining,
                       passed=remaining, rejected=0, rejections=[]))
    # Strict improvements/no success are existing task prerequisites, not new
    # physical tolerances. Counts below are MODELS, never pooled trial results.
    for name, predicate, category in (
        ('base_validation_beats_persistence',
         lambda c: c['wheel_mae'] < c['persistence_wheel_mae'], 'base_below_persistence'),
        ('base_has_closed_loop_success', lambda c: c['success_n'] > 0,
         'base_zero_closed_loop_success'),
    ):
        passed, rejections = [], []
        for candidate in candidates:
            if predicate(candidate):
                passed.append(candidate)
            else:
                rejections.append(stop_event(category, blocking_object=candidate['id'],
                    detail='saved candidate evidence; not a new rollout or causal diagnosis'))
        rejection_counts[category] = len(rejections)
        stages.append(dict(gate=name, input=remaining, passed=len(passed),
                           rejected=len(rejections), rejections=rejections))
        candidates, remaining = passed, len(passed)
    stages.append(dict(gate='runtime_authorization_and_integration', input=remaining,
                       passed=0, rejected=remaining,
                       rejections=[stop_event('design_only', blocking_object=c['id'],
                           detail='training prohibited in this task; real integration unverified')
                           for c in candidates]))
    table = dict(schema='ugrp.rlprep.funnel.v1', counting_unit='saved base-policy candidates',
                 source_path=str(folder / 'inputs.json'),
                 reproduce_command='python -m scripts.prepare_rlprep',
                 stages=stages, rejection_distribution=rejection_counts,
                 raw_evidence=inputs['evidence'])
    plan = dict(schema='ugrp.rlprep.plan.v1', status='DESIGN_ONLY_NOT_A_QUEUE',
                execution_allowed=False, training_entrypoint='unconditionally disabled',
                rlprep_batch_v1=False, future_candidate_rlprep_batch_v1=True,
                rejection_table=str(folder / 'rejection-table.json'),
                pilot=dict(worlds=8, transitions=7200,
                           aggregate_sim_s=CountBudget().aggregate_sim_s,
                           max_critic_updates=7200, gpu_occupancy_h_proposal=1),
                stage1=dict(worlds=16, transitions=72000,
                            aggregate_sim_s=CountBudget(16, 72000).aggregate_sim_s,
                            max_critic_updates=72000, gpu_occupancy_h_proposal=3),
                gpu_occupancy_total_h_proposal=4, episode_cap_sim_s=90,
                gpu='one L4; no GPU operation authorized by this file',
                host_project='ugrp-sim-b-1014', base_candidates=inputs['base_candidates'],
                warp3_marker=marker)
    summary = dict(schema='ugrp.rlprep.summary.v1', status='DESIGN_READY_RUNTIME_NOT_READY',
                   task_activity=dict(new_physics_runs=0, gpu_starts=0, learner_updates=0,
                                      model_calls=0, gui_opens=0),
                   activity_scope='this preparation task only; prior rl1b runs excluded',
                   integration_verified=False, held_world_reads_policy_runtime='unmeasured',
                   evidence_sha256={name: hashlib.sha256((folder / name).read_bytes()).hexdigest()
                                    for name in ('inputs.json', 'warp3-record-api-ready.json',
                                                 'reference-sources.json')})
    for name, row in [('rejection-table.json', table), ('plan.json', plan), ('summary.json', summary)]:
        (folder / name).write_text(json.dumps(row, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    print(json.dumps(dict(status=summary['status'], execution_allowed=False,
                         rejection_table=plan['rejection_table']), ensure_ascii=False))


if __name__ == '__main__':
    main()
