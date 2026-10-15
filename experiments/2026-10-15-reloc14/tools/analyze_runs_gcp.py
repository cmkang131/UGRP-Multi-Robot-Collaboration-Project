from pathlib import Path
import json,sys,hashlib
sys.path.insert(0,'/tmp')
from analyze_reloc14 import selfmap
from analyze_reloc14_carry import analyze as carry
R=Path('/home/ugrp/ugrp-sim');O=R/'outputs/reloc14';label=sys.argv[1];round=int(sys.argv[2])
reports=[]
for p in sorted(R.glob(f'runs/reloc14-r{round}-*')):
 try:
  r=selfmap(p) if '-selfmap-' in p.name else carry(p)
  reports.append(r)
 except Exception as e:
  reports.append(dict(run=p.name,analysis_error=repr(e)));continue
full=O/(label+'-full.json');full.write_text(json.dumps(dict(runs=reports),indent=2)+'\n')
for r in reports:
 if 'drift' in r:
  r['drift'].pop('frames');r['drift'].pop('increments');r['bad_errors'].pop('frames')
j=dict(schema='ugrp.reloc14.summary.v1',analysis_host='gcp1',runs=reports,
 full_analysis=dict(path=str(full),sha256=hashlib.sha256(full.read_bytes()).hexdigest()))
(O/(label+'.json')).write_text(json.dumps(j,indent=2)+'\n')
for r in reports:
 if 'analysis_error' in r:print(r);continue
 keys=('run','funnel','registered_errors','termination','false_registration_events') if 'drift' in r else ('run','status','funnel','physical_success','termination_reason','pose_error','v7_scene_audit')
 print(json.dumps({k:r[k] for k in keys}))
