"""Recount historical raw logs only. No simulator, render, or controller calls."""
import argparse,hashlib,json,math,subprocess
from pathlib import Path
from collections import Counter,defaultdict


def main():
 p=argparse.ArgumentParser();p.add_argument('--source-root',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
 sources={};missing=[]
 def read(path,lines=False):
  if not path.exists():path=Path(str(path)+'.zst')
  if not path.exists():missing.append(str(path));return None
  raw=path.read_bytes();digest=hashlib.sha256(raw).hexdigest()
  if path.suffix=='.zst':raw=subprocess.check_output(['zstd','-qdc',str(path)])
  sources[str(path)]={'sha256':digest,'decoded_sha256':hashlib.sha256(raw).hexdigest()}
  return [json.loads(x) for x in raw.splitlines() if x.strip()] if lines else json.loads(raw)
 result=[]
 for host in ('azure3','azure4'):
  for cohort in ('r69','r76','r80'):
   for run in sorted((a.source_root/f'{host}-runs').glob('*-'+cohort)):
    raw=run/'raw';r=read(raw/'result.json');trace=read(raw/'transport-trace.json')
    if r is None or trace is None:continue
    referee=read(raw/'eval_only/referee_truth.jsonl',True)
    # The archived referee held bit means ANY finger contact, not joint grasp.
    # Its absence proves no grasp; its presence alone cannot prove a grasp.
    valid_referee=bool(referee) and all(type(x.get('items',{}).get('beam_1',{}).get('held')) is bool for x in referee)
    any_contact=any(x['items']['beam_1']['held'] for x in referee) if valid_referee else None
    row={'run':run.name,'host':host,'cohort':cohort,'source_sha':r.get('source_sha'),'result_status':r.get('status'),
         'observed_sim_s':r.get('sim_s'),'termination':r.get('failure_type'),'controller_failure':r.get('controller_failure'),
         'global_align':any(x.get('event')=='phase' and x.get('state')=='align' for x in trace),'robots':{},
         'raw_local':str(raw),'referee_any_finger_contact':any_contact,'seed':r.get('seed')}
    supports=read(raw/'eval_only/setdown.jsonl',True)
    proxy={}
    for actor in ('r1','r2','joint'):
     active=('r1','r2') if actor=='joint' else (actor,)
     times=[]
     for sample in supports or []:
      lifted=sample.get('cargo_z_m',0)-(supports[0]['cargo_z_m'])>=.03
      touches=all(len(sample.get('fingers',{}).get(rid,[]))==2 and all(sample['fingers'][rid]) for rid in active)
      if lifted and touches and sample.get('cargo_tilt_deg',math.inf)<=10:times.append(sample['t'])
     start=previous=None;longest=0.
     for now in times:
      if previous is None or now-previous>.051:start=now
      longest=max(longest,now-start);previous=now
     proxy[actor]={'n':int(bool(times)),'N':1 if supports else 0,'first_world_t':times[0] if times else None,'longest_s':longest}
    row['contact_geometry_only_proxy']=proxy
    fingerprints=[]
    for rid in ('r1','r2'):
     path=raw/f'robots/{rid}/ownmap.jsonl';own=read(path,True);commands=read(raw/f'robots/{rid}/commands.jsonl',True)
     if own is None:row['robots'][rid]={'stages':None};continue
     actual=path if path.exists() else Path(str(path)+'.zst');fingerprints.append(sources[str(actual)]['decoded_sha256'])
     obs=[(x.get('own_beam_observation') or {}).get('result') or {} for x in own]
     approach=[x.get('carrier_approach') or {} for x in own]
     ready=any(x.get('robot_id')==rid and x.get('event')=='s3_coarse_fine' and x.get('phase')=='ready' for x in trace)
     stages={'seen':any(x.get('visible') or x.get('body_visible') for x in obs),'estimate':any(x.get('own_beam') for x in own),
             'estimated_stance_8cm':any(x.get('distance_m',math.inf)<=.08 for x in approach),
             'fine_alignment_entered':any(x.get('status')=='visual_servo' for x in approach),'alignment_ready':ready,
             'close_command':None if commands is None else any(x.get('kind')=='arm' and x.get('servo_id')==1 and x.get('pulse',2500)<=1600 for x in commands),
             'closed_measured':None,'held':False if any_contact is False else None,'joint_held':False if any_contact is False else None}
     row['robots'][rid]={'stages':stages,'own_samples':len(own),'first_unreached_observed_stage':next((k for k,v in stages.items() if v is False),None),
       'detector_nonvisible_frame_reasons':dict(Counter(x.get('reason','unspecified') for x in obs if not x.get('visible')))}
    row['owned_log_fingerprint']=hashlib.sha256(json.dumps(fingerprints).encode()).hexdigest() if len(fingerprints)==2 else None
    result.append(row)
 groups={};dupes=defaultdict(list)
 for row in result:
  if row['owned_log_fingerprint']:dupes[row['owned_log_fingerprint']].append(row['run'])
 for key in sorted({(r['host'],r['cohort']) for r in result}):
  rows=[r for r in result if (r['host'],r['cohort'])==key];group={'run_N':len(rows),'global_align':{'n':sum(r['global_align'] for r in rows),'N':len(rows)},'distinct_seeds':sorted({r['seed'] for r in rows}),'robots':{}}
  for rid in ('r1','r2'):
   values=[r['robots'][rid] for r in rows];valid=[x for x in values if x['stages'] is not None]
   stages={}
   for stage in (valid[0]['stages'] if valid else []):
    known=[x['stages'][stage] for x in valid if x['stages'][stage] is not None]
    stages[stage]={'n':sum(known),'N':len(known),'unknown_N':len(rows)-len(known)}
   group['robots'][rid]={'stages':stages,'first_unreached_observed_stage':dict(Counter(x['first_unreached_observed_stage'] for x in valid))}
  groups['/'.join(key)]=group
 report={'schema':'ugrp.grasp.historical_recount.v1','scope':'saved local raw only; no new simulation; counts mean reached before recorded termination, not final success rate',
         'groups':groups,'runs':result,'identical_owned_logs':[v for v in dupes.values() if len(v)>1],
         'source_files':sources,'missing':missing,'limitations':['full jaw closure not logged','any finger contact is insufficient for held/joint held; those cases remain unknown','different hosts/cohorts are not pooled','no new failure-cause or video diagnosis from event counts','pose/geometry error not recomputed in this recount','contact_geometry_only_proxy requires bilateral contacts, COM rise30mm and tilt<=10deg but force was not logged, so it is not the positive-force held label or the new3s gate','same seed across bundles is not independent start-state evidence']}
 a.out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'runs':len(result),'source_files':len(sources),'missing':len(missing),'groups':groups},ensure_ascii=False))
if __name__=='__main__':main()
