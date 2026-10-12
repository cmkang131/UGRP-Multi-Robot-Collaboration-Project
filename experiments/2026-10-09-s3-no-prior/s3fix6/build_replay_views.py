"""Derived scalar-only views of the sealed saved-input comparison."""
import argparse,hashlib,json
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--comparison',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
c=json.loads(a.comparison.read_text());a.output.mkdir(parents=True,exist_ok=False)
source=dict(path=str(a.comparison.resolve()),sha256=hashlib.sha256(a.comparison.read_bytes()).hexdigest())
labels={'off':'B','effective_sqrt_v1':'C1','effective_mean_v1':'C2','effective_sqrt_alpha_v1':'C3'}
for option,table in c['table'].items():
    for case,row in table.items():
        scalars={'offline/'+k:v for k,v in row.items() if isinstance(v,(int,float)) and not isinstance(v,bool)}
        scalars['offline/physical_runs']=0
        scalars['gate/option_selected_for_s3_smoke']=int(option==c['smoke_option'])
        eligible=True if option=='off' else c['selection'][option]['eligible']
        view=dict(schema='ugrp.offline_audit_view.v1',derived_view_only=True,
            offline_source=source,offline_scalar_scope='Saved own-RGB/issued-command full-controller replay; reported belief including original termination behavior; GT only in separate evaluation; no new physical run',
            policy=labels[option],case=case,condition=option,source_sha=c['replay_receipts'][case.split('/')[0]+'-'+option]['source_sha'],
            seed=14201 if case.startswith('v') else int(case.split('/')[0]),
            outcome='baseline' if option=='off' else ('eligible' if eligible else 'rejected'),offline_scalars=scalars,
            hparam_metrics=['offline/xy_rmse_m','offline/final_error_m','offline/sigma_rms_m','offline/over_3sigma_fraction'],
            texts={'provenance/replay_admission':dict(arm_receipt=c['replay_receipts'][case.split('/')[0]+'-'+option],excluded=c['retained_arms_equivalence']['excluded_old_c3'],originals_preserved=True), 'evaluation/scope':dict(sigma_definition=row['sigma_definition'],selected=c['smoke_option'],selection_target='S3 v151 only; no own-map production admission',rule='No actual-error deterioration on any of eight trajectories; consistency improves',thresholds_changed=False)})
        dest=a.output/(case.replace('/','-')+'-'+labels[option]);dest.mkdir()
        (dest/'result.json').write_text(json.dumps(view,indent=2,allow_nan=False)+'\n')
print(json.dumps(dict(views=32,output=str(a.output))))
