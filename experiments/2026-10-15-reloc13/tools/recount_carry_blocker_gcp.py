from pathlib import Path
from scripts.analyze_reloc11_selfmap import rows,obj
from harness.static_keepouts import keepout_rects
from sim.solo_carry_obstacles import RGBObstacleMemory
from importlib.util import spec_from_file_location,module_from_spec
import json,math,hashlib
from harness import reloc12_ledger as mod
R=Path('/home/ugrp/ugrp-sim/runs');out=[]
for p in R.glob('reloc13-r1-carry-*-retry1'):
 result=obj(p/'raw/result.json');trace=rows(p/'raw/teacher-commands.jsonl')
 if result.get('termination_reason')!='carry_recovery_setdown_envelope_blocked':continue
 r=trace[-1];m=r['map_pose'];x,y,a=m['pose_estimate'];now=r['t'];static=obj(p/'raw/carry-static-map.json')
 obs=RGBObstacleMemory(managed=True);obs.tracks=r['carry_obstacles']['tracks']
 rec=mod.segment_rejection_context((x,y),(x-.15*math.cos(a),y-.15*math.sin(a)),obs.discs(now),keepout_rects(static,perimeter=True),.26,names=[o['id'] for o in static['obstacles']],disc_names=[f"own_rgb:{t['kind']}:{t.get('id',i)}" for i,t in enumerate(obs.tracks)])
 out.append(dict(run=p.name,t=now,source='saved permitted map pose and own RGB obstacle memory; no truth',**rec))
Path('/tmp/reloc13-carry-blockers.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out))
