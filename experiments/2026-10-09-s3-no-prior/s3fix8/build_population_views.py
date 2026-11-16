import hashlib,json
from pathlib import Path
R=Path('/Users/changmin/projects/ugrp/outputs/s3fix8-20261010');src=R/'population-comparison.json';c=json.loads(src.read_text());out=R/'population-views';out.mkdir(exist_ok=False)
for label,row in c['table'].items():
 d=out/('N'+label);d.mkdir();v=dict(schema='ugrp.offline_audit_view.v1',derived_view_only=True,source_sha=c['queue']['source_sha'],seed=55001,case='55001',condition='particles-'+label,policy='population-only',outcome='baseline' if label=='100' else 'one-input-support',offline_source=dict(path=str(src),sha256=hashlib.sha256(src.read_bytes()).hexdigest()),offline_scalar_scope='One saved 1341-frame own-RGB/issued-command replay; GT only in evaluation; eTPinvE diagnostic uses highest-weight point and mixture covariance, not Gaussian NEES certification',offline_scalars={'offline/'+k:x for k,x in row.items() if isinstance(x,(int,float)) and not isinstance(x,bool)},hparam_metrics=['offline/xy_rmse_m','offline/final_error_m','offline/over_3sigma_fraction','offline/wall_s','offline/cpu_s'],texts={'evaluation/selection':c['selection'],'provenance/timing_scope':c['timing_scope']})
 v['offline_scalars']['offline/physical_runs']=0
 (d/'result.json').write_text(json.dumps(v,indent=2)+'\n')
print(str(out))
