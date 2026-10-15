import json,subprocess,math,collections,hashlib,statistics
from pathlib import Path
base=Path('/Users/changmin/projects/ugrp/outputs/gcp1-runs');sources=[];records=[];ns=0;bins=collections.defaultdict(list)

def read(p):
 if not p.exists():p=Path(str(p)+'.zst')
 b=subprocess.check_output(['zstd','-dc',str(p)]) if p.suffix=='.zst' else p.read_bytes()
 sources.append(dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),decoded_sha256=hashlib.sha256(b).hexdigest()));return b
for raw in sorted(base.glob('crate*/raw')):
 try:d=json.loads(read(raw/'result.json'))
 except FileNotFoundError:continue
 if not(d.get('cargo_scene_version')=='crate_mass_025_v1' and d.get('prefix_held')):sources.pop();continue
 ns+=1
 ev={round(r['t'],3):r for r in map(json.loads,read(raw/'eval-only.jsonl').splitlines())}
 for rid in ('r1','r2'):
  for r in map(json.loads,read(raw/f'teacher-{rid}.jsonl').splitlines()):
   if not r.get('holding_belief') or not any(r.get('wheels',[])):continue
   v=ev.get(round(r['t'],3));n=ev.get(round(r['t']+.1,3))
   if not v or not n:continue
   if not (all(min(x)>.5 for x in v.get('contacts',{}).values()) and v['crate']['min_z']>=.012):continue
   w=r['wheels'];axis='forward' if max(w)==min(w) else 'yaw' if w==[-w[1],w[1],-w[1],w[1]] else 'lateral' if w==[-w[1],w[1],w[1],-w[1]] else 'mixed'
   if axis=='mixed':continue
   a=v['robots'][rid]['pose'];b=n['robots'][rid]['pose'];dx=b[0]-a[0];dy=b[1]-a[1]
   motion=abs(math.atan2(math.sin(b[2]-a[2]),math.cos(b[2]-a[2]))) if axis=='yaw' else abs(dx*math.cos(a[2])+dy*math.sin(a[2])) if axis=='forward' else abs(-dx*math.sin(a[2])+dy*math.cos(a[2]))
   width=round(min(.1,max(r['wheel_until'])-r['t']),3);bins[(axis,width)].append(motion)
   records.append(dict(run=raw.parent.name,rid=rid,t=r['t'],axis=axis,width_s=width,physical_effect=motion))
out=dict(scope='mass025 GCP prior successful hold episodes; held_belief + nonzero release wheels',runs_checked=ns,sources=sources,records=records)
out['table']=[dict(axis=a,width_s=w,n=len(v),median=statistics.median(v)) for (a,w),v in sorted(bins.items())]
out['identifiability']={'forward':'only40ms+ samples during already-moving carry; breakaway minimum not identified','lateral':'no samples','yaw':'no samples','runtime_use':False}
Path('outputs/crate18/held-inventory.json').write_text(json.dumps(out,indent=2)+'\n')
small={k:v for k,v in out.items() if k!='records'};small['pairs']={'path':str(Path('outputs/crate18/held-inventory.json').resolve()),'sha256':hashlib.sha256(Path('outputs/crate18/held-inventory.json').read_bytes()).hexdigest(),'n':len(records)}
Path('experiments/2026-10-15-crate18/held-calibration.json').write_text(json.dumps(small,indent=2)+'\n');print('runs',ns,'held physical commands',len(records));print(out['table'])
