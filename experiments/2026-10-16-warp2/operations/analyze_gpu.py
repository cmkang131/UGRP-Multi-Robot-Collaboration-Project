"""gcp2 only read-only reconciliation; running jobs never become complete."""
from pathlib import Path
import json,hashlib,subprocess,sys
r=Path('/home/ugrp/ugrp-sim/runs/warp2');records=[]
for round_name in ('r1-70553d2f','r2-54563a38','r3-521f2585'):
 root=r/round_name
 if not (root/'jobs.json').exists():continue
 for job in json.loads((root/'jobs.json').read_text()):
  out=Path(job['out']);p=out/'summary.json';s=json.loads(p.read_text()) if p.exists() else None
  status='running' if 'ended' not in job else ('complete' if job.get('exit')==0 else 'supervisor_stop_or_HOST_ERROR')
  if 'ended' not in job and (root/'cleanup.json').exists():
   status='complete' if s and s.get('status')=='complete' else 'supervisor_stop_or_HOST_ERROR'
  row=dict(round=round_name,job=job['name'],status=status,raw=str(out),command=job['command'],exit=job.get('exit'),summary_sha256=hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None)
  stop=out/'SUPERVISOR_STOP_NOT_BATCHABLE.json'
  if stop.exists():row.update(supervisor=json.loads(stop.read_text()),physical_failure_claim=False)
  if s:
   row.update(kind='initialization_only' if s.get('status') in ('compiled_export_only','transport_preflight_only') else ('fixed_work_prefix' if job['name'].startswith('prefix-') else 'full_teacher'),raw_status=s.get('status'))
   row.update(source_sha=s['source_sha'],backend=s['physics_backend'],host=s['host'],counts=s.get('counts'),worlds=s.get('worlds'),aggregate_completed_sim_s=s.get('aggregate_completed_sim_s'),
    summary_wall_s=s.get('wall_s'),timing=s.get('timing'),scope=s.get('scope'),native_initialization_sim_s=s.get('native_initialization_sim_s'),rollout_physics_steps=s.get('rollout_physics_steps'))
   checked=0;bad=[]
   if status!='running':
    for rel,sha in s.get('sha256',{}).items():
     f=out/rel;checked+=1
     if hashlib.sha256(f.read_bytes()).hexdigest()!=sha:bad.append(str(f))
   row['sha256_check']=dict(files=checked,mismatches=bad,scope='completed file manifest only' if status!='running' else 'not checked while writing')
   if status=='complete' and s.get('aggregate_completed_sim_s',0)>0:
    end=job.get('ended',p.stat().st_mtime);wall=end-job['started'];sim=s['aggregate_completed_sim_s'];row['time_basis']='coordinator process return' if 'ended' in job else 'final summary file persistence minus coordinator job start; coordinator canceled after this completed child';row.update(batch_wall_s=wall,sim_s_per_wall_s=sim/wall,sim_s_per_usd_estimate=3600*sim/wall/s['hourly_usd'],price_hourly_usd=s['hourly_usd'],price_basis=s['price_basis'])
  records.append(row)
r3=r/'r3-521f2585'
if (r3/'cleanup.json').exists():
 observed={x['job'] for x in records if x['round']=='r3-521f2585'}
 for name in ('prefix-n16','prefix-n64','prefix-n256','known-six-n16'):
  if name not in observed:records.append(dict(round='r3-521f2585',job=name,status='unstarted',raw=str(r3/name),physical_failure_claim=False))
result=dict(schema='ugrp.warp2.gpu_reconciliation.v1',records=records,backends_pooled=False,
 allocation=json.loads((r/'allocation.json').read_text()),
 scope='completed full teacher trials, completed fixed-work prefixes, initialization exports and supervised interruptions are separate populations; VM price estimates are not billing')
(r/'analysis').mkdir(exist_ok=True);(r/'analysis/gpu-reconciliation.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps([dict(round=x['round'],job=x['job'],status=x['status'],counts=x.get('counts'),throughput=x.get('sim_s_per_wall_s')) for x in records],indent=2))
