"""GCP-side trace recount, evaluator-only registration errors and exact replay."""
import argparse
from collections import Counter
import hashlib,json,math,subprocess
from pathlib import Path
import numpy as np
from scripts.analyze_reloc11_selfmap import rows,obj,stats


def analyze(folder):
 raw=folder/'raw';trace=rows(raw/'trace.jsonl');truth=rows(raw/'eval_only/trajectory.jsonl')
 gt={round(r['t'],6):r for r in truth};gates=Counter();reasons=Counter();candidates=Counter();confirmations=Counter()
 errors=[];pf_errors=[];events=[];odom_errors=[];registered_before=False;replay_N=0;miss=0
 for r in trace:
  s=r.get('static_registration',{});diag=s.get('reloc10_diagnostics',{});rej=diag.get('rejection_reasons',[])
  reasons.update(rej);ambiguity=s.get('geometry',{}).get('ambiguity',{})
  candidates[str(ambiguity.get('candidate_count')) if ambiguity.get('evaluated') else 'not_evaluated']+=1
  confirmations[s.get('confirmations',0)]+=1
  checks=[('sensor_update',s.get('updated',False)),('pf_resolved',s.get('pf_resolved',False)),
   ('cluster_mass','cluster_mass' not in rej),('xy_covariance','xy_covariance' not in rej),('yaw_covariance','yaw_covariance' not in rej),
   ('geometry','geometry' not in rej),('unique_solution',ambiguity.get('unique',False)),('reliable',s.get('resolved',False))]
  passed=True
  for key,ok in checks:
   gates[key+'_pass']+=bool(ok);passed=passed and bool(ok);gates[key+'_cumulative']+=passed
  x=s.get('reloc12',{});packet=x.get('replay');replay_N+=bool(packet)
  t=gt.get(round(r['t'],6))
  if t:
   def error(p):
    xy=math.dist(p[:2],t['robot_xyz_m'][:2]);yaw=abs((p[2]-t['robot_yaw_rad']+math.pi)%(2*math.pi)-math.pi)
    return dict(t=r['t'],xy_m=xy,yaw_deg=math.degrees(yaw),within_10cm_5deg=bool(xy<=.1 and yaw<=math.radians(5)))
   if s.get('pf_resolved') and s.get('world_pose') is not None:pf_errors.append(error(s['world_pose']))
   p=x.get('registered_world_pose')
   if p is not None:
    odom_errors.append(error(p))
    from harness.natural_floor_slam import compose
    from harness.selfmap4_geometry import inverse
    anchor=compose(p,inverse(x['replay']['own_odometry_pose']))
    controller_world=compose(anchor,r['pose'])
    e=error(controller_world);errors.append(e)
    if not registered_before:events.append(error(s['world_pose']))
  registered_before=bool(s.get('registered'))
 def err(es):return dict(N=len(es),correct_N=sum(e['within_10cm_5deg'] for e in es),false_N=sum(not e['within_10cm_5deg'] for e in es),xy_m=stats([e['xy_m'] for e in es]),yaw_deg=stats([e['yaw_deg'] for e in es]))
 result=obj(raw/'result.json')
 return dict(run=folder.name,analysis_host='gcp1',source_sha=result.get('source_sha'),frame_N=len(trace),
  status=result.get('status'),termination_category=result.get('termination_category'),elapsed_sim_s=result.get('elapsed_sim_s'),stop_reason=result.get('stop_reason'),
  first30=obj(raw/'first30.json'),gates=dict(gates),rejections=dict(reasons),candidate_count_distribution=dict(candidates),
  confirmation_length_distribution=dict(confirmations),max_confirmations=max(confirmations,default=0),
  registered_N=sum(bool(r.get('static_registration',{}).get('registered')) for r in trace),
  registration_events=events,registration_event_errors=err(events),registered_frame_errors=err(errors),command_odometry_anchor_error=err(odom_errors),pf_error=err(pf_errors),
  registered_frame_error_definition='map_from_own composed with actual emitted controller pose; separate from projected command odometry',
  replay_packets=replay_N,input_audit=result.get('input_audit'),
  invisible_measurements=result.get('invisible_measurements'),held_world_reads=result.get('held_world_reads'),
  failures_to_review=sorted(errors,key=lambda e:(e['within_10cm_5deg'],-e['xy_m']))[:6],
  raw_sha256={str(p.relative_to(folder)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [raw/'result.json',raw/'trace.jsonl.zst',raw/'eval_only/trajectory.jsonl.zst'] if p.exists()})


def main():
 p=argparse.ArgumentParser();p.add_argument('folders',nargs='+',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 data=[analyze(f) for f in a.folders];a.output.write_text(json.dumps(data,indent=2,allow_nan=False)+'\n')
 for r in data:print(json.dumps({k:r[k] for k in ('run','frame_N','registered_N','registration_events','gates','candidate_count_distribution','stop_reason')}))


if __name__=='__main__':main()
