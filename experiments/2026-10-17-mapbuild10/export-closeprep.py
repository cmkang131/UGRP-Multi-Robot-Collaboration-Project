"""One-shot archival and own-lease release; refuses existing export directory.

Compresses only owned result JSON after roundtrip SHA checks. Never stops a VM.
"""
import argparse,datetime,hashlib,json,os,re,shutil,subprocess
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--host',choices=['gcp3','gcp5'],required=True);a=p.parse_args();b=Path('/home/ugrp/ugrp-sim');o=b/'ops-reviews/mapbuild10';dest=o/'export-final';dest.mkdir(exist_ok=False)
def raw(p):return p.read_bytes() if p.exists() else subprocess.check_output(['zstd','-qdc',str(p)+'.zst'])
def sha(p):return hashlib.sha256(raw(p)).hexdigest()
def read(p):return json.loads(raw(p))
def dump(p,x):p.write_text(json.dumps(x,indent=2,allow_nan=False)+'\n')
export=[]
def copy(p,name):
 data=raw(p);original=hashlib.sha256(data).hexdigest()
 if len(data)>65536 and p.suffix=='.json':
  j=json.loads(data)
  if 'aggregates' in j:
   keys=['stream','mode','trials','converged_trials','wrong_converged_trials','offline_pass_trials','final_handoff_pass_trials','final_xy_m','final_yaw_deg','off_final_xy_m','off_final_yaw_deg']
   j={k:v for k,v in j.items() if k!='aggregates'}|dict(aggregates=[{k:r[k] for k in keys} for r in j['aggregates']],export_projection=True)
   data=(json.dumps(j,indent=2)+'\n').encode()
  else:raise ValueError('NOT_A_SMALL_SUMMARY:'+str(p))
 (dest/name).write_bytes(data);export.append(dict(file=name,source=str(p),source_sha256=original,local_sha256=hashlib.sha256(data).hexdigest(),bytes=len(data)))
v='v2' if a.host=='gcp5' else 'v3';field=o/('field-7f2f1baae-'+v);assert read(field/'exit.json')['status']=='COMPLETE'
copy(field/'exit.json','field-exit.json')
works=[('mapbuild10-rgb-field-legacy-'+v,'field-legacy')]
if a.host=='gcp5':works += [('mapbuild10-public-baseline-v2','public-baseline'),('mapbuild10-public-rgb-field-v2','public-field')]
for run,prefix in works:
 root=b/'runs'/run
 for n in ['summary.json','compact-summary.json','phase-summary.json','rejection_table.json','final-integrity.json']:
  copy(root/n,prefix+'-'+n)
 for n in ['queue.json','stack.json']:copy(field/run/n,prefix+'-'+n)
copy(Path('/tmp/mapbuild10-field-run-v2.py' if a.host=='gcp5' else '/tmp/mapbuild10-field-run-v3.py'),'field-run.py')
rawchecks=[];archives=[]
if a.host=='gcp5':
 r=b/'runs/mapbuild10-long-round1';long=o/'long-round1-v2'
 for n,pth in [('physical-summary.json',r/'unloaded-v2/summary.json'),('physical-rejection_table.json',r/'unloaded-v2/rejection_table.json'),('physical-events.json',r/'unloaded-v2/events.json'),('physical-scene.json',r/'unloaded-v2/scene.json'),('public-start-zone.json',r/'unloaded-v2/public-start-zone.json'),('physical-input-audit.json',r/'unloaded-v2/teacher-input-audit.json'),('recording1-summary.json',r/'unloaded/summary.json'),('recording1-stop.json',r/'unloaded/SUPERVISOR_STOP.json'),('post-summary.json',long/'score-with-plots/summary.json'),('post-rejection_table.json',long/'score-with-plots/rejection_table.json'),('post-prediction-seal.json',long/'score-with-plots/prediction-seal.json'),('post-SHA256SUMS.json',long/'score-with-plots/SHA256SUMS.json'),('camera-transition-summary.json',long/'camera-transition/summary.json'),('field-adapter-summary.json',field/'adapter-audit/summary.json'),('queue-physical.json',long/'queue.json'),('stack-physical.json',long/'stack-with-xml.json'),('admission-main.json',long/'admission-main-efc484ad5.json'),('stack-main.json',long/'stack-main-efc484ad5.json')]:copy(pth,n)
 for name in ['unloaded','unloaded-v2']:
  root=r/name;manifest=read(root/'SHA256SUMS.json');bad=[n for n,h in manifest.items() if sha(root/n)!=h]
  if bad:raise ValueError('RAW_CHANGED:'+str(bad))
  rawchecks.append(dict(raw=str(root),files=len(manifest),mismatch=bad,manifest_sha256=sha(root/'SHA256SUMS.json')))
 assert sha(long/'score/frame-errors.json')==sha(long/'score-with-plots/frame-errors.json')
 for idx in [1,125,317,380]:copy(r/f'unloaded-v2/own-rgb/r1-{idx:05d}.jpg',f'selected-r1-{idx:05d}.jpg')
 for root in [r,o/'long-round1',long,field/'adapter-audit']:
  for pth in sorted(root.rglob('*.json')):
   if not pth.is_file() or pth.is_symlink() or pth.stat().st_size<=65536:continue
   h=sha(pth);z=Path(str(pth)+'.zst')
   if not z.exists():subprocess.run(['zstd','-q','-T1',str(pth),'-o',str(z)],check=True)
   if hashlib.sha256(subprocess.check_output(['zstd','-qdc',str(z)])).hexdigest()!=h:raise ValueError('ARCHIVE_CHANGED')
   archives.append(dict(original=str(pth),sha256=h,compressed=str(z),compressed_sha256=hashlib.sha256(z.read_bytes()).hexdigest()));pth.unlink()
 dump(dest/'raw-archive.json',archives)
parity=None
if a.host=='gcp5':
 import math
 pp=read(b/'runs/mapbuild10-public-baseline-v2/predictions/public-r1-coarse-000.json')['rows'];tt=read(b/'runs/mapbuild10-long-round1/unloaded-v2/online-trajectory.json')
 xy=[];yy=[];missing=[]
 for r,z in zip(pp,tt):
  u=r['candidate'];v=z['map_event']['absolute_proposal']
  if (u is None)!=(v is None):missing.append(r['frame_id'])
  if u is not None and v is not None:
   xy.append(max(abs(u[0]-v[0]),abs(u[1]-v[1])));d=u[2]-v[2];yy.append(abs(math.atan2(math.sin(d),math.cos(d))))
 parity=dict(frames=len(pp),presence_mismatch=missing,max_abs_xy_component_m=max(xy),max_abs_yaw_rad=max(yy))
# MC finalizers already verify every input/prediction/source/GT and lossless archives.
dump(dest/'retrieval-manifest.json',dict(host=a.host,export=export,raw_checks=rawchecks,public_trial0_online_parity=parity,plot_addition_frame_errors_identical=a.host=='gcp5',verified_at=datetime.datetime.now(datetime.timezone.utc).isoformat()))
selfpid=os.getpid();procs=[]
for row in subprocess.check_output(['ps','-u','ugrp','-o','pid=,ppid=,comm='],text=True).splitlines():
 x=row.split(None,2)
 if len(x)==3 and int(x[0])!=selfpid and (x[2].startswith('python') or 'mujoco' in x[2] or 'ffmpeg' in x[2]):procs.append(dict(pid=int(x[0]),ppid=int(x[1]),comm=x[2]))
gpu=subprocess.check_output(['nvidia-smi','--query-compute-apps=pid,process_name,used_memory','--format=csv,noheader'],text=True).strip()
lease=b/'leases/mapbuild10.json';assert read(lease)['task']=='mapbuild10';lease.unlink();others=[];stale=[]
for x in (b/'leases').iterdir():
 if x.name=='.warp9-claim.lock' and x.stat().st_size==0 and subprocess.run(['fuser',str(x)],capture_output=True).returncode==1:stale.append(x.name)
 else:others.append(x.name)
close=dict(host=a.host,other_leases=others,other_user_python_mujoco_ffmpeg=procs,gpu_processes=gpu,own_lease_removed=True,preserved_approved_stale_locks=stale,safe_to_stop=not(others or procs or gpu),checked_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
dump(dest/'close-check.json',close);dump(dest/'SHA256SUMS.json',{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in dest.iterdir() if p.is_file()});print(json.dumps(close),flush=True)
