"""Finite gcp4-only host-path diagnostic; no lifecycle or credential access."""
import argparse,copy,datetime,fcntl,json,os,platform,subprocess,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BASE=Path('/home/ugrp/ugrp-sim')
def write(p,v):p.write_text(json.dumps(v,indent=2)+'\n')
def resources():
    return dict(leases={p.name:json.loads(p.read_text()) for p in (BASE/'leases').glob('*.json')},
        gpu_processes=subprocess.check_output(['nvidia-smi','--query-compute-apps=pid,process_name','--format=csv,noheader'],text=True).strip(),
        utc=datetime.datetime.now(datetime.timezone.utc).isoformat())

def main():
    p=argparse.ArgumentParser();p.add_argument('--sizes',nargs='+',type=int,choices=(1,4,16,64),default=[1,4,16,64])
    p.add_argument('--output',type=Path,required=True);p.add_argument('--uninstrumented',action='store_true')
    p.add_argument('--first30',action='store_true');p.add_argument('--motion-first30',action='store_true');p.add_argument('--control-pool',action='store_true');p.add_argument('--eval-arena-reset',action='store_true');a=p.parse_args()
    if a.motion_first30:
        if a.sizes!=[16]:raise ValueError('registered motion cohort is N16; specify --sizes 16')
        a.first30=True;a.uninstrumented=True
    if platform.node().split('.')[0]!='ugrp-act-l4-gcp4':raise ValueError('gcp4 only')
    sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    if subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=ROOT):raise ValueError('clean pinned source required')
    a.output.mkdir(parents=True,exist_ok=False);lease=BASE/'leases/warp10.json';claimed=False
    try:
        with (BASE/'leases/.warp10-claim.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX);state=resources();write(a.output/'admission.json',state)
            if state['leases'] or state['gpu_processes']:raise ValueError('gcp4 occupied; no work submitted')
            with lease.open('x') as f:json.dump(dict(task='warp10',pid=os.getpid(),started_at=state['utc'],
                expected_end='finite requested SIM work, no wall cap',concurrency=max(a.sizes),source_sha=sha),f)
            claimed=True
        original=json.loads((ROOT/'experiments/2026-10-16-warp9/warp7-r3-queue.json').read_text())
        for n in a.sizes:
            table=a.output/f'n{n}-selection.json'
            write(table,dict(unit='explicit_world_replica',independent_task_trials=0,
                stages=[dict(stage='fixed_original_case',cumulative_pass_n=1,rejected_n=0),dict(stage='scaling_replication',cumulative_pass_n=n,rejected_n=0)],
                previous_controller_table=str(ROOT/'experiments/2026-10-16-warp7/final-record/rejection-table.json'),
                rejection_distribution=str(ROOT/'experiments/2026-10-16-warp10/pre-fix-rejection-table.json'),
                raw=str(ROOT/'experiments/2026-10-16-warp9/warp7-r3-queue.json'),reproduction=sys.argv))
            q=copy.deepcopy(original);q.update(task='warp10',source_sha=sha,rejection_table=str(table),
                render_gate=str(ROOT/'experiments/2026-10-16-warp7/colour/r5-summary.json'),
                runs=[copy.deepcopy(original['runs'][0]) for _ in range(n)],warp9_exclusive_host_v1='gcp4',
                warp9_profile_v1=not a.uninstrumented,profile_sim_s=.3,
                warp9_state_snapshot_v1=True,warp10_render_stage_v1=True,warp10_eval_export_v1=True,
                warp10_command_batch_v1=True,warp10_same_state_audit_v1=True,warp10_speed_per_execution_v1=True,
                warp10_control_pool_v1=a.control_pool,
                warp10_eval_arena_reset_v1=a.eval_arena_reset,
                warp10_fixed_work_v1=not a.first30,warp10_first30_only_v1=a.first30,
                independent_initial_cases=1,duplicate_isolation_worlds=n-1,
                interpretation='fixed initial replica diagnostic, not independent task success')
            if a.motion_first30:
                # COORDINATOR_NOTE/reloc21: progress candidates were rejected.
                # Keep them off; this new cohort measures only the host bundle.
                q['runs']=copy.deepcopy(original['runs'])
                for run in q['runs']:
                    run['plan']['reloc21_route_progress_v1']=False
                    run['condition']='warp10_host_candidate_reloc21_progress_off'
                unique=len({r['seed'] for r in q['runs']})
                q.update(independent_initial_cases=unique,duplicate_isolation_worlds=n-unique,
                    interpretation='six registered initial cases, explicit replicas, progress off; first30 teacher motion diagnostic, no LLM/ACT success',
                    warp10_motion_first30_v1=True)
                selected=json.loads(table.read_text());selected.update(unit='motion_world',independent_initial_cases=unique,
                    explicit_replicas=n-unique,controller='existing baseline with rejected reloc21 progress off',
                    stages=[dict(stage='registered_initial_cases',cumulative_pass_n=unique,rejected_n=0),
                            dict(stage='explicit_N16_replication',cumulative_pass_n=n,rejected_n=0)],
                    LLM_ACT_scope='not integrated; not an E2E gate')
                write(table,selected)
            if a.first30:q['warp9_profile_v1']=False
            if a.eval_arena_reset:
                selected=json.loads(table.read_text());selected['previous_same_fault_table']=str(ROOT/'experiments/2026-10-16-warp10/pre-parent-fix-rejection-table.json')
                write(table,selected)
            for key,value in q['environment'].items():
                if key.endswith('CALIBRATION'):q['environment'][key]=str(ROOT/'experiments'/value.split('/experiments/',1)[1])
            q['storage_budget']['reserved_bytes']=0
            qp=a.output/f'n{n}-queue.json';write(qp,q)
            command=[sys.executable,'-m','scripts.run_warp5_batch','--execute','--queue',str(qp),'--output',str(a.output/f'n{n}')]
            write(a.output/'status.json',dict(status='RUNNING',nworld=n,source_sha=sha,command=command))
            env=dict(os.environ,MUJOCO_GL='osmesa',PYOPENGL_PLATFORM='osmesa',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',PYTHONPATH=str(ROOT/'scripts')+':'+str(ROOT))
            with (a.output/f'n{n}.log').open('xb') as log:result=subprocess.run(command,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
            if result.returncode:raise RuntimeError(f'N{n} failed with {result.returncode}; no automatic retry')
        write(a.output/'status.json',dict(status='COMPLETE',source_sha=sha,task_success='unmeasured'))
    except BaseException as exc:
        write(a.output/'status.json',dict(status='HOST_ERROR',source_sha=sha,reason=repr(exc)));raise
    finally:
        if claimed:
            if json.loads(lease.read_text()).get('pid')!=os.getpid():raise RuntimeError('lease ownership changed')
            lease.unlink()
        write(a.output/'release.json',dict(remaining=resources(),own_lease_removed=claimed,vm_stop_attempts=0))
if __name__=='__main__':main()
