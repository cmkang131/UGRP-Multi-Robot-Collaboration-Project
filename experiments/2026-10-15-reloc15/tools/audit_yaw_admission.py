from pathlib import Path
from scripts.analyze_reloc11_selfmap import rows
import json,math,collections,numpy as np
out=[]
for p in sorted(Path('/home/ugrp/ugrp-sim/runs').glob('reloc15-r3-carry-*')):
 cs=rows(p/'raw/teacher-commands.jsonl');truth={round(r['t'],5):r for r in rows(p/'raw/eval-only.jsonl') if r.get('map_pose_error_yaw_rad') is not None};frames={round(r['t'],5):r for r in cs};hs={r['map_pose'].get('reloc15_heading',{}).get('exposure_sim_t'):r['map_pose'].get('reloc15_heading',{}) for r in cs};es=[]
 for t,h in sorted((t,h) for t,h in hs.items() if t is not None):
  if h.get('category')!='relative_rgb_yaw':continue
  prev=frames.get(round(t-.2,5));cur=frames.get(round(t,5));a=truth.get(round(t-.2,5));b=truth.get(round(t,5))
  if not all((prev,cur,a,b)) or prev['map_pose']['rgb_fixes']!=cur['map_pose']['rgb_fixes']:continue
  before=prev['map_pose']['pose_estimate'][2]-a['map_pose_error_yaw_rad'];after=cur['map_pose']['pose_estimate'][2]-b['map_pose_error_yaw_rad'];actual=(after-before+math.pi)%(2*math.pi)-math.pi;error=(h['delta_yaw']-actual+math.pi)%(2*math.pi)-math.pi
  es.append(dict(t=t,error_deg=math.degrees(error),actual_delta_deg=math.degrees(actual),observed_delta_deg=math.degrees(h['delta_yaw']),precision_bound_deg=math.degrees(h['precision_bound_rad']),forward_backward_rms_px=h['forward_backward_rms_px'],ecc=h['ecc']))
 values=sorted(es,key=lambda r:abs(r['error_deg']),reverse=True);rec=dict(run=p.name,N=len(es),above_5deg_N=sum(abs(r['error_deg'])>5 for r in es),error_abs_p50_p95_max_deg=np.quantile([abs(r['error_deg']) for r in es],[.5,.95,1]).tolist() if es else [],worst=values[:5]);out.append(rec);print(json.dumps(rec))
Path('/home/ugrp/ugrp-sim/outputs/reloc15/quality-admission-audit.json').write_text(json.dumps(out,indent=2)+'\n')
