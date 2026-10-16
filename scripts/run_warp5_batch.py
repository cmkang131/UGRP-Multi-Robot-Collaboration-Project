"""Explicit gcp2 MJWarp relocation batch; queue/funnel and clean SHA required."""
from __future__ import annotations
import argparse,datetime,hashlib,json,os,platform,subprocess,sys,time,traceback
from pathlib import Path
import numpy as np
from scripts.warp5_batch import Batch
from scripts.warp5_episode import make_carry,make_selfmap

ROOT=Path(__file__).resolve().parents[1]


def write(p,value):p.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')


def identity():
    from scripts.grasp_act_host import metadata
    base='http://169.254.169.254/computeMetadata/v1/'
    get=lambda key:metadata(base+key,{'Metadata-Flavor':'Google'})
    host=dict(provider='gcp',project_id=get('project/project-id'),instance=get('instance/name'),
              machine_type=get('instance/machine-type').rsplit('/',1)[-1],zone=get('instance/zone').rsplit('/',1)[-1],
              cpu_count=len(os.sched_getaffinity(0)),schema='ugrp.grasp_act.host.v1')
    if (host['project_id'],host['instance'])!=('ugrp-sim-b-1014','ugrp-act-l4-gcp2'):raise ValueError('gcp2 L4 only')
    return host


def run(a):
    q=json.loads(a.queue.read_text());sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    if q['source_sha']!=sha or subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=ROOT):raise ValueError('clean pinned source required')
    rejection=Path(q['rejection_table'])
    if not rejection.is_absolute() or not rejection.is_file():raise ValueError('existing absolute rejection_table required')
    if not a.setup_only:
        gate=json.loads(Path(q['render_gate']).read_text())
        if not gate.get('admitted',False):raise ValueError('MJWarp renderer not qualified; control batch withheld')
        if len(q['runs'])<16:raise ValueError('N16 minimum for run-first batch')
    host=identity();a.output.mkdir(parents=True,exist_ok=False)
    write(a.output/'queue.json',q)
    report=dict(status='RUNNING',source_sha=sha,host=host,shared_load=True,model_calls=0,
        physics_backend='mjwarp_batch_v1',pool_with_cpu=False,attempted=len(q['runs']),worlds=[],errors=[])
    hooks=Batch(host,sha,'mjwarp_batch_v1',a.output)
    hooks.warp5_native_visual_v1=q.get('warp5_native_visual_v1',False)
    lanes=[];bridges=[];contexts=[];active=np.ones(len(q['runs']),bool)
    started=time.perf_counter()
    try:
        for i,t in enumerate(q['runs']):
            out=a.output/f'world-{i:03d}'/'raw';out.parent.mkdir()
            if t['kind']=='carry':lane,bridge=make_carry(ROOT,t['plan'],out,host,t['kwargs'])
            elif t['kind']=='selfmap':lane,bridge=make_selfmap(ROOT,t['bundle'],out,host)
            else:raise ValueError('registered carry/selfmap lane required')
            lanes.append(lane);bridges.append(bridge)
            context=next(lane)
            if context['kind']!='setup':raise ValueError('missing isolated setup barrier')
            contexts.append(context)
        report['adapter_ast']=[b.ast_audit for b in bridges]
        write(a.output/'initial-state.json',dict(worlds=[dict(world=i,seed=t['seed'],
            qpos_sha256=hashlib.sha256(c['world'].data.qpos.tobytes()).hexdigest(),origin=c['origin']) for i,(t,c) in enumerate(zip(q['runs'],contexts))]))
        if a.setup_only:
            report.update(status='SETUP_ONLY',physics_steps=0);return
        from scripts.warp_act_core import model_key
        keys={model_key(c['world'].scene_xml) for c in contexts}
        if len(keys)!=1:raise ValueError('exact model topology group required; canonical model dependency must be supplied')
        hooks.initialize(contexts)
        report.update(camera=hooks.camera,compatibility=hooks.compat,capacities=hooks.capacities)
        loop=time.perf_counter()
        while active.any():
            for i in np.flatnonzero(active):
                try:
                    event=next(lanes[i])
                    if event['kind']!='step':raise ValueError('missing step barrier')
                except StopIteration as done:
                    active[i]=False;result=done.value
                    report['worlds'].append(dict(world=int(i),seed=q['runs'][i]['seed'],result=result))
            if active.any():hooks.step(contexts,active)
            elapsed=hooks.tick*.1
            write(a.output/'progress.json',dict(sim_s=elapsed,active=int(active.sum()),completed=len(report['worlds']),wall_s=time.perf_counter()-loop,timing=dict(hooks.seconds)))
            if elapsed>=30 and not (a.output/'first30.json').exists():
                ratio=(time.perf_counter()-loop)/elapsed
                write(a.output/'first30.json',dict(sim_s=elapsed,wall_per_sim=ratio,shared_load=True,status='SPEED_GATE_FAIL' if ratio>6 else 'PASS'))
        report.update(status='COMPLETE',batch_sim_s=hooks.tick*.1)
    except BaseException as exc:
        report.update(status='HOST_ERROR',errors=[dict(category='HOST_ERROR',reason=repr(exc),blocked_object='batch_adapter',minimum_gap_m=None,gap_status='not_measured',traceback=traceback.format_exc())])
        raise
    finally:
        for lane in lanes:
            try:lane.close()
            except BaseException as exc:report['errors'].append(dict(category='HOST_ERROR',reason=repr(exc),blocked_object='finalizer',minimum_gap_m=None))
        hooks.close();report['wall_s']=time.perf_counter()-started
        write(a.output/'summary.json',report)
        write(a.output/'rejection-table.json',dict(stages=[dict(stage='requested',cumulative_pass_n=len(q['runs']),rejected_n=0),dict(stage='setup',cumulative_pass_n=len(contexts),rejected_n=len(q['runs'])-len(contexts)),dict(stage='completed',cumulative_pass_n=len(report['worlds']),rejected_n=len(q['runs'])-len(report['worlds']))],errors=report['errors'],raw=str(a.output),reproduction=sys.argv))
        write(a.output/'SHA256SUMS.json',{str(p.relative_to(a.output)):hashlib.sha256(p.read_bytes()).hexdigest() for p in a.output.rglob('*') if p.is_file() and p.name!='SHA256SUMS.json'})


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--queue',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--execute',action='store_true');p.add_argument('--setup-only',action='store_true')
    a=p.parse_args()
    if not a.execute or platform.system()!='Linux':p.error('explicit Linux gcp2 execution required; Mac physics/render forbidden')
    run(a)


if __name__=='__main__':main()
