"""Sealed P1 records only. GT alignment/shortest path never enter the policy."""
from pathlib import Path
from collections import Counter
import argparse,hashlib,json,math,sys
import numpy as np
from scipy.spatial import cKDTree
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from scripts.run_goal_route_continuous import RAW,EXP,SEEDS
from scripts.run_active_wall_rotleft import dump
from harness.self_odom_grid import transform
from harness.self_map_prob import wrap
from harness.public_navigation.costmap import Costmap
sys.path.insert(0,str(ROOT/'experiments/2026-10-05-ego-wall-map-probe/code'))
from odom_grid_replay import wall_samples,quality,boundary_dist


def load(p):return json.loads(p.read_text())
def rows(p):return [json.loads(s) for s in p.read_text().splitlines()] if p.exists() else []
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def shortest(static,start,target):
    """Evaluation-only 5cm 8-neighbor Dijkstra, same Nav2 inflation formula."""
    rect=np.array([r['center_m']+r['half_extents_m'] for r in static['obstacles']])
    lo=np.min(rect[:,:2]-rect[:,2:],axis=0)-.2;hi=np.max(rect[:,:2]+rect[:,2:],axis=0)+.2
    resolution=.05;shape=np.ceil((hi-lo)/resolution).astype(int)
    yy,xx=np.indices(shape[::-1]);xy=lo+(np.stack([xx,yy],axis=-1)+.5)*resolution
    blocked=np.any(np.all(abs(xy[:,:,None,:]-rect[None,None,:,:2])<=rect[None,None,:,2:],axis=-1),axis=-1)
    cm=Costmap(np.where(blocked,254,0).astype(np.uint8),lo,resolution)
    free=cm.costs<253;a=cm.world_to_map(start);b=cm.world_to_map(target)
    if a is None or b is None or not free[b[1],b[0]]:return None
    free[a[1],a[0]]=True
    ids=np.arange(free.size).reshape(free.shape);src=[];dst=[];weights=[]
    h,w=free.shape
    for dy,dx in ((0,1),(1,0),(1,1),(1,-1)):
        y,x=np.nonzero(free);v=(y+dy<h)&(x+dx>=0)&(x+dx<w);y,x=y[v],x[v]
        ok=free[y+dy,x+dx]
        if dy and dx:ok&=free[y+dy,x]&free[y,x+dx]
        y,x=y[ok],x[ok];p=ids[y,x];q=ids[y+dy,x+dx]
        src.extend(p);dst.extend(q);weights.extend([resolution*math.hypot(dx,dy)]*len(p))
    matrix=csr_matrix((weights,(src,dst)),shape=(free.size,free.size))
    value=dijkstra(matrix,directed=False,indices=ids[a[1],a[0]])[ids[b[1],b[0]]]
    return float(value) if np.isfinite(value) else None


def score(seed):
    ep=RAW/f'seed{seed}';out=EXP/'results'
    if not (ep/'result.json').exists():return dict(seed=seed,started=False,status='NOT_RUN',excluded=False)
    receipt=load(ep/'artifacts.sha256.json')
    for name in ('result.json','route-map.json','frontend-grid.json','own-controller.jsonl','eval_only/trajectory.jsonl'):
        if (ep/name).exists():assert sha(ep/name)==receipt[name],name
    result=load(ep/'result.json');trace=rows(ep/'own-controller.jsonl');gt=rows(ep/'eval_only/trajectory.jsonl')
    summary=dict(seed=seed,condition='T1' if seed<55004 else 'T2',started=True,status=result['status'],
        acquisition=result,arrived_B=False,false_declarations=0,returned_start=False,excluded=False)
    if not trace or not gt:
        summary['failure']='no_trace_or_gt';dump(out/f'{seed}.json',summary);return summary
    static=load(ep/'inputs/static_map.json');graph=load(ep/'route-map.json');events=load(ep/'utility-events.json')
    by_t={round(r['t'],6):r for r in gt};origin=np.r_[gt[0]['robot_xyz_m'][:2],gt[0]['robot_yaw_rad']]
    usable=[r for r in trace if round(r['t'],6) in by_t]
    predicted=np.array([r['local_pose'] for r in usable]);world=transform(predicted[:,:2],origin)
    truth=np.array([by_t[round(r['t'],6)]['robot_xyz_m'][:2] for r in usable]);delta=world-truth
    error=np.linalg.norm(delta,axis=1);sigma=np.array([r['sigma_xy'] for r in usable]);ratio=error/np.maximum(sigma,1e-12)
    cov={round(r['t'],6):r['covariance'] for r in rows(ep/'frontend-covariances.jsonl')}
    c,s=math.cos(origin[2]),math.sin(origin[2]);local_delta=delta@np.array([[c,-s],[s,c]])
    nees=[float(d@np.linalg.pinv(np.asarray(cov[round(r['t'],6)])[:2,:2])@d) for d,r in zip(local_delta,usable)]
    zone=static['regions']['zone_B'];declarations=[]
    for e in events:
        if e['reason']!='goal_reached' or e['entity']!='B':continue
        row=by_t[round(e['t'],6)];inside=bool(np.all(abs(np.array(row['robot_xyz_m'][:2])-zone['center_m'])<=zone['half_extents_m']))
        declarations.append(dict(t=e['t'],inside=inside))
    g=load(ep/'frontend-grid.json');cells=np.array([v for v in g['cells'] if v[2]>0]).reshape(-1,3)
    occupied=transform((cells[:,:2]+.5)*g['resolution_m'],origin)
    rect=np.array([r['center_m']+r['half_extents_m'] for r in static['obstacles'] if r.get('kind')=='wall'])
    samples=wall_samples(rect);q,covered=quality(occupied,rect,samples)
    actual=np.array([r['robot_xyz_m'][:2] for r in gt]);path=cKDTree(actual)
    in_tube=path.query(samples)[0]<=1.;cell_tube=path.query(occupied)[0]<=1.
    tq,tc=quality(occupied[cell_tube],rect,samples[in_tube]) if in_tube.any() else ({'occupied_cells':int(cell_tube.sum()),'precision_015':None,'precision_cell':None,'wall_coverage':0.,'wall_error_rmse_m':None},np.zeros(0,bool))
    map_lo=np.min(rect[:,:2]-rect[:,2:],axis=0);map_hi=np.max(rect[:,:2]+rect[:,2:],axis=0)
    outside=int(np.any((occupied<map_lo-.5)|(occupied>map_hi+.5),axis=1).sum())
    contacts=rows(ep/'eval_only/contact-audit.jsonl');episodes={}
    for kind in ('wall','robot'):
        mask=[any(p['kind']==kind for p in r['pairs']) for r in contacts]
        episodes[kind]=sum(v and (i==0 or not mask[i-1]) for i,v in enumerate(mask))
    B=graph['reached'].get('B');path_ratio=None;shortest_m=None;route_length=None
    if B:
        # Actual temporal route, no inferred unverified shortcut.
        edges=[e for e in graph['graph']['edges'] if graph['graph']['nodes'][e['b']]['t']<=B['t']]
        route_length=sum(e['length_m'] for e in edges)
        shortest_m=shortest(static,origin[:2],zone['center_m'])
        path_ratio=route_length/shortest_m if shortest_m else None
    matches=graph['matches'];accepted=sum(r['status']=='accepted' for r in matches)
    failures='success' if declarations and all(d['inside'] for d in declarations) else ('physical_or_host' if result['status']!='RECORDED' else 'unobserved_B' if 'B' not in graph['entities'] else 'approach_or_localization')
    summary.update(arrived_B=any(d['inside'] for d in declarations),false_declarations=sum(not d['inside'] for d in declarations),
        declarations=declarations,returned_start=bool(result.get('declared_return')),
        return_GT_distance_m=float(np.linalg.norm(actual[-1]-actual[0])) if result.get('declared_return') else None,
        reached_entities=graph['reached'],failure=failures,final_error_m=float(error[-1]),path_rmse_m=float(np.sqrt(np.mean(error**2))),
        final_sigma_m=float(sigma[-1]),final_error_sigma=float(ratio[-1]),final_nees=float(nees[-1]),over_3sigma_frames=int((ratio>3).sum()),
        error_samples=len(error),map=q,map_samples=len(samples),map_covered_samples=int(covered.sum()),
        tube=tq,tube_samples=int(in_tube.sum()),tube_covered_samples=int(tc.sum()),tube_occupied_cells=int(cell_tube.sum()),
        outside_cells=outside,contacts=episodes,cue_count=len(graph['cues']),nodes=len(graph['graph']['nodes']),
        local_match_accepted=accepted,local_match_attempts=len(matches),local_match_success=None if not matches else accepted/len(matches),
        travelled_m=float(np.linalg.norm(np.diff(actual,axis=0),axis=1).sum()),hold_fraction=sum(r['command']['kind']=='hold' for r in trace)/len(trace),
        rotation_fraction=sum(abs(r['command'].get('turn',0))>0 for r in trace)/len(trace),sim_s=gt[-1]['t']-result['start_sim_s'],
        route_length_to_B_m=route_length,GT_shortest_to_B_center_m=shortest_m,route_length_ratio=path_ratio,
        insertion_frames=len(load(ep/'frontend-ledger.json')),insertion_reasons=dict(Counter(r['reason'] for r in load(ep/'decisions.json'))))
    summary['gates']=dict(B_arrival=summary['arrived_B'],no_false_declaration=summary['false_declarations']==0,
        tube_coverage=tq['wall_coverage']>=.7,tube_precision=(tq['precision_015'] or 0)>=.7,
        tube_rmse=tq['wall_error_rmse_m'] is not None and tq['wall_error_rmse_m']<=.2,
        no_outside=outside==0,cue_ledger=bool(graph['cues']),route_ratio=path_ratio is not None and path_ratio<=2.)
    dump(out/f'{seed}.json',summary);return summary


def aggregate():
    reports=[score(s) for s in SEEDS]
    summary={'registered':9,'started':sum(r['started'] for r in reports),'excluded':[], 'reports':reports}
    for name,seeds in [('T1',SEEDS[:3]),('T2',SEEDS[3:])]:
        r=[v for v in reports if v['seed'] in seeds];errs=[v['final_error_m'] for v in r if 'final_error_m' in v]
        summary[name]=dict(arrivals=sum(v['arrived_B'] for v in r if v['started']),denominator=len(seeds),
            error_n=len(errs),error_median=None if not errs else float(np.median(errs)),error_max=max(errs) if errs else None)
    dump(EXP/'results/summary.json',summary);return summary

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--seed',type=int,choices=SEEDS);a=p.parse_args()
    print(json.dumps(score(a.seed) if a.seed else aggregate(),ensure_ascii=False,indent=2))
