"""Run on gcp2: compact result retrieval with raw-file hash verification."""
import argparse,hashlib,json,platform,subprocess,datetime
from pathlib import Path
if platform.system()!='Linux':raise RuntimeError('remote analysis only')
p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
rows=[]
keys=('status','physics_backend','source_sha','teacher_sha','host','nworld','seed','world_seeds','unique_seeds','cap_s','training_rgb','training_recording_supported','student_evaluation_supported','native_sleep_policy_compat_v1','float32_solver_default_v1','sap_segmented_v1','teacher_vectorized','gate_eligible','scene_status','scope','reproduce','model_counts','camera','capacities','model_batch','solver_numerics','sleep_compact','initial_world_state','reset_proof','prototype_reset','setup_compile_s','wall_s','loop_wall_s','aggregate_completed_sim_s','completed','attempted','physical_success','cap_end','timing','physical_batch_sim_s','attempted_control_sim_s','vm_cost_estimate_usd','sim_s_per_wall_s','sim_s_per_usd','useful_completed_sim_s_per_usd','error_type','error','worlds','hourly_usd','price_basis','backend','n','elapsed_s','vm_hourly_usd','cost_estimate_usd','aggregate_sim_s','cold_sim_s_per_wall_s','cold_sim_s_per_usd','HOST_ERROR')
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
for f in sorted(a.root.rglob('summary.json')):
 s=json.loads(f.read_text());root=f.parent;row={'run':str(root.relative_to(a.root)),'raw':str(root),'summary_sha256':sha(f),**{k:s[k] for k in keys if k in s}}
 if 'mujoco' in s:row['mujoco']=s['mujoco']
 marker=root/'SUPERVISOR_STOP.json'
 if marker.exists():
  stop=json.loads(marker.read_text());row['supervision']=stop
  row['outcome_category']='cap_end' if stop.get('category')=='cap_end' or stop.get('reason')=='resource_cap4h' else 'supervisor_stop'
  row['outcome_reason']=stop.get('reason') or 'explicit supervisor marker; raw exception retained'
 elif s.get('status')=='HOST_ERROR':
  row['outcome_category']='HOST_ERROR';row['outcome_reason']=s.get('error') or s.get('error_type') or 'missing exception detail'
 elif s.get('status')=='complete' and s.get('cap_end',0):
  row['outcome_category']='cap_end';row['outcome_reason']='predeclared finite SIM horizon; task completion not inferred'
 else:row['outcome_category']=s.get('status','unknown')
 if s.get('status')=='running':row['verification']={'status':'running_not_complete'}
 else:
  expected=s.get('sha256',{});bad=[]
  for name,digest in expected.items():
   path=root/name
   if not path.is_file() or sha(path)!=digest:bad.append(name)
  row['verification']={'files_checked':len(expected),'mismatches':bad,'scope':'files in runner final manifest; outer logs separately inventoried'}
 world=[]
 for wf in sorted(root.glob('world-*/result.json*')):
  data=json.loads(subprocess.check_output(['zstd','-qdc',str(wf)])) if wf.suffix=='.zst' else json.loads(wf.read_text())
  wanted=('status','physical_success','lift_success','release_success','cap_end','sim_s','input_audit','failure_rgb_buffer','input_funnel','route_funnel','route_rejections','teacher','visibility','lookaround')
  world.append({'raw':str(wf),'sha256':sha(wf),**{k:data[k] for k in wanted if k in data}})
 if world:
  for w in world:
   parent=Path(w['raw']).parent
   funnel=parent/'input-funnel.json'
   if funnel.exists():w['input_funnel']=json.loads(funnel.read_text())
   elif w.get('input_audit'):
    audit=w['input_audit'];measurements=sum(audit.get('measurements_by_phase',{}).values())
    hidden=audit.get('blocked_hidden',0);held=audit.get('blocked_held',0)
    w['input_funnel']={'counts':{'frames':measurements+hidden+held,'not_held':measurements+hidden,'visible_not_held':measurements,'measurements':measurements},
      'basis':'derived from mutually exclusive frozen InputAudit.measure85-103 counters; earlier adapter did not save a separate funnel',
      'raw':w['raw']}
   route=parent/'route-rejections.json'
   if route.exists():w['route_rejections']=json.loads(route.read_text())
  row['world_results']=world
 rows.append(row)
# One file inventory per VM; no source credentials or home-directory traversal.
inventory=[]
for f in sorted(a.root.rglob('*')):
 if f.is_file():inventory.append({'relative':str(f.relative_to(a.root)),'bytes':f.stat().st_size,'sha256':sha(f)})
a.out.parent.mkdir(parents=True,exist_ok=True)
manifest=a.out.with_name(a.out.stem+'-raw-manifest.json');manifest.write_text(json.dumps({'root':str(a.root),'files':inventory},separators=(',',':'))+'\n')
a.out.write_text(json.dumps({'collected_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'analysis_script_sha256':sha(Path(__file__)),'snapshot_status':'incomplete_running' if any(r.get('status')=='running' for r in rows) else 'all_reported_runs_terminal','root':str(a.root),'runs':rows,'raw_manifest':str(manifest),'raw_manifest_sha256':sha(manifest),'raw_files':len(inventory),'raw_bytes':sum(r['bytes'] for r in inventory),'raw_backup':'VM only; hashes are not a backup'},indent=2)+'\n')
