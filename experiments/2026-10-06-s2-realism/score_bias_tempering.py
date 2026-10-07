"""Posthoc evaluation after own-input predictions seal; no fitting here."""
import argparse,json,math
from pathlib import Path
import numpy as np
from scripts.audit_s2_formal_stops import RUNS,OUTPUTS,read,rows,decisions,uncertain,sha
HERE=Path(__file__).resolve().parent
OLD=OUTPUTS/'s2-consistency-v44-20261008/diagnosis-final'
CONDITIONS=('off','scale','temper','combined')


def truth(seed):
    r=read(OUTPUTS/RUNS[seed]/'student_record.json');tr=rows(OUTPUTS/RUNS[seed]/'eval_only/trajectory.jsonl')
    tt=np.array([q['t'] for q in tr]);xy=np.array([q['robot_xyz_m'][:2] for q in tr])
    at=lambda t:np.array([np.interp(t,tt,xy[:,j]) for j in (0,1)])
    begin,end=next(e['t'] for e in r['events'] if e.get('state')=='carry'),next(e['t'] for e in r['events'] if e.get('state')=='real_carry_return')
    return r,at,begin,end


def metrics(poses,r,at,begin,end,times):
    by_t={round(q['t'],6):q for q in poses};score=[];warnings=misses=0;unavailable=[]
    for d in decisions(r):
        p=by_t[round(d['t'],6)];e=np.array([p['x'],p['y']])-at(p['t_est']);alarm=uncertain(p)
        miss=not alarm and np.linalg.norm(e)>.25;warnings+=alarm;misses+=miss
        if round(d['t'],6) not in times:continue
        mode=p['observation_quality']['diagnostics'].get('pose_estimate',{});cov=np.array(mode.get('selected_cluster_cov',[]))
        good=(mode.get('cluster_count')==1 and cov.shape==(3,3) and np.linalg.eigvalsh(cov[:2,:2]).min()>0 and np.isclose(np.trace(cov[:2,:2]),p['std_xy_m']**2,rtol=1e-7,atol=1e-10))
        if not good:unavailable.append(d['t']);continue
        score.append(dict(t=d['t'],nees=float(e@np.linalg.solve(cov[:2,:2],e)),alarm=alarm,miss=bool(miss),error=e.tolist()))
    errors=[np.linalg.norm(np.array([p['x'],p['y']])-at(p['t_est'])) for p in poses if begin<=p['t']<end]
    return dict(nees_available=len(score),primary_n=len(times),nees_exceeded=sum(q['nees']>5.991464547107979 for q in score),
        nees_rate=sum(q['nees']>5.991464547107979 for q in score)/len(score) if score else None,
        all_warnings=int(warnings),all_misses=int(misses),carry_rmse_m=float(np.sqrt(np.mean(np.square(errors)))),carry_frames=len(errors),unavailable_times=unavailable),score


def audit_measurements(root,condition):
    result=[]
    for seed in RUNS:
        r,at,begin,end=truth(seed);qs=read(root/'replay'/f's{seed}-{condition}-measurement.json')['measurements'];events=[]
        for q in qs:
            event={k:v for k,v in q.items() if k not in ('prior','posterior','resampled')}
            event['carry']=begin<=q['t']<end
            for stage in ('prior','posterior','resampled'):
                a=q[stage];e=np.array(a['mean'][:2])-at(q['t']);c=np.array(a['cov'])[:2,:2]
                event[stage]={**a,'error_m':float(np.linalg.norm(e)),
                    'nees':float(e@np.linalg.solve(c,e)) if np.linalg.eigvalsh(c).min()>1e-16 else None}
            event['trace_ratio']=q['posterior']['xy_trace']/q['prior']['xy_trace']
            event['ess_ratio']=q['posterior']['ess']/q['prior']['ess']
            events.append(event)
        case=dict(seed=seed,rows=events,groups={})
        for name,subset in [('all',events),('carry',[q for q in events if q['carry']]),('with_landmarks',[q for q in events if q['features']])]:
            if not subset:continue
            ratios=[q['trace_ratio'] for q in subset];corr=[q['log_score_correlation'] for q in subset if q['log_score_correlation'] is not None]
            valid=[q for q in subset if all(q[k]['nees'] is not None for k in ('prior','posterior'))]
            case['groups'][name]=dict(n=len(subset),covariance_shrink_count=sum(v<1 for v in ratios),median_trace_ratio=float(np.median(ratios)),
                median_ess_ratio=float(np.median([q['ess_ratio'] for q in subset])),minimum_posterior_ess=min(q['posterior']['ess'] for q in subset),
                median_posterior_ess=float(np.median([q['posterior']['ess'] for q in subset])),
                nees_worse_count=sum(q['posterior']['nees']>q['prior']['nees'] for q in valid),nees_available=len(valid),
                nees_prior_median=float(np.median([q['prior']['nees'] for q in valid])) if valid else None,
                nees_post_median=float(np.median([q['posterior']['nees'] for q in valid])) if valid else None,
                minimum_resampled_unique=min(q['resampled']['unique_poses'] for q in subset),
                median_log_score_correlation=float(np.median(corr)) if corr else None,correlation_n=len(corr))
        result.append(case)
    return dict(condition=condition,gt_use='posthoc evaluation only; scores and particle updates already sealed',runs=result)


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--diagnose-only',action='store_true');a=p.parse_args();root=a.root
    opts=('off',) if a.diagnose_only else CONDITIONS
    for seed in RUNS:
        for opt in opts:assert not read(root/'replay'/f's{seed}-{opt}.json')['partial']
    for opt in opts:
        target=root/f'measurement-diagnosis-{opt}.json'
        if target.exists():continue
        target.write_text(json.dumps(audit_measurements(root,opt),indent=2)+'\n')
    if a.diagnose_only:
        print(json.dumps([{k:v for k,v in q.items() if k!='rows'} for q in read(root/'measurement-diagnosis-off.json')['runs']],indent=2));return
    result=dict(criteria=read(HERE/'bias-tempering-criteria.json'),runs=[],physics=0,gt_use='scale fit in training runs only; all trajectory/NEES and heldout GT posthoc',hashes={})
    for seed in RUNS:
        r,at,begin,end=truth(seed);times={round(q['t'],6) for q in read(OLD/f's{seed}-off-rows.json')};case=dict(seed=seed,conditions={},gates={})
        off=read(root/'replay'/f's{seed}-off.json');cached=read(OUTPUTS/'s2-rotation-left-v42-20261008/replay'/f's{seed}-off.json')
        same=(json.dumps(off['poses']).encode()==json.dumps(cached['poses']).encode() and off['particle_trajectory_sha256']==cached['particle_trajectory_sha256'])
        fit=read(root/'fit'/f's{seed}-calibration.json');assert seed not in fit['fit_seeds'];case['fit_seeds']=fit['fit_seeds']
        for opt in CONDITIONS:
            path=root/'replay'/f's{seed}-{opt}.json';pred=read(path);m,detail=metrics(pred['poses'],r,at,begin,end,times);case['conditions'][opt]=m
            (root/f's{seed}-{opt}-evaluation.json').write_text(json.dumps(detail)+'\n');result['hashes'][str(path)]=sha(path)
            if opt!='off':
                gates=dict(covariance_coverage=m['nees_available']==m['primary_n'],nees=m['nees_rate'] is not None and m['nees_rate']<=.2,
                    misses=m['all_misses']==0,carry_rmse=m['carry_rmse_m']<=case['conditions']['off']['carry_rmse_m']+1e-9,off_byte_identical=same)
                case['gates'][opt]=dict(**gates,passed=all(gates.values()))
        result['runs'].append(case)
    result['admitted_conditions']=[opt for opt in CONDITIONS[1:] if all(q['gates'][opt]['passed'] for q in result['runs'])]
    result['physical_admitted']=bool(result['admitted_conditions'])
    result['totals']={opt:dict(nees_exceeded=sum(q['conditions'][opt]['nees_exceeded'] for q in result['runs']),
        nees_available=sum(q['conditions'][opt]['nees_available'] for q in result['runs']),
        misses=sum(q['conditions'][opt]['all_misses'] for q in result['runs']),warnings=sum(q['conditions'][opt]['all_warnings'] for q in result['runs'])) for opt in CONDITIONS}
    with (root/'result.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()
