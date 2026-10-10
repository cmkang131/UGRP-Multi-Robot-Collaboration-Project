"""Post-replay classification; truth enters only here, never navigation."""
from pathlib import Path
import sys,json,hashlib,collections
import numpy as np
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
EXP=Path(__file__).resolve().parents[1]
RAW=Path('/Users/changmin/projects/ugrp/outputs/wall-segment-dev-v1/new-seed')
OUT=Path('/Users/changmin/projects/ugrp/outputs/frontier-visibility-v1/diagnosis')
from harness.active_wall_recovery import ExplorationRecoveryNavigator
from harness.public_navigation_unknown import UnknownCostmap
from scripts.run_active_wall_rotleft import dump

def rows(p):return [json.loads(x) for x in p.read_text().splitlines()]
def left(p):return -1.025<p[0]<2.175 and -3.125<p[1]<1.425
def world(p):return np.array([3.25,.75])-np.asarray(p)
def main():
    tr=rows(RAW/'own-controller.jsonl');replay=rows(OUT/'traces.jsonl')
    assert len(tr)==len(replay)==891
    assert all(json.dumps(a)==json.dumps(b) for a,b in zip(tr,replay))
    events=json.loads((RAW/'navigation.json').read_text());nav=ExplorationRecoveryNavigator();audits=[]
    selected=[]
    for e in events:
        if e['reason']=='frontier_selected':selected.append(dict(t=e['t'],world=world(e['target']),left_interior=left(world(e['target']))))
    for file in sorted(OUT.glob('*.npz')):
        d=np.load(file);row=min(tr,key=lambda x:np.linalg.norm(np.array(x['pose'])-d['pose']))
        assert np.linalg.norm(row['pose']-d['pose'])<1e-12
        t=row['t'];costmap=UnknownCostmap(d['raw'],d['origin'],float(d['resolution']))
        nav.blacklist=[np.array(e['target']) for e in events if e['t']<=t and e['reason'] in ('ABORTED_unreachable','progress_timeout_blacklist','ABORTED_goal_blacklisted')]
        candidates=[]
        for rank,f in enumerate(nav.core.frontiers(costmap.raw,costmap.origin,costmap.resolution,d['pose'][:2])):
            candidates.append(dict(rank=rank+1,own=f[:2],world=world(f[:2]),left_interior=left(world(f[:2])),
                size=int(f[5]),min_distance_m=float(f[4]),cost=float(f[6]),blacklisted=nav.blocked(f[:2],costmap.resolution),
                path_points=len(nav.plan_to(costmap,d['pose'],f[:2]))))
        doors=[]
        for y,width in [(.05,.5),(-2.625,1.)]:
            p=np.r_[world([2.65,y]),0.];q=np.r_[world([1.75,y]),0.]
            doors.append(dict(world_y=y,width_m=width,footprint_width_m=.24,straight_footprint_clear=costmap.sweep_clear(p,q),
                path_points=len(nav.plan_to(costmap,p,q[:2]))))
        audits.append(dict(t=t,snapshot=file.name,candidates=candidates,doors=doors))
    ls=[a for a in audits if any(f['left_interior'] for f in a['candidates'])]
    lf=[f for a in audits for f in a['candidates'] if f['left_interior']]
    actual=rows(RAW/'eval_only/trajectory.jsonl');xy=np.array([x['robot_xyz_m'][:2] for x in actual])
    result=dict(input=str(RAW),trace_frames=891,trace_bytes_equal=True,physics_runs=0,
        audit_snapshots=len(audits),first_left=ls[0],left_present_snapshots=len(ls),
        left_candidate_instances=len(lf),left_candidate_cells_sum=sum(f['size'] for f in lf),
        left_sizes_range=[min(f['size'] for f in lf),max(f['size'] for f in lf)],
        left_blocked=sum(f['blacklisted'] for f in lf),left_path_exists=sum(bool(f['path_points']) for f in lf),
        selected=selected,events=dict(collections.Counter(e['reason'] for e in events)),
        truth_bounds=[xy.min(0),xy.max(0)],actual_left_frames=int(sum(xy[:,0]<2.175)),
        final_elapsed_s=tr[-1]['t']-tr[0]['t'],audits=audits,
        storage_recovery='Initial replay finished all891 byte assertions; final audit JSON rejected initial -inf. Recover original frozen costmaps without rerunning physics/estimator; no raw overwrite.',
        cell_denominator='candidate cells are repeated cluster instances, NOT unique visible wall cells')
    dump(EXP/'results/diagnosis.json',result)
    dump(OUT/'seal.json',dict(trace_bytes_equal=True,n=891,gt_used_by_replay=False,
        artifacts={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.iterdir() if p.is_file() and p.name!='seal.json'}))
    sys.path.insert(0,str(ROOT/'outputs/self-map-plot-deps'))
    import matplotlib;matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    from matplotlib.colors import ListedColormap
    walls=[x for x in json.loads((RAW/'inputs/static_map.json').read_text())['obstacles'] if x.get('kind')=='wall']
    fig,axes=plt.subplots(2,2,figsize=(12,8))
    for ax,ti in zip(axes.flat,[21.3,63.1,82.3,179.3]):
        a=min(audits,key=lambda x:abs(x['t']-ti));d=np.load(OUT/a['snapshot']);row=min(tr,key=lambda x:abs(x['t']-a['t']))
        raw=d['raw'];cost=d['costs'];res=float(d['resolution']);lo=d['origin'];hi=lo+res*np.array(raw.shape[::-1]);wl,wh=world(hi),world(lo)
        display=np.where(raw==255,0,np.where(raw==254,3,np.where(cost>=253,2,1)))
        ax.imshow(display[::-1,::-1],origin='lower',extent=[wl[0],wh[0],wl[1],wh[1]],cmap=ListedColormap(['#eeeeee','#cfdfed','#eaba70','#a32a28']),vmin=0,vmax=3)
        for w in walls:
            center=np.array(w['center_m']);half=np.array(w['half_extents_m']);ax.add_patch(Rectangle(center-half,*2*half,fill=False,edgecolor='black',linewidth=1.3))
        for f in a['candidates']:
            p=f['world'];ax.scatter(*p,c='green' if f['left_interior'] else 'orange',s=18);ax.text(*p,str(f['rank']),fontsize=7)
        p=world(np.array(row['path']).reshape(-1,2))
        if len(p):ax.plot(*p.T,color='purple',linewidth=1)
        ax.scatter(*world(row['pose'][:2]),color='black',s=25)
        ax.set(xlim=(-1.5,5.8),ylim=(-4,3.6),aspect='equal',title=f't={a["t"]:.1f}s | numbered native candidates')
    fig.suptitle('Frozen own costmap + current path; outlines are evaluation-only true walls\nwhite unknown / blue free / tan inscribed inflation / red hits; green left-interior candidates')
    fig.tight_layout();(EXP/'figures').mkdir(exist_ok=True);fig.savefig(EXP/'figures/frontier-audit.png',dpi=130);plt.close(fig)
    print(json.dumps({k:v for k,v in result.items() if k not in ('audits','selected','first_left')},default=lambda x:x.tolist(),indent=2))
if __name__=='__main__':main()
