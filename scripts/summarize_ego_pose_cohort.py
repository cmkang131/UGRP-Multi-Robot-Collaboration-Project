"""Aggregate fetch-lite receipts; evaluation only, never a policy input."""
import argparse
import hashlib
import json
import math
from pathlib import Path


def aggregate(root, sha):
    jobs, pairs, receipts = {}, {}, []
    for folder in sorted(root.glob('egojump-online-v2-*')):
        for p in sorted(folder.glob(f'egojump-63*-{sha[:8]}-r1*-summary.json')):
            row = json.loads(p.read_text())
            receipts.append(dict(path=str(p), sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
            rows = [row['job']] if 'job' in row else (row.get('summary') or {}).get('runs', [])
            for job in rows:
                if job.get('result', {}).get('source_sha') != sha:
                    raise ValueError('MIXED_WORKER_SOURCE')
                key = job['seed'], job['condition']
                if key in jobs and jobs[key] != job:
                    raise ValueError('CONFLICTING_DUPLICATE_RESULT')
                jobs[key] = job
            if row.get('common_horizon'):
                pairs[row['name']] = row['common_horizon']
    conditions = {}
    for condition in ('off', 'cluster', 'innovation'):
        selected = [jobs[(seed, condition)] for seed in range(63001, 63007)
                    if (seed, condition) in jobs]
        measured = [j for j in selected if j.get('score') and j['status'] in
                    ('RECORDED', 'PHYSICAL_FAILURE') and not j.get('interrupted_reason')]
        scores = [j['score'] for j in measured]
        frames = sum(s['samples'] for s in scores)
        paired = [s for p in pairs.values() for s in p['runs'] if s['condition'] == condition]
        regressions=[]
        for name,pair in pairs.items():
            by_condition={r['condition']:r for r in pair['runs']}
            candidate=by_condition[condition]['rmse_m'];baseline=by_condition['off']['rmse_m']
            if candidate>baseline+1e-12:
                regressions.append(dict(group=name,candidate_rmse_m=candidate,baseline_rmse_m=baseline))
        def jumps(which, values):
            return dict(transitions=sum(s[which]['transitions'] for s in values),
                        counts={k: sum(s[which]['counts'][k] for s in values)
                                for k in ('0.05', '0.2', '0.5')},
                        max_m=max((s[which]['max_m'] for s in values), default=None))
        conditions[condition] = dict(registered=6, measured=len(measured),
            host_errors=sum(j['status'].startswith('HOST_ERROR') for j in selected),
            physical_failures=sum(j['status'] == 'PHYSICAL_FAILURE' for j in measured),
            B=sum(s['B_arrived'] for s in scores), returned=sum(s['returned'] for s in scores),
            B_and_return=sum(s['B_arrived'] and s['returned'] for s in scores),
            false_declarations=sum(not d['valid'] for s in scores for d in s['declarations']),
            false_B=sum(d['kind']=='goal_reached' and not d['valid']
                        for s in scores for d in s['declarations']),
            false_return=sum(d['kind']=='return_start_declared' and not d['valid']
                             for s in scores for d in s['declarations']),
            frames=frames, full_rmse_m=math.sqrt(sum(s['samples']*s['xy_rmse_m']**2
                for s in scores)/frames) if frames else None,
            mean_final_error_m=sum(s['final_error_m'] for s in scores)/len(scores) if scores else None,
            map_jumps=jumps('map_jumps',scores), control_jumps=jumps('control_jumps',scores),
            paired_map_jumps=jumps('map_jumps',paired), paired_control_jumps=jumps('control_jumps',paired),
            paired_groups=len(paired), paired_frames=sum(s['frames'] for s in paired),
            paired_rmse_regressions=regressions,
            paired_rmse_m=math.sqrt(sum(s['squared_error_sum_m2'] for s in paired)/
                sum(s['frames'] for s in paired)) if paired else None,
            commands=sum(s['commands'] for s in scores),
            wall_s=sum(j['result'].get('wall_s', 0) for j in measured))
    compact=[]
    for (seed, condition), job in sorted(jobs.items()):
        compact.append(dict(seed=seed, condition=condition, status=job['status'],
            score=job.get('score'), failure=job.get('result', {}).get('failure'),
            initial_check=job.get('initial_check'), root=job['root']))
    return dict(source_sha=sha, registered=18, recorded=len(jobs),
        complete=len(jobs)==18 and all(c['measured']==6 for c in conditions.values()),
        scope='fresh same-seed DEV; full trajectories have unequal exposure; paired RMSE uses common elapsed prefix',
        model_calls=0, vm_cost='not measured', conditions=conditions, runs=compact,
        common_horizons=pairs, receipt_sources=receipts)


if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True)
    p.add_argument('--sha',required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();result=aggregate(a.root,a.sha)
    a.output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps(dict(complete=result['complete'],recorded=result['recorded'],
                         conditions=result['conditions']),allow_nan=False))
