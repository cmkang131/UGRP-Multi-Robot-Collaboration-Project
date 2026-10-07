"""Evaluation only: identify v4 blocked raster cells; no actor or world rollout."""
from pathlib import Path
import hashlib
import importlib.util
import json
import sys
import numpy as np
import cv2

ROOT=Path(__file__).resolve().parents[3]
EXP=Path(__file__).resolve().parents[1]
OUT=Path('/Users/changmin/projects/ugrp/outputs/mapfree-s4-final-v1')
sys.path.insert(0,str(ROOT))
spec=importlib.util.spec_from_file_location('geometry_audit',ROOT/'experiments/2026-10-07-mapfree-stop-geometry/code/audit.py')
a=importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)
from harness.public_navigation_outline import OutlineCostmap
from harness.public_navigation_persistent import raytrace_cells
from harness.self_odom_grid import transform

PREV=Path('/Users/changmin/projects/ugrp/outputs/mapfree-stop-geometry-v1')
CASE='s4-G-4701-static_map'


def polygon(center,half,yaw=0.):
    return transform(np.array([[-1,-1],[1,-1],[1,1],[-1,1]])*half,(*center,yaw))


def overlap(first,second):
    return max(0.,float(cv2.intersectConvexConvex(np.asarray(first,np.float32),np.asarray(second,np.float32))[0]))


def classify_cell(cell,cm,rects):
    xy=cm.map_to_world(cell)
    own=polygon(xy,np.array([cm.resolution/2]*2))
    world=transform(own,a.START)
    centre=transform([xy],a.START)[0]
    walls=[]
    for i,r in enumerate(rects):
        q=np.abs(a.inverse([centre],(*r['center'],r['yaw']))[0])-r['half']
        distance=float(np.linalg.norm(np.maximum(q,0))+min(max(q),0))
        area=overlap(world,polygon(r['center'],r['half'],r['yaw']))
        if distance<=.15 or area>0:
            walls.append(dict(index=i,id=r.get('id'),kind=r.get('kind'),center=r['center'],half=r['half'],yaw=r['yaw'],
                centre_signed_distance_m=distance,overlap_m2=area,centre_inside=bool(max(q)<=0)))
    centre_inside=any(r['centre_inside'] for r in walls)
    cell_overlap=sum(r['overlap_m2'] for r in walls)
    return dict(cell=list(cell),own_center_m=xy.tolist(),world_center_m=centre.tolist(),polygon_world_m=world.tolist(),
        raw=int(cm.raw[cell[1],cell[0]]),cost=int(cm.costs[cell[1],cell[0]]),nearby_geometry=walls,
        classification='true_wall_center' if centre_inside else 'wall_boundary_cell' if cell_overlap>1e-8 else 'raster_padding_only',
        actual_geometry_overlap_fraction=cell_overlap/cm.resolution**2)


def outline_cells(cm,pose):
    _,poly=cm.footprint_mask(pose)
    cells=[cm.world_to_map(p) for p in poly]
    if None in cells:return []
    return sorted(set(c for u,v in zip(cells,cells[1:]+cells[:1]) for c in raytrace_cells(u,v)))


def main():
    dest=OUT/'diagnosis'
    dest.mkdir(parents=True,exist_ok=False)
    folder=PREV/'development-v4'/CASE
    # Stored v3 snapshot is valid only if the complete v4 actor/grid/commands match.
    parity={}
    for name in ('actor.jsonl','own_grid.json','commands.jsonl','navigation_events.jsonl','eval_path.json'):
        new=folder/name
        old=a.OLD/CASE/name
        assert new.read_bytes()==old.read_bytes()
        parity[str(new)]=a.digest(new)
    logs=a.rows(folder/'actor.jsonl')
    prior=a.load(PREV/'audit-v2'/f'{CASE}.json')
    _,static,rects,_=a.load_layout(4)
    goal=a.inverse([static['regions']['zone_B']['center_m']],a.START)[0]
    results=[]
    cms=[]
    for record in prior['snapshots']:
        stage=record['stage']
        npz=PREV/'audit-v2'/f'{CASE}-{stage}.npz'
        arr=np.load(npz)
        cm=OutlineCostmap(arr['raw'],arr['origin'],.1)
        parity[str(npz)]=a.digest(npz)
        log=next(r for r in logs if r['frame']==record['frame'])
        pose=np.asarray(log['pose_odom'])
        samples,blocked,twist=a.projection_samples(cm,pose,log['plan'])
        edge=[] if blocked is None else outline_cells(cm,blocked)
        blockers=[classify_cell(c,cm,rects) for c in edge if cm.costs[c[1],c[0]]>=254]
        path=np.asarray(log['plan']['path_m']).reshape(-1,2)
        path_cells=[cm.world_to_map(p) for p in path]
        footprint=[]
        for p in [pose,blocked] if blocked is not None else [pose]:
            _,poly=cm.footprint_mask(p)
            poly=transform(poly,a.START)
            footprint.append(dict(world_polygon_m=poly.tolist(),wall_overlap_m2=sum(overlap(poly,polygon(r['center'],r['half'],r['yaw'])) for r in rects)))
        g=cm.world_to_map(goal)
        results.append(dict(stage=stage,t=log['t'],pose_odom=pose.tolist(),goal_odom=goal.tolist(),goal_cell=g,
            goal_raw=int(cm.raw[g[1],g[0]]),goal_cost=int(cm.costs[g[1],g[0]]),path_points=len(path),
            path_lethal_centers=sum(cm.costs[y,x]>=254 for x,y in path_cells),
            path_inscribed_centers=sum(cm.costs[y,x]==253 for x,y in path_cells),
            path_unknown_centers=sum(cm.costs[y,x]==255 for x,y in path_cells),
            first_rejected_after_s=None if blocked is None else next(i*.05 for i,p in enumerate(samples) if np.array_equal(p,blocked)),
            rejected_pose=None if blocked is None else blocked.tolist(),blockers=blockers,footprints=footprint,
            path=path.tolist(),frontier=None,condition='static_map'))
        cms.append(cm)
    # NumPy integers are normalized at the serialization boundary.
    results=json.loads(json.dumps(results,default=lambda x:x.item()))
    a.write(dest/'diagnosis.json',dict(records=results,source_hashes=parity,
        terminal_event=prior['terminal_event'],new_physics=0,new_model_calls=0,new_rollouts=0))
    a.write(EXP/'results/diagnosis.json',a.load(dest/'diagnosis.json'))
    plot(results,cms,rects)
    print(json.dumps([{k:v for k,v in r.items() if k not in ('footprints','path')} for r in results],indent=2))


def plot(records,cms,rects):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon
    fig,axes=plt.subplots(1,3,figsize=(15,5),layout='constrained')
    for ax,rec,cm in zip(axes,[records[0],records[0],records[1]],[cms[0],cms[0],cms[1]]):
        extent=[*cm.origin,*cm.origin]  # image corners in own odometry coordinates
        extent=[cm.origin[0],cm.origin[0]+cm.raw.shape[1]*cm.resolution,cm.origin[1],cm.origin[1]+cm.raw.shape[0]*cm.resolution]
        ax.imshow(cm.costs,origin='lower',extent=extent,cmap='YlOrRd',vmin=0,vmax=255,alpha=.6)
        for r in rects:
            poly=a.inverse(polygon(r['center'],r['half'],r['yaw']),a.START)
            ax.add_patch(Polygon(poly,fc='.45',ec='.25',alpha=.85))
        for p,color,label in [(rec['pose_odom'],'blue','Stopped footprint'),(rec['rejected_pose'],'magenta','Rejected projected footprint')]:
            if p is None:continue
            _,poly=cm.footprint_mask(np.asarray(p))
            ax.add_patch(Polygon(poly,fill=False,ec=color,lw=1.8,label=label))
        path=np.array(rec['path']).reshape(-1,2)
        if len(path):ax.plot(*path.T,color='green',label='NavFn path centres')
        ax.scatter(*rec['goal_odom'],marker='*',c='navy',s=100,label='Authored B goal')
        for b in rec['blockers']:
            own=a.inverse(b['polygon_world_m'],a.START)
            ax.add_patch(Polygon(own,fill=False,ec='red',lw=2))
            ax.annotate(str(tuple(b['cell'])),b['own_center_m'],fontsize=8,xytext=(0,-22),textcoords='offset points',ha='center')
        ax.set_aspect('equal')
        ax.set_xlabel('Own x (m)');ax.set_ylabel('Own y (m)')
    axes[0].set_title('s4 static baseline: B and path are free')
    path=np.array(records[0]['path'])
    axes[0].set_xlim(path[:,0].min()-.5,path[:,0].max()+.5)
    axes[0].set_ylim(path[:,1].min()-.5,path[:,1].max()+.5)
    for ax,r in zip(axes[1:],records):
        p=r['pose_odom']
        ax.set_xlim(p[0]-.4,p[0]+.5);ax.set_ylim(p[1]-.4,p[1]+.5)
    axes[1].set_title('110s: boundary cells reject the footprint')
    axes[2].set_title('125s: stopped after recovery exhaustion')
    axes[0].legend(fontsize=7,loc='upper left')
    axes[1].legend(fontsize=7,loc='upper left')
    path=EXP/'figures/s4-blocked-cells.png'
    path.parent.mkdir(parents=True,exist_ok=True)
    fig.savefig(path,dpi=140)
    plt.close(fig)


if __name__=='__main__':main()
