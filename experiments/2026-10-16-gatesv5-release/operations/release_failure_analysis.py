"""Evaluation-only diagnosis from saved results; no physics stepping or image edits."""
from pathlib import Path
import json,subprocess,sys,math
R=Path('/home/ugrp/ugrp-sim');OPS=R/'ops-reviews/gatesv5';sys.path.insert(0,str(R/'src/a41781dd122b1e20b8eec7e43c553e779e6cfc30'))
from harness.zone_final_environment import resolve
from harness.static_keepouts import disc_footprint,polygon_at,rect_corners
from sim.release23 import _polygon_gap
def read(p):return json.loads(p.read_bytes() if p.exists() else subprocess.check_output(['zstd','-qdc',str(p)+'.zst']))
rows=[]
for candidate in ['A','B']:
 run='gv5-release-gate-current_'+candidate+'-110633-a41781dd-retry1';raw=R/'runs'/run/'raw';d=read(raw/'result.json');plan=read(raw/'plan.json');static,_,_=resolve(plan['map_id']);wall=next(x for x in static['obstacles'] if x['id']=='wall_north');locs={}
 for rid,v in (d.get('lookaround_result') or {}).items():
  l=v['localizer'];e=v['evaluation'];P=l['final_sigma'];halo=max(.02,2*max(P[:2]));foot=polygon_at(l['final_estimate'],disc_footprint(.18));rect=(*wall['center_m'],*wall['half_extents_m'],wall.get('yaw_rad',0))
  locs[rid]=dict(final_estimate=l['final_estimate'],final_sigma=P,halo_m=halo,starting_robot_only_north_gap_m=_polygon_gap(foot,rect_corners(rect,margin=halo)),same_geometry_without_uncertainty_halo_gap_m=_polygon_gap(foot,rect_corners(rect)),decision_accepted=l['decision']['accepted'],decision_reason=l['decision']['reason'],fit_segment_rms_m=l['decision'].get('inlier_segment_rms_m'),last_lookaround_evaluation=e.get('after'),view_count=len(l['views']))
 rows.append(dict(run=run,saved_status=d['status'],outcome=d['release_outcome'],input_audit=d['input_audit'],choice=d.get('code_decisions'),shift_steps=d.get('shift_steps'),reported_sweep=d.get('release23_sweep_checks'),localizers=locs,final_evaluation=d.get('evaluation_last'),failure_reasons=d.get('release_failure_reasons'),missing_finalization_fields=not bool(d.get('lookaround_result'))))
value=dict(source_sha='a41781dd122b1e20b8eec7e43c553e779e6cfc30',rows=rows,source_geometry='sim/release23.py:137-187, unchanged robot envelope0.18m and halo=max(.02,2sigma); these are diagnostic reuse of existing constants, not new acceptance values',scope='The logged rejection is the uncertainty-expanded planned sweep. Starting robot envelope is checked separately from the full original sweep; no prediction is a physical collision measurement. The exact localization/uncertainty/planner cause and whether the block is unnecessary remain unresolved. No evidence here establishes a scene color detection regression.',reproduce='/home/ugrp/ugrp-sim/ugrp/.venv-sim/bin/python '+str(Path(__file__).resolve()))
(OPS/'release-failure-analysis.json').write_text(json.dumps(value,indent=2)+'\n');print(json.dumps([dict(run=x['run'],loc=x['localizers']) for x in rows]))
