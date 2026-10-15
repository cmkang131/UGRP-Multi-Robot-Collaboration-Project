"""Recount recorded localization candidate populations, without refitting or physics."""
from pathlib import Path
import json,subprocess,hashlib,collections,sys
OPS=Path('/home/ugrp/ugrp-sim/ops-reviews/release25')
R=OPS.parents[1]
def read(p):
 return json.loads(p.read_bytes() if p.exists() else subprocess.check_output(['zstd','-qdc',str(p)+'.zst']))
config=Path(sys.argv[1]);cfg=read(config);rows=[];runtime=[]
for run in cfg['runs']:
 raw=R/'runs'/run['name']/'raw'
 if not raw.exists():continue
 d=read(raw/'result.json');scene=d.get('gatesv5_scene') or {}
 quality=scene.get('contexts') or {}
 runtime.append(dict(run=run['name'],audit=d.get('input_audit'),scene=scene.get('scene_profile'),camera_quality=scene.get('camera_quality'),new_boundary_toggle=scene.get('scene_colour_transition_v1'),floor_v1_exact=scene.get('profile',{}).get('floor_v1_histogram_exact'),no_mip_all_contexts=bool(quality) and all(t['min']==9729 and t['mag']==9729 for c in quality.values() for t in c['textures'])))
 for rid,v in (d.get('lookaround_result') or {}).items():
  # A localizer's last decision duplicates its last evaluation sweep decision.
  # Each saved sweep is one fit event. Never add that last decision again.
  sweeps=v.get('evaluation',{}).get('sweeps',[])
  for i,sweep in enumerate(sweeps):
   a=sweep.get('decision') or {};support=a.get('support_audit')
   row=dict(run=run['name'],robot=rid,sweep=i,t0=sweep.get('t0'),fit_reason=a.get('reason'),accepted=a.get('accepted'),source_result=str(raw/'result.json'),original_support_audit=support)
   if support:
    N=support['generated'];after=N-support['rejected_before_score'];unique=a['hypotheses'];assert 0<=unique<=after<=N
    row['candidate_funnel']=[dict(gate='finite_correspondence_generated',entered=N,cumulative_passed=N,rejected=0),dict(gate='source_pose_supported',entered=N,cumulative_passed=after,rejected=N-after),dict(gate='source_numerical_deduplication',entered=after,cumulative_passed=unique,rejected=after-unique)]
    row['not_recorded']='cluster seed count and intermediate optimizer survivor counts were not logged; source alternatives is truncated to four, so no extra counts are inferred'
   checks=a.get('acceptance_checks') or {};alive=1;gates=[]
   for key in ['lines','views','normal_rank','score_gap']:
    if key not in checks:break
    survived=alive if checks[key] else 0;gates.append(dict(gate='best_fit_'+key,entered=alive,cumulative_passed=survived,rejected=alive-survived));alive=survived
   row['best_fit_event_funnel']=gates;rows.append(row)
out=OPS/('release-'+cfg['stage']+'-analysis-'+cfg['source_sha'][:8])
value=dict(schema='ugrp.gatesv5.recorded-localization-candidates.v1',rows=rows,runtime=runtime,source_sha=cfg['source_sha'],scope='Per-fit candidate proposals and best-fit decision events are separate populations. Counts come from original support_audit/hypotheses/acceptance_checks; no source change, no refit, no physics steps.',source_definition='sim/global_landmark_localization.py:140-265',reproduce='/home/ugrp/ugrp-sim/ugrp/.venv-sim/bin/python '+str(Path(__file__).resolve())+' '+str(config))
p=out/'candidate-funnels.json';p.write_text(json.dumps(value,indent=2)+'\n')
for source,target in [('summary.json','summary-with-candidates.json'),('rejection_table.json','rejection_table-with-candidates.json')]:
 d=read(out/source);d['candidate_funnels']=str(p);d['candidate_funnels_sha256']=hashlib.sha256(p.read_bytes()).hexdigest();d['candidate_funnels_script_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest();(out/target).write_text(json.dumps(d,indent=2)+'\n')
print(json.dumps(dict(fit_events=len(rows),runtime_runs=len(runtime),all_scene_expected=all(r['scene']=='walls_floor_contrast_v5_indigo110_s80' and r['camera_quality']=='no_mip_v1' and r['new_boundary_toggle']=='off' and r['floor_v1_exact'] and r['no_mip_all_contexts'] for r in runtime),audit_all_zero=all(all(r['audit'][k]==0 for k in ['invisible_measurements','held_world_reads','control_top_camera_reads']) for r in runtime))))
