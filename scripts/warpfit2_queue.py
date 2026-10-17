"""Three finite rounds, immutable inputs, native-contact-v1 only, gcp6 only."""
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import subprocess
import sys
from scripts.warpfit import host,dump,digest


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True)
    p.add_argument('--round',type=int,choices=(1,2,3),required=True)
    a=p.parse_args();host();root=a.root.resolve()
    source=Path(__file__).resolve().parents[1]
    phase=root/f'R{a.round}';phase.mkdir()
    preceding=(source/'experiments/2026-10-16-warpfit/warpfit2-rejection-initial.json' if a.round==1
               else root/f'R{a.round-1}/funnel.json')
    if not preceding.is_file():raise ValueError('preceding rejection table missing')
    n=64 if a.round==3 else 16
    profiles=['off','warp_upstream_plane_v1'] if a.round==1 else (
        ['off','warp_measured_capacity_v1'] if a.round==2 else
        ['warp_measured_capacity_v1','warp_upstream_plane_v1','off'])
    cases=[('box','tape',1),('box','tape',2),('beam','tape',1),('drive','warm6',1)]
    if a.round==3:cases=[c for c in cases if c[2]==1]
    jobs=[dict(kind=k,case=c,repeat=r,profile=pr) for k,c,r in cases for pr in profiles]
    queue=dict(enabled=True,round=a.round,nworld=n,jobs=jobs,rejection_table=str(preceding),
        fixed_contact_profile='warp_native_contact_v1',source_sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=source,text=True).strip(),
        runtime_default='off',round_limit=3,limit_kind='fixed issued tape ticks; no wall cap',models=0)
    dump(phase/'queue.json',queue)
    lease=Path('/home/ugrp/ugrp-sim/leases/warpfit.json')
    dump(lease,dict(task='warpfit',subtask='warpfit2',pid=os.getpid(),owner='codex/warpfit',
        started=datetime.now(timezone.utc).isoformat(),expected_end='after finite round; no wall cap',round=a.round,
        independent_gpu_processes=1,worlds=n))
    rows=[]
    for job in jobs:
        k,c,r,pr=[job[t] for t in ('kind','case','repeat','profile')]
        fixture=root/'fixtures'/k
        out=phase/f'{k}-{r}-{pr}'
        reference=root/f'capacity-{k}.json'
        if pr=='warp_measured_capacity_v1':
            result=root/f'R1/{k}-1-off/result.json'
            value=json.loads(result.read_text());e=value['every_step_envelope']
            e.update(source_result_sha256=digest(result),source_states_sha256=digest(result.parent/'states.npz'),raw=str(result.parent))
            dump(reference,dict(every_step_envelope=e,fixture_sha256=digest(fixture/'fixture.npz')))
        else:
            original=Path('/home/ugrp/ugrp-sim/runs/warpfit')/('drive-clear-capacity-reference.json' if k=='drive' else k+'-capacity-reference.json')
            reference=original
        cmd=[sys.executable,'-m','scripts.sim_cli','workflow','run','warpfit','--record',str(out)+'-managed',
            '--input',str(fixture),'--input',str(phase/'queue.json'),'--input',str(reference),'--',
            '--enabled','--fixture',str(fixture),'--output',str(out),'--queue',str(phase/'queue.json'),
            '--profile','warp_native_contact_v1','--runtime-profile',pr,'--nworld',str(n),'--round',str(a.round),
            '--case',c,'--capacity-reference',str(reference),'--record-own-rgb-ring','--measure-runtime-envelope']
        entry=dict(**job,output=str(out),command=cmd,started=datetime.now(timezone.utc).isoformat(),status='running')
        rows.append(entry);dump(phase/'attempts.json',rows)
        print('START',out.name,flush=True)
        env=os.environ.copy();env.update(OMP_NUM_THREADS='1',MUJOCO_GL='disable',PYTHONPATH=str(source))
        with Path(str(out)+'.log').open('w') as log:
            proc=subprocess.run(cmd,cwd=source,env=env,stdout=log,stderr=subprocess.STDOUT)
        entry.update(status='complete' if proc.returncode==0 else 'HOST_ERROR',exit_code=proc.returncode,
                     ended=datetime.now(timezone.utc).isoformat())
        dump(phase/'attempts.json',rows)
        passed=sum(r['status']=='complete' for r in rows)
        dump(phase/'funnel.json',dict(stages=[dict(gate='planned',cumulative_pass=len(jobs),rejected=0),
            dict(gate='submitted',cumulative_pass=len(rows),rejected=len(jobs)-len(rows)),
            dict(gate='fixed_work_complete',cumulative_pass=passed,rejected=len(rows)-passed)],
            reasons=[dict(category='HOST_ERROR',reason='nonzero exit; inspect preserved result/log',blocked_object='runtime',
                minimum_gap_m=None,gap_status='not_geometric',raw=r['output']) for r in rows if r['status']=='HOST_ERROR'],
            raw=str(phase),reproduce=sys.argv))
        if proc.returncode:raise SystemExit('actual failure; inspect before any further submission')
    print('DONE',len(rows),flush=True)


if __name__=='__main__':main()
