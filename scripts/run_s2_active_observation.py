"""s2v58 bounded active own-RGB observations; exclusive lock and no GT control."""
import argparse,copy,json,os
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from harness import zone_s2_active_observation_contract as contract
from harness.zone_solo_cyan_active_observation import attach,OPTION
from harness.zone_final_pair_binding import bind
from scripts import run_s2_unknown_start as previous
from scripts.run_final_environment_checks import check_source,write


def runtime_factory(b,clouds,index):
    plain=copy.deepcopy(b);option=plain['options'].pop('active_localization')
    factory=previous.runtime_factory(plain)
    def make(*a,**kw):
        r=attach(factory(*a,**kw),active_localization=option)
        frame=r.on_frames;pf=r.pose.provider.loc._pf;last=[-1]
        def on_frames(now,frames):
            result=frame(now,frames)
            if int(now)!=last[0]:
                key=f'p{len(index):04d}';clouds[key]=pf.px.copy();clouds[key+'w']=pf._weights().copy()
                index.append(dict(key=key,t=float(pf.t),capture_t=now));last[0]=int(now)
            return result
        r.on_frames=on_frames
        return r
    return make


def run(b,out):
    clouds={};index=[]
    def factory(bundle):return runtime_factory(bundle,clouds,index)
    # Reuse v139 result/unknown-start metrics, with its full-loop inner binding
    # pointing to our own factory and contract. Sealed snapshots are evaluated
    # only after backend destruction; no evaluator is available to the runtime.
    try:
        return bind(previous.run,contract=contract,runtime_factory=factory)(b,out)
    finally:
        if out.exists():
            np.savez_compressed(out/'belief_snapshots.npz',**clouds)
            write(out/'belief_snapshots.json',dict(periodic=index,gt_inputs=False))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--execute',action='store_true')
    p.add_argument('--expected-source-sha',required=True);p.add_argument('--seed',type=int,required=True)
    p.add_argument('--active-localization',choices=('off',OPTION),default='off');p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();b=contract.bundle(a.expected_source_sha,a.seed,active_localization=a.active_localization)
    if not a.execute:print(json.dumps(dict(execution_started=False,bundle=b['execution_bundle_id'],options=b['options'])));return
    check_source(a.expected_source_sha);contract.require_execution(b)
    if os.getpriority(os.PRIO_PROCESS,0)!=0:raise ValueError('nice must be zero; do not renice')
    from scripts import agent_lock
    from harness.zone_pair_highpose_exact_speedups import install
    expected=agent_lock.DEFAULT_ROOT.parent/f's2-realism-{a.expected_source_sha[:8]}-s{a.seed}-v140-active-observation'
    if not a.output.is_absolute() or a.output.resolve()!=expected.resolve() or a.output.exists():raise ValueError('new preregistered primary output required')
    held=agent_lock.acquire(agent_lock.DEFAULT_ROOT,owner='codex',branch='codex/s2-realism',purpose=f's2v58 active observation s{a.seed}',pid=os.getpid(),expected_minutes=45,timing_sensitive=True)
    undo=None
    try:
        _,undo=install('v98-exact-v6');result=run(b,a.output)
        print(json.dumps({k:result.get(k) for k in ('status','failure','evaluation','wall_per_sim')}),flush=True)
    finally:
        if undo:undo()
        released=agent_lock.release(agent_lock.DEFAULT_ROOT,owner='codex')
        write(a.output/'lock.json',dict(acquired=held,released=released,status_after=agent_lock.status(agent_lock.DEFAULT_ROOT)))

if __name__=='__main__':main()
