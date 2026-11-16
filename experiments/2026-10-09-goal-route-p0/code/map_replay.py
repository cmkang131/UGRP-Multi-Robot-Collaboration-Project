"""P0 map-only replay. Predict/seal without GT; evaluate in a separate call."""
from pathlib import Path
import argparse,hashlib,json,math,subprocess,sys
import numpy as np
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from harness import goal_route_p0 as adapter
from harness.self_pulse_odom import command_odometry
from harness.self_odom_grid import transform
from harness.grid_acceleration import using
BASE=Path('/Users/changmin/projects/ugrp/outputs')
OUT=BASE/'goal-route-p0-v1';EXP=Path(__file__).resolve().parents[1]
def load(p):return json.loads(Path(p).read_text())
def rows(p):return [json.loads(l) for l in Path(p).read_text().splitlines()]
def dump(p,value):
 p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(value,allow_nan=False,indent=2)+'\n')
def sha(p):return hashlib.file_digest(Path(p).open('rb'),'sha256').hexdigest()
def source(seed):return BASE/('wall-segment-dev-v1/new-seed' if seed==32002 else f'own-map-return-repeat-v1/seed{seed}')
def predict(seed):
 ep=source(seed);dest=OUT/'maps'/str(seed);dest.mkdir(parents=True,exist_ok=False)
 names=['frontend-grid.json','frontend-ledger.json','own-controller.jsonl','frontend-covariances.jsonl','own-contacts.jsonl','decisions.json','bundle.json']
 hashes={n:sha(ep/n) for n in names}
 grid=load(ep/names[0]);ledger=load(ep/names[1]);poses=rows(ep/'frontend-covariances.jsonl');trace=rows(ep/'own-controller.jsonl');obs=rows(ep/'own-contacts.jsonl');dec=load(ep/'decisions.json')
 last=poses[-1]['t'];trace=[r for r in trace if r['t']<=last]
 odom=command_odometry(trace[0]['t'],motion_model=load(ep/'bundle.json')['estimator_options']['motion_model'])
 dr={}
 for r in trace:
  dr[r['frame_id']]=list(odom.advance(r['t']));odom.command(r['command'])
 with using('scalar_rays_v1'):
  outputs={'off':adapter.hygiene(grid,ledger,poses),
    'hygiene':adapter.hygiene(grid,ledger,poses,route_hygiene=adapter.HYGIENE),
    'accumulation':adapter.accumulate(grid,ledger,obs,poses,dr,dec,scan_accumulation=adapter.ACCUMULATE)}
 assert outputs['off'] is grid
 for key,value in outputs.items():dump(dest/(key+'.json'),value)
 dump(dest/'prediction.json',dict(seed=seed,inputs=hashes,input_root=str(ep),gt_inputs=False,
  source_sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
  files={key:sha(dest/(key+'.json')) for key in outputs},
  off_bytes_identical=json.dumps(outputs['off']).encode()==json.dumps(grid).encode(),
  insertion_keyframes=len(ledger),observed_frames=len([r for r in obs if r['t']<=last]),last_t=last,
  gate_counts={k:sum(r['reason']==k for r in dec) for k in sorted(set(r['reason'] for r in dec))}))
 print(seed,'SEALED',outputs['accumulation']['scan_accumulation']['integrated_observations'],flush=True)


def visible(points,cameras,rects,maximum):
 # Existing egomap22 score.in_view, only range exposed for denominator audit.
 sys.path.insert(0,str(ROOT/'experiments/2026-09-26-markerless-probe'))
 import markerless_probe as mp
 pts=np.c_[points,np.full(len(points),.01)];ever=np.zeros(len(points),bool)
 for camera in cameras:
  origin=np.array(camera['camera_xyz']);R=np.array(camera['camera_rotation']).reshape(3,3)@np.diag([1,-1,-1])
  vec=pts-origin;optical=vec@R
  with np.errstate(divide='ignore',invalid='ignore'):uv=(optical@mp.K.T)[:,:2]/optical[:,2,None]
  candidate=(~ever)&(optical[:,2]>0)&(uv[:,0]>=0)&(uv[:,0]<640)&(uv[:,1]>=0)&(uv[:,1]<480)&(np.linalg.norm(vec,axis=1)<=maximum)
  ids=np.flatnonzero(candidate)
  if not len(ids):continue
  d=pts[ids,:2]-origin[:2];blocked=np.zeros(len(ids),bool)
  for x,y,hx,hy in rects:
   lo=np.array([x-hx,y-hy]);hi=np.array([x+hx,y+hy])
   with np.errstate(divide='ignore',invalid='ignore'):a=(lo-origin[:2])/d;b=(hi-origin[:2])/d
   entry=np.maximum(np.minimum(a,b).max(1),0);exit=np.minimum(np.maximum(a,b).min(1),1)
   blocked|=(entry<exit)&(entry<1-.05/np.maximum(np.linalg.norm(d,axis=1),.05))&(exit>0)
  ever[ids[~blocked]]=True
 return ever


def evaluate(seed):
 from scipy.spatial import cKDTree
 sys.path.insert(0,str(ROOT/'experiments/2026-10-05-ego-wall-map-probe/code'))
 import odom_grid_replay as metric
 dest=OUT/'maps'/str(seed);seal=load(dest/'prediction.json');ep=source(seed)
 for k,h in seal['files'].items():assert sha(dest/(k+'.json'))==h
 truth=[r for r in rows(ep/'eval_only/trajectory.jsonl') if r['t']<=seal['last_t']]
 cameras=[r for r in rows(ep/'eval_only/camera.jsonl') if r['t']<=seal['last_t']]
 static=load(ep/'inputs/static_map.json');origin=[*truth[0]['robot_xyz_m'][:2],truth[0]['robot_yaw_rad']]
 walls=np.array([o['center_m']+o['half_extents_m'] for o in static['obstacles'] if o.get('kind')=='wall']);samples=metric.wall_samples(walls)
 all_gt=np.array([r['robot_xyz_m'][:2] for r in truth]);tree_path=cKDTree(all_gt)
 near=visible(samples,cameras,walls,2.5);seen=visible(samples,cameras,walls,4.)
 estimated=rows(ep/'frontend-covariances.jsonl');path=transform([r['pose'][:2] for r in estimated],origin)
 eligible_path=cKDTree(path).query(all_gt)[0]<=1.
 c,s=np.cos(origin[2]),np.sin(origin[2]);local_gt=(all_gt-origin[:2])@np.array([[c,-s],[s,c]])
 reports={}
 for name in seal['files']:
  g=load(dest/(name+'.json'));cells=np.array([r for r in g['cells'] if r[2]>0]).reshape(-1,3)
  xy=transform((cells[:,:2]+.5)*g['resolution_m'],origin);q,cover=metric.quality(xy,walls,samples)
  distance=metric.boundary_dist(xy,walls);sd=cKDTree(xy).query(samples)[0] if len(xy) else np.full(len(samples),np.inf)
  area=tree_path.query(xy)[0]<=1. if len(xy) else np.array([],bool)
  wall_area=tree_path.query(samples)[0]<=1.
  xmin,xmax,ymin,ymax=static['bounds_m'];outside=np.linalg.norm(np.maximum(np.c_[xmin-xy[:,0],ymin-xy[:,1]],np.maximum(np.c_[xy[:,0]-xmax,xy[:,1]-ymax],0)),axis=1)
  values={(x,y):v for x,y,v in g['cells']};gtkeys=np.floor(local_gt/g['resolution_m']).astype(int)
  unknown=np.array([tuple(k) not in values or values[tuple(k)]==0 for k in gtkeys])
  row=dict(**q,full_wall_samples=len(samples),full_covered_015=int(cover.sum()),coverage_040=float((sd<=.4).mean()),
   visible_4m_samples=int(seen.sum()),visible_4m_recall=float(cover[seen].mean()) if seen.any() else None,
   reduced_2p5m_samples=int(near.sum()),reduced_2p5m_recall=float(cover[near].mean()) if near.any() else None,
   reduced_2p5m_cover_040=float((sd[near]<=.4).mean()) if near.any() else None,
   area_occupied_cells=int(area.sum()),area_precision=float((distance[area]<=.15).mean()) if area.any() else None,
   area_wall_samples=int(wall_area.sum()),area_recall=float(cover[wall_area].mean()) if wall_area.any() else None,
   outside_050_cells=int((outside>=.5).sum()),gt_path_samples=len(truth),gt_path_unknown=int(unknown.sum()),
   gt_path_in_tube_samples=int(eligible_path.sum()),gt_path_in_tube_unknown=int(unknown[eligible_path].sum()),
   start_free=values.get((0,0),0)<0,
   integration=g.get('scan_accumulation',g.get('route_hygiene',dict(scans=seal['insertion_keyframes']))))
  row['integration']={k:v for k,v in row['integration'].items() if k not in ('swept_cells','integrated_frame_ids')}
  reports[name]=row
 a,b=reports['off'],reports['hygiene']
 checks=dict(outside_zero=b['outside_050_cells']==0,coverage_loss_within_5pp=b['coverage_040']>=a['coverage_040']-.05,
  area_precision_nondecrease=b['area_precision'] is not None and (a['area_precision'] is None or b['area_precision']>=a['area_precision']),
  gt_tube_unknown_zero=b['gt_path_in_tube_unknown']==0,start_free=b['start_free'])
 result=dict(seed=seed,source=str(ep),status=load(ep/'result.json')['status'],excluded=False,**{k:seal[k] for k in ['insertion_keyframes','observed_frames','gate_counts','off_bytes_identical']},conditions=reports,checks=checks,passed=all(checks.values()),
  denominator_note='Full 0.1m wall boundary samples and potential visible <=2.5/4m samples; object occlusion not modelled. Area=within1m of GT path evaluation only.')
 dump(EXP/'results'/f'map-{seed}.json',result);print(seed,'EVALUATED',checks,flush=True)
 if seed==49002:
  import matplotlib;matplotlib.use('Agg')
  import matplotlib.pyplot as plt
  fig,axes=plt.subplots(1,2,figsize=(10,4.5),sharex=True,sharey=True,layout='constrained')
  for ax,name in zip(axes,['off','hygiene']):
   g=load(dest/(name+'.json'));cells=np.array([r for r in g['cells'] if r[2]>0]).reshape(-1,3);xy=transform((cells[:,:2]+.5)*g['resolution_m'],origin)
   ax.scatter(samples[:,0],samples[:,1],s=7,c='0.7',label='GT wall (evaluation)');ax.scatter(xy[:,0],xy[:,1],s=8,c='#155998',label='Own occupied cells')
   ax.plot(all_gt[:,0],all_gt[:,1],c='#dd9e32',lw=.8,label='GT path');ax.plot(path[:,0],path[:,1],c='#249254',lw=.8,label='Estimated path')
   q=reports[name];ax.set_title(f"49002 {name}: P {q['precision_015']:.1%}, coverage {q['wall_coverage']:.1%}\n{q['occupied_cells']} cells, RMSE {q['wall_error_rmse_m']:.3f} m")
   ax.set_aspect('equal');ax.set(xlabel='World x (m), aligned once at start',ylabel='y (m)');ax.legend(fontsize=6)
  figure=EXP/'figures/hygiene-49002.png';figure.parent.mkdir(exist_ok=True);fig.savefig(figure,dpi=145,bbox_inches='tight',pad_inches=.15);plt.close(fig)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('mode',choices=['predict','evaluate']);p.add_argument('--seed',type=int,required=True);a=p.parse_args()
 (predict if a.mode=='predict' else evaluate)(a.seed)
