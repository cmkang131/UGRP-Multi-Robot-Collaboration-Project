"""Post-hoc truth-only scoring; never imported by the physical/controller runner."""
from pathlib import Path
import argparse,json,math,sys,hashlib
import numpy as np
from scipy.spatial import cKDTree
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from harness.self_odom_grid import transform
sys.path.insert(0,str(ROOT/'experiments/2026-10-05-ego-wall-map-probe/code'))
from odom_grid_replay import wall_samples,quality

def read(p):return json.loads(p.read_text())
def rows(p):return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def score(p):
 p=Path(p);r=read(p/'result.json')
 result={k:r.get(k) for k in ('host','mode','profile','seed','status','source_sha','wall_s','failure','checkpoint')}
 result['raw']=str(p);result['result_sha256']=sha(p/'result.json')
 if not (p/'eval_only/trajectory.jsonl').exists():return result
 allgt=rows(p/'eval_only/trajectory.jsonl');trace=rows(p/'own-controller.jsonl');start=r['start_sim_s']
 if not allgt or not trace:return result
 truth={round(x['t'],6):x for x in allgt};usable=[x for x in trace if x['t']>=start and round(x['t'],6) in truth]
 if not usable:return result
 origin=[*allgt[0]['robot_xyz_m'][:2],allgt[0]['robot_yaw_rad']]
 delta=transform([x['local_pose'][:2] for x in usable],origin)-np.array([truth[round(x['t'],6)]['robot_xyz_m'][:2] for x in usable])
 error=np.linalg.norm(delta,axis=1);sigmas=np.array([x['sigma_xy'] for x in usable]);ratio=error/np.maximum(sigmas,1e-12)
 events=read(p/'utility-events.json');static=read(p/'inputs/static_map.json');B=static['regions']['zone_B']
 declarations=[]
 for e in events:
  if e['t']<start or e['reason'] not in ('goal_reached','return_start_declared'):continue
  if e['reason']=='goal_reached' and e.get('entity')!='B':continue
  g=truth.get(round(e['t'],6))
  if g is None:declarations.append(dict(t=e['t'],kind=e['reason'],valid=False,reason='missing_GT'));continue
  xy=np.asarray(g['robot_xyz_m'][:2])
  valid=bool(np.all(abs(xy-B['center_m'])<=B['half_extents_m'])) if e['reason']=='goal_reached' else bool(np.linalg.norm(xy-origin[:2])<=.20)
  declarations.append(dict(t=e['t'],kind=e['reason'],valid=valid))
 contacts=[x for x in rows(p/'eval_only/contact-audit.jsonl') if x['t']>=start];counts={}
 for kind in ('wall','robot'):
  mask=[any(z['kind']==kind for z in x['pairs']) for x in contacts];counts[kind]=sum(v and (i==0 or not mask[i-1]) for i,v in enumerate(mask))
 grid=read(p/'frontend-grid.json');cells=np.array([v for v in grid['cells'] if v[2]>0]).reshape(-1,3)
 occupied=transform((cells[:,:2]+.5)*grid['resolution_m'],origin)
 rect=np.array([x['center_m']+x['half_extents_m'] for x in static['obstacles'] if x.get('kind')=='wall']);samples=wall_samples(rect)
 path=np.array([truth[round(x['t'],6)]['robot_xyz_m'][:2] for x in usable]);tree=cKDTree(path)
 ins=tree.query(samples)[0]<=1.;inc=tree.query(occupied)[0]<=1.
 q,covered=quality(occupied[inc],rect,samples[ins])
 result.update(samples=len(usable),over_3sigma=int((ratio>3).sum()),over_3sigma_rate=float((ratio>3).mean()),final_error_m=float(error[-1]),
  final_sigma_m=float(sigmas[-1]),final_error_sigma=float(ratio[-1]),path_rmse_m=float(np.sqrt(np.mean(error**2))),
  B_arrived=any(d['valid'] and d['kind']=='goal_reached' for d in declarations),returned=any(d['valid'] and d['kind']=='return_start_declared' for d in declarations),
  false_declarations=sum(not d['valid'] for d in declarations),declarations=declarations,contacts=counts,
  final_return_distance_m=float(np.linalg.norm(path[-1]-origin[:2])),sim_s=usable[-1]['t']-start,
  occupied_cells=len(cells),tube=q,tube_wall_samples=int(ins.sum()),tube_covered_samples=int(covered.sum()),
  per_phase={name:dict(samples=int(m.sum()),over_3sigma=int((ratio[m]>3).sum()),over_3sigma_rate=float((ratio[m]>3).mean()) if m.any() else None) for name,m in
   [('approach',np.array([x['t']<start+60 for x in usable])),('return',np.array([x['t']>=start+60 for x in usable]))]})
 return result

def select(reports):
 baseline={r['seed']:r for r in reports if r['profile']=='baseline'};qualified=[];gates={}
 for profile in ('a','b','c'):
  trial={r['seed']:r for r in reports if r['profile']==profile};valid=set(trial)==set(baseline)=={60011,60012} and all(r['status']=='RECORDED' and r.get('samples',0)>0 for r in list(trial.values())+list(baseline.values()))
  g={'complete_two':valid}
  if valid:
   avg=lambda group,key:float(np.mean([r[key] for r in group.values()]))
   g.update(overconfidence=avg(trial,'over_3sigma_rate')<=.9*avg(baseline,'over_3sigma_rate') and avg(trial,'over_3sigma_rate')<avg(baseline,'over_3sigma_rate'),
    position=avg(trial,'final_error_m')<=1.2*avg(baseline,'final_error_m'),
    B=sum(r['B_arrived'] for r in trial.values())>=sum(r['B_arrived'] for r in baseline.values()),
    returned=sum(r['returned'] for r in trial.values())>=sum(r['returned'] for r in baseline.values()),
    false=sum(r['false_declarations'] for r in trial.values())==0,
    contacts=sum(sum(r['contacts'].values()) for r in trial.values())<=sum(sum(r['contacts'].values()) for r in baseline.values()))
   if all(g.values()):qualified.append((avg(trial,'over_3sigma_rate'),avg(trial,'final_error_m'),profile))
  gates[profile]=g
 return dict(gates=gates,selected=min(qualified)[2] if qualified else None,thresholds_changed=False)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('raw',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 report=score(a.raw);a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
