"""Evaluation-only aggregation of saved records; no controller GT input."""
import hashlib,json,math,statistics
from pathlib import Path
from crate13_replay import RAW,read,js,rows
from harness.grasp_act_visible_world import command_delta
HERE=Path(__file__).parent
OUT=Path('/Users/changmin/projects/ugrp/outputs/e2e18-admin/crate13-audit')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 records=[];drift=[];hashchecks=[]
 visual=json.loads((OUT/'visual-review.json').read_text())
 for run in sorted(RAW.glob('crate-*-fd724191')):
  raw=run/'raw';res=js(raw/'result.json');ev=[v for v in rows(raw/'eval-only.jsonl') if v['stage']=='grasp']
  manifest={}
  for line in (run/'SHA256SUMS').read_text().splitlines():
   h,p=line.split(None,1);rel=p.split('/'+run.name+'/',1)[1];manifest[rel]=h
  files=['plan.json','result.json','eval-only.jsonl','teacher-r1.jsonl','teacher-r2.jsonl']
  selected=next(x['frames'] for x in visual if x['run']==run.name)
  for rel in ['raw/'+f for f in files]+[str(Path(f).relative_to(run)) for f in selected]:
   f=run/rel;data=read(f)
   if rel in manifest:actual=hashlib.sha256(data).hexdigest();expected=manifest[rel]
   elif rel+'.zst' in manifest:actual=sha(str(f)+'.zst');expected=manifest[rel+'.zst']
   else:raise ValueError('manifest absent '+str(f))
   hashchecks.append({'run':run.name,'file':rel,'sha256':actual,'match':actual==expected})
  records.append({'run':run.name,'source_sha':res['source_sha'],'raw':str(raw),
   'status':res['status'],'operator_stopped':res['status']=='interrupted','independent_failure':res['status']=='complete',
   'prefix_held':res.get('prefix_held'),'release_success':res.get('release_success'),'release_outcome':res.get('release_outcome'),
   'input_audit':{k:res.get('input_audit',{}).get(k) for k in ('held_world_reads','invisible_measurements')},
   'input_sha256':{f:hashlib.sha256(read(raw/f)).hexdigest() for f in files}})
  for rid in ('r1','r2'):
   ledger=[v for v in rows(raw/f'teacher-{rid}.jsonl') if 'applied_command' in v];pose=[0.,0.,0.];track=[]
   for i,(v,l) in enumerate(zip(ev,ledger)):
    if i:
     dx,dy,da=command_delta(ledger[i-1]['applied_command'],min(.15,max(0,v['t']-ev[i-1]['t'])))
     c,s=math.cos(pose[2]),math.sin(pose[2]);pose=[pose[0]+c*dx-s*dy,pose[1]+s*dx+c*dy,pose[2]+da]
    gt=v['robots'][rid]['pose'];initial=ev[0]['robots'][rid]['pose'];dx,dy=gt[0]-initial[0],gt[1]-initial[1];c,s=math.cos(initial[2]),math.sin(initial[2]);local=(c*dx+s*dy,-s*dx+c*dy)
    track.append({'phase':l['teacher_phase'],'issued':list(pose),'gt':gt,'error_mm':1000*math.dist(pose[:2],local)})
   issued=sum(math.dist(a['issued'][:2],b['issued'][:2]) for a,b in zip(track,track[1:]));gt=sum(math.dist(a['gt'][:2],b['gt'][:2]) for a,b in zip(track,track[1:]));approach=[x['error_mm'] for x in track if x['phase']=='approach']
   drift.append({'run':run.name,'robot':rid,'ticks':len(track),'issued_path_m':issued,'gt_path_m':gt,
    'path_ratio_issued_over_gt':issued/gt if gt>.5 else None,'ratio_admitted_gt_path_over_0_5m':gt>.5,
    'approach_error_median_mm':statistics.median(approach) if approach else None,'approach_error_max_mm':max(approach) if approach else None})
 assert all(x['match'] for x in hashchecks)
 baseline=json.loads((OUT/'baseline-final.json').read_text());candidate=json.loads((OUT/'candidate-final.json').read_text());release=js(OUT/'release-replay.json');geo=[]
 for r in baseline[:2]:
  own=[g for g in r['geometry'] if g['rid']=='r1'];first=own[0];c=first['candidates'];ispeer='77990' in r['run']
  gaps=[x['disc_gap_mm'][0] if ispeer else min(x['wall_sat_gap_mm']) for x in c]
  geo.append({'run':r['run'],'first_t':first['t'],'legal_candidates':len(c),'blocked_reason':'visible_peer_r2' if ispeer else 'remembered_south_wall',
    'first_nominal_gap_mm':gaps[0],'all_legal_gap_range_mm':[min(gaps),max(gaps)],'first_path_test_reached':False,'planning_ticks':[g['t'] for g in own]})
 (OUT/'source-hashcheck.json').write_text(json.dumps(hashchecks,indent=2)+'\n')
 (OUT/'odometry-eval-only.json').write_text(json.dumps(drift,indent=2)+'\n')
 ratios=[x['path_ratio_issued_over_gt'] for x in drift if x['path_ratio_issued_over_gt'] is not None]
 summary={'schema':'ugrp.crate13.offline.v1','base_sha':'fd724191b2e71ad411f04c18ef9cb0e62f258830','profile':'crate13_v1','physical_runs':0,
  'prior_runs':records,'independent_failures':3,'operator_stops':4,'baseline_matching_grasp_commands':sum(r['matched_commands'] for r in baseline),
  'baseline_complete_ledger_match':all(r['complete_ledger_match'] for r in baseline),'candidate_first_divergences':[{k:r[k] for k in ('run','matched_commands','first_differences')} for r in candidate],
  'candidate_geometry':geo,'release_replay':{k:v for k,v in release.items() if k!='reverse_paths'},
  'odometry_eval_only':{'robot_trajectories':len(drift),'moving_over_0_5m_N':len(ratios),'median_path_ratio':statistics.median(ratios),
   'per_robot':drift,'alignment':'first saved GT pose defines evaluation-only origin; approach position error per tick; full grasp path length, >0.5m GT subset as beam ratio.py',
   'correction_implemented':False,'dependency':'beam search17 diagnosis owns shared integration correction'},
  'hash_verification':{'files':len(hashchecks),'mismatches':0,'manifest_missing':0},
  'visual_review':visual,'tests':{'files':['tests/test_crate13.py','tests/test_crate12.py','tests/test_crate_approach_recovery.py'],'result':(OUT/'tests.log').read_text().strip().splitlines()[-1]},
  'artifacts':{str(p):sha(p) for p in OUT.iterdir() if p.is_file() and p.name in ('tests.log','tests.xml','baseline-final.json','candidate-final.json','release-replay.json','source-hashcheck.json','odometry-eval-only.json')},
  'limitations':['physical staging/return/release effect unverified','release observations inferred empty from all-zero counters, not per-tick raw in fd724191',
   'visible-relative demonstration adapter remains; strict RGB-only interpretation unconfirmed','live remote inventory not queried (prohibited); saved inventories only','gate and training not admitted']}
 (HERE/'crate13-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'files_verified':len(hashchecks),'baseline_commands':summary['baseline_matching_grasp_commands'],'geometry':geo,'moving_N':len(ratios),'median_ratio':statistics.median(ratios),'drift':drift},ensure_ascii=False))
if __name__=='__main__':main()
