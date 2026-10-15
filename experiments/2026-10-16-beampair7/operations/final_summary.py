"""Final gcp2 summaries; keep every cohort distinct and preserve full recounts."""
from pathlib import Path
from collections import Counter
import json,hashlib,statistics,sys
ROOT=Path('/home/ugrp/ugrp-sim');OPS=ROOT/'ops-reviews/beampair7';SHA='835ccef26aa84b08cc8f7e256fd0f43aa1583ef9'
sys.path.insert(0,str(ROOT/'src'/SHA))
from scripts.audit_beampair1 import read
report=read(OPS/'analysis-gate-r2/summary.json');table=read(OPS/'analysis-gate-r2/rejection-table.json');runtime=read(OPS/'runtime-audit-gate-r2.json');timing=read(OPS/'analysis-gate-r2/runtime-verification.json')
assert report['n']==report['N']==40 and not any(report[k] for k in ('incomplete_N','cap_end_N','HOST_ERROR_N','unstarted_N','held_world_reads','invisible_measurements','missing_rejection_audit_N'))
assert all(runtime[k] for k in ('source_clean','all_input_clean','all_weld_training_student_off','all_recording_10hz_last10','all_planning_checks','all_scene_bound'))
def totals(groups):
 result={}
 for g in groups:
  for name,pop in g.items():
   x=result.setdefault(name,dict(N=0,ordered_funnel={}))
   x['N']+=pop['N']
   for row in pop['ordered_funnel']:
    stage=x['ordered_funnel'].setdefault(row['gate'],Counter())
    for k,v in row.items():
     if k!='gate':stage[k]+=v
 for x in result.values():x['ordered_funnel']=[dict(gate=k,**v) for k,v in x['ordered_funnel'].items()]
 return result
anchor_queries=[]
for run in runtime['runs']:
 if not run['anchor_queries']:continue
 d=read(Path(run['raw'])/'result.json')
 for rid,t in d['teachers'].items():
  for e in t.get('peer_yield_connector_log',[]):
   anchor_queries.append(dict(seed=run['seed'],robot=rid,t=e['t'],potential_grid_N=e['grid_population_N'],checked_N=e['checked_N'],not_checked_N=e['grid_population_N']-e['checked_N'],endpoint_clear_N=sum(c['reason']=='connector_feasible' for c in e['candidates']),continuation_found=e['rest_path_found']))
compact_table=dict(source_sha=SHA,raw_root=report['raw_root'],episode_funnel=table['episode_funnel'],reason_distribution=table['reason_distribution'],blocked_objects=table['blocked_objects'],candidate_population_totals=totals(table['candidate_populations'].values()),frame_population_totals=totals([{'own_frame_candidates':dict(N=v[0]['entered'],ordered_funnel=v)} for v in table['frame_populations'].values()]),event_population_totals=totals([{'own_protocol_events':dict(N=v[0]['entered'],ordered_funnel=v)} for v in table['event_populations'].values()]),rendezvous_event_population_totals=totals([{'retry_events':dict(N=v[0]['entered'],ordered_funnel=v)} for v in table['rendezvous_event_populations'].values()]),anchor_grid_queries=anchor_queries,anchor_population_note='Checked closest-first prefixes form the acceptance funnel. Remaining lattice candidates are unexamined, not rejections.',missing_rejection_audit_N=report['missing_rejection_audit_N'],full_table_path=str(OPS/'analysis-gate-r2/rejection-table.json'),full_table_sha256=hashlib.sha256((OPS/'analysis-gate-r2/rejection-table.json').read_bytes()).hexdigest(),reproduce=report['reproduce'])
(OPS/'rejection_table.json').write_text(json.dumps(compact_table,indent=2)+'\n')
speeds=[x['wall_per_sim'] for x in timing['first30']]
keys=('seed','raw','result_path','result_sha256','eval_path','eval_sha256','adapter_sha','dependency_sha','strict_success','visible_eligible','cap_end','sim_s','max_strict_hold_s','manifest_verified_files','adapter_manifest_verified_files')
cohorts=[]
for label,p in [('R1 short',OPS/'analysis-short-r1/summary.json'),('R1 gate',OPS/'analysis-gate-r1/summary.json'),('R2 short',OPS/'analysis-short-r2/summary.json'),('R2 gate',OPS/'analysis-gate-r2/summary.json')]:
 d=read(p);cohorts.append(dict(label=label,source_sha=d['source_sha'],planned_N=d['planned_N'],N=d['N'],n=d['n'],cap_end_N=d['cap_end_N'],HOST_ERROR_N=d['HOST_ERROR_N'],incomplete_N=d['incomplete_N'],unstarted_N=d['unstarted_N'],supervisor_stop_N=d.get('supervisor_stop_N',0),path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
summary=dict(task='beampair7',status='READY',execution_sha=SHA,base_sha='0b5faa4cfdc52f87df0fdf49e7b254bafc5b8bc0',dependency_sha='26f84d0f0ada1c33473c83cca2d3415ce51bd247',pr=533,pr_url='https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/533',toggle='beampair_peer_yield_v1',default='off',rounds_used=2,max_rounds=3,scene_profile='walls_floor_contrast_v5_indigo110_s80',floor='v1',camera_quality='no_mip_v1',host='gcp2',project='ugrp-sim-b-1014',machine_type='n4-highcpu-64',backend='C MuJoCo3.12.0 CPU',gate=dict(n=40,N=40,planned_N=40,cap_end_N=0,HOST_ERROR_N=0,incomplete_N=0,unstarted_N=0,first_two_seeds=[8318711,8318728],max_parallel=16,min_strict_hold_s=min(x['max_strict_hold_s'] for x in report['runs']),verified_raw_adapter_files=sum((x.get('manifest_verified_files') or 0)+(x.get('adapter_manifest_verified_files') or 0) for x in report['runs'])),input_audit=dict(invisible_measurements=0,held_world_reads=0,complete_N=40,hidden_measurement_ticks_range=[min(x['hidden_measurement_ticks'] for x in runtime['runs']),max(x['hidden_measurement_ticks'] for x in runtime['runs'])],scope='final raw input audit and separate adapter held guard, not student execution'),first30=dict(N=len(speeds),median_wall_per_sim=statistics.median(speeds),max_wall_per_sim=max(speeds),warning_threshold=3.5,block_threshold=6.0,scope='all completed gate runs with a full30SIM window; shorter successes excluded from timing only'),recording_checks={k:runtime[k] for k in ('all_weld_training_student_off','all_recording_10hz_last10','all_planning_checks','all_scene_bound')},cohorts=cohorts,pooling='Only R2 gate40 forms40/40. No prior0b5faa4c15/16, short cohorts, R1 gate or gcp1 pooled.',runs=[{k:v for k,v in e.items() if k in keys} for e in report['runs']],rejection_table=str(OPS/'rejection_table.json'),rejection_table_sha256=hashlib.sha256((OPS/'rejection_table.json').read_bytes()).hexdigest(),source_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),limitations=['ACT student, transport/release, and physical hardware success untested.','Full raw data retained on gcp2 persistent disk; no separate raw backup.','PR merge and independent pre-merge review are separate from teacher gate readiness.'])
(OPS/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(dict(status=summary['status'],gate=summary['gate'],first30=summary['first30'],anchors=anchor_queries)))
