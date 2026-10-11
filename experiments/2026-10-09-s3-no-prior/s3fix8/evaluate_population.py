import hashlib,importlib.util,json
from pathlib import Path
import numpy as np
R=Path('/Users/changmin/projects/ugrp/outputs/s3fix8-20261010');raw=Path('/Users/changmin/projects/ugrp/outputs/goal-route-motion-audit-v1/seed55001')
spec=importlib.util.spec_from_file_location('prior_eval',Path('experiments/2026-10-09-s3-no-prior/s3fix6/evaluate.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
frames=m.rows(raw/'robots/r3/frames.jsonl');span=frames[-1]['sim_time']-frames[0]['sim_time'];out={'table':{},'gt_evaluation_only':True,'sole_change':'RBPFOptions.particles=100 or500','input_sim_s':span,'timing_scope':m.read(R/'timing-scope.json'),'queue':m.read(R/'population-queue.json')}
for n in (100,500):
 path=R/f'population-{n}';v=m.own(path,raw);run=m.read(path/'result.json');perf=m.read(path/'population.json');cov=np.array([p['covariance'] for p in m.rows(path/'frontend-covariances.jsonl')])[:,:2,:2];eig=np.linalg.eigvalsh(cov);audit=perf['audit']
 v.update(particles=n,min_xy_eigenvalue=float(eig[:,0].min()),covariance_floor_fraction=float(np.mean(eig[:,1]<=1.01e-10)),min_unique_after=min(x['unique_after'] for x in audit),resample_checks=len(audit),median_ess_before=float(np.median([x['ess_before'] for x in audit])),wall_s=perf['wall_s'],cpu_s=perf['cpu_s'],wall_per_input_sim=perf['wall_s']/span,cpu_per_input_sim=perf['cpu_s']/span,peak_rss_bytes=perf['peak_rss_bytes'],loadavg_start=perf['loadavg_start'],loadavg_end=perf['loadavg_end'],original_frontend_equal=run['original_frontend_equal'],original_proposals_equal=run['original_proposals_equal'],original_contacts_equal=run['original_contacts_equal'],receipt_sha256=m.sha(path/'result.json'),population_sha256=m.sha(path/'population.json'))
 out['table'][str(n)]=v
b,n=out['table']['100'],out['table']['500'];out['selection']=dict(consistent_with_population_shortage=(n['over_3sigma_fraction']<b['over_3sigma_fraction'] and n['xy_rmse_m']<=b['xy_rmse_m'] and n['final_error_m']<=b['final_error_m']),s3_adoption=False,thresholds_changed=False,wall_ratio=n['wall_s']/b['wall_s'],cpu_ratio=n['cpu_s']/b['cpu_s'],scope='one development input, fixed issued commands; not a physical success or universal cause')
assert out['queue']['adapter_before']==out['queue']['adapter_after']
(R/'population-comparison.json').write_text(json.dumps(out,indent=2,allow_nan=False)+'\n');print(json.dumps(out,indent=2))
