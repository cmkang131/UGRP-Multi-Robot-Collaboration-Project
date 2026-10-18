"""Evaluator-only fixed-denominator comparison; retains duplicates and misses."""
import argparse
import json
from pathlib import Path
import platform
import sys
import numpy as np
from scripts.egomem1_offline import read,dump,digest
from scripts.egomem2_diagnose import index


def stats(values, total):
    finite=sorted(values)
    def quantile(q):
        # Missing memory has unknown error, represented as +infinity mass for
        # full-denominator rank only. Never report conditional P95 as full P95.
        rank=int(np.ceil(q*total))-1
        return finite[max(0,rank)] if finite and rank<len(finite) else None
    return dict(covered=len(values),denominator=total,coverage=len(values)/total if total else None,
                conditional_median_m=float(np.median(values)) if values else None,
                conditional_p95_m=float(np.percentile(values,95)) if values else None,
                full_denominator_median_m=quantile(.5),full_denominator_p95_m=quantile(.95),
                null_quantile_meaning='rank falls into missing-memory mass (+infinity), not zero')


def compare(baseline, rovio, candidate):
    directories=dict(baseline=baseline,rovio=rovio,candidate=candidate)
    indices={k:index(read(d/'frame-errors.json')) for k,d in directories.items()}
    keys=sorted(indices['baseline'])
    def select(rows):
        # Controller-visible recency; no error/GT-nearest selection. Both sides
        # use the same rule. All duplicate rows remain counted in the report.
        return min(rows,key=lambda r:(r['age_s'],int(r['memory_id'][1:])))
    reports={};paired={}
    for name,idx in indices.items():
        reports[name]={}
        for kind in sorted({k[2] for k in keys}):
            subset=[k for k in keys if k[2]==kind]
            reports[name][kind]=stats([select(idx[k])['error_m'] for k in subset if k in idx],len(subset))
            reports[name][kind]['duplicate_keys']=sum(len(idx[k])>1 for k in subset if k in idx)
            reports[name][kind]['evaluated_memory_rows']=sum(len(idx[k]) for k in subset if k in idx)
    shared=[k for k in keys if k in indices['candidate']]
    for kind in sorted({k[2] for k in keys}):
        subset=[k for k in shared if k[2]==kind]
        before=[select(indices['baseline'][k])['error_m'] for k in subset]
        after=[select(indices['candidate'][k])['error_m'] for k in subset]
        paired[kind]=dict(baseline=stats(before,len(subset)),candidate=stats(after,len(subset)),
                          candidate_lower_n=sum(a<b for a,b in zip(after,before)))
    return dict(status='OFFLINE_ONLY',frames=2026,denominator=len(keys),
                selection='minimum age_s then numeric memory birth ID, equally on both; never minimum error',
                report=reports,matched_recency_selected_error=paired,
                rejection_table=dict(unit='unchanged_baseline_label_timestamp_keys',
                    funnel=[dict(stage='all_baseline_keys',input_n=len(keys),cumulative_pass_n=len(keys),rejected_n=0),
                            dict(stage='candidate_present',input_n=len(keys),cumulative_pass_n=len(shared),rejected_n=len(keys)-len(shared)),
                            dict(stage='recency_selected_including_duplicates',input_n=len(shared),cumulative_pass_n=len(shared),rejected_n=0)],
                    reasons=dict(candidate_memory_absent=len(keys)-len(shared),duplicate_excluded=0),
                    blocked_object='not_observed',minimum_gap_m=None,gap_status='not_measured',
                    raw=[str(d) for d in directories.values()],reproduction=sys.argv),
                original_unique_only_comparison_is_additional=True,
                actual_reacquisition_trials=0,physical_success=False,student_success=False,llm_success=False,
                limitation='Offline birth labels remain nearest same-appearance evaluator geometry; cannot prove correct identity or actual navigational return.',
                sha256={str(d/'frame-errors.json'):digest(d/'frame-errors.json') for d in directories.values()})


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for key in ('baseline','rovio','candidate','output'):p.add_argument('--'+key,type=Path,required=True)
    a=p.parse_args()
    if not platform.node().startswith('ugrp-act-l4-gcp5'):raise ValueError('GCP5_ORIGINAL_CPU_ONLY')
    dump(a.output,compare(a.baseline,a.rovio,a.candidate))
