from pathlib import Path
from collections import Counter
import json,hashlib,math,numpy as np,sys
round_id=sys.argv[1] if len(sys.argv)>1 else "1"
from scripts.analyze_reloc14 import selfmap
from scripts.analyze_reloc14_carry import analyze as carry
from scripts.analyze_reloc11_selfmap import rows,obj
R=Path('/home/ugrp/ugrp-sim');out=R/'outputs/reloc15';rs=[]
for p in sorted(R.glob(f'runs/reloc15-r{round_id}-*')):
 if not (p/'EXIT').exists():continue
 raw=p/'raw';result=obj(raw/'result.json')
 if 'selfmap' in p.name:
  full=selfmap(p);es=full['drift']['frames']
  report={k:v for k,v in full.items() if k!='drift'}
  report['drift']={k:v for k,v in full['drift'].items() if k not in ['frames','increments','epochs','fix_frames']}
  trace=rows(raw/'trace.jsonl');reasons=Counter();fresh=[]
  for r in trace:
   s=r.get('static_registration',{});tr=s.get('tracking',{});gate=r.get('correction_admission') or {}
   if s.get('registered'):
    reasons[gate.get('reason','not_evaluated')]+=1
   if s.get('updated') and r.get('pose_source')=='visual_relocalized':fresh.append(r)
  report['correction_reason_counts']=dict(reasons)
  report['actual_measurement_t_unique_N']=len({r.get('last_measurement_t') for r in trace if r.get('last_measurement_t') is not None})
 else:
  report=carry(p);trace=rows(raw/'teacher-commands.jsonl');truth={round(r['t'],5):r for r in rows(raw/'eval-only.jsonl') if 'map_pose_error_yaw_rad' in r}
  held=[truth[round(r['t'],5)] for r in trace if round(r['t'],5) in truth and truth[round(r['t'],5)].get('finger_contacts') and truth[round(r['t'],5)]['min_z']>truth[round(r['t'],5)].get('support_z',0.)]
  yaw=[abs(math.degrees(r['map_pose_error_yaw_rad'])) for r in held if r['map_pose_error_yaw_rad'] is not None]
  unique={r['map_pose'].get('reloc15_heading',{}).get('exposure_sim_t'):r['map_pose'].get('reloc15_heading',{}) for r in trace}
  report['heading_observation_counts']=dict(Counter(h.get('category','off') for h in unique.values()))
  report['held_cargo_yaw']=dict(N=len(yaw),p50_p95_max_deg=np.quantile(yaw,[.5,.95,1]).tolist() if yaw else [],over20_N=sum(y>=20 for y in yaw))
  if result.get('sim_s',0)>=150.-1e-6 and not report.get('physical_success'):report['termination_category']='cap_end'
 report['first30']=obj(raw/'first30.json')
 report['failure_rgb_buffer']=result.get('failure_rgb_buffer');report['result_status']=result.get('status');report['input_audit']=result.get('input_audit');rs.append(report)
(out/f'round{round_id}-full.json').write_text(json.dumps(dict(runs=rs),indent=2)+'\n')
allowed={'run','raw','source_sha','funnel','registered_errors','drive_errors','map_inserted_errors','registration_events','false_registration_events','termination','first30','input_audit','correction_reason_counts','held_cargo_yaw','heading_observation_counts','pose_error','physical_success','termination_category','termination_reason','sim_s','status','result_status','failure_rgb_buffer','registration_frame_funnel','known_mode_measurement_funnel','sha256','raw_sha256','actual_measurement_t_unique_N'}
portable=[{k:({a:b for a,b in v.items() if a!='frames'} if k=='failure_rgb_buffer' and v else v) for k,v in r.items() if k in allowed} for r in rs]
(out/f'round{round_id}.json').write_text(json.dumps(dict(runs=portable,original_full_analysis=str(out/f'round{round_id}-full.json')),indent=2)+'\n')
for r in rs:
 print(json.dumps({k:r[k] for k in ('run','funnel','registered_errors','drive_errors','termination','termination_reason','held_cargo_yaw','heading_observation_counts','correction_reason_counts','failure_rgb_buffer') if k in r},ensure_ascii=False)[:2400])
