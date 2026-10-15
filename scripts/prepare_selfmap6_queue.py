"""Create a NEW deny-by-default smooth queue; no submission or remote access."""
import argparse
import hashlib
import json
from pathlib import Path

from scripts.prepare_selfmap5_queue import make_queue as previous_queue
from scripts.run_self_map_diagnostic import bundle
from harness.selfmap5_revision import OPTION as REVISION
from harness.selfmap5_registration import OPTION as MULTIFRAME
from harness.selfmap6_safety import OPTION as SAFETY


def make_queue(source):
    q = previous_queue(source)
    q.update(task='selfmap6-pr506-precommit-gate-rollback-ambiguity', run_count=3,
        record='experiments/2026-10-15-self-map/selfmap6.md',
        dependencies=[], stages=q['stages'][:3],
        seed_reservation=dict(seeds=[93560, 93561, 93562], remote_history_checked=False,
            remote_check_required_before_submission=True),
        offline_verdict='FIXED_TRACE_GATE_AND_ROLLBACK_VERIFIED_LIVE_UNVERIFIED',
        texture_deferred=dict(pr=511, enabled=False, approved=False, execute=False,
            requirement='separate new queue after merge and source integration'))
    runs = q['runs'][:3]
    previous = None
    for run, seed in zip(runs, [93560, 93561, 93562]):
        old_name = run['name']; name = f'selfmap6-smooth-{seed}-{source[:8]}'
        run.update(name=name, seed=seed, depends_on=previous, raw=run['raw'].replace(old_name, name))
        run['bundle'] = bundle(source, seed, run['cap_sim_s'], bootstrap='command_prior_v1',
            initial_sweep='required_360_v1', recovery_profile='selfmap4_recovery_v1',
            revision_gate=REVISION, multiframe_registration=MULTIFRAME, correction_safety=SAFETY)
        command = [s.replace(old_name, name) for s in run['command'] if s != '--execute']
        command[command.index('--seed')+1] = str(seed)
        command.extend(['--correction-safety', SAFETY])
        run['command'] = command  # operator must add --execute only after approval
        previous = name
    q['runs'] = runs; q['storage_budget_mib'] = sum(r['reserved_mib'] for r in runs)
    q['preconditions'] = [
        'Prepared only. Approve exact pushed SHA, append --execute, and submit separately; no automatic promotion.',
        'Serial smooth first30 -> review raw -> 180s-a -> review raw -> 180s-b. Every stage remains false.',
        'Verify GCP project ugrp-act-train-1014 budget-stop, 8h STOP, idle20min, disk, machine speed and seed collisions before submission.',
        'Own RGB/issued commands/authored map only; GT evaluation only; no previous-result pooling.',
        'First30: >=6 evenly spaced frames, RGB hashes/cadence, ORB matches/inliers, admissions with NIS/P/R/evidence IDs, competing hypotheses.',
        'Inspect quarantine start/rebuild receipts/rollback release <=10 SIM s or two failures; no completion certification from rollback.',
        'S2: global geometric candidate count including repeated rooms, unique candidate/PF agreement and fresh distinct views.',
        'Known defect: stop affected owned runs and fix before proceeding. No model calls or training.',
        'Texture is excluded; PR511 merge/integration requires a separate newly pinned and approved queue.',
        'Local offline replay uses saved proposals only; full RGB bank replay and live navigation improvement remain unverified.'
    ]
    return q


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-sha', required=True); p.add_argument('--output', type=Path, required=True)
    a = p.parse_args(); q = make_queue(a.source_sha); a.output.parent.mkdir(parents=True, exist_ok=True)
    with a.output.open('x') as f:
        json.dump(q, f, indent=2, ensure_ascii=False, allow_nan=False); f.write('\n')
    print(json.dumps(dict(path=str(a.output), sha256=hashlib.sha256(a.output.read_bytes()).hexdigest(),
                         runs=3, approved=False, execute=False)))


if __name__ == '__main__':
    main()
