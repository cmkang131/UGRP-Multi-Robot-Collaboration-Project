"""Posthoc phase bias explanation; no correction or admission-threshold change."""
import argparse,json
from collections import Counter
from pathlib import Path
import numpy as np
from scripts.audit_s2_formal_stops import RUNS,OUTPUTS,read,sha


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);root=p.parse_args().root
    result=dict(scope='posthoc explanation only; means never supplied to filter',runs=[])
    for seed in RUNS:
        raw=read(OUTPUTS/RUNS[seed]/'student_record.json');begin=next(e['t'] for e in raw['events'] if e.get('state')=='carry');end=next(e['t'] for e in raw['events'] if e.get('state')=='real_carry_return')
        ev=read(root/f's{seed}-combined-evaluation.json');pred=root/'replay'/f's{seed}-combined.json';poses={round(q['t'],6):q for q in read(pred)['poses']};case=dict(seed=seed,phases={},prediction_sha256=sha(pred))
        for phase,qs in [('approach',[q for q in ev if q['t']<begin]),('carry',[q for q in ev if begin<=q['t']<end]),('place',[q for q in ev if q['t']>=end])]:
            e=np.array([q['error'] for q in qs]);cov=np.array([poses[round(q['t'],6)]['observation_quality']['diagnostics']['pose_estimate']['selected_cluster_cov'] for q in qs])[:,:2,:2]
            centered=e-e.mean(0);nees=np.einsum('ij,ijk,ik->i',centered,np.linalg.inv(cov),centered)
            case['phases'][phase]=dict(n=len(qs),nees_exceeded=sum(q['nees']>5.991464547107979 for q in qs),phase_demeaned_nees_exceeded=int(sum(nees>5.991464547107979)),bias_xy_m=e.mean(0).tolist(),mean_reported_xy_variance=np.diagonal(cov,axis1=1,axis2=2).mean(0).tolist())
        prior=read(root/'result.json')['runs'][list(RUNS).index(seed)]['conditions']['combined']['unavailable_times'];modes=[poses[round(t,6)]['observation_quality']['diagnostics']['pose_estimate'] for t in prior]
        case['comparison_unavailable']=dict(n=len(modes),cluster_counts=dict(Counter(q['cluster_count'] for q in modes)),max_mass_min=min((q['maximum_cluster_weight'] for q in modes),default=None),reason='v44 fixed single-cluster covariance comparison fails; reports still exist')
        result['runs'].append(case)
    with (root/'remaining-bias.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()
