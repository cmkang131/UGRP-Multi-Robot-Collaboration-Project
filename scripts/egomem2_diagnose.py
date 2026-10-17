"""Evaluator-only decomposition of the unchanged egomem1 pairing denominator.

Runs on the original GCP5 CPU. No controller imports or input modifications.
"""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import platform
import sys

from scripts.egomem1_offline import read, dump, digest


def index(rows):
    result = defaultdict(list)
    for r in rows:
        result[(r['t'], r['target'], r['kind'])].append(r)
    return result


def diagnose(baseline, candidate):
    old = index(read(baseline/'frame-errors.json'))
    new = index(read(candidate/'frame-errors.json'))
    pred = read(candidate/'predictions.json')
    allowed = read(candidate/'allowed.json')
    base_pred = read(baseline/'predictions.json')
    labels = {r['memory_id']: (r['target'], r['kind']) for rs in new.values() for r in rs}
    base_labels = {r['memory_id']: (r['target'], r['kind']) for rs in old.values() for r in rs}
    timeline = defaultdict(list)
    births = defaultdict(list)
    creation_causes = Counter()
    by_time = defaultdict(Counter)
    same_tick_births = Counter()
    for row in pred:
        born_here = Counter()
        for e in row['events']:
            label = labels.get(e.get('memory_id'))
            if label:
                timeline[label].append((row['t'], e['reason'], e.get('memory_id')))
                if e['reason'] == 'created':
                    births[label].append(row['t'])
                    born_here[label] += 1
        for label, count in born_here.items():
            if count > 1:
                same_tick_births[str(label)] += count - 1
    missing = Counter(); duplicates = Counter(); details = []
    # Same inputs/detector: baseline-present keys cannot measure objects that
    # neither detector ever saw. Do not invent a 'first detection failure' count.
    for key, rows in sorted(old.items()):
        t, target, kind = key; label = (target, kind)
        if key not in new:
            previous = [e for e in timeline[label] if e[0] <= t]
            removed = [e for e in previous if e[1].endswith('_removed') or e[1].endswith('_evicted')]
            if removed:
                reason = 'after_' + removed[-1][1]
            elif not previous:
                reason = 'before_first_candidate_birth' if births[label] else 'never_candidate_labelled'
            else:
                reason = 'label_present_history_but_absent_now_unexplained'
            missing[reason] += 1; by_time[f'{int(t//20)*20:03d}-{int(t//20)*20+20:03d}'][reason] += 1
            details.append(dict(t=t,target=target,kind=kind,reason=reason,
                                last_removal=removed[-1] if removed else None))
        elif len(rows) != 1 or len(new[key]) != 1:
            reason = ('both_duplicate' if len(rows)>1 and len(new[key])>1 else
                      'baseline_only_duplicate' if len(rows)>1 else 'candidate_only_duplicate')
            duplicates[reason] += 1
            by_time[f'{int(t//20)*20:03d}-{int(t//20)*20+20:03d}'][reason] += 1
    # Outcomes for the exact observations which created baseline memories.
    for b, c, a in zip(base_pred, pred, allowed):
        assert b['t'] == c['t'] == a['t']
        for e in b['events']:
            if e['reason'] != 'created': continue
            outcomes = [v['reason'] for v in c['events'] if v.get('observation') == e['observation']]
            creation_causes.update(outcomes or ['no_candidate_observation_outcome'])
    shared = set(old) & set(new)
    unique = [k for k in shared if len(old[k]) == len(new[k]) == 1]
    return dict(status='DIAGNOSIS_ONLY', denominator=len(old), shared=len(shared), unique=len(unique),
                missing=dict(missing), duplicate=dict(duplicates), by_20_sim_s=dict(by_time),
                baseline_birth_observation_candidate_outcomes=dict(creation_causes),
                candidate_same_tick_duplicate_birth_excess=dict(same_tick_births),
                first_detection_failure='not identifiable in baseline-present denominator; shared detector, excluded objects never observed by either require separate detector audit',
                limitation='Evaluator birth labels are nearest same-appearance geometry; label duplicates may include wrong labels, never ground-truth identities in control.',
                details=details,
                raw=[str(baseline),str(candidate)], reproduction=sys.argv,
                blocked_object='not_observed',minimum_gap_m=None,gap_status='not_measured',
                sha256={str(p):digest(p) for d in (baseline,candidate) for p in
                        (d/'predictions.json',d/'frame-errors.json',d/'allowed.json')})


def main():
    p=argparse.ArgumentParser();p.add_argument('--baseline',type=Path,required=True)
    p.add_argument('--candidate',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if not platform.node().startswith('ugrp-act-l4-gcp5'):raise ValueError('GCP5_ORIGINAL_CPU_ONLY')
    if not Path('/home/ugrp/ugrp-sim/leases/egomem2.json').is_file():raise ValueError('OWN_LEASE_REQUIRED')
    result=diagnose(a.baseline,a.candidate);details=result.pop('details')
    a.output.mkdir(parents=True,exist_ok=False)
    dump(a.output/'missing-rows.json',details);dump(a.output/'rejection_table.json',result)
    print(json.dumps(result,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
