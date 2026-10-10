"""Evaluation-only explanation of sealed no_path snapshots."""
from pathlib import Path
import sys,json,math
import numpy as np
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
EXP=Path(__file__).resolve().parents[1];OUT=Path('/Users/changmin/projects/ugrp/outputs/active-recovery-v1/diagnostic-off')
RAW=Path('/Users/changmin/projects/ugrp/outputs/rbpf-wide-confirm-v1/new-seed')
from scripts.run_active_wall_wide import dump
from harness.public_navigation_unknown import UnknownCostmap
from harness.public_navigation_monitor import MonitorNavigator
from harness.public_navigation_persistent import raytrace_cells
from harness.self_odom_grid import transform
from harness.active_wall_mapping import ActiveMapper
from harness.active_camera import SEARCH
load=lambda p:json.loads(p.read_text())
rows=lambda p:[json.loads(l) for l in p.read_text().splitlines()]
assert load(OUT/'seal.json')['trace_bytes_equal']
sys.path.insert(0,str(ROOT/'experiments/2026-10-05-ego-wall-map-probe/code'))
import odom_grid_replay as metrics
truth=rows(RAW/'eval_only/trajectory.jsonl');origin=[*truth[0]['robot_xyz_m'][:2],truth[0]['robot_yaw_rad']]
walls=np.array([r['center_m']+r['half_extents_m'] for r in load(RAW/'inputs/static_map.json')['obstacles'] if r.get('kind')=='wall'])
audits=load(OUT/'audits.json');result=[]
sys.path.insert(0,str(ROOT/'outputs/self-map-plot-deps'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon
fig,axes=plt.subplots(1,2,figsize=(12,5))
for index,choice in enumerate([audits[0],audits[4]]):
 z=np.load(OUT/(choice['snapshot']+'.npz'));cost=UnknownCostmap(z['raw'],z['origin'],float(z['resolution']));pose=z['pose'];target=z['target'];nav=MonitorNavigator()
 start=cost.world_to_map(pose[:2]);goal=cost.world_to_map(target);cells=nav.core.plan(cost.costs,start,goal)
 connector=cost.map_to_world(cells)[0] if len(cells) else None
 blocking=set()
 if connector is not None:
  for u in np.linspace(0,1,max(2,math.ceil(np.linalg.norm(connector-pose[:2])/.025)+1)):
   p=np.r_[pose[:2]+u*(connector-pose[:2]),pose[2]];_,poly=cost.footprint_mask(p)
   cs=[cost.world_to_map(q) for q in poly]
   for a,b in zip(cs,cs[1:]+cs[:1]):
    if a is not None and b is not None:
     blocking.update((x,y) for x,y in raytrace_cells(a,b) if cost.costs[y,x]==254)
 blocked_xy=cost.map_to_world(list(blocking)) if blocking else np.empty((0,2))
 dist=metrics.boundary_dist(transform(blocked_xy,origin),walls) if len(blocking) else np.array([])
 # Clear resettable navigation layer, then reapply only current own RGB rays/footprint.
 actor=ActiveMapper('r3',1.3,SEARCH,active_mapping='frontier_rbpf_v1')
 row=next(r for r in rows(RAW/'own-contacts.jsonl') if abs(r['t']-choice['t'])<1e-8)
 actor._rays(row,pose)
 from harness.public_navigation_unknown import from_observed_grid
 fresh=from_observed_grid(actor.grid,pose,actor.latest,set())
 fs=nav.core.frontiers(fresh.raw,fresh.origin,fresh.resolution,pose[:2])
 result.append(dict(t=choice['t'],stage=choice['path_failure'],supplied_goal=choice['supplied_goal'],retained_target=target.tolist(),
   footprint_clear=cost.pose_clear(pose),target_raw=choice['goal_raw'],target_cost=choice['goal_cost'],
   connector=None if connector is None else connector.tolist(),blocking_cells=[list(c) for c in sorted(blocking)],
   blocking_gt_wall_distances_m=dist.tolist(),blocking_false_wall_cells=int((dist>.15).sum()),
   frontiers_before=len(choice['frontiers']),reachable_frontiers_before=sum(x['path_points']>0 for x in choice['frontiers']),
   path_without_inflation=choice['path_without_inflation'],path_after_reset_current_scan=len(nav.plan_to(fresh,pose,target)),
   frontiers_after_reset=len(fs),reachable_frontiers_after_reset=sum(bool(nav.plan_to(fresh,pose,f[:2])) for f in fs)))
 ax=axes[index];extent=[*cost.origin,*(cost.origin+np.array(cost.raw.shape[::-1])*.1)]
 ax.imshow(cost.costs,origin='lower',extent=[extent[0],extent[2],extent[1],extent[3]],cmap='viridis',vmin=0,vmax=255)
 _,poly=cost.footprint_mask(pose);ax.add_patch(Polygon(poly,fill=False,edgecolor='red',linewidth=2))
 if connector is not None:
  ax.plot(*np.array([pose[:2],connector]).T,'w-o',label='start connector')
  _,p2=cost.footprint_mask([*connector,pose[2]]);ax.add_patch(Polygon(p2,fill=False,edgecolor='orange',linewidth=2))
 if len(blocking):ax.scatter(*blocked_xy.T,color='red',s=60,marker='x',label='lethal edge cells')
 ax.scatter(*target,c='cyan',marker='*',s=80,label='retained target')
 if choice['supplied_goal'] is not None:ax.scatter(*choice['supplied_goal'],c='pink',s=50,label='requested B approach')
 ax.set(xlim=(pose[0]-.5,pose[0]+1.1),ylim=(pose[1]-.7,pose[1]+.7),aspect='equal',title=f"t={choice['t']}s: {choice['path_failure']}",xlabel='own x (m)',ylabel='own y (m)');ax.legend(fontsize=7)
fig.tight_layout();(EXP/'figures').mkdir(exist_ok=True);fig.savefig(EXP/'figures/stop-costmap.png',dpi=140)
dump(EXP/'results/offline-cause.json',dict(reproduced_frames=891,audits=audits,geometry=result,
    qualification='GT only classifies blocking cells after sealed replay; not provided to control'))
print(json.dumps(result,indent=2))
