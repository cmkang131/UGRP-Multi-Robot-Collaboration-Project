import argparse,datetime,hashlib,json,os,platform,subprocess,sys,traceback
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--host',choices=['gcp5','gcp3'],required=True);a=p.parse_args()
b=Path('/home/ugrp/ugrp-sim');s=b/'src/mapbuild10-7f2f1baae';o=b/'ops-reviews/mapbuild10/field-7f2f1baae-v3';o.mkdir(exist_ok=False)
if not platform.node().startswith('ugrp-act-l4-'+a.host):raise ValueError('ORIGINAL_VM_ONLY')
head=subprocess.check_output(['git','-C',str(s),'rev-parse','HEAD'],text=True).strip();(s/'SOURCE_SHA').write_text(head+'\n')
lease=b/'leases/mapbuild10.json';lease.write_text(json.dumps(dict(task='mapbuild10',pid=os.getpid(),state='offline_field_MC20',start_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),expected_end='after sealed analysis/retrieval, no wall cap')))
py=str(b/'ugrp/.venv-warp/bin/python') if a.host=='gcp3' else '/home/ugrp/ugrp-rl1b-act-env/bin/python';cal=b/'ops-reviews/mapbuild9/own-noise-command-r1-r2.json';req=s/'experiments/2026-10-17-mapbuild8/requirements.json'
env=os.environ.copy();env.update(OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1')
def call(cmd):
 print(json.dumps(cmd),flush=True);subprocess.run(cmd,check=True,cwd=s,env=env)
def link(src,dst):
 dst.mkdir(exist_ok=False)
 for name in ['own-streams.json','own-seal.json','priors.json','prior-generation-eval-only.json']:
  orig=src/name
  if not orig.exists():orig=Path(str(orig)+'.zst')
  os.link(orig,dst/orig.name)  # read-only hardlink: zstd rejects symlink inputs by default
def run(name,profile,source=None,public=False):
 work=b/'runs'/name;ops=o/name;ops.mkdir()
 q=dict(flow='self_map',replay_of=str(source) if source else 'recorded public-start-box native-v7 input',source_sha=head,amcl_profile=profile,rejection_table=str(s/'experiments/2026-10-17-mapbuild10/field-prior-rejection_table.json'),host=a.host,project='ugrp-sim-e-1016' if a.host=='gcp5' else 'ugrp-sim-c-1016',account='changmin5781@gmail.com',trials=20,workers=4,physics_steps=0,render_calls=0,wall_cap=None,scope='old synthetic-prior cohort' if not public else 'actual public prior, one recording repeated particle seeds; no pooled accuracy')
 if a.host=='gcp3':q.update(adapter_counterexample_table=q['rejection_table'],rejection_table=str(b/'runs/mapbuild10-mc20/rejection_table.json'))
 (ops/'queue.json').write_text(json.dumps(q,indent=2));call(['python3',str(s/'scripts/check_current_stack.py'),str(ops/'queue.json'),'--output',str(ops/'stack.json')])
 base=[py,str(s/'scripts/mapbuild10_mc.py'),'--host',a.host,'--work',str(work),'--calibration',str(cal),'--requirements',str(req),'--queue',str(ops/'queue.json'),'--stack-check',str(ops/'stack.json'),'--amcl-profile',profile]
 if public and source is None:
  call(base+['--stage','prepare-own','--public-recording',str(b/'runs/mapbuild10-long-round1/unloaded-v2')]);call(base+['--stage','prepare-priors'])
 else:link(source,work)
 for stage in ['predict','score']:call(base+['--stage',stage])
 call([py,str(s/'scripts/mapbuild10_mc_finalize.py'),'--host',a.host,'--work',str(work),'--source',str(s),'--skip-likelihood-diagnostic'])
 return work
try:
 run('mapbuild10-rgb-field-legacy-v3','nav2_rgb_field_v1',b/'runs/mapbuild10-mc20')
 if a.host=='gcp5':
  original=run('mapbuild10-public-baseline-v2','nav2_defaults_v1',public=True)
  run('mapbuild10-public-rgb-field-v2','nav2_rgb_field_v1',original,public=True)
  call([py,str(s/'scripts/mapbuild10_field_audit.py'),'--source',str(s),'--input',str(b/'runs/mapbuild10-long-round1/unloaded-v2'),'--prediction',str(b/'ops-reviews/mapbuild10/long-round1-v2/score'),'--output',str(o/'adapter-audit')])
 result=dict(status='COMPLETE',source_sha=head,end_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
except BaseException as exc:
 traceback.print_exc();result=dict(status='FAILED',error=repr(exc),source_sha=head,end_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
finally:
 (o/'exit.json').write_text(json.dumps(result,indent=2));lease.write_text(json.dumps(dict(task='mapbuild10',pid=os.getpid(),state='analysis_retrieval_pending',result=result)))
 print(json.dumps(result),flush=True)
