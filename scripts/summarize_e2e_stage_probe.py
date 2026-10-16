#!/usr/bin/env python3
"""Offline paired stage results, including missing and HOST_ERROR runs."""
import argparse
import json
from pathlib import Path
import statistics
from harness.e2e_stage_checkpoint import digest


def distribution(values):
    return dict(n=len(values),median=statistics.median(values) if values else None,max=max(values) if values else None)


def summarize(matrix, records):
    expected={(r['source_run'],r['seed'],r['condition']):r for r in matrix['runs']}
    found={}
    for result in records:
        key=tuple(result[k] for k in ('source_run','seed','condition'))
        if key not in expected or key in found:raise ValueError('UNKNOWN_OR_DUPLICATE_PAIRED_RESULT')
        if result['checkpoint_sha256']!=expected[key]['checkpoint_sha256']:raise ValueError('PAIRED_CHECKPOINT_MISMATCH')
        found[key]=result
    def group(keys):
        rs=[found[k] for k in keys if k in found]
        times=[r['both_held_s'] for r in rs if r.get('both_held') and r.get('both_held_s') is not None]
        return dict(planned_N=len(keys),observed_N=len(rs),missing_N=len(keys)-len(rs),
            first_attempt_n=sum(r.get('first_attempt_success',False) for r in rs),
            held_n=sum(r.get('both_held',False) for r in rs),
            host_errors=sum(r['status']=='HOST_ERROR' for r in rs),
            held_sim_s=distribution(times),held_gap_s=distribution([r['held_gap_s'] for r in rs if r.get('held_gap_s') is not None]),
            censored_sim_s=distribution([r['censored_s'] for r in rs if r.get('censored_s') is not None]),
            scan_cycles={rid:distribution([r['scan_cycles'][rid] for r in rs if 'scan_cycles' in r]) for rid in ('r1','r2')},
            reacquisition_entries={rid:distribution([r['reacquisition_entries'][rid] for r in rs if 'reacquisition_entries' in r]) for rid in ('r1','r2')},
            statuses={s:sum(r['status']==s for r in rs) for s in sorted({r['status'] for r in rs})})
    conditions={c:group([k for k in expected if k[2]==c]) for c in matrix['conditions']}
    core_conditions={c:group([k for k in expected if k[2]==c and k[0] in matrix['core_source_runs']]) for c in matrix['conditions']}
    core=group([k for k in expected if k[0] in matrix['core_source_runs']])
    paired={}
    for candidate in matrix['conditions'][1:]:
        pairs=[];deltas=[]
        for source in matrix['source_runs']:
            for seed in matrix['seeds']:
                a=found.get((source,seed,'v375'));b=found.get((source,seed,candidate))
                if a and b:
                    equal=bool(a.get('own_map_sha256') and a.get('initial_physics_sha256') and
                        a['own_map_sha256']==b.get('own_map_sha256') and
                        a['initial_physics_sha256']==b.get('initial_physics_sha256') and a.get('source_sha')==b.get('source_sha'))
                    row=dict(initial_state_hashes_match=equal,source_run=source,seed=seed,baseline=a['status'],candidate=b['status'],
                        first_attempt_delta=int(b.get('first_attempt_success',False))-int(a.get('first_attempt_success',False)))
                    if equal and a.get('both_held') and b.get('both_held'):
                        row['held_sim_delta_s']=b['both_held_s']-a['both_held_s'];deltas.append(row['held_sim_delta_s'])
                    pairs.append(row)
        paired[candidate]=dict(paired_N=len(pairs),verified_same_state_N=sum(p['initial_state_hashes_match'] for p in pairs),both_completed_delta_s=distribution(deltas),pairs=pairs)
    baseline=[r for k,r in found.items() if k[2]=='v375']
    reproduction=dict(observed_N=len(baseline),reacquisition_reproduced_n=sum(any(r.get('reacquisition_entries',{}).values()) for r in baseline),
        criterion='at least one acquisition after align entry, like selected r80 failure scenes; not trajectory equivalence')
    return dict(schema='ugrp.e2e_stage_summary.v1',all=group(list(expected)),core=core,conditions=conditions,core_conditions=core_conditions,
                paired=paired,baseline_reproduction=reproduction,records_sha256=digest(records),
                retrieved_results_finalized=bool(found) and all(r.get('finalization_complete') for r in found.values()),
                missing_are_not_failures_or_successes=True)


def main():
    p=argparse.ArgumentParser();p.add_argument('--matrix',type=Path,required=True)
    p.add_argument('--result',type=Path,action='append',default=[]);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();rs=[json.loads(p.read_text()) for p in a.result]
    report=summarize(json.loads(a.matrix.read_text()),rs)
    report['sources']=[dict(path=str(p),sha256=__import__('hashlib').sha256(p.read_bytes()).hexdigest()) for p in a.result]
    from harness.e2e_result_writer import write
    write(a.output,report)

if __name__=='__main__':main()
