"""Additional legacy FOV-region precision; retain registered tube metrics too."""
from map_replay import *
from scipy.spatial import cKDTree
sys.path.insert(0,str(ROOT/'experiments/2026-10-05-ego-wall-map-probe/code'))
import odom_grid_replay as metric

def audit(seed):
 result=load(EXP/'results'/f'map-{seed}.json');dest=OUT/'maps'/str(seed);seal=load(dest/'prediction.json');ep=source(seed)
 truth=rows(ep/'eval_only/trajectory.jsonl');origin=[*truth[0]['robot_xyz_m'][:2],truth[0]['robot_yaw_rad']]
 cameras=[r for r in rows(ep/'eval_only/camera.jsonl') if r['t']<=seal['last_t']]
 walls=np.array([w['center_m']+w['half_extents_m'] for w in load(ep/'inputs/static_map.json')['obstacles'] if w.get('kind')=='wall'])
 report=dict(seed=seed,conditions={})
 for mode in ['off','hygiene','accumulation']:
  assert sha(dest/(mode+'.json'))==seal['files'][mode]
  g=load(dest/(mode+'.json'));cells=np.array([r for r in g['cells'] if r[2]>0]).reshape(-1,3);xy=transform((cells[:,:2]+.5)*g['resolution_m'],origin)
  region=visible(xy,cameras,walls,4.);correct=metric.boundary_dist(xy,walls)<=.15
  report['conditions'][mode]=dict(legacy_region_precision=float(correct[region].mean()) if region.any() else None,correct_cells=int(correct[region].sum()),region_cells=int(region.sum()),potential_visible_recall=result['conditions'][mode]['visible_4m_recall'])
 a,b=[report['conditions'][m]['legacy_region_precision'] for m in ['off','hygiene']]
 report['legacy_precision_nondecrease']=a is not None and b is not None and b>=a
 dump(EXP/'results'/f'visibility-{seed}.json',report)
 print(seed,'legacy visible area',report['conditions'],flush=True)
if __name__=='__main__':
 for seed in [49001,49002,49003,49004,49005,49006,32002]:audit(seed)
