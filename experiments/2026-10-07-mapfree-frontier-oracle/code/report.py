"""Read saved episodes only: verify receipts and diagnose first-view connectivity.

No World/episode execution, commands, tuning, added free cells or sensor changes.
Reconstructs the recorded own map exactly before querying the frozen planner.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys
import numpy as np
from scipy.ndimage import label

import run_frontier as run
from harness.public_navigation_resolution import ResolutionActor
from harness.public_navigation.costmap import from_grid
from harness.public_navigation_outline import OutlineCostmap


def lines(path):
    return [json.loads(s) for s in path.read_text().splitlines() if s.strip()]


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+'\n')


def diagnose(path):
    records=lines(path/'actor.jsonl')
    assert len(records)==1  # observed failure shape; refuse to silently omit frames
    record=records[0]
    assert not record['patches'] and not lines(path/'commands.jsonl')
    pose=np.asarray(record['pose_odom'])
    actor=ResolutionActor('own_frontier',navigation='public_ros_v5')
    actor.odom.correct(pose,np.zeros((3,3)))
    actor.t=record['t']
    actor.receive(record['observation'],[])
    grid=run.read(path/'own_grid.json')
    assert grid['resolution_m']==.05
    assert actor.grid.odds=={(x,y):v for x,y,v in grid['cells']}
    original=from_grid(actor.grid,pose,actor.latest,actor.static_hits)
    costmap=OutlineCostmap(original.raw,original.origin,original.resolution)
    labels,n=label(costmap.costs<253)  # 4-connectivity, matching NavFn propagation
    sx,sy=costmap.world_to_map(pose[:2])
    assert labels[sy,sx]>0
    connected=labels==labels[sy,sx]
    yy,xx=np.nonzero(costmap.costs<253)
    cells=np.column_stack([xx,yy])
    points=costmap.map_to_world(cells)
    frontiers=actor.navigator.core.frontiers(costmap.raw,costmap.origin,costmap.resolution,pose[:2])
    details=[]
    for f in frontiers:
        selected=np.linalg.norm(points-f[:2],axis=1)<=.5
        candidates=cells[selected]
        counts=Counter(candidates=len(candidates),connected_candidates=0,native_empty=0,connector_rejected=0,valid=0)
        for x,y in candidates:
            counts['connected_candidates']+=int(connected[y,x])
            path_cells=actor.navigator.core.plan(costmap.costs,(sx,sy),(int(x),int(y)))
            if not len(path_cells):counts['native_empty']+=1
            elif not costmap.sweep_clear(pose,[*costmap.map_to_world(path_cells)[0],pose[2]]):counts['connector_rejected']+=1
            else:counts['valid']+=1
        details.append(dict(centroid=f[:2].tolist(),frontier_cells=int(f[5]),**counts))
    # Native query centroids must equal the recorded, rejected targets.
    events=lines(path/'navigation_events.jsonl')
    rejected=[e['target'] for e in events if e['reason']=='ABORTED_unreachable']
    np.testing.assert_allclose(rejected,[f[:2] for f in frontiers],atol=1e-12)
    floor=np.asarray(record['observation']['floor_xy'])
    unique_x=np.unique(np.round(floor[:,0],9))
    result=dict(case=path.name,grid_exact=True,observations=len(records),
        observed_free_cells=int((costmap.raw==0).sum()),navigable_cells=len(cells),
        navigable_components=int(n),robot_component_cells=int(connected.sum()),
        observed_floor_min_x_m=float(floor[:,0].min()),
        floor_sample_x_spacing_m=float(np.median(np.diff(unique_x))),
        costmap_resolution_m=costmap.resolution,frontiers=details,
        events=dict(Counter(e['reason'] for e in events)))
    return result,(costmap,connected,frontiers,points,pose)


def figure(data,destination):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap
    from matplotlib.patches import Circle,Polygon,Patch
    m,connected,frontiers,points,pose=data
    fig,axes=plt.subplots(1,3,figsize=(12,4),layout='constrained')
    extent=[m.origin[0],m.origin[0]+m.raw.shape[1]*m.resolution,
            m.origin[1],m.origin[1]+m.raw.shape[0]*m.resolution]
    state=np.where(m.raw==255,0,np.where(m.raw==254,2,1))
    for ax in axes[:2]:
        ax.imshow(state,origin='lower',extent=extent,interpolation='nearest',
                  cmap=ListedColormap(['#aeb6c0','#ffffff','#303030']),vmin=0,vmax=2)
        _,polygon=m.footprint_mask(pose)
        ax.add_patch(Polygon(polygon,fill=False,color='#c02b2b',lw=1.5))
        ax.plot(*pose[:2],'r+',ms=8)
    for f in frontiers:
        axes[0].plot(*f[:2],'x',color='#b62685',ms=8)
        axes[0].add_patch(Circle(f[:2],.5,fill=False,color='#b62685',lw=1))
    axes[0].set(xlim=(-.3,3.4),ylim=(-2,1.6),title='s1/K: recorded first view, t=2 s')
    axes[1].set(xlim=(-.2,.85),ylim=(-.4,.4),title='Near robot: unknown gaps')
    axes[1].set_xticks(np.arange(-.2,.86,.1))
    axes[1].grid(alpha=.25)
    graph=np.zeros_like(state)
    graph[m.costs<253]=1
    graph[connected]=2
    axes[2].imshow(graph,origin='lower',extent=extent,interpolation='nearest',
                   cmap=ListedColormap(['#aeb6c0','#f6bd60','#187d98']),vmin=0,vmax=2)
    for f in frontiers:
        selected=points[np.linalg.norm(points-f[:2],axis=1)<=.5]
        axes[2].scatter(selected[:,0],selected[:,1],s=5,color='#b62685')
    axes[2].set(xlim=(-.3,3.4),ylim=(-2,1.6),title='NavFn: 36 reachable / 58 rejected goals')
    for ax in axes:
        ax.set_aspect('equal')
        ax.set_xlabel('own x (m)')
        ax.set_ylabel('own y (m)')
    axes[0].legend(handles=[Patch(color='#aeb6c0',label='Unknown'),Patch(color='white',ec='k',label='Free'),
                           Patch(color='#303030',label='Observed wall')],fontsize=7,loc='lower right')
    destination.parent.mkdir(parents=True,exist_ok=True)
    fig.savefig(destination,dpi=150)
    plt.close(fig)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--raw',type=Path,required=True)
    args=parser.parse_args()
    raw=args.raw
    rows=run.read(raw/'results.json')
    source=run.read(raw/'source.json')
    assert run.hashes()==source['hashes']==run.read(run.EXP/'freeze.json')['hashes']
    gate=run.summary(rows,True)
    assert gate==run.read(raw/'gate.json') and gate['complete'] and not gate['passed']
    starts={(f"s{r['scenario']}",r['start'],r['seed']):np.asarray(r['pose']) for r in run.read(run.EXP/'cohort.json')['rows']}
    audits=[]
    actor_samples=0
    max_pose_error=0.
    for r in rows:
        folder=raw/f"{r['scenario']}-{r['start']}-{r['seed']}-{r['condition']}"
        assert run.read(folder/'result.json')==r
        actors,truth=lines(folder/'actor.jsonl'),lines(folder/'eval_only.jsonl')
        assert len(actors)==len(truth)==r['observations']
        start=starts[(r['scenario'],r['start'],r['seed'])]
        for a,e in zip(actors,truth):
            assert a['t']==e['t'] and a['frame']==e['frame']
            expected=[*run.inverse([e['pose_world'][:2]],start)[0],e['pose_world'][2]-start[2]]
            err=float(np.max(np.abs(np.asarray(a['pose_odom'])-expected)))
            assert err<1e-12
            actor_samples+=1
            max_pose_error=max(max_pose_error,err)
        if r['condition']=='own_frontier':
            d,data=diagnose(folder)
            audits.append(d)
            if folder.name=='s1-K-6701-own_frontier':figure(data,run.EXP/'figures/first-view-connectivity.png')
    assert 'mujoco' not in sys.modules
    frozen_after=run.hashes()==source['hashes']
    assert frozen_after
    out=run.EXP/'results'
    dump(out/'gate.json',gate)
    dump(out/'diagnosis.json',audits)
    dump(out/'verification.json',dict(source_sha=source['sha'],episodes=len(rows),
        original_result_match=64,frozen_files=len(source['hashes']),hashes_unchanged=frozen_after,
        actor_pose_samples=actor_samples,max_pose_component_error=max_pose_error,
        own_map_exact_reconstructions=len(audits),physics=0,model_calls=0,noisy_runs=0))
    dump(out/'raw-manifest.json',dict(root=str(raw),files=[dict(path=str(p.relative_to(raw)),bytes=p.stat().st_size,sha256=run.sha(p))
         for p in sorted(raw.rglob('*')) if p.is_file()]))
    columns=['scenario','start','seed','condition','status','coverage','time_s','distance_m','collisions',
             'door_attempts','false_candidate_passage_attempts']
    import csv
    with (out/'episodes.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=columns,extrasaction='ignore',lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)
    totals=Counter()
    for d in audits:
        for f in d['frontiers']:
            totals.update({k:f[k] for k in ('candidates','connected_candidates','native_empty','connector_rejected','valid')})
    print(json.dumps(dict(gate=gate['checks'],diagnoses=len(audits),targets=dict(totals),
        components_range=[min(d['navigable_components'] for d in audits),max(d['navigable_components'] for d in audits)],
        robot_cells=sorted(set(d['robot_component_cells'] for d in audits)),
        actor_samples=actor_samples,max_pose_error=max_pose_error),indent=2))


if __name__=='__main__':main()
