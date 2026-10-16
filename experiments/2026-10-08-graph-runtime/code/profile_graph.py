"""Own saved frontend -> original final graph. No simulator or GT imports."""
from pathlib import Path
import argparse,cProfile,hashlib,io,json,os,pstats,sys,time
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
EXP=Path(__file__).resolve().parents[1]
RAW=Path('/Users/changmin/projects/ugrp/outputs/graph-runtime-v1')
EP=Path('/Users/changmin/projects/ugrp/outputs/navfn-start-recovery-v1/new-seed')
from scripts.run_active_wall_rotleft import dump


def load(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def encoded(v):
    import numpy as np
    return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False,
        default=lambda x:x.tolist() if isinstance(x,np.ndarray) else x.item()).encode()


def inputs():
    manifest=load(EP/'artifacts.sha256.json')
    for name in ('frontend-ledger.json','frontend-poses.json','bundle.json'):
        assert sha(EP/name)==manifest[name]
    return load(EP/'frontend-ledger.json'),load(EP/'frontend-poses.json'),load(EP/'bundle.json')


def memory():
    from harness.self_wall_memory_robust import SelfWallMemory
    rows,poses,bundle=inputs()
    m=SelfWallMemory('r3',**bundle['estimator_options'],self_map_options={'start_time':1.3})
    m.self_map.ledger=rows
    return m,poses


def run(name,profile=False,acceleration='off',state=None):
    import harness.self_pose_graph as g
    import harness.self_loop_rejection as rejection
    import harness.self_wall_memory_robust as robust
    out=RAW/name;out.mkdir(parents=True,exist_ok=False)
    m,poses=memory() if state is None else state;durations={};calls={};reports={};undo=[]
    if acceleration!='off' and not hasattr(m,'graph_cache'):
        from harness.self_graph_cache import install
        install(m,graph_acceleration=acceleration)
    def wrap(obj,fn,label):
        original=getattr(obj,fn)
        def observed(*a,**kw):
            start=time.perf_counter()
            try:
                result=original(*a,**kw)
                if label in ('legacy_optimize','switchable_optimize'):reports[label]=result[1]
                return result
            finally:
                durations[label]=durations.get(label,0.)+time.perf_counter()-start
                calls[label]=calls.get(label,0)+1
        setattr(obj,fn,observed);undo.append(lambda:setattr(obj,fn,original))
    for obj,fn,label in [(g,'make_submaps','make_submaps'),(g,'match_loop','match_loop'),
        (g,'optimize','legacy_optimize'),(rejection,'optimize_switchable','switchable_optimize'),
        (g,'rebuild','legacy_rebuild'),(robust,'rebuild','robust_rebuild'),
        (g.ProbabilityField,'__init__','probability_field'),(g.DistanceField,'__init__','distance_field')]:wrap(obj,fn,label)
    prof=cProfile.Profile() if profile else None
    if prof:prof.enable()
    start=time.perf_counter()
    try:result=m.finalize_pose_graph(poses)
    finally:
        wall=time.perf_counter()-start
        if prof:prof.disable()
        for restore in reversed(undo):restore()
        if prof:
            prof.dump_stats(out/'cpu.prof');s=io.StringIO();pstats.Stats(prof,stream=s).sort_stats('cumtime').print_stats(65)
            (out/'top.txt').write_text(s.getvalue())
    grid=m._graph_view.export();d=result['diagnostics']
    dump(out/'graph.json',result);dump(out/'grid.json',grid)
    stats=dict(name=name,profile=profile,graph_acceleration=acceleration,wall_s=wall,stage_s=durations,
        calls=calls,optimizers=reports,scans=len(result['ledger']),path_nodes=len(poses),
        pose_nodes=len(d['submaps'])+len(result['ledger']),submaps=len(d['submaps']),
        constraints=len(d['constraints']),loop_counts=d['loop_counts'],switch_counts=d.get('switch_counts'),
        graph_sha256=hashlib.sha256(encoded(result)).hexdigest(),grid_sha256=hashlib.sha256(encoded(grid)).hexdigest(),
        source_sha=__import__('subprocess').check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        input_sha256={n:sha(EP/n) for n in ('frontend-ledger.json','frontend-poses.json','bundle.json')},
        gt_input=False,physics=0)
    if hasattr(m,'graph_cache'):stats['cache']=m.graph_cache.stats()
    dump(out/'stats.json',stats)
    print(json.dumps({k:v for k,v in stats.items() if k not in ('optimizers','input_sha256')},indent=2),flush=True)
    return stats


def main():
    p=argparse.ArgumentParser();p.add_argument('name');p.add_argument('--profile',action='store_true');p.add_argument('--acceleration',default='off');a=p.parse_args()
    from scripts.agent_lock import DEFAULT_ROOT,status,acquire,release
    assert status(DEFAULT_ROOT) is None,'TIMING_LOCK_OCCUPIED'
    lock=acquire(DEFAULT_ROOT,owner='codex',branch='claude/ego-wall-map',purpose='egomap48 graph '+a.name,pid=os.getpid(),expected_minutes=15,timing_sensitive=True)
    try:run(a.name,a.profile,a.acceleration)
    finally:release(DEFAULT_ROOT,owner='codex')
    dump(RAW/a.name/'lock.json',lock)

if __name__=='__main__':main()
