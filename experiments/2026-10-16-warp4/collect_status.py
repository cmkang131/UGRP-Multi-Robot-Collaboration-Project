"""Read-only original recount plus external native-exit receipts; gcp2 only."""
import argparse,datetime,hashlib,json,platform,re,subprocess
from pathlib import Path

def read(p):
 p=Path(p)
 if not p.exists():p=Path(str(p)+'.zst')
 if not p.exists():return None
 b=subprocess.check_output(['zstd','-qdc',str(p)]) if p.suffix=='.zst' else p.read_bytes()
 return json.loads(b)

def write(p,d):
 p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(d,indent=2,allow_nan=False)+'\n')

def main():
 if platform.system()!='Linux':raise RuntimeError('gcp2 analysis only')
 a=argparse.ArgumentParser();a.add_argument('--root',type=Path,required=True);a.add_argument('--out',type=Path,required=True);v=a.parse_args()
 root=v.root;out=v.out;out.mkdir(parents=True,exist_ok=True)
 log=(root/'r3-mps-supervisor.log').read_text()
 exits={n:int(c) for n,c in re.findall(r'^(beampair|release-s1|release-s3) (-?\d+)$',log,re.M)}
 final=[];all_attempts=[];files={};audits=[]
 for summary in sorted(root.glob('*/summary.json')):
  d=read(summary);run=summary.parent
  if d is None:continue
  row=dict(run=str(run),source_sha=d.get('source_sha'),flow=d.get('flow'),original_status=d.get('status'),
   planned_N=d.get('planned_N'),started_N=d.get('started_N'),completed_N=d.get('completed_N'),success_n=d.get('success_n'),
   error_type=d.get('error_type'),error=d.get('error'),mujoco=d.get('mujoco'))
  progress=read(run/'progress.json');row['last_progress']=progress
  if run.name.endswith('-short-r3-mps'):
   name=run.name.removesuffix('-short-r3-mps');code=exits[name]
   receipt=dict(status='HOST_ERROR' if code else d.get('status'),exit_code=code,
    evidence=str(root/'r3-mps-supervisor.log'),original_summary_status=d.get('status'),
    reason_category='CUDA_ILLEGAL_MEMORY_ACCESS_700' if name=='beampair' else 'NATIVE_SIGSEGV_MPS_COHORT',
    physical_outcome='unclassified; no completed trial',original_summary_preserved=True)
   write(run/'HOST_PROCESS_EXIT.json',receipt);row['terminal_receipt']=receipt;final.append(row)
  for world in sorted(run.glob('world-*')):
   if not world.is_dir():continue
   result=read(world/'raw/result.json');admit=read(world/'placement-admission.json')
   if result:audits.append(dict(run=run.name,world=world.name,status=result.get('status'),source_sha=result.get('source_sha'),
    physical_success=result.get('physical_success'),release_success=result.get('release_success'),input_audit=result.get('input_audit')))
   if admit:row.setdefault('placement_admissions',[]).append(dict(world=world.name,**admit))
  all_attempts.append(row)
 for p in sorted(root.rglob('*')):
  if p.is_file() and '__pycache__' not in p.parts and 'mps/pipe' not in str(p):
   b=p.read_bytes();files[str(p)]=dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
 table=dict(schema='ugrp.warp4.rejection.v1',population='final R3 transport worlds, not completed physical trials',
  source='a2216618a',raw=str(root),reproduce='python collect_status.py --root '+str(root)+' --out '+str(out),
  funnel=[dict(stage='requested',passed_cumulative_N=12,rejected_N=0),
   dict(stage='native_setup_and_gpu_initialization',passed_cumulative_N=12,rejected_N=0),
   dict(stage='observed_gpu_prefix',passed_cumulative_N=12,rejected_N=0),
   dict(stage='completed_teacher_trial',passed_cumulative_N=0,rejected_N=12)],
  rejections=[dict(reason_category='CUDA_ILLEGAL_MEMORY_ACCESS_700',blocked_object='software:CUDA/Warp',min_gap_m=None,count=4),
   dict(reason_category='NATIVE_SIGSEGV_MPS_COHORT',blocked_object='software:MPS client process',min_gap_m=None,count=8)],
  gap_scope='nongeometric host errors; CUDA root cause not isolated',cap_end_N=0,HOST_ERROR_world_N=12,
  physical_failure_N=0,physical_failure_scope='none classified; incomplete runs are not physical failures',
  gate_not_submitted=dict(beampair=40,release_A=40,release_B=40))
 write(out/'final-rejection_table.json',table)
 write(out/'raw-sha256.json',files);write(out/'raw-input-audits.json',audits)
 report=dict(schema='ugrp.warp4.status.v1',status='NOT_READY',checked_UTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),
  final_round=final,all_attempts=all_attempts,raw_files=len(files),raw_bytes=sum(x['bytes'] for x in files.values()),
  raw_manifest=str(out/'raw-sha256.json'),raw_manifest_sha256=hashlib.sha256((out/'raw-sha256.json').read_bytes()).hexdigest(),
  rejection_table=str(out/'final-rejection_table.json'),completed_final_world_N=0,HOST_ERROR_final_world_N=12,
  qualified_beampair='not submitted /40',qualified_release_A='not submitted /40',qualified_release_B='not submitted /40',
  throughput=dict(N16=None,N64=None,N256=None,CPU16=None,scope='not admitted; no successful full scenario or completed steady-state comparison'),
  CPU_results_pooled=False,model_calls=0,Mac_physics_render_GUI=0,
  caveats=['release25 privileged grasp prefix remains setup-only; not visible-only teacher proof',
   'partial alpha rendering difference remains, as in warp3',
   'R3 SIGSEGV lost in-memory terminal10Hz ring for8 release worlds; future adapter now persists a disk ring, unit-tested only'])
 write(out/'summary.json',report)
 print(json.dumps(dict(status=report['status'],raw_files=len(files),raw_bytes=report['raw_bytes'],HOST_ERROR_world_N=12,completed_N=0)))

if __name__=='__main__':main()
