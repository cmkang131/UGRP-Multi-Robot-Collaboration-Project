from pathlib import Path
import json,time,subprocess
base=Path.home()/'ugrp-sim'
def read(p):
 try:
  if p.exists():return json.loads(p.read_text())
  if p.with_name(p.name+'.zst').exists():return json.loads(subprocess.check_output(['zstd','-qdc',str(p)+'.zst']))
 except (OSError,ValueError,subprocess.SubprocessError):pass
 return {}
rows=[]
for seed in range(61001,61004):
 for g in ('a','b'):
  n=f'e2e15r2-{g}-s{seed}';r=base/'runs'/n
  if not r.exists():continue
  m=read(r/'RUN_META.json');raw=r/m.get('raw_relative','raw');h=read(r/'latest-health.json');p=read(raw/'e2e-progress.json');f=read(raw/'result.json')
  rows.append(dict(run=n,exit=(r/'EXIT').read_text().strip() if (r/'EXIT').exists() else None,initial=read(r/'initial-health.json'),latest=h,progress=p,result=f,archive=read(base/'e2e15r2-finished'/(n+'.json')),observer_error=read(base/(n+'-observer-error.json'))))
alerts={p.name:read(p) for p in (base/'e2e15r2-alerts').glob('*.json')}
print(json.dumps(dict(checked_unix=time.time(),runs=rows,alerts=alerts)))
