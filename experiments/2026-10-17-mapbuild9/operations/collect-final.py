"""gcp5 summary-only export; raw arrays/images stay on original VM."""
from pathlib import Path
import datetime
import hashlib
import json
import subprocess

base=Path('/home/ugrp/ugrp-sim');runs=base/'runs/mapbuild9';ops=base/'ops-reviews/mapbuild9';out=ops/'export-final';out.mkdir(exist_ok=False)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())
def dump(p,v):p.write_text(json.dumps(v,indent=2,allow_nan=False)+'\n')
rows=[];funnels=[];seals=[];exports=[]
for p in sorted(runs.glob('eval-*/summary.json')):
 a=read(p);name=p.parent.name;target=out/(name+'.json');target.write_bytes(p.read_bytes());exports.append(target)
 pred=Path(a['prediction']);s=read(pred/'summary.json');f=read(pred/'rejection_table.json')
 rows.append(dict(name=name,raw=a['raw'],prediction=a['prediction'],status=a['status'],frames=a['frames'],
  ready_updates=a['ready_updates'],wrong_convergence_updates=a['wrong_convergence_updates'],convergence_sim_s=a['convergence_sim_s'],
  convergence_own_estimated_path_m=a['convergence_own_estimated_path_m'],off=a['off_all'],candidate_absolute_diagnostic=a['amcl_candidate_absolute_all'],
  after_convergence=a['since_first_convergence'],phases=a['phases'],requirements_sha256=a['requirements_sha256'],source_summary_sha256=sha(p),
  own_map_frames=s['own_map_frames'],motion_sources=s.get('motion_sources'),full_posterior=s['full_posterior']))
 funnels.append(dict(name=name,raw=a['raw'],prediction=a['prediction'],**f))
for p in sorted(runs.glob('*/prediction-seal.json')):
 s=read(p);seals.append(dict(path=str(p),sha256=sha(p),inputs=len(s['input_sha256']),predictions=len(s['prediction_sha256']),
  input_mismatch=[n for n,h in s['input_sha256'].items() if sha(Path(n))!=h],prediction_mismatch=[n for n,h in s['prediction_sha256'].items() if sha(p.parent/n)!=h]))
raw=[]
for i in range(1,4):
 p=base/f'runs/mapbuild8/recording-r{i}';m=read(p/'SHA256SUMS.json');raw.append(dict(raw=str(p),files=len(m),manifest_sha256=sha(p/'SHA256SUMS.json'),mismatch=[n for n,h in m.items() if sha(p/n)!=h]))
dump(out/'comparison.json',dict(rows=rows,physical_runs=0,unique_recordings=3,unique_frames=1044,all_status='NOT_READY'))
dump(out/'funnels.json',dict(cohorts=funnels,scope='same raw frames repeated per setting; never pooled'))
dump(out/'final-integrity.json',dict(time=datetime.datetime.now(datetime.timezone.utc).isoformat(),raw=raw,seals=seals,
 source_shas={str(p):subprocess.check_output(['git','-C',str(p),'rev-parse','HEAD'],text=True).strip() for p in [base/'src/mapbuild9-offline-v1',base/'src/mapbuild9-profiles-d7cb236f6',base/'src/mapbuild9-product-3d3050c87',base/'src/mapbuild9-product-slots-v2']}))
for p in ops.glob('*queue*.json'):
 (out/p.name).write_bytes(p.read_bytes())
for p in ops.glob('*stack*.json'):
 (out/p.name).write_bytes(p.read_bytes())
for name in ['tests.txt','product-tests.txt','product-slots-tests.txt','native-parity.json','native-parity-full.json','likelihood-audit-r3-sealed.json','batch.log','batch-profiles.log']:
 p=ops/name
 if p.exists():(out/name).write_bytes(p.read_bytes())
for i in (1,3):
 p=base/f'runs/mapbuild8/review-r{i}/review-3x.mp4'
 data=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration,size','-show_entries','stream=nb_frames','-of','json',str(p)]))
 dump(out/f'playback-r{i}.json',dict(path=str(p),sha256=sha(p),ffprobe=data))
leases=list((base/'leases').iterdir());processes=subprocess.run(['pgrep','-a','-u','ugrp','-x','python[0-9.]*|mujoco|ffmpeg'],capture_output=True,text=True).stdout
# This collector PID is explicitly owned by mapbuild9; only it may be ignored.
import os
remaining=[line for line in processes.splitlines() if not line.startswith(str(os.getpid())+' ')]
dump(out/'close-load-check.json',dict(time=datetime.datetime.now(datetime.timezone.utc).isoformat(),collector_pid=os.getpid(),leases=[str(p) for p in leases],
 all_python_processes=processes,other_python_processes=remaining,gpu=subprocess.check_output(['nvidia-smi','--query-gpu=utilization.gpu,memory.used','--format=csv,noheader'],text=True)))
dump(out/'export-sha256.json',{p.name:sha(p) for p in out.iterdir() if p.is_file()})
print(json.dumps(dict(export=str(out),summaries=len(rows),raw_files=sum(r['files'] for r in raw),prediction_seals=len(seals),other_processes=remaining,leases=[str(p) for p in leases])))
