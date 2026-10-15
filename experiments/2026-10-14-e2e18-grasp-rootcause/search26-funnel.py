"""Augment raw funnels with search26 command checks and separate cap_end events."""
import argparse,json,hashlib
from pathlib import Path
from scripts.analyze_grasp_act_search24 import read
ap=argparse.ArgumentParser();ap.add_argument('root',type=Path);ap.add_argument('--report',type=Path,required=True);a=ap.parse_args()
path=a.report/'rejection_table.json';table=json.loads(path.read_text());attempts=safe=eligible=issued=0;caps=[];runsteps={k:0 for k in ('scheduled','terminal','not_HOST_ERROR','not_cap_end','success')}
for raw in sorted(a.root.glob('diagnostic*/episode-*/raw')):
 data=read(raw/'result.json');r=json.loads(data);runsteps['scheduled']+=1;runsteps['terminal']+=r['status']=='complete';runsteps['not_HOST_ERROR']+=r['status']=='complete';runsteps['not_cap_end']+=r['status']=='complete' and not r.get('cap_end');runsteps['success']+=r.get('physical_success') is True
 if r.get('cap_end'):caps.append({'raw_result':str(raw/'result.json'),'decoded_sha256':hashlib.sha256(data).hexdigest(),'reason':r.get('end_reason'),'category':'cap_end','blocked_object':'none:planning_wall_safety_cap','min_gap_m':None,'gap_scope':'host safety termination; no geometric blocker; interrupted candidate stage not inferred'})
 for rid,t in r.get('teachers',{}).items():
  for e in t.get('search20_log',[]):
   if e.get('event')!='alignment_pulse_check':continue
   attempts+=1;safe+=e['reason']!='safety_reject';eligible+=e['reason']=='admitted'
  for b in (read(raw/f'teacher-{rid}.jsonl') or b'').splitlines():
   z=json.loads(b);issued+=z.get('teacher_phase')=='align' and any(z.get('applied_command',{}).get('wheels',[]))
def steps(items):
 out=[];prior=None
 for k,n in items:
  assert prior is None or n<=prior,(k,n,prior)
  out.append({'gate':k,'cumulative_pass':n,'rejected_here':None if prior is None else prior-n});prior=n
 return out
table['schema']='ugrp.search26.rejection_table.v1';table['alignment_candidate_funnel']=steps([('axis_pulse_checks',attempts),('body_and_arm_safety',safe),('nonzero_and_merit_or_IK_recovery',eligible),('selected_one_per_tick',issued),('issued_after_final_safety',issued)])
table['run_funnel']=steps(list(runsteps.items()));table['cap_end_events']=caps;table['cap_end_unknown_candidate_stage_N']=len(caps)
table['search26_augmentation_reproduce']=f'PYTHONPATH=. .venv-sim/bin/python /home/ugrp/ugrp-sim/outputs/search26-funnel.py {a.root} --report {a.report}'
path.write_text(json.dumps(table,indent=2)+'\n');print(json.dumps({'alignment_funnel':table['alignment_candidate_funnel'],'run_funnel':table['run_funnel'],'cap_end':len(caps)}))
