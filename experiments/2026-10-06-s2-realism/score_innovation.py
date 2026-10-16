"""Evaluate sealed own-input replays with unchanged v44/v45 holdout gates."""
import importlib.util,json
from pathlib import Path
import numpy as np
from scripts.audit_s2_formal_stops import RUNS,OUTPUTS,read,rows,truth_at,wrap,sha
HERE=Path(__file__).resolve().parent
ROOT=OUTPUTS/'s2-innovation-v46-20261008'
spec=importlib.util.spec_from_file_location('previous_score',HERE/'score_bias_tempering.py')
previous=importlib.util.module_from_spec(spec);spec.loader.exec_module(previous)


def main():
    for seed in RUNS:
        for opt in ('baseline','candidate'):assert not read(ROOT/'replay'/f's{seed}-{opt}.json')['partial']
    result=dict(criteria=read(HERE/'innovation-criteria.json'),runs=[],physics_runs=0,
        gt_use='posthoc evaluation only; no new fit; frozen v45 two-run forward scale tables',hashes={})
    for seed in RUNS:
        record,at,begin,end=previous.truth(seed);times={round(q['t'],6) for q in read(previous.OLD/f's{seed}-off-rows.json')}
        tr=rows(OUTPUTS/RUNS[seed]/'eval_only/trajectory.jsonl')
        case=dict(seed=seed,fit_seeds=read(OUTPUTS/'s2-bias-tempering-v45-20261008/fit'/f's{seed}-calibration.json')['fit_seeds'],conditions={})
        for opt in ('baseline','candidate'):
            path=ROOT/'replay'/f's{seed}-{opt}.json';pred=read(path);m,detail=previous.metrics(pred['poses'],record,at,begin,end,times)
            approach=[p for p in pred['poses'] if 10<=p['t']<begin]
            es=np.array([np.array([p['x'],p['y']])-at(p['t_est']) for p in approach])
            m.update(approach_bias_xy_m=es.mean(0).tolist(),approach_rmse_m=float(np.sqrt(np.mean(np.sum(es**2,axis=1)))))
            m['updates']=pred['amcl']['updates'];case['conditions'][opt]=m
            (ROOT/f's{seed}-{opt}-evaluation.json').write_text(json.dumps(detail)+'\n');result['hashes'][str(path)]=sha(path)
        off=read(ROOT/'replay'/f's{seed}-baseline.json');cached=read(OUTPUTS/'s2-bias-tempering-v45-20261008/replay'/f's{seed}-combined.json')
        identical=(json.dumps(off['poses']).encode()==json.dumps(cached['poses']).encode() and off['particle_trajectory_sha256']==cached['particle_trajectory_sha256'])
        m=case['conditions']['candidate'];gate=dict(nees=m['nees_rate'] is not None and m['nees_rate']<=.2,
            covariance_coverage=m['nees_available']==m['primary_n'],misses=m['all_misses']==0,
            carry_rmse=m['carry_rmse_m']<=case['conditions']['baseline']['carry_rmse_m']+1e-9,off_bytes=identical)
        case['gates']=dict(**gate,passed=all(gate.values()))
        measured=[]
        for row in read(ROOT/'replay'/f's{seed}-candidate.json')['slip']['rows']:
            if not row.get('unloaded_coarse_vo'):continue
            item={k:v for k,v in row.items() if k!='intervals'}
            counts={}
            for interval in row.get('intervals',[]):counts[interval['status']]=counts.get(interval['status'],0)+1
            item['interval_status_counts']=counts
            if 'end' in row:
                a,b=(np.array(truth_at(tr,t)) for t in (row['t'],row['end']));c,s=np.cos(a[2]),np.sin(a[2])
                dxy=(b[:2]-a[:2])@np.array([[c,-s],[s,c]]);actual=np.r_[dxy,wrap(b[2]-a[2])]
                item['eval_actual_delta']=actual.tolist()
                for name in ('expected_delta','applied_delta'):
                    if name in row:item['eval_'+name+'_error']=(np.array(row[name])-actual).tolist()
            measured.append(item)
        case['ground_measurements']=measured;result['runs'].append(case)
    result['physical_admitted']=all(q['gates']['passed'] for q in result['runs'])
    result['totals']={opt:dict(nees_exceeded=sum(q['conditions'][opt]['nees_exceeded'] for q in result['runs']),
        nees_available=sum(q['conditions'][opt]['nees_available'] for q in result['runs']),warnings=sum(q['conditions'][opt]['all_warnings'] for q in result['runs']),
        misses=sum(q['conditions'][opt]['all_misses'] for q in result['runs'])) for opt in ('baseline','candidate')}
    with (ROOT/'result.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    (HERE/'innovation-result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='runs'},indent=2))
    for r in result['runs']:print(r['seed'],r['conditions'],r['gates'])

if __name__=='__main__':main()
