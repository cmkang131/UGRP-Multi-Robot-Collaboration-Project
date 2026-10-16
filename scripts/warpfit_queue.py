"""One finite phase of the three-round warpfit benchmark; no retuning loop."""
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from scripts.warpfit import dump,host

PROFILES=['baseline_noslip10','warp_native_contact_v1','warp_native_contact_v2','warp_native_fast_v1']
CASES=[('box','tape'),('beam','tape'),('drive','group0'),('drive','group1')]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True)
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--round',type=int,choices=[1,2,3],required=True)
    p.add_argument('--reference-only',action='store_true')
    p.add_argument('--attempt-tag',choices=['','retry1'],default='')
    p.add_argument('--preceding-funnel',type=Path)
    p.add_argument('--enabled',action='store_true')
    a=p.parse_args()
    if not a.enabled:p.error('--enabled required')
    host();root=a.root.resolve();source=a.source.resolve()
    phase=root/((f'R{a.round}-Cref' if a.reference_only else f'R{a.round}')+
                ('-'+a.attempt_tag if a.attempt_tag else ''))
    phase.mkdir(exist_ok=False)
    rejection=(source/'experiments/2026-10-16-warpfit/rejection_table.json' if a.round==1
               else root/f'R{a.round-1}/funnel.json')
    if a.preceding_funnel:rejection=a.preceding_funnel.resolve()
    if not rejection.is_file():raise ValueError('preceding rejection funnel missing')
    queue=dict(enabled=True,round=a.round,source=str(source),root=str(root),rejection_table=str(rejection),
        maximum_sim_s_per_case=None,profiles=PROFILES,models=0,planning_limit_kind='fixed physics ticks',
        resource_watchdog_s=10800,resource_watchdog_basis='user target 2-3h; host-only, never selects robot actions')
    dump(phase/'queue.json',queue)
    lease=Path('/home/ugrp/ugrp-sim/leases/warpfit.json')
    dump(lease,dict(task='warpfit',pid=os.getpid(),started=datetime.now(timezone.utc).isoformat(),
        expected_end=None,round=a.round,phase='C reference' if a.reference_only else 'paired diagnostic',
        owner='codex/warpfit',worlds=1 if a.reference_only or a.round==1 else 16 if a.round==2 else 64,
        independent_gpu_processes=0 if a.reference_only else 1))
    env=os.environ.copy();env.update(PYTHONPATH=str(source),MUJOCO_GL='disable',OMP_NUM_THREADS='1')
    cpu='/home/ugrp/ugrp-sim/ugrp/.venv-sim/bin/python'
    warp='/home/ugrp/ugrp-sim/ugrp/.venv-warp/bin/python'
    jobs=([('baseline_noslip10','box','tape'),('baseline_noslip10','beam','tape')] if a.reference_only
          else [(pr,kind,case) for kind,case in CASES for pr in (PROFILES if a.round!=3 else list(reversed(PROFILES)))])
    results=[];started=time.monotonic()
    for pr,kind,case in jobs:
        out=phase/f'{kind}-{case}-{pr}'
        n=1 if a.reference_only or a.round==1 else 16 if a.round==2 else 64
        exe=cpu if a.reference_only else warp
        cmd=[exe,'-m','scripts.sim_cli','workflow','run','warpfit','--record',str(out)+'-managed',
            '--input',str(root/kind),'--input',str(phase/'queue.json'),'--',
            '--enabled','--fixture',str(root/kind),'--output',str(out),'--queue',str(phase/'queue.json'),
            '--profile',pr,'--nworld',str(n),'--round',str(a.round),'--case',case,
            '--engine','cpu' if a.reference_only else 'warp']
        if not a.reference_only:
            reference=(root/f'R1-Cref/{kind}-tape-baseline_noslip10/result.json' if kind!='drive'
                       else root/'drive-capacity-reference.json')
            if reference.is_file():cmd+=['--capacity-reference',str(reference)]
            if a.round==1:cmd+=['--max-sim-s','.1','--nconmax','128','--njmax','512']
            else:cmd+=['--record-own-rgb-ring']
        entry=dict(profile=pr,kind=kind,case=case,output=str(out),command=cmd,status='running',
                   started_utc=datetime.now(timezone.utc).isoformat())
        results.append(entry);dump(phase/'attempts.json',results)
        print('START',out.name,flush=True)
        try:
            with Path(str(out)+'.log').open('w') as log:
                proc=subprocess.run(cmd,cwd=source,env=env,stdout=log,stderr=subprocess.STDOUT,
                                    timeout=max(1,10800-(time.monotonic()-started)))
            entry.update(exit_code=proc.returncode,status='complete' if proc.returncode==0 else 'HOST_ERROR')
        except subprocess.TimeoutExpired:
            entry.update(status='HOST_ERROR',reason='host_resource_watchdog',cap_end=True)
        entry['ended_utc']=datetime.now(timezone.utc).isoformat()
        dump(phase/'attempts.json',results)
        if entry['status']!='complete':
            print('STOP',entry,flush=True)
            break  # Inspect the actual cause before any new submission.
    passed=sum(r['status']=='complete' for r in results)
    dump(phase/'funnel.json',dict(stages=[dict(gate='planned_fixed_jobs',cumulative_pass=len(jobs),rejected=0),
        dict(gate='submitted',cumulative_pass=len(results),rejected=len(jobs)-len(results)),
        dict(gate='process_complete',cumulative_pass=passed,rejected=len(results)-passed)],
        reasons=[dict(category='HOST_ERROR',reason=r.get('reason','nonzero exit; inspect log'),
            blocked_object='runtime',minimum_gap_m=None,gap_status='not_geometric',raw=r['output'])
            for r in results if r['status']!='complete'],raw=str(phase),reproduce=sys.argv))
    print('DONE',passed,'/',len(jobs),flush=True)
    if passed!=len(jobs):raise SystemExit(1)


if __name__=='__main__':main()
