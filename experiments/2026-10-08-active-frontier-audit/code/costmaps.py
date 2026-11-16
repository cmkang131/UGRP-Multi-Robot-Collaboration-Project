"""Rebuild from sealed OWN observations; GT-only barrier ablation stays in evaluation."""
from pathlib import Path
import sys,json,hashlib
import numpy as np
from scipy.ndimage import label
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
EXP=Path(__file__).resolve().parents[1]
RAW=Path('/Users/changmin/projects/ugrp/outputs/active-frontier-audit-v1')
EP=Path('/Users/changmin/projects/ugrp/outputs/active-recovery-v1/new-seed')
from harness.own_map_navigation import ObservedGrid
from harness.public_navigation_raytrace import receive_rays
from harness.public_navigation_unknown import clear_current_footprint,from_observed_grid,UnknownCostmap
from harness.public_navigation_resolution import RESOLUTION
from harness.active_wall_recovery import ExplorationRecoveryNavigator
from harness.self_map_csm import sample_segments
from harness.self_odom_grid import transform
from scripts.run_active_wall_recovery import dump
load=lambda p:json.loads(p.read_text())
rows=lambda p:[json.loads(s) for s in p.read_text().splitlines()]


def rebuild(records,res):
    grid=ObservedGrid('r3',res);latest={}
    for item in records:
        r,p=item['row'],item['pose']; wall=sample_segments(r['segments']) if r['segments'] else np.empty((0,2))
        floor=np.array(r['floor_xy']).reshape(-1,2)
        receive_rays(grid,latest,set(),dict(robot_id='r3',frame_id=r['frame_id'],floor_xy=floor,wall_xy=wall,
            floor_origins_xy=np.tile(r['camera'],(len(floor),1)),wall_origins_xy=np.tile(r['camera'],(len(wall),1))),p)
        clear_current_footprint(grid,latest,set(),p)
    return grid,latest


def stats(cost,pose,blacklist):
    nav=ExplorationRecoveryNavigator();nav.blacklist=[np.array(p) for p in blacklist]
    fronts=nav.core.frontiers(cost.raw,cost.origin,cost.resolution,pose[:2])
    out=[]
    for f in fronts:
        cell=cost.world_to_map(f[:2]);start=cost.world_to_map(pose[:2])
        path=nav.plan_to(cost,pose,f[:2]);cells=nav.core.plan(cost.costs,start,cell)
        out.append(dict(center=f[:2].tolist(),goal_raw=int(cost.raw[cell[1],cell[0]]),
            goal_cost=int(cost.costs[cell[1],cell[0]]),blacklisted=nav.blocked(f[:2],cost.resolution),
            path_points=len(path),navfn_cells=len(cells)))
    comps,n=label(cost.raw==0);start=cost.world_to_map(pose[:2]);c=comps[start[1],start[0]]
    return dict(resolution=cost.resolution,shape=list(cost.raw.shape),free_cells=int((cost.raw==0).sum()),
        occupied_cells=int((cost.raw==254).sum()),unknown_cells=int((cost.raw==255).sum()),
        free_components=n,start_component_cells=int((comps==c).sum()) if c else 0,
        footprint_clear=cost.pose_clear(pose),frontiers=out,
        available=sum(not x['blacklisted'] and bool(x['path_points']) for x in out))


def main():
    src=RAW/'diagnostic-off';seal=load(src/'seal.json');assert seal['trace_bytes_equal']
    assert (src/'traces.jsonl').read_bytes()==(EP/'own-controller.jsonl').read_bytes()
    a=load(src/'audits.json')[-1];z=np.load(src/(a['snapshot']+'.npz'));records=load(src/(a['snapshot']+'-own-rebuild.json'))
    costs=[];report={}
    for res in [.1,RESOLUTION]:
        grid,latest=rebuild(records,res);cost=from_observed_grid(grid,z['pose'],latest,set());costs.append(cost)
        if res==.1:
            assert np.array_equal(cost.raw,z['raw']) and np.array_equal(cost.costs,z['costs'])
        report[str(res)]=stats(cost,z['pose'],a['before']['blacklist'])
    # Seal all own-only counterfactuals before opening evaluation truth.
    dump(RAW/'own-costmap-comparison.json',report)
    sys.path.insert(0,str(ROOT/'experiments/2026-10-05-ego-wall-map-probe/code'))
    import odom_grid_replay as metric
    truth=rows(EP/'eval_only/trajectory.jsonl');origin=[*truth[0]['robot_xyz_m'][:2],truth[0]['robot_yaw_rad']]
    walls=np.array([r['center_m']+r['half_extents_m'] for r in load(EP/'inputs/static_map.json')['obstacles'] if r.get('kind')=='wall'])
    false_masks=[]
    for cost in costs:
        yy,xx=np.nonzero(cost.raw==254);xy=cost.map_to_world(np.c_[xx,yy]);dist=metric.boundary_dist(transform(xy,origin),walls)
        mask=np.zeros_like(cost.raw,bool);mask[yy[dist>.15],xx[dist>.15]]=True;false_masks.append(mask)
        entry=report[str(cost.resolution)];entry['false_wall_cells_gt_eval']=int(mask.sum())
        diagnostic=cost.raw.copy();diagnostic[mask]=0
        entry['GT_EVALUATION_ONLY_false_cells_removed']=stats(UnknownCostmap(diagnostic,cost.origin,cost.resolution),z['pose'],a['before']['blacklist'])
    report.update(t=a['t'],navigation_epoch=a['epoch'],record_count=len(records),full_trace_frames=seal['frames'],
        qualification='0.05 navigation is rebuilt from raw own rays/own poses. GT ablation is evaluation only, never used by controller or option. No new pose/physical performance from fixed recording.')
    dump(EXP/'results/costmap-audit.json',report)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon
    from matplotlib.colors import ListedColormap
    fig,axes=plt.subplots(1,2,figsize=(12,5))
    for ax,cost,false in zip(axes,costs,false_masks):
        v=np.where(cost.raw==255,0,np.where(cost.raw==254,3,np.where(cost.costs>=253,2,1)))
        hi=cost.origin+np.array(cost.raw.shape[::-1])*cost.resolution
        ax.imshow(v,origin='lower',extent=[cost.origin[0],hi[0],cost.origin[1],hi[1]],vmin=0,vmax=3,cmap=ListedColormap(['.75','white','#ffdab0','#333333']))
        y,x=np.nonzero(false);xy=cost.map_to_world(np.c_[x,y]);ax.scatter(*xy.T,s=5,c='red',label='False hit (>0.15m, evaluation)')
        _,poly=cost.footprint_mask(z['pose']);ax.add_patch(Polygon(poly,fill=False,edgecolor='blue'))
        for f in report[str(cost.resolution)]['frontiers']:
            ax.scatter(*f['center'],marker='*',s=100,c='green' if f['path_points'] else 'purple')
        ax.set(aspect='equal',title=f"{cost.resolution:.2f}m: {report[str(cost.resolution)]['available']} reachable frontier",xlabel='own x (m)',ylabel='own y (m)');ax.legend(fontsize=7)
    fig.tight_layout();fig.savefig(EXP/'figures/costmaps.png',dpi=140);plt.close(fig)
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
