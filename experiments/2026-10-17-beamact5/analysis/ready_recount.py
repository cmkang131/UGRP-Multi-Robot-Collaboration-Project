#!/usr/bin/env python3
"""Offline recount from the stored beamdiag summary; no raw episode access.

The raw per-tick own RGB, issued commands and start-protocol GO times are on
gcp2 (not accessed by this worker).  This script therefore recomputes only what
the merged summary/robots ledger contains and labels the stored protocol-audit
aggregate as stored evidence.  It never invents a later GO time.
"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SUMMARY = ROOT / 'experiments/2026-10-16-beamdiag/summary.json'
OUT = ROOT / 'experiments/2026-10-17-beamact5/ready-recount.json'
# Merged beamdiag protocol audit: analysis/protocol_audit.py read each raw
# start-protocol.json GO time and the nearest eval-only truth row.  The audit
# output itself is not in this worktree; the merged summary records its counts.
STORED_AUDIT = {
    'source': 'experiments/2026-10-16-beamdiag/summary.json hypotheses[1].evidence',
    'tool': 'experiments/2026-10-16-beamdiag/analysis/protocol_audit.py',
    'raw_inputs': 'gcp2 start-protocol.json + eval-only.jsonl (not re-read here)',
    'arms': {'A': {'GO_N': 20, 'GO_before_joint_alignment_N': 20},
             'B': {'GO_N': 20, 'GO_before_joint_alignment_N': 20}},
}

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

summary = json.loads(SUMMARY.read_text())
runs, both = [], []
for arm in ('A', 'B'):
    for run in summary['arms'][arm]['runs']:
        robots = run['robots']
        times = {rid: robots[rid]['first_assigned_aligned_sim_s'] for rid in ('r1', 'r2')}
        ever = {rid: robots[rid]['ever_assigned_aligned'] for rid in ('r1', 'r2')}
        row = dict(arm=arm, seed=run['seed'], raw=run['raw'],
                   first_assigned_aligned_sim_s=times,
                   ever_assigned_aligned=ever,
                   sim_end_s=run['sim_range_s'][1],
                   termination=run['termination'],
                   physical_success=run['physical_success'])
        if all(ever.values()):
            # Teaching/owncam alignment are not the same estimator.  This value
            # is only an upper-bound start for an ideal own-camera witness: the
            # stored eval-truth alignment may fire later or not be observable.
            earliest = max(times.values()) + .1  # two fresh 10 Hz frames
            row.update(earliest_possible_witness_ready_s=earliest,
                       cap_margin_after_witness_s=run['sim_range_s'][1] - earliest)
            both.append(row)
        runs.append(row)
stored_go = sum(v['GO_N'] for v in STORED_AUDIT['arms'].values())
stored_early = sum(v['GO_before_joint_alignment_N'] for v in STORED_AUDIT['arms'].values())
out = dict(
    schema='ugrp.beamact5.ready-recount.v1',
    source=dict(summary=str(SUMMARY), sha256=sha(SUMMARY),
                robots_csv=str(ROOT/'experiments/2026-10-16-beamdiag/robots.csv'),
                robots_csv_sha256=sha(ROOT/'experiments/2026-10-16-beamdiag/robots.csv')),
    stored_protocol_audit=STORED_AUDIT,
    recount=dict(
        runs_N=len(runs),
        original_GO_N=stored_go,
        original_GO_before_joint_alignment_N=stored_early,
        admitted_at_original_GO_N=stored_go - stored_early,
        admitted_at_original_GO='0/40',
        reason='every stored GO preceded joint alignment, so an alignment witness '
               'would not have emitted READY at that GO time',
        both_ever_aligned_N=len(both),
        both_ever_aligned_by_arm={a: sum(r['arm'] == a for r in both) for a in ('A', 'B')},
        witness_ready_upper_bound='4/40 (A 1/20, B 3/20) if each aligned robot '
                                  'could observe and hold its own alignment for two frames',
        physical_success_N=sum(bool(r['physical_success']) for r in runs)),
    both_ever_aligned_runs=both,
    runs=runs,
    not_computable=[
        'exact later re-GO/re-ACK time and any execution outcome after it',
        'whether the own camera could detect the alignment at those times (stored '
        'times are eval-truth geometry, not witness outputs)',
        'later alignment loss/reacquisition and streak resets',
    ],
    why_not_computable='the merged Mac artifacts keep per-run first-alignment times and '
        'aggregate protocol counts, but not per-tick own RGB, issued commands or the GO '
        'time; those raw files are under the gcp2 ops-review paths and gcp2 is outside '
        'this worker assignment.',
    scope='historical stored-ledger recount only; no new run, inference, physics or render',
)
OUT.write_text(json.dumps(out, indent=2, ensure_ascii=False) + '\n')
print(json.dumps(out['recount'], indent=2))
