"""Recompute noslip10 VAL5 A/B from post-action raw scoring/action ledgers.

The frozen score uses exactly the original thresholds. Per-chunk done times
were not logged, so failure-message wording is not independently reconstructed;
physical lift/release/drop and full task success are independently recomputed.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import subprocess
import sys

from act16w_runtime import require_gcp2, sha256

ACT = Path('/home/ugrp/ugrp-sim/src/3f99d58c5ada0862e669ef4065c0ba957f1b4547')


def read(path, *, lines=False):
    raw = path.read_bytes() if path.exists() else subprocess.check_output(['zstd','-dc',str(path)+'.zst'])
    return [json.loads(line) for line in raw.splitlines() if line.strip()] if lines else json.loads(raw)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    host = require_gcp2(training=True)
    sys.path.insert(0, str(ACT))
    from harness.grasp_act_rollout import SoloScore
    results = {}
    for arm in ('A', 'B'):
        root = a.root/(arm+'-native'); parent = read(root/'summary.json')
        if not parent.get('complete'):
            raise ValueError('baseline must finish unchanged before recount '+arm)
        rows, receipts = [], []
        for group in sorted(root.glob('group-*')):
            ev = group/'evaluation'; summary = read(ev/'summary.json')
            plans = read(group/'plans.json')['episodes']
            actions = read(ev/'actor-actions.jsonl', lines=True)
            assigned = [SoloScore() for _ in plans]; same = {}
            for path, is_same in ((ev/'owner/evaluation-only.jsonl', False), (ev/'owner/same-kind-evaluation-only.jsonl', True)):
                actual = path if path.exists() else path.with_suffix('.jsonl.zst')
                receipts.append(dict(path=str(actual), sha256=sha256(actual)))
                for value in read(path, lines=True):
                    if 'min_z' not in value: continue
                    world = value['world']; i = max(0, round(value['elapsed_sim_s']/.1)-1)
                    score = same.setdefault((world,value['item_id']), SoloScore()) if is_same else assigned[world]
                    score.add(value['t'], skill=actions[min(i,len(actions)-1)]['skills'][world],
                        linear_speed=value['speed'], clearance=value['min_z'], tilt=value['tilt_deg'],
                        forces=value['finger_forces'], weld=value['weld_active'])
            for world, plan in enumerate(plans):
                score = assigned[world].record({}, with_release=True)
                original = read(ev/'owner'/f'world-{world:03d}'/'result.json')
                success = bool(score['physical_success'] and original['issued_done'] and not original['cap_end'])
                any_same = any(s.record({}, with_release=True)['physical_success'] and original['issued_done']
                               and not original['cap_end'] for (w,_),s in same.items() if w == world)
                expected = summary['student_scores'][world]
                for key in ('lift_success','release_success','physical_success','drop_detected','max_stable_lift_s','max_stable_release_s'):
                    if score[key] != expected[key]: raise ValueError('raw score mismatch '+arm+' '+str(plan['seed'])+' '+key)
                if success != expected['task_success'] or bool(any_same) != expected['any_same_kind_success']:
                    raise ValueError('raw assigned/same-kind task recount mismatch')
                rows.append(dict(seed=plan['seed'], kind=plan['kind'], task_success=success,
                    any_same_kind_success=bool(any_same), cap_end=original['cap_end'],
                    issued_sequence_complete=original['issued_done'],
                    **{k:score[k] for k in ('lift_success','release_success','physical_success','drop_detected')}))
        if len(rows) != 5 or len({r['seed'] for r in rows}) != 5:
            raise ValueError('exact VAL5 denominator required')
        kinds = {k:dict(n=sum(r['task_success'] for r in rows if r['kind']==k),N=sum(r['kind']==k for r in rows)) for k in ('cyan','red','green','yellow')}
        eligible = list(rows); counts = [len(rows)]
        for key in ('issued_sequence_complete','lift_success','release_success','task_success'):
            eligible = [r for r in eligible if r[key]]; counts.append(len(eligible))
        results[arm] = dict(n=sum(r['task_success'] for r in rows), N=5,
            n_any_same_kind=sum(r['any_same_kind_success'] for r in rows), kinds=kinds, rows=rows,
            funnel=[dict(gate=g,passed=n,rejected=counts[i-1]-n if i else 0) for i,(g,n) in enumerate(zip(('requested','sequence_done','stable_lift','stable_release','task_success'),counts))],
            cap_end=sum(r['cap_end'] for r in rows), raw_receipts=receipts,
            raw_recomputed_metrics_match_original=True)
    report = dict(status='complete', complete=True, host=host, contact_profile='baseline_noslip10',
        pooled_with_native_contact=False, final40_accessed=False, arms=results,
        limitation='per-chunk done timestamps unavailable; failure message wording not independently reconstructed',
        reproduce=sys.argv)
    a.out.write_text(json.dumps(report,indent=2)+'\n')


if __name__ == '__main__':
    main()
