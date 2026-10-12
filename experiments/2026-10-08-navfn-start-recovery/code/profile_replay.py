"""Locked first-30s own-input replay; no simulator/GT, cProfile once."""
from pathlib import Path
import sys,json,time,hashlib,cProfile,pstats,io,os,argparse,collections
from contextlib import contextmanager
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
EXP=Path(__file__).resolve().parents[1]
RAW=Path('/Users/changmin/projects/ugrp/outputs/navfn-start-recovery-v1')
EP=RAW/'new-seed'
from scripts.run_active_navfn_start import actor
from scripts.run_active_wall_rotleft import install_profile,dump
from harness.active_camera import SEARCH
from harness.active_wall_vision import observe


def rows(p):return [json.loads(l) for l in p.read_text().splitlines()]
def blob(v):
    import numpy as np
    return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False,
        default=lambda x:x.tolist() if isinstance(x,np.ndarray) else x.item()).encode()

class Timers:
    def __init__(self):self.stack=[];self.totals=collections.defaultdict(float)
    @contextmanager
    def span(self,name):
        node=[name,time.perf_counter(),0.];self.stack.append(node)
        try:yield
        finally:
            elapsed=time.perf_counter()-node[1];self.stack.pop();self.totals[name]+=elapsed-node[2]
            if self.stack:self.stack[-1][2]+=elapsed
    def wrap(self,obj,name,label):
        original=getattr(obj,name)
        def wrapper(*a,**kw):
            with self.span(label):return original(*a,**kw)
        setattr(obj,name,wrapper)
        return lambda:setattr(obj,name,original)


def replay(name,profile=False,acceleration='off'):
    import numpy as np
    from PIL import Image
    from harness.self_odom_grid import OdomGrid
    import harness.wall_confidence as confidence
    frames=rows(EP/'robots/r3/frames.jsonl')[:151]
    expected={r['frame_id']:r for r in rows(EP/'own-controller.jsonl')}
    start=frames[0]['sim_time']
    c=actor('r3',start,SEARCH,active_mapping='frontier_rbpf_v1',active_loop='information_gain_v1',seed=47001,
        active_recovery='nav2_frontier_v1',navigation_map='public_ros_v8',motion_model='s2_pulse_v122_rotL_v1')
    install_profile(c.memory.self_map,profile='egomap27_wide')
    if acceleration!='off':
        from harness.grid_acceleration import install
        install(c,map_acceleration=acceleration)
    timers=Timers();undo=[]
    for obj,fn,label in [(c,'graph','pose_graph'),(c.memory.self_map,'observe_contacts_confident','rbpf_matching'),
            (OdomGrid,'insert','map_insertion'),(confidence,'weighted_insert','map_insertion'),
            (c.navigator.core,'plan','navfn_plan'),(c.navigator.core,'frontiers','frontier_search')]:
        undo.append(timers.wrap(obj,fn,label))
    traces=[];measure=[];states=hashlib.sha256();prof=cProfile.Profile() if profile else None
    started=time.perf_counter()
    try:
        for i,frame in enumerate(frames):
            if prof:prof.enable()
            before=dict(timers.totals);t=frame['sim_time'];tick=time.perf_counter()
            with timers.span('image_decode'):
                rgb=np.asarray(Image.open(EP/frame['path']).convert('RGB'))
            if i>=10:
                with timers.span('wall_detection'):obs=observe(rgb,SEARCH,body_settling=.7)
                with timers.span('controller_other'):
                    command,trace=c.receive(robot_id='r3',t=t,frame_id=frame['frame_id'],rgb=rgb,servo=SEARCH,observation=obs)
                # Preserve issued commands: final profile frame was not final physical frame.
                with timers.span('command_propagation'):c.command(expected[frame['frame_id']]['command'])
            elapsed=time.perf_counter()-tick
            if prof:prof.disable()
            if i>=10:
                same=blob(trace)==blob(expected[frame['frame_id']])
                traces.append(dict(t=t,identical_to_physical=same))
                states.update(blob(dict(trace=trace,grid=c.memory.self_map.export(),poses=c.poses)))
                measure.append(dict(elapsed_s=t-start,wall_s=elapsed,status=trace['status'],
                    map_cells=len(c.memory.self_map.maps[c.memory.self_map.best].cells),particles=len(c.memory.self_map.maps),
                    inserted=len(c.memory.self_map.ledger),parts={k:v-before.get(k,0) for k,v in timers.totals.items()}))
            if i%50==0:print(name,i,flush=True)
    finally:
        for f in reversed(undo):f()
    out=RAW/'profile'/name;out.mkdir(parents=True,exist_ok=False)
    if prof:
        prof.dump_stats(out/'cpu.prof');buf=io.StringIO();pstats.Stats(prof,stream=buf).sort_stats('cumtime').print_stats(50)
        (out/'top.txt').write_text(buf.getvalue())
    measured=sum(r['wall_s'] for r in measure)
    result=dict(name=name,profile=profile,acceleration=acceleration,sim_s=30,rgb=151,controller_frames=len(traces),
        identical_to_physical=sum(x['identical_to_physical'] for x in traces),all_outputs_sha256=states.hexdigest(),
        measured_wall_s=measured,wall_per_sim=measured/30,total_replay_wall_s=time.perf_counter()-started,
        parts=dict(timers.totals),frames=measure,rendering='NOT_MEASURED_saved_JPEG_only',gt_input=False,physics=0)
    dump(out/'result.json',result);print(json.dumps({k:v for k,v in result.items() if k!='frames'},indent=2))
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('name');p.add_argument('--profile',action='store_true');p.add_argument('--acceleration',default='off');a=p.parse_args()
    from scripts.agent_lock import DEFAULT_ROOT,status,acquire,release
    assert status(DEFAULT_ROOT) is None,'TIMING_LOCK_OCCUPIED'
    lock=acquire(DEFAULT_ROOT,owner='codex',branch='claude/ego-wall-map',purpose='egomap47 offline profile '+a.name,pid=os.getpid(),expected_minutes=10,timing_sensitive=True)
    try:replay(a.name,a.profile,a.acceleration)
    finally:release(DEFAULT_ROOT,owner='codex')
    dump(RAW/'profile'/a.name/'lock.json',lock)

if __name__=='__main__':main()
