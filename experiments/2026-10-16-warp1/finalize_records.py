"""gcp2-only report assembly from verified receipts; never runs a simulator."""
import argparse,collections,datetime,hashlib,json,platform
from pathlib import Path
if platform.system()!='Linux':raise RuntimeError('gcp2 result analysis only')
p=argparse.ArgumentParser();p.add_argument('--l4',type=Path,required=True);p.add_argument('--cpu',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
l4=json.loads(a.l4.read_text());cpu=json.loads(a.cpu.read_text());a.out.mkdir(parents=True,exist_ok=True)
rows=cpu['runs']+l4['runs'];cohorts={};ledger=[];frame_funnels=[];bench=[];failures=[]
for r in rows:
 if '/worker-' in r['run']:continue # parent preserves CPU concurrency timing; children remain in raw receipts.
 args=r.get('reproduce',[])
 native=r.get('native_sleep_policy_compat_v1','--native-sleep-policy-compat-v1' in args)
 sap=r.get('sap_segmented_v1','--sap-segmented-v1' in args)
 numeric=r.get('float32_solver_default_v1','--float32-solver-default-v1' in args)
 n=r.get('nworld',r.get('n'));raw=r['raw'];category=r.get('outcome_category',r.get('status','CPU_batch'))
 entry={k:r[k] for k in ('run','raw','summary_sha256','status','outcome_reason','verification','error_type','error','completed','attempted','cap_end','physical_success') if k in r}
 entry.update(category=category,nworld=n,native_sleep=bool(native),sap=bool(sap),float32_default=bool(numeric))
 ledger.append(entry)
 if r.get('cap_s',0)>4 and r.get('physics_backend') and category not in ('supervisor_stop','HOST_ERROR') and not r['run'].startswith(('export','sleep-export')):
  host=r['host'];key=f"{r['physics_backend']}|{host['instance']}|native{int(native)}|SAP{int(sap)}|tol{int(numeric)}|N{n}"
  c=cohorts.setdefault(key,dict(backend=r['physics_backend'],host=host,nworld=n,native_sleep=bool(native),sap=bool(sap),runs=[],attempted_worlds=0,returned_worlds=0,physical_success_worlds=0,cap_end_worlds=0,supervisor_stop_worlds=0,seeds=set(),successful_seeds=set()))
  c['runs'].append(raw);c['attempted_worlds']+=r.get('attempted',n or 0);c['returned_worlds']+=r.get('completed',0);c['physical_success_worlds']+=r.get('physical_success',0) or 0
  c['cap_end_worlds']+=r.get('cap_end',0) or 0;c['seeds'].update(r.get('world_seeds',[r.get('seed')]))
  if category=='supervisor_stop':c['supervisor_stop_worlds']+=r.get('attempted',n or 0)-r.get('completed',0)
  if r.get('physical_success')==r.get('attempted') and r.get('completed')==r.get('attempted'):c['successful_seeds'].update(r.get('world_seeds',[r.get('seed')]))
 if 'bench-' in r['run'] or r['run'].startswith('cpu-n16-'):
  sim=r.get('aggregate_completed_sim_s',r.get('aggregate_sim_s',0));wall=r.get('wall_s',r.get('elapsed_s'));rate=r.get('hourly_usd',r.get('vm_hourly_usd'))
  bench.append(dict(run=r['run'],raw=raw,nworld=n,world_cap_SIM_s=r.get('cap_s'),native_sleep=bool(native),sap=bool(sap),aggregate_SIM_s=sim,wall_s=wall,loop_wall_s=r.get('loop_wall_s'),cold_SIM_s_per_wall_s=sim/wall if wall else None,loop_SIM_s_per_wall_s=r.get('sim_s_per_wall_s'),estimated_SIM_s_per_USD=sim/(wall*rate/3600) if wall and rate else None,assumed_VM_USD_per_hour=rate,condition='shared-load; horizon/profile explicitly separate; no intrinsic efficiency verdict'))
 for w in r.get('world_results',[]):
  f=w.get('input_funnel')
  if f:
   counts=f['counts'];frame_funnels.append(dict(raw=w['raw'],backend=r.get('physics_backend'),run=r['run'],unit='frames',gates=[dict(gate='frames',entered=counts['frames'],passed=counts['frames'],rejected=0),dict(gate='not_held',entered=counts['frames'],passed=counts['not_held'],rejected=counts['frames']-counts['not_held']),dict(gate='currently_visible',entered=counts['not_held'],passed=counts['visible_not_held'],rejected=counts['not_held']-counts['visible_not_held']),dict(gate='lazy_measurement',entered=counts['visible_not_held'],passed=counts['measurements'],rejected=counts['visible_not_held']-counts['measurements'])],basis=f.get('basis','actual input-funnel.json'),input_audit=w.get('input_audit')))
 for rj in r.get('world_results',[]):
  route=rj.get('route_rejections',{})
  failures.extend(dict(row,raw=rj['raw']) for row in route.get('rows',[]))
for c in cohorts.values():
 c['unique_seeds']=len(c['seeds']);c['seeds']=sorted(c['seeds']);c['successful_unique_seeds']=len(c['successful_seeds']);c['successful_seeds']=sorted(c['successful_seeds'])
rejection=dict(schema='ugrp.warp1.rejection_table.v1',status='NOT_READY',ledger=ledger,episode_funnel=list(cohorts.values()),frame_funnels=frame_funnels,route_rejections=failures,
 non_geometric_reasons=[dict(category='unbatchable_model_field',reason='dof_length differs across randomized source models; unsupported array not approximated',blocking_object='model.dof_length',minimum_gap_m=None,minimum_gap_status='model compatibility, not geometric'),dict(category='unsupported_explicit_sleep_policy',reason='original explicit policy rejected; separate runtime-predicate compatibility adapter tested afterward',blocking_object='tree_sleep_policy',minimum_gap_m=None,minimum_gap_status='API feature admission, not geometric'),dict(category='conditional_trace_compression_path',reason='first interruption probe pointed at missing .zst for small trace; source005fe58c fixed path and second actual probe passed',blocking_object='funnel raw path',minimum_gap_m=None,minimum_gap_status='record integrity, not geometric')],
 raw_roots={'CPU':cpu['root'],'L4':l4['root']},reproduce='collect_records.py --root ... --out ...; finalize_records.py --l4 ... --cpu ... --out ...; exact simulator argv in per-run receipts',
 aborted_attempts=[e for e in ledger if e['category'] in ('supervisor_stop','HOST_ERROR')],
 interpretation='All aborted attempts are retained separately; no aborted bootstrap/probe is silently turned into a teacher success. Prefix caps and explicit supervisor/resource stops remain separate; replicas are not independent seeds; no C/MJWarp or scene/numeric/host pooling')
(a.out/'rejection_table.json').write_text(json.dumps(rejection,ensure_ascii=False,indent=2)+'\n')
summary=dict(status='NOT_READY',generated_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),physics_backend='mjwarp_batch_v1',backend_default='off',PR='https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/534',base_sha='142dbf04c2128c3d7ca1c3ceb03ee3b651d9a7e5',teacher_sha='6f057f7e97c1a3aec9e8c398b8d9068e27b25df8',scope='batched physics/issued commands/RGB; scalar teacher/IK/raycast; separate evaluator',nonphysics_tests=41,cohorts=list(cohorts.values()),throughput=bench,
 records={'CPU':{'raw_manifest':cpu['raw_manifest'],'sha256':cpu['raw_manifest_sha256'],'files':cpu['raw_files']},'L4':{'raw_manifest':l4['raw_manifest'],'sha256':l4['raw_manifest_sha256'],'files':l4['raw_files'],'snapshot_status':l4.get('snapshot_status')}},
 raw_hash_mismatches=[dict(run=r['run'],files=r['verification']['mismatches']) for r in rows if r.get('verification',{}).get('mismatches')],
 gate_queue=dict(status='HOLD_SCENE',approved=False,executed=False,independent_cases=40,training_rgb=False,rejection_table='/Users/changmin/projects/ugrp-wt/warp-act/experiments/2026-10-16-warp1/rejection_table.json'),
 remaining=['scene owner must select/freeze scenetex5 profile and exact model refs','full NumPy teacher/IK/raycast port remains','training recording admission and ACT student evaluation adapters remain','heterogeneous source models contain unbatchable dof_length; grouping/layout must be resolved','>=95%/40 independent MJWarp teacher gate not executed; multiple-seed and steady-state efficiency verification incomplete'],
 prohibitions_observed=dict(Mac_physics_render_training_GUI=0,model_calls=0,training=0,student_evaluations=0,GCP1_access=0,foreign_process_stops=0),cost_scope='VM rates are assumptions from simalt3 plan ($1.096/h L4, $3.145/h n4), not actual billing; overlapping per-run estimates must not be summed',raw_backup='VM originals only; local compact results/videos and hashes are not full raw backup')
(a.out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
