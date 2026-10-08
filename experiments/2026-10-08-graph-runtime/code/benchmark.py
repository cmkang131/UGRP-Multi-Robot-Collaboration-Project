"""Sequential, locked exact-output benchmarks. No physics or GT."""
import importlib.util,json,os,time
import profile_graph as p
from harness.grid_acceleration import using
from harness.self_graph_cache import install
from scripts.agent_lock import DEFAULT_ROOT,status,acquire,release


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def frame_replay(name,enabled):
    old=module('eg47_profile',p.ROOT/'experiments/2026-10-08-navfn-start-recovery/code/profile_replay.py')
    old.RAW=p.RAW
    original=old.actor;graph_times=[]
    def actor(*args,**kw):
        c=original(*args,**kw)
        if enabled:install(c.memory,graph_acceleration='match_cache_v1')
        graph=c.graph
        def measured(*a,**k):
            start=time.perf_counter()
            try:return graph(*a,**k)
            finally:graph_times.append(time.perf_counter()-start)
        c.graph=measured
        return c
    old.actor=actor
    result=old.replay(name,acceleration='scalar_rays_v1' if enabled else 'off')
    result['inclusive_graph_s']=sum(graph_times);result['graph_calls']=len(graph_times)
    result['graph_acceleration']='match_cache_v1' if enabled else 'off'
    p.dump(p.RAW/'profile'/name/'result.json',result)
    return result


def main():
    assert status(DEFAULT_ROOT) is None,'TIMING_LOCK_OCCUPIED'
    lock=acquire(DEFAULT_ROOT,owner='codex',branch='claude/ego-wall-map',purpose='egomap48 offline exact cache benchmarks',pid=os.getpid(),expected_minutes=10,timing_sensitive=True)
    try:
        rows=[p.run('off-timing')]
        state=p.memory()
        rows.append(p.run('cache-cold',acceleration='match_cache_v1',state=state))
        rows.append(p.run('cache-warm',acceleration='match_cache_v1',state=state))
        with using('scalar_rays_v1'):
            rows.append(p.run('combined-cold',acceleration='match_cache_v1'))
        baseline=p.load(p.RAW/'off-profile/stats.json')
        assert all(r['graph_sha256']==baseline['graph_sha256'] and r['grid_sha256']==baseline['grid_sha256'] for r in rows)
        frames=[frame_replay('combined-off',False),frame_replay('combined-on',True)]
        assert len({r['all_outputs_sha256'] for r in frames})==1
        assert all(r['identical_to_physical']==141 for r in frames)
        p.dump(p.RAW/'benchmark.json',dict(graph=rows,frames=[{k:v for k,v in r.items() if k!='frames'} for r in frames],lock=lock,physics=0,gt_input=False))
    finally:release(DEFAULT_ROOT,owner='codex')

if __name__=='__main__':main()
