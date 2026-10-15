import json,collections,math
from pathlib import Path
p=Path('/home/ugrp/ugrp-sim/ops-reviews/reloc15-93315');a=[json.loads(x) for x in (p/'evaluation.jsonl').read_text().splitlines()];ph=json.loads((p/'physics.json').read_text());print('mass',ph['robot_mass_kg'],ph['cargo_mass_kg'],'drive',ph['drive']['parameters']);out=[]
for lo,hi in [(1.3,32),(32,47),(82.4,103),(103,115.7),(115.7,125.7)]:
 es=[r for r in a if lo<=r['t']<hi];contact=collections.Counter();N=collections.Counter();mom=collections.defaultdict(list);ground=0
 for r in es:
  for c in r['contacts']:
   names=c['names'];other=next((n for n in names if not n.startswith('r1__')),None)
   if other and c['normal_N']>0:contact[other]+=c['normal_N'];N[other]+=1;mom[other].append(abs(c['moment_z_Nm']))
   if any('cargo' in n for n in names) and any(n in ['floor','ground'] or 'floor' in n for n in names):ground+=1
 row=dict(lo=lo,hi=hi,N=len(es),yaw0_deg=math.degrees(es[0]['yaw_rad']),yaw1_deg=math.degrees(es[-1]['yaw_rad']),cargo_min_center_z=min(r['cargo_xyz'][2] for r in es),cargo_ground_contact_N=ground,contacts=[dict(object=k,samples=N[k],normal_mean_per_tick=contact[k]/len(es),max_abs_torque_z=max(mom[k])) for k in contact]);out.append(row)
print(json.dumps(out,indent=2));(p/'contact-summary.json').write_text(json.dumps(dict(physical=ph,segments=out),indent=2)+'\n')
