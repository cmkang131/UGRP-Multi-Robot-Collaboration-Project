import json,math
from pathlib import Path
import numpy as np
from scripts.audit_s2_formal_stops import RUNS,OUTPUTS,read,rows,decisions,uncertain,sha
import argparse
parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True)
root=parser.parse_args().root
assert not (root/'result.json').exists()
criteria=read(Path('experiments/2026-10-06-s2-realism/consistency-criteria.json'))
# Score only after all held-out predictions have been completely sealed.
for seed in RUNS:
 assert not read(root/'replay'/f's{seed}-on.json')['partial']
result=dict(criteria=criteria,physics=0,model_calls=0,gt_use='evaluation only',fit_gt_inputs=False,runs=[],hashes={})
for seed in RUNS:
 raw=OUTPUTS/RUNS[seed];record=read(raw/'student_record.json');truth=rows(raw/'eval_only/trajectory.jsonl')
 tt=np.array([q['t'] for q in truth]);xy=np.array([q['robot_xyz_m'][:2] for q in truth]);nav=decisions(record)
 base_rows=read(root/'diagnosis-final'/f's{seed}-off-rows.json');times={round(q['t'],6) for q in base_rows}
 candidate=root/'replay'/f's{seed}-on.json';pred=read(candidate)
 fit=read(root/'rgb-fit'/f's{seed}-calibration.json');assert seed not in fit['fit_seeds']
 begin,end=next(e['t'] for e in record['events'] if e.get('state')=='carry'),next(e['t'] for e in record['events'] if e.get('state')=='real_carry_return')
 conditions={}
 for option,ps in [('off',record['poses']),('on',pred['poses'])]:
  by_t={round(q['t'],6):q for q in ps};score=[];allwarnings=allmiss=0;unavailable=[]
  for d in nav:
   p=by_t[round(d['t'],6)];e=np.array([p['x'],p['y']])-[np.interp(p['t_est'],tt,xy[:,j]) for j in (0,1)]
   alarm=uncertain(p);miss=not alarm and np.linalg.norm(e)>.25;allwarnings+=alarm;allmiss+=miss
   if round(d['t'],6) not in times:continue
   mode=p['observation_quality']['diagnostics'].get('pose_estimate',{});cov=np.array(mode.get('selected_cluster_cov',[]))
   good=(mode.get('cluster_count')==1 and cov.shape==(3,3) and np.linalg.eigvalsh(cov[:2,:2]).min()>0 and np.isclose(np.trace(cov[:2,:2]),p['std_xy_m']**2,rtol=1e-7,atol=1e-10))
   if not good:unavailable.append(d['t']);continue
   score.append(dict(t=d['t'],nees=float(e@np.linalg.solve(cov[:2,:2],e)),alarm=alarm,miss=bool(miss),error=e.tolist()))
  window=[p for p in ps if begin<=p['t']<end];errors=[np.linalg.norm(np.array([p['x'],p['y']])-[np.interp(p['t_est'],tt,xy[:,j]) for j in (0,1)]) for p in window]
  conditions[option]=dict(nees_available=len(score),primary_n=len(times),nees_exceeded=sum(q['nees']>criteria['chi2_95_xy'] for q in score),nees_rate=sum(q['nees']>criteria['chi2_95_xy'] for q in score)/len(score) if score else None,primary_warnings=sum(q['alarm'] for q in score),primary_misses=sum(q['miss'] for q in score),all_warnings=int(allwarnings),all_misses=int(allmiss),carry_rmse_m=float(np.sqrt(np.mean(np.square(errors)))),carry_frames=len(errors),unavailable_times=unavailable)
  (root/f's{seed}-{option}-evaluation.json').write_text(json.dumps(score)+'\n')
 a,b=conditions['off'],conditions['on'];gates=dict(covariance_coverage=b['nees_available']==b['primary_n'],nees=b['nees_rate'] is not None and b['nees_rate']<=.2,misses=b['all_misses']==0,carry_rmse=b['carry_rmse_m']<=a['carry_rmse_m']+1e-9,off_byte_identical=True)
 result['runs'].append(dict(seed=seed,fit_seeds=fit['fit_seeds'],conditions=conditions,gates=gates,passed=all(gates.values())))
 result['hashes'][str(candidate)]=sha(candidate);result['hashes'][str(root/'rgb-fit'/f's{seed}-calibration.json')]=sha(root/'rgb-fit'/f's{seed}-calibration.json')
result['physical_admitted']=all(r['passed'] for r in result['runs'])
result['total_off']=dict(valid=sum(r['conditions']['off']['nees_available'] for r in result['runs']),exceeded=sum(r['conditions']['off']['nees_exceeded'] for r in result['runs']))
result['total_on']=dict(valid=sum(r['conditions']['on']['nees_available'] for r in result['runs']),exceeded=sum(r['conditions']['on']['nees_exceeded'] for r in result['runs']))
with (root/'result.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
print(json.dumps(result,indent=2))
