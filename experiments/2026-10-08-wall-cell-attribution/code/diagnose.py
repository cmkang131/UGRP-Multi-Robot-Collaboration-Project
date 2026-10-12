"""Evaluation-only weighted cell provenance; NumPy geometry, no MuJoCo."""
from pathlib import Path
from collections import Counter, defaultdict
import hashlib, importlib.util, json, math, sys
import numpy as np

ROOT=Path(__file__).resolve().parents[3]
EXP=Path(__file__).resolve().parents[1]
RAW=Path('/Users/changmin/projects/ugrp/outputs/wall-cell-attribution-v1')
EPISODES={'31001':Path('/Users/changmin/projects/ugrp/outputs/active-frontier-audit-v1/new-seed'),
          '32002':Path('/Users/changmin/projects/ugrp/outputs/wall-segment-dev-v1/new-seed')}
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'experiments/2026-10-05-ego-wall-map-probe/code'))
import odom_grid_replay as metric
from harness.self_odom_grid import OdomGrid, ray_cells, transform
from harness.active_wall_vision import modules

CATEGORIES=('detector','pose','range_projection','object','cell_boundary','unresolved')
def load(p):return json.loads(Path(p).read_text())
def rows(p):return [json.loads(l) for l in Path(p).read_text().splitlines()]
def dump(p,v):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(v,indent=2,allow_nan=False)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def frame_evidence(row):
    """Exact weighted_insert order, with all equally strong hit witnesses."""
    cam=transform([row['camera']],row['pose'])[0]
    hits,free={},{}
    for index,(segment,w) in enumerate(zip(row['segments'],row['insertion_weights'])):
        w*=row.get('insertion_weight',1.)
        if w==0:continue
        ends=transform(segment,row['pose'])
        n=max(2,int(math.ceil(np.linalg.norm(ends[1]-ends[0])/.05))+1)
        for local,p in zip(np.linspace(*np.asarray(segment),n),np.linspace(*ends,n)):
            cells=ray_cells(cam,p,.1);k=cells[-1]
            witness=dict(frame_id=row['frame_id'],t=row['t'],local=local.tolist(),estimated=p.tolist(),segment=index)
            if k not in hits or w>hits[k][0]:hits[k]=(w,[witness])
            elif w==hits[k][0]:hits[k][1].append(witness)
            for cell in cells[:-1]:free[cell]=max(free.get(cell,0.),w)
    return hits,{k:v for k,v in free.items() if k not in hits}


def provenance(ledger):
    grid=OdomGrid('r3');mass={}
    for row in ledger:
        hit,free=frame_evidence(row)
        for k,w in free.items():
            old=grid.cells.get(k,0.);new=min(grid.hi,max(grid.lo,old+grid.miss*w))
            if old>0:
                factor=max(new,0)/old
                for record in mass.get(k,[]):record['mass']*=factor
                if new<=0:mass[k]=[]
            grid.cells[k]=new
        for k,(w,sources) in hit.items():
            old=grid.cells.get(k,0.);new=min(grid.hi,max(grid.lo,old+grid.hit*w))
            if new>0:
                increment=new-max(old,0)
                if old<=0:mass[k]=[]
                if increment>0:
                    mass.setdefault(k,[]).extend(dict(s,mass=increment/len(sources)) for s in sources)
            grid.cells[k]=new
        grid.frames+=1
    for k,v in grid.cells.items():
        if v>0:assert abs(sum(r['mass'] for r in mass[k])-v)<1e-10
    return grid,mass


def first_box_hit(origin,rays,lower,upper):
    with np.errstate(divide='ignore',invalid='ignore'):
        a=(np.asarray(lower)-origin)/rays;b=(np.asarray(upper)-origin)/rays
    entry=np.maximum(np.minimum(a,b).max(-1),0.)
    exit=np.maximum(a,b).min(-1)
    return np.where((exit>=entry)&(exit>0),entry,np.inf)


class Labels:
    def __init__(self,ep):
        self.ep=ep;self.K=modules()[0].K
        self.truth={round(r['t'],6):r for r in rows(ep/'eval_only/trajectory.jsonl')}
        first=self.truth[min(self.truth)];self.origin=[*first['robot_xyz_m'][:2],first['robot_yaw_rad']]
        self.cameras={round(r['t'],6):r for r in rows(ep/'eval_only/camera.jsonl')}
        self.own={r['frame_id']:r for r in rows(ep/'own-contacts.jsonl')}
        self.frames={r['frame_id']:r for r in rows(ep/'robots/r3/frames.jsonl')}
        self.setup=load(ep/'eval_only/setup.json')
        self.walls=np.array([r['center_m']+r['half_extents_m'] for r in load(ep/'inputs/static_map.json')['obstacles'] if r.get('kind')=='wall'])
        self.records={}

    def classify(self,s):
        frame=s['frame_id'];local=np.array(s['local']);key=(frame,*s['local'])
        if key in self.records:return self.records[key]
        t=round(s['t'],6);gt=self.truth[t];cam=self.cameras[t];own=self.own[frame]
        world=transform([s['estimated']],self.origin)[0]
        body=transform([local],[*gt['robot_xyz_m'][:2],gt['robot_yaw_rad']])[0]
        distances=metric.boundary_dist(np.array([world,body]),self.walls)
        optical=(np.r_[local,0.]-own['camera_origin'])@np.array(own['camera_rotation'])
        uv=(self.K@optical)[:2]/optical[2]
        actual_origin=np.array(cam['camera_xyz'])
        actual_R=np.array(cam['camera_rotation']).reshape(3,3)@np.diag([1,-1,-1])
        ray=actual_R@np.linalg.solve(self.K,np.r_[uv,1.])
        floor=actual_origin-actual_origin[2]*ray/ray[2]
        actual_error=float(metric.boundary_dist(floor[None,:2],self.walls)[0]) if ray[2]<0 else None
        # Compare to projected floor-contact lines, with actual camera and wall geometry.
        contact_px=[]
        for x,y,hx,hy in self.walls:
            corners=np.array([[x-hx,y-hy,0],[x+hx,y-hy,0],[x+hx,y+hy,0],[x-hx,y+hy,0]])
            o=(corners-actual_origin)@actual_R
            proj=o@self.K.T
            for i,j in ((0,1),(1,2),(2,3),(3,0)):
                if min(o[i,2],o[j,2])<=0:continue
                a,b=proj[[i,j],:2]/proj[[i,j],2,None]
                if abs(b[0]-a[0])<1e-6 or not min(a[0],b[0])<=uv[0]<=max(a[0],b[0]):continue
                v=a[1]+(uv[0]-a[0])*(b[1]-a[1])/(b[0]-a[0])
                # Require contact in front of first intervening wall along its 2D ray.
                r=actual_R@np.linalg.solve(self.K,[uv[0],v,1.])
                p=actual_origin-actual_origin[2]*r/r[2]
                d=p[:2]-actual_origin[:2]
                ranges=[float(first_box_hit(actual_origin[:2],d,np.array([cx-hw,cy-hh]),np.array([cx+hw,cy+hh]))) for cx,cy,hw,hh in self.walls]
                if min(ranges)>=1-1e-6:contact_px.append(abs(uv[1]-v))
        pixel_error=min(contact_px) if contact_px else None
        patch=uv+np.array([(dx,dy) for dx in (-2,0,2) for dy in (-10,-6,-2)])
        rays=np.c_[patch,np.ones(len(patch))]@np.linalg.inv(self.K).T@actual_R.T
        hit=np.full(len(rays),np.inf);sem=np.full(len(rays),'sky',dtype=object)
        def include(d,label):
            mask=d<hit;hit[mask]=d[mask];sem[mask]=label
        include(np.where(rays[:,2]<0,-actual_origin[2]/rays[:,2],np.inf),'floor')
        for x,y,hx,hy in self.walls:include(first_box_hit(actual_origin,rays,[x-hx,y-hy,0],[x+hx,y+hy,.4]),'wall')
        # Recorded moving cyan box, exact oriented box. No GT enters estimator.
        R=np.array(gt['cyan_rotation']).reshape(3,3);c=np.array(gt['cyan_xyz_m']);h=np.array(gt['box_half_m'])
        include(first_box_hit((actual_origin-c)@R,rays@R,-h,h),'box')
        # Parked peers have no actual per-link state in these recordings. Conservative
        # envelopes flag ambiguity; never assert these are exact object labels.
        candidate=np.zeros(len(rays),bool)
        for robot,spawn in self.setup['spawns'].items():
            if robot=='r3':continue
            cx,cy=spawn[:2]
            d=first_box_hit(actual_origin,rays,[cx-.20,cy-.18,0],[cx+.20,cy+.18,.4])
            candidate|=d<hit
        band=Counter(sem.tolist())
        if distances[0]<=.15:label='cell_boundary'
        elif distances[1]<=.15:label='pose'
        elif actual_error is not None and actual_error<=.15:label='range_projection'
        elif band['box']>=5:label='object'
        elif candidate.any():label='unresolved'
        elif pixel_error is not None and pixel_error<=2:label='range_projection'
        else:label='detector'
        result=dict(category=label,frame_id=frame,t=s['t'],uv=uv.tolist(),local=local.tolist(),
            world=world.tolist(),gt_body_xy=body.tolist(),gt_camera_xy=floor[:2].tolist() if ray[2]<0 else None,
            estimated_error_m=float(distances[0]),gt_body_error_m=float(distances[1]),gt_camera_error_m=actual_error,
            contact_pixel_error=pixel_error,range_m=float(np.linalg.norm(local-np.array(own['camera']))),
            above_band=dict(band),peer_envelope_candidate=bool(candidate.any()))
        self.records[key]=result;return result


def main():
    for seed,ep in EPISODES.items():
        expected=load(ep/'artifacts.sha256.json')
        for name in ('grid.json','graph.json','frontend-ledger.json','own-contacts.jsonl','eval_only/trajectory.jsonl','eval_only/camera.jsonl','eval_only/setup.json','robots/r3/frames.jsonl','inputs/static_map.json'):
            assert sha(ep/name)==expected[name],name
        ledger=load(ep/'graph.json')['ledger'];g,mass=provenance(ledger)
        saved=load(ep/'grid.json');assert g.export()['cells']==saved['cells'],'GRID_REPLAY_MISMATCH'
        labels=Labels(ep);out=[];fractions=np.zeros(len(CATEGORIES));counts=Counter()
        for cell,v in sorted(g.cells.items()):
            if v<=0:continue
            world=transform([(np.array(cell)+.5)*.1],labels.origin)[0]
            err=float(metric.boundary_dist(world[None],labels.walls)[0])
            if err<=.15:continue
            parts=np.zeros(len(CATEGORIES));sources=[]
            for s in mass[cell]:
                label=labels.classify(s);weight=s['mass']/v
                parts[CATEGORIES.index(label['category'])]+=weight
                sources.append(dict(label,weight=weight))
            category=CATEGORIES[int(np.argmax(parts))];counts[category]+=1;fractions+=parts
            out.append(dict(cell=list(map(int,cell)),world=world.tolist(),wall_distance_m=err,log_odds=v,
                category=category,fractions=dict(zip(CATEGORIES,parts.tolist())),sources=sources))
        dump(RAW/f'{seed}-false-cells.json',out)
        ranges={}
        for low,high in ((0,1),(1,2),(2,3),(3,4)):
            n=np.zeros(len(CATEGORIES))
            for cell in out:
                for s in cell['sources']:
                    if low<=s['range_m']<high:n[CATEGORIES.index(s['category'])]+=s['weight']
            ranges[f'{low}-{high}m']=dict(zip(CATEGORIES,n.tolist()))
        summary=dict(seed=seed,episode=str(ep),ledger_frames=len(ledger),occupied_cells=len(g.occupied_points()),false_cells=len(out),
            categories={c:dict(cells=counts[c],percent=100*counts[c]/len(out),fractional_cells=float(fractions[i]),
                fractional_percent=float(100*fractions[i]/len(out))) for i,c in enumerate(CATEGORIES)},
            ranges_fractional_cells=ranges,grid_rebuild_all_cells_exact=True,
            source_hashes={k:expected[k] for k in ('grid.json','graph.json','own-contacts.jsonl','eval_only/camera.jsonl')})
        dump(EXP/f'results/{seed}-diagnosis.json',summary)
        print(json.dumps(summary,indent=2),flush=True)

if __name__=='__main__':main()
