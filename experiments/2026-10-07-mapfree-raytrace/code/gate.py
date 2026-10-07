"""Exact original five thresholds, new registered M/N identifiers only."""
from collections import Counter
import numpy as np
from common import CRITERIA

def summary(rows,boundary):
    expected={(f's{i}',s,seed) for i in range(1,9) for s in ('M','N') for seed in (7701,7702)}
    groups={c:[r for r in rows if r['condition']==c] for c in ('static_map','own_frontier')}
    complete=all(len(g)==32 and {(r['scenario'],r['start'],r['seed']) for r in g}==expected for g in groups.values())
    aggregates={}
    for condition,g in groups.items():
        success=[r for r in g if r['status']=='B_confirmed']
        med=lambda values:float(np.median(values)) if values else None
        aggregates[condition]=dict(n=len(g),true_B=len(success),false_B=sum(r['status']=='B_false_confirmed' for r in g),
            coverage_median=med([r['coverage'] for r in g]),first_B_time_s=med([r['first_B']['time_s'] for r in success]),
            first_B_distance_m=med([r['first_B']['distance_m'] for r in success]),
            end_time_s=med([r['time_s'] for r in g]),end_distance_m=med([r['distance_m'] for r in g]),
            collisions=sum(r['collisions'] for r in g),wrong_doors=sum(r['wrong_door_attempts'] for r in g),
            false_passage=sum(r['false_candidate_passage_attempts'] for r in g),door_attempts=sum(r['door_attempts'] for r in g),
            statuses=dict(Counter(r['status'] for r in g)),
            max_end_pose_error_m=max((r['end_position_error_m'] for r in g),default=None))
    pairs={}
    for r in rows:pairs.setdefault((r['scenario'],r['start'],r['seed']),{})[r['condition']]=r
    d,t=[],[]
    for pair in pairs.values():
        if len(pair)==2 and all(r['status']=='B_confirmed' for r in pair.values()):
            a,b=pair['own_frontier']['first_B'],pair['static_map']['first_B']
            d.append(a['distance_m']/max(1e-9,b['distance_m']))
            t.append(a['time_s']/b['time_s'])
    paired=dict(common_successes=len(d),distance_ratio=float(np.median(d)) if d else None,
                time_ratio=float(np.median(t)) if t else None)
    own=aggregates['own_frontier']
    checks=dict(boundary=bool(boundary and complete),B_confirmation=own['true_B']/32>=.8 and own['false_B']==0,
        efficiency=bool(d and paired['distance_ratio']<=2 and paired['time_ratio']<=2),
        coverage=own['coverage_median'] is not None and own['coverage_median']>=.4,
        safety=own['collisions']==0 and own['wrong_doors']==0 and own['false_passage']==0 and own['door_attempts']>=1)
    return dict(conditions=aggregates,paired=paired,checks=checks,criteria_passed=sum(checks.values()),
                passed=all(checks.values()),criteria=CRITERIA,complete=complete,
                pose_condition='oracle_gt_pose_v1',noisy_runs=0,physics=0,model_calls=0)
