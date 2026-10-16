"""Collect exactly the preregistered20 TRAIN prefixes, grouped by native model.

Teacher commands are labels only. No wall deadline, task-success claim,
validation/final starts or shared-backend edits.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import subprocess
import time
from act16w_runtime import require_gcp2, frozen_source, sha256

B = Path('/home/ugrp/ugrp-sim')
ROOT = Path(__file__).resolve().parents[1]
Q = B/'src/f0db6b1abb842ea65b71c433738210254f300a7c'
ACT = B/'src/3f99d58c5ada0862e669ef4065c0ba957f1b4547'
PY = B.parent/'ugrp-rl1b-act-env/bin/python'


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2)+'\n')
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--enabled', action='store_true')
    for key in ('checkpoint', 'starts', 'references-root', 'groups', 'capacity-receipt', 'out'):
        parser.add_argument('--'+key, type=Path, required=True)
    parser.add_argument('--max-worlds', type=int, default=20)
    args = parser.parse_args()
    if not args.enabled or not 1 <= args.max_worlds <= 40:
        parser.error('explicit finite TRAIN collection required')
    host, source = require_gcp2(training=True), frozen_source(ROOT)
    seeds = read(args.starts)['seeds']
    protocol = read(ROOT/'experiments/2026-10-16-act16w/resume2/comparison-protocol-v2.json')
    if len(seeds) != 20 or len(set(seeds)) != 20 or not set(seeds) <= set(protocol['train_seeds']):
        raise ValueError('exact registered20 unique TRAIN starts required')
    provenance = read(args.checkpoint/'adapter.json')['provenance']
    if provenance.get('synthetic_only') or provenance.get('step') != 10000:
        raise ValueError('completed fixed-step student checkpoint required')
    plans = read(args.references_root/'plans.json')['episodes']
    inventory = read(args.references_root/'inventory.json')
    pending = [(i, [j for j in group['indices'] if plans[j]['seed'] in seeds])
               for i, group in enumerate(read(args.groups)['groups'])]
    pending = [(i, group) for i, group in pending if group]
    if sorted(plans[j]['seed'] for _, group in pending for j in group) != sorted(seeds):
        raise ValueError('reference coverage missing or duplicated')
    args.out.mkdir(parents=True, exist_ok=False)
    lease = B/'leases/act16w-dagger-batch.json'
    report = dict(status='running', complete=False, source_sha=source, host=host,
        started_utc=datetime.now(timezone.utc).isoformat(), wall_cap=None,
        checkpoint_sha256=sha256(args.checkpoint/'model.safetensors'), starts_sha256=sha256(args.starts),
        requested_seeds=seeds, teacher_actions_executed=0, task_success_claim=False,
        rejection_table=str(args.out/'rejection_table.json'))
    write(args.out/'RUN_META.json', {'class':'study','pr':539,'branch':'claude/act16w',
                                    'sha':source,'batch':'act16w-dagger1'})
    write(args.out/'queue.json', dict(source_sha=source, rejection_table=report['rejection_table'],
        registered_starts=seeds, prefix_SIM_s=30, wall_cap=None, model_sha256=report['checkpoint_sha256']))
    write(args.out/'rejection_table.json', dict(funnel=[dict(gate='registered_TRAIN_starts',passed=20,rejected=0)],
        rejections=[], raw=str(args.out), reproduce=__import__('sys').argv))
    with lease.open('x') as stream:
        json.dump(dict(task='act16w-dagger-batch',pid=os.getpid(),start=report['started_utc'],
                       expected_end='exact20 x30SIM prefixes; no wall cap',concurrency=0),stream)
    running, finished = {}, []
    stopping = {'requested':False}
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stopping.update(requested=True))
    def foreign():
        receipt=read(args.capacity_receipt)
        if (receipt['project_id']!='ugrp-sim-b-1014'
                or datetime.fromisoformat(receipt['valid_until_utc']).timestamp()<time.time()):
            return 40
        return int(receipt['foreign_cpu_worlds'])+sum(int(read(p).get('concurrency',0))
            for p in lease.parent.glob('*.json') if p!=lease)
    try:
        while pending or running:
            if stopping['requested']:
                raise InterruptedError('supervisor stop')
            for i, job in list(running.items()):
                code=job['proc'].poll()
                if code is not None:
                    job['log'].close()
                    finished.append(dict(group=i,indices=job['indices'],exit_code=code,raw=str(job['out'])))
                    del running[i]
                    if code:
                        raise RuntimeError('DAgger child failed; retain raw and diagnose before retry')
            capacity=min(args.max_worlds,40-foreign())-sum(len(j['indices']) for j in running.values())
            for i, indices in list(pending):
                if len(indices)>capacity:
                    continue
                root=args.out/f'group-{i:02d}';root.mkdir()
                plan=root/'plans.json';write(plan,dict(episodes=[plans[j] for j in indices]))
                out=root/'collection';first=inventory[indices[0]]
                argv=[str(PY),'-u',str(ROOT/'scripts/collect_act16w_dagger.py'),'--enabled',
                    '--physics-python',str(B/'runs/simalt3/warp-env/bin/python'),
                    '--qualified-source',str(Q),'--teacher-source',str(B/'src/warp1-teacher-snapshot-6f057f7e'),
                    '--qualification',str(B/'runs/warp3/teacher-gate-qualification-r1.json'),
                    '--references',str(args.references_root/'per-world-references.json'),
                    '--compiled-reference',first['actuator'],'--compiled-geometry',first['geometry'],
                    '--plans',str(plan),'--actor-source',str(ACT),'--checkpoint',str(args.checkpoint),
                    '--dagger-starts',str(args.starts),'--out',str(out)]
                log=(root/'collection.log').open('x')
                child=subprocess.Popen(argv,cwd=Q,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,
                    start_new_session=True,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1',
                    'OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1'})
                write(root/'launch.json',dict(pid=child.pid,argv=argv,indices=indices,source_sha=source))
                running[i]=dict(proc=child,log=log,indices=indices,out=out)
                pending.remove((i,indices));capacity-=len(indices)
            report.update(active=[dict(group=i,pid=j['proc'].pid,indices=j['indices']) for i,j in running.items()],
                          finished=finished,pending=[dict(group=i,indices=g) for i,g in pending])
            write(args.out/'summary.json',report)
            write(lease,dict(task='act16w-dagger-batch',pid=os.getpid(),start=report['started_utc'],
                expected_end='exact20 x30SIM prefixes; no wall cap',concurrency=sum(len(j['indices']) for j in running.values()),children=report['active']))
            time.sleep(2)
        completed=[]
        for job in finished:
            row=read(Path(job['raw'])/'summary.json')
            if not row['complete'] or row['status']!='prefix_complete' or row['interface_probe_only']:
                raise ValueError('complete TRAIN prefix coverage required')
            completed.extend(plans[j]['seed'] for j in job['indices'])
        if sorted(completed)!=sorted(seeds):
            raise ValueError('DAgger20 coverage incomplete')
        report.update(status='prefix_complete',complete=True,N=20,
                      collections=[j['raw'] for j in finished],next='audit h0 targets and D0 normalization before admitting D1')
        write(args.out/'rejection_table.json',dict(funnel=[
            dict(gate='registered_TRAIN_starts',passed=20,rejected=0),
            dict(gate='completed_student_prefixes',passed=20,rejected=0)],rejections=[],
            raw=report['collections'],scope='coverage only; label rejection table produced by dataset audit',
            reproduce=__import__('sys').argv))
    except BaseException as error:
        report.update(status='SUPERVISOR_STOP' if isinstance(error,InterruptedError) else 'HOST_ERROR',
                      complete=False,error=repr(error))
        write(args.out/'parent-failure.json',dict(category=report['status'],reason=repr(error),
            blocking_object='not_applicable_prefix_runtime',minimum_gap_m=None,
            minimum_gap_status='not_applicable_non_geometric'))
        raise
    finally:
        for job in running.values():
            if job['proc'].poll() is None:
                os.killpg(job['proc'].pid,signal.SIGINT)
                try:job['proc'].wait(timeout=90)
                except subprocess.TimeoutExpired:
                    os.killpg(job['proc'].pid,signal.SIGKILL);job['proc'].wait()
            job['log'].close()
        report['ended_utc']=datetime.now(timezone.utc).isoformat()
        write(args.out/'summary.json',report)
        if lease.exists() and read(lease).get('pid')==os.getpid():lease.unlink()


if __name__=='__main__':
    main()
