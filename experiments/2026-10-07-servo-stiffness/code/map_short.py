"""One gate-admitted own-camera map. Prediction seal precedes all truth reads."""
from pathlib import Path
import importlib.util
import json
import math
import subprocess
import sys
import numpy as np
EXP=Path(__file__).resolve().parents[1]
ROOT=EXP.parents[1]
spec=importlib.util.spec_from_file_location('egomap19_replay',Path(__file__).with_name('replay.py'))
r=importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)
c=r.c
RAW=r.RAW
CASE='stiff-explore'
EPISODE=RAW/CASE
OUT=RAW/'short-map'


def predict():
    from harness.self_wall_memory_motion import SelfWallMemory
    from harness.self_pose_graph import rebuild
    assert all(c.read(EXP/'results/pulse'/(case+'-floor.json'))['gate']['passed']
               for case in ('stiff-north','stiff-south'))
    OUT.mkdir(exist_ok=False)
    c.EPISODES={CASE:EPISODE}
    r.MODE='pulse'
    frames,commands=c.old.own_inputs(EPISODE,'r3')
    contacts=[]
    command_cursor=0
    expiry=-math.inf
    for f,cm,reason,pose,cov in r.stream(CASE):
        t=f['sim_time']
        while command_cursor<len(commands) and commands[command_cursor]['t']<t-1e-8:
            cmd=commands[command_cursor]
            if cmd['kind'] in ('mecanum','drive'):expiry=cmd['t']+cmd['duration_s']
            elif cmd['kind'] in ('hold','stop'):expiry=min(expiry,cmd['t'])
            command_cursor+=1
        if cm is None:continue
        segments,features,guard=c.old.detections(EPISODE,f,cm,np.zeros(3),.5+.5*np.clip((t-expiry)/.25,0,1))
        keep=[i for i,s in enumerate(segments) if np.linalg.norm(np.asarray(s)-cm.origin[:2],axis=1).max()<=4.]
        if keep:
            contacts.append(dict(frame_id=f['frame_id'],t=t,camera=cm.origin[:2].tolist(),
                segments=[segments[i] for i in keep],features=[features[i] for i in keep],guard=guard))
    c.old.rows(OUT/'contacts.jsonl',contacts)
    options=dict(self_map='odom_grid_v1',pose_correction='own_map_rbpf_v1',pose_correction_options={'particles':100},
        wall_projection_guard='positive_depth_v1',pose_graph='own_submap_v1',wall_confidence='inverse_sensor_v1',
        self_map_options={'start_time':frames[0]['sim_time']},motion_model='s2_pulse_v122')
    memory=SelfWallMemory('r3',**options)
    memory.command(dict(t=frames[0]['sim_time'],kind='initial_servo_command',pulses=frames[0]['commanded_servo']))
    grid=memory.self_map
    index={row['frame_id']:row for row in contacts}
    cursor=0
    poses=[]
    for i,f in enumerate(frames):
        t=f['sim_time']
        while cursor<len(commands) and commands[cursor]['t']<t-1e-8:
            memory.command(commands[cursor])
            cursor+=1
        grid.odom.advance(t)
        contact=index.get(f['frame_id'])
        if contact:
            grid.observe_contacts_confident(t=t,frame_id=f['frame_id'],segments=contact['segments'],
                features=contact['features'],camera_xy=contact['camera'],robot_id='r3')
        poses.append(dict(robot_id='r3',t=t,pose=grid.odom.pose))
        if i%50==0:print('RBPF100',i,'/',len(frames),'inserted',grid.frames,flush=True)
    c.old.rows(OUT/'frontend-poses.jsonl',poses)
    c.old.rows(OUT/'frontend-ledger.jsonl',grid.ledger)
    c.old.rows(OUT/'frontend-decisions.jsonl',grid.decisions)
    c.dump(OUT/'frontend-grid.json',grid.export())
    assert rebuild('r3',grid.ledger).export()['cells']==grid.export()['cells']
    print('Graph scans',len(grid.ledger),flush=True)
    graph=memory.finalize_pose_graph(poses)
    c.old.rows(OUT/'graph-poses.jsonl',graph['poses'])
    c.old.rows(OUT/'graph-ledger.jsonl',graph['ledger'])
    c.dump(OUT/'graph-diagnostics.json',graph['diagnostics'])
    c.dump(OUT/'grid.json',memory._graph_view.export())
    (OUT/'llm.txt').write_text(memory.snapshot()['self_map_text']+'\n')
    c.dump(OUT/'prediction.json',dict(source_sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        options=options,camera='v3_unloaded_extrinsic_v1',detector='off',frontend_counts=grid.export()['correction_counts'],
        inserted=grid.frames,loop_counts=graph['diagnostics']['loop_counts'],
        inputs={str(p):c.sha(p) for p in [EPISODE/'robots/r3/frames.jsonl',EPISODE/'robots/r3/commands.jsonl']},
        hashes={p.name:c.sha(p) for p in OUT.iterdir() if p.is_file()}))
    assert 'mujoco' not in sys.modules
    print('Own map sealed',flush=True)


def score():
    from harness.self_odom_grid import transform,OdomGrid
    from harness.self_pose_graph import rebuild
    frozen=c.read(OUT/'prediction.json')
    assert all(c.sha(OUT/p)==h for p,h in frozen['hashes'].items())
    truth=c.old.current_truth(EPISODE)
    poses=c.old.base.read_rows(OUT/'graph-poses.jsonl')
    origin=truth[round(poses[0]['t'],6)]
    rects=np.array([w['center_m']+w['half_extents_m'] for w in c.read(EPISODE/'inputs/static_map.json')['obstacles'] if w.get('kind')=='wall'])
    samples=c.old.base.wall_samples(rects)
    grid=OdomGrid('r3')
    grid.cells={(x,y):v for x,y,v in c.read(OUT/'grid.json')['cells']}
    occupied=transform(grid.occupied_points(),origin)
    quality=c.old.base.quality(occupied,rects,samples)[0]
    result=dict(quality=quality,path=c.old.path_score(poses,truth),inserted=frozen['inserted'],
        loop_counts=frozen['loop_counts'],frontend_counts=frozen['frontend_counts'],
        qualification='new plant, 30 s authored path, not autonomous exploration or S2/hardware validation')
    c.dump(EXP/'results/short-map.json',result)
    # Standard plot stack, installed previously outside runtime venv.
    sys.path.insert(0,str(ROOT/'outputs/self-map-plot-deps'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    fig,ax=plt.subplots(figsize=(8,6))
    for x,y,hx,hy in rects:
        ax.add_patch(Rectangle((x-hx,y-hy),2*hx,2*hy,color='.7',label=None))
    cells=[(x,y,v) for (x,y),v in sorted(grid.cells.items()) if v>0]
    xy=transform(np.array([[(x+.5)*.1,(y+.5)*.1] for x,y,v in cells]),origin)
    belief=1/(1+np.exp(-np.array([v for x,y,v in cells])))
    points=ax.scatter(xy[:,0],xy[:,1],c=belief,cmap='Blues',vmin=.5,vmax=1.,s=22,marker='s',label='Own map')
    path=transform(np.array([p['pose'][:2] for p in poses]),origin)
    ax.plot(path[:,0],path[:,1],color='#ed7d31',lw=1.6,label='Estimated path')
    gt=np.array([truth[round(p['t'],6)][:2] for p in poses])
    ax.plot(gt[:,0],gt[:,1],'--',color='#338855',lw=1,label='GT path (evaluation)')
    fig.colorbar(points,ax=ax,label='Occupancy belief (log-odds; not calibrated correctness)')
    ax.set(aspect='equal',xlabel='world x (m), start GT alignment only',ylabel='world y (m)',
        title='New servo plant / tape / v122 + RBPF100 + pose graph')
    ax.legend(loc='lower left')
    fig.tight_layout()
    dest=EXP/'figures'
    dest.mkdir(exist_ok=True)
    fig.savefig(dest/'short-map.png',dpi=150)
    plt.close(fig)
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument('stage',choices=['predict','score'])
    args=p.parse_args()
    predict() if args.stage=='predict' else score()
