"""Independently recount native ACT scores from immutable post-action ledgers.

Uses the frozen SoloScore thresholds, never steps physics or changes policy.
Chunk done timestamps were not saved; physical and task counts are independently
reconstructed, while the original failure-message wording is not reproduced.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys

from act16w_runtime import require_gcp2, frozen_source, sha256

ROOT = Path(__file__).resolve().parents[1]
ACT = Path('/home/ugrp/ugrp-sim/src/3f99d58c5ada0862e669ef4065c0ba957f1b4547')


def read(path, *, lines=False):
    actual = path if path.exists() else Path(str(path)+'.zst')
    raw = actual.read_bytes() if actual.suffix != '.zst' else subprocess.check_output(['zstd','-dc',str(actual)])
    value = [json.loads(line) for line in raw.splitlines() if line.strip()] if lines else json.loads(raw)
    return value, dict(path=str(actual), sha256=sha256(actual))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--evaluation', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    host, source = require_gcp2(training=True), frozen_source(ROOT)
    frozen_source(ACT, ACT.name)
    sys.path.insert(0,str(ACT))
    from harness.grasp_act_rollout import SoloScore
    parent, receipt = read(a.evaluation/'summary.json')
    if (not parent['complete'] or parent['checkpoint_provenance'].get('contact_profile') != 'warp_native_contact_v1'
            or parent['N'] not in (8,40) or parent['N'] != parent['N_requested']):
        raise ValueError('completed registered native VAL8 or FINAL40 required')
    rows, receipts = [], [receipt]
    for group in sorted(a.evaluation.glob('group-*')):
        ev = group/'evaluation'
        summary, receipt = read(ev/'summary.json'); receipts.append(receipt)
        plans, receipt = read(group/'plans.json'); receipts.append(receipt); plans=plans['episodes']
        actions, receipt = read(ev/'actor-actions.jsonl',lines=True); receipts.append(receipt)
        assigned=[SoloScore() for _ in plans]; same={}
        observed=[dict(max_grasp_bilateral_finger_n=0.,max_grasp_clearance_m=None) for _ in plans]
        for filename, is_same in (('evaluation-only.jsonl',False),('same-kind-evaluation-only.jsonl',True)):
            values, receipt=read(ev/'owner'/filename,lines=True); receipts.append(receipt)
            for value in values:
                if 'min_z' not in value: continue
                world=value['world']; i=max(0,round(value['elapsed_sim_s']/.1)-1)
                score=same.setdefault((world,value['item_id']),SoloScore()) if is_same else assigned[world]
                skill=actions[min(i,len(actions)-1)]['skills'][world]
                score.add(value['t'],skill=skill,
                    linear_speed=value['speed'],clearance=value['min_z'],tilt=value['tilt_deg'],
                    forces=value['finger_forces'],weld=value['weld_active'])
                if not is_same and skill=='grasp':
                    peak=observed[world]
                    peak['max_grasp_bilateral_finger_n']=max(peak['max_grasp_bilateral_finger_n'],min(value['finger_forces']))
                    peak['max_grasp_clearance_m']=max(value['min_z'],peak['max_grasp_clearance_m']) if peak['max_grasp_clearance_m'] is not None else value['min_z']
        for world, plan in enumerate(plans):
            score=assigned[world].record({},with_release=True)
            original,receipt=read(ev/'owner'/f'world-{world:03d}'/'result.json');receipts.append(receipt)
            expected=summary['student_scores'][world]
            success=bool(score['physical_success'] and original['issued_done'] and not original['cap_end'])
            any_same=any(s.record({},with_release=True)['physical_success'] and original['issued_done']
                and not original['cap_end'] for (w,_),s in same.items() if w==world)
            for key in ('lift_success','release_success','physical_success','drop_detected','max_stable_lift_s','max_stable_release_s'):
                if score[key] != expected[key]: raise ValueError(f'raw score mismatch {plan["seed"]} {key}')
            if success != expected['task_success'] or bool(any_same) != expected['any_same_kind_success']:
                raise ValueError('assigned/any-same-kind task recount mismatch')
            rows.append(dict(seed=plan['seed'],kind=plan['kind'],item_id=plan['item_id'],
                task_success=success,any_same_kind_success=bool(any_same),cap_end=original['cap_end'],
                resource_cap_end=expected['resource_cap_end'],issued_sequence_complete=original['issued_done'],
                **{key:score[key] for key in ('lift_success','release_success','physical_success','drop_detected')},
                **observed[world],
                bilateral_load_observed=observed[world]['max_grasp_bilateral_finger_n']>=assigned[world].lift.CRITERIA['finger_each_n'],
                raw_world=str(ev/'owner'/f'world-{world:03d}')))
    if len(rows)!=parent['N'] or {r['seed'] for r in rows}!=set(parent['requested_seeds']):
        raise ValueError('exact registered denominator/seeds required')
    if sum(r['task_success'] for r in rows)!=parent['n']:
        raise ValueError('batch recount mismatch')
    eligible=list(rows); counts=[len(rows)]
    for key in ('issued_sequence_complete','lift_success','release_success','task_success'):
        eligible=[r for r in eligible if r[key]];counts.append(len(eligible))
    report=dict(status='complete',complete=True,utc=datetime.now(timezone.utc).isoformat(),host=host,
        source_sha=source,contact_profile='warp_native_contact_v1',noslip10_pooled=False,
        n=sum(r['task_success'] for r in rows),N=len(rows),n_any_same_kind=sum(r['any_same_kind_success'] for r in rows),
        kinds={k:dict(n=sum(r['task_success'] for r in rows if r['kind']==k),N=sum(r['kind']==k for r in rows)) for k in ('cyan','red','green','yellow')},
        funnel=[dict(gate=g,passed=n,rejected=counts[i-1]-n if i else 0) for i,(g,n) in enumerate(zip(('requested','sequence_done','stable_lift','stable_release','task_success'),counts))],
        cap_end=sum(r['cap_end'] for r in rows),resource_cap_end=sum(r['resource_cap_end'] for r in rows),
        independent_stage_counts={key:sum(r[key] for r in rows) for key in ('bilateral_load_observed','lift_success','release_success','issued_sequence_complete','task_success')},
        bilateral_load_threshold_n=assigned[0].lift.CRITERIA['finger_each_n'],
        threshold_source='unchanged frozen3f99d58c LiftScore.CRITERIA finger_each_n; additional descriptive metric, no new task acceptance rule',
        rows=rows,raw_receipts=receipts,raw_recomputed_metrics_match_original=True,
        limitation='chunk done timestamps unavailable; failure-message wording not independently reconstructed',reproduce=sys.argv)
    with a.out.open('x') as stream:
        json.dump(report,stream,indent=2);stream.write('\n')
    print(json.dumps({k:report[k] for k in ('status','n','N','n_any_same_kind','kinds','funnel')}))


if __name__=='__main__': main()
