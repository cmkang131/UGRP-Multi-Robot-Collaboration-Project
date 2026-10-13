"""Post-run diagnosis only; no controller imports this file."""
import json,collections,math,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from scripts.e2e_stage_pose_eval import read
base=Path(__file__).parent
out=[]
for entry in read(base/'diagnostic-cohort.json'):
 p=ROOT/'outputs/azure3-runs'/entry['name'];plan=read(p/'STAGE_PLAN.json');cp=read(ROOT/plan['checkpoint']);cut=cp['cutoff_s'];trace=read(p/'raw/transport-trace.json')
 item=dict(name=p.name,relation=entry['relation'],robots={})
 for rid in ['r1','r2']:
  own=read(p/f'raw/robots/{rid}/ownmap.jsonl',True);cmd=read(p/f'raw/robots/{rid}/commands.jsonl',True);gt=read(p/f'raw/eval_only/{rid}/trajectory.jsonl',True)
  counts=collections.Counter();segments=[]
  for row in own:
   status=(row.get('carrier_approach') or {}).get('status','none');t=row['t']-cut;counts[status]+=1
   if segments and segments[-1]['status']==status:segments[-1]['end']=t;segments[-1]['frames']+=1
   else:segments.append(dict(status=status,start=t,end=t,frames=1))
  for seg in segments:seg['duration_s']=round(seg['end']-seg['start'],3)
  obs=[(r.get('own_beam_observation') or {}).get('result',{}) for r in own]
  motion=[r for r in cmd if r.get('kind')=='mecanum']
  gtpoints=np.array([r['robot_xyz_m'][:2] for r in gt]);gtyaw=np.unwrap([r['robot_yaw_rad'] for r in gt])
  abandoned=[r for r in trace if r.get('robot_id')==rid and r.get('event')=='own_arm_clearance_scan_abandoned']
  views=[r for r in trace if r.get('robot_id')==rid and r.get('event')=='own_pregrasp_acquisition_view']
  ready=[r['t']-cut for r in trace if r.get('robot_id')==rid and r.get('event')=='s3_coarse_fine' and r.get('phase')=='ready']
  item['robots'][rid]=dict(end=entry['robots'][rid]['reached_end'],status_counts=dict(counts),longest_segments=sorted(segments,key=lambda s:s['duration_s'],reverse=True)[:6],end_visible=sum(bool(v.get('end_visible')) for v in obs),observation_reasons=dict(collections.Counter(v.get('reason') for v in obs)),motion_commands=len(motion),zero_commands=sum(all(abs(r.get(k,0))<1e-8 for k in ['forward','left','turn']) for r in motion),translation_path_m=float(np.linalg.norm(np.diff(gtpoints,axis=0),axis=1).sum()),translation_span_m=float(np.linalg.norm(gtpoints-gtpoints[0],axis=1).max()),rotation_path_rad=float(abs(np.diff(gtyaw)).sum()),abandoned_scans=abandoned,latest_scan_view=views[-1] if views else None,ready_times=ready,latest_status=own[-1].get('carrier_approach'))
 out.append(item)
(base/'ledger-diagnosis.json').write_text(json.dumps(out,indent=2)+'\n')
for r in out:
 print(r['name'], {rid:{k:v[k] for k in ['end','end_visible','translation_span_m','zero_commands','motion_commands','ready_times','longest_segments']} for rid,v in r['robots'].items()})
