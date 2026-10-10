"""Evaluation-only truth join; never imported by the replay or controller."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
RAW = Path('/Users/changmin/projects/ugrp/outputs')
ARMS = ('n100', 'n500', 'sensor100')
S3 = {'v149': RAW/'s3-sweep-b73ce193-s14201-v149',
      'v150': RAW/'s3-odometry-4c9eb3aa-s14201-v150'}


def read(p): return json.loads(p.read_text())
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()


def evaluate(base):
    path = HERE.parent/'s3fix6/evaluate.py'
    spec = importlib.util.spec_from_file_location('original_evaluation', path)
    old = importlib.util.module_from_spec(spec); spec.loader.exec_module(old)
    table, costs, receipts, originals = {}, {}, {}, {}
    for arm in ARMS:
        table[arm], costs[arm] = {}, {}
        for case in ('55001', '55002', 'v149', 'v150'):
            folder = base/(case+'-'+arm)
            r, c = read(folder/'result.json'), read(folder/'proposal-cost.json')
            assert r.get('failure') is None and r.get('error') is None
            receipts[case+'-'+arm] = dict(path=str(folder.resolve()),
                result_sha256=sha(folder/'result.json'), cost_sha256=sha(folder/'proposal-cost.json'))
            costs[arm][case] = {k: v for k, v in c.items() if k != 'audit'}
            if case in S3:
                rows = {rid: old.s3(folder, S3[case], rid) for rid in ('r1', 'r2', 'r3')}
                for rid, value in rows.items():
                    a = c['audit'][rid]
                    pop = a['rows']
                    value.update(unique_min=min(q['unique'] for q in pop),
                        unique_median=float(np.median([q['unique'] for q in pop])),
                        population_audit_rows=len(pop), tracking_handoff=a['handoff'],
                        initial_particles=a['initial_particles'])
                    table[arm][case+'/'+rid] = value
            else:
                value = old.own(folder, RAW/f'goal-route-motion-audit-v1/seed{case}')
                pop = c['audit']['population']
                value.update(unique_min=min(q['unique'] for q in pop),
                    unique_median=float(np.median([q['unique'] for q in pop])), population_audit_rows=len(pop))
                table[arm][case+'/r3'] = value
                if arm == 'n100':
                    assert r['original_frontend_equal'] and r['original_contacts_equal'] and r['original_proposals_equal']
                    receipts[case+'-'+arm]['original_identity'] = True
    for case, raw in S3.items():
        reference = RAW/'s3fix6-20261010/replays-v4'/(case+'-off')
        originals[case] = {rid: old.s3(reference, raw, rid) for rid in ('r1', 'r2', 'r3')}
    failures = []
    for key, new in table['sensor100'].items():
        b = table['n100'][key]
        for metric in ('xy_rmse_m', 'final_error_m'):
            if new[metric] > b[metric]+1e-9:
                failures.append(dict(trajectory=key, metric=metric, before=b[metric], after=new[metric]))
        for metric in ('over_3sigma_fraction', 'false_certificates'):
            if new.get(metric, 0) > b.get(metric, 0):
                failures.append(dict(trajectory=key, metric=metric, before=b[metric], after=new[metric]))
        if new['frames'] != b['frames'] or new['invalid_frames']:
            failures.append(dict(trajectory=key, metric='frame_coverage'))
    pooled = lambda a: sum(v['over_3sigma'] for v in table[a].values())/sum(v['frames'] for v in table[a].values())
    if pooled('sensor100') >= pooled('n100'):
        failures.append(dict(metric='pooled_over_3sigma', before=pooled('n100'), after=pooled('sensor100')))
    for case, c in costs['sensor100'].items():
        if c['cpu_s'] >= costs['n500'][case]['cpu_s']:
            failures.append(dict(case=case, metric='CPU_not_below_500',
                candidate=c['cpu_s'], n500=costs['n500'][case]['cpu_s']))
    return dict(table=table, costs=costs, original_s3_2000_tracking=originals,
        receipts=receipts, selected='off' if failures else 'sensor_mixture_v1', failures=failures,
        gt_evaluation_only=True, physics_runs=0, preregistration_sha256=sha(HERE/'README.md'),
        pooled_over_3sigma={a: pooled(a) for a in ARMS},
        cpu_scope='per full saved input; each S3 cost includes all three robots and unchanged global phase')


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--input', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True); a = p.parse_args()
    value = evaluate(a.input)
    with a.output.open('x') as stream: stream.write(json.dumps(value, indent=2, allow_nan=False)+'\n')
    print(json.dumps(dict(selected=value['selected'], failures=value['failures']), indent=2))
