"""One-parameter archived RBPF population ablation; no renderer or GT imports."""
import argparse,hashlib,importlib,importlib.util,json,os,resource,time
from pathlib import Path

HERE=Path(__file__).parent

def install_population(module, count):
    if count not in (100,500):raise ValueError('preregistered 100/500 only')
    original=module.RBPFOptions
    if count==100:return original
    def options(*args,**kwargs):
        value=original(*args,**kwargs)
        if value.particles!=100:raise ValueError('expected archived 100-particle configuration')
        # Only this process-local archived constructor's population changes.
        # The frozen adapter files, seed and all other fields stay unchanged.
        object.__setattr__(value,'particles',count)
        return value
    module.RBPFOptions=options
    return original

def run(raw,out,adapter,count):
    spec=importlib.util.spec_from_file_location('saved_population_replay',HERE.parent/'s3fix6/replay_ownmap.py')
    prior=importlib.util.module_from_spec(spec);spec.loader.exec_module(prior)
    from harness.zone_final_pair_binding import bind
    for name in ('harness','scripts','sim'):
        importlib.import_module(name).__path__=[str(adapter/name)]
    module=importlib.import_module('harness.self_map_rbpf')
    install_population(module,count)
    audit=[]
    def attach(grid,**kwargs):
        assert len(grid.poses)==count
        old=grid.resample_if_needed
        def resample():
            import numpy as np
            ess=float(1/np.sum(grid.weights**2));result=old()
            audit.append(dict(t=grid.odom.t,n=len(grid.poses),ess_before=ess,unique_after=len(np.unique(grid.poses,axis=0))))
            return result
        grid.resample_if_needed=resample
    before=time.monotonic();cpu=time.process_time();load=os.getloadavg()
    try:
        bind(prior.replay,attach_ownmap=attach)(raw,out,adapter,'off' if count==100 else 'population500_only')
    finally:
        if out.exists():
            (out/'population.json').write_text(json.dumps(dict(particles=count,wall_s=time.monotonic()-before,cpu_s=time.process_time()-cpu,
                peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,loadavg_start=load,loadavg_end=os.getloadavg(),
                sole_change='RBPFOptions.particles',physics_runs=0,gt_inputs=False,audit=audit),indent=2)+'\n')
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--raw',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--adapter',type=Path,required=True);p.add_argument('--particles',type=int,choices=[100,500],required=True);a=p.parse_args();run(a.raw,a.output,a.adapter,a.particles)
