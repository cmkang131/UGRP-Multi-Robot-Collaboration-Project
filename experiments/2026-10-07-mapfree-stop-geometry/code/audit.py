"""Evaluation-only reconstruction of frozen v3 stops. No physics or actor changes."""
from pathlib import Path
import hashlib
import json
import math
import subprocess
import sys
from types import SimpleNamespace
import numpy as np

ROOT=Path(__file__).resolve().parents[3]
EXP=Path(__file__).resolve().parents[1]
OUT=Path('/Users/changmin/projects/ugrp/outputs/mapfree-stop-geometry-v1')
OLD=Path('/Users/changmin/projects/ugrp/outputs/mapfree-navigation-persistence-v3/diagnostic')
sys.path[:0]=[str(ROOT),str(ROOT/'experiments/2026-10-07-mapfree-explore/code')]
from run_grid import static_inputs
from grid_world import load_layout,inverse
from diagnose_environment import rectangle_contacts
from harness.public_navigation_persistent import PersistentActor
from harness.public_navigation.costmap import from_grid,HALF
from harness.public_navigation_recovery import regulated_twist,issued_twist
from harness.public_navigation.follower import command_from_twist
from harness.self_odom_grid import transform
from harness.own_map_navigation import astar

START=np.array([-.45,-2.30,math.pi/6])
BARE=np.array([.12,.10])
RES=.025


def load(p):return json.loads(Path(p).read_text())
def rows(p):return [json.loads(x) for x in Path(p).read_text().splitlines()]
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,value):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')


def world_pose(pose):return np.r_[transform([pose[:2]],START)[0],pose[2]+START[2]]


def replay_observation(actor,log):
    # Evaluation replay uses the stored OWN DR, never world pose. No predictor
    # is corrected: replace the unused live odometer with a read-only record.
    actor.t=log['t']
    actor.odom=SimpleNamespace(pose=np.asarray(log['pose_odom']))
    actor.receive(log['observation'],[])


def disk_margin(points,rects,bounds,radius):
    """Exact distance to OBB union minus circumscribed radius (outside obstacles)."""
    pts=np.asarray(points,float).reshape(-1,2)
    x0,x1,y0,y1=bounds
    margin=np.min(np.c_[pts[:,0]-x0,x1-pts[:,0],pts[:,1]-y0,y1-pts[:,1]],axis=1)
    for r in rects:
        local=inverse(pts,(*r['center'],r['yaw']))
        q=np.abs(local)-r['half']
        # Negative signed box distance inside; Euclidean distance outside.
        d=np.linalg.norm(np.maximum(q,0),axis=1)+np.minimum(np.maximum(q[:,0],q[:,1]),0)
        margin=np.minimum(margin,d)
    return margin-radius


def path_certificate(path,rects,bounds,radius):
    """1-Lipschitz signed distance: sample min - half max spacing bounds each segment."""
    samples=[]
    step=0.
    for a,b in zip(path,path[1:]):
        n=max(1,math.ceil(np.linalg.norm(np.asarray(a)-b)/.002))
        samples.extend(np.linspace(a,b,n+1))
        step=max(step,float(np.linalg.norm(np.asarray(a)-b)/n))
    if not samples:samples=list(path)
    measured=float(np.min(disk_margin(samples,rects,bounds,radius)))
    return dict(samples=len(samples),sample_min_clearance_m=measured,
                continuous_clearance_lower_m=measured-step/2,max_sample_spacing_m=step)


def witness(start,goal,rects,bounds,half):
    radius=float(np.linalg.norm(half))
    start=np.asarray(start,float)[:2]
    goal=np.asarray(goal,float)
    margins=disk_margin([start,goal],rects,bounds,radius)
    if np.min(margins)<=0:
        return dict(found=False,reason='circumscribed_disk_endpoint_blocked_not_impossibility_proof',
                    endpoint_margins_m=margins.tolist(),radius_m=radius)
    x0,x1,y0,y1=bounds
    origin=np.array([x0,y0])
    x,y=np.meshgrid(np.arange(x0,x1+1e-8,RES),np.arange(y0,y1+1e-8,RES))
    pts=np.c_[x.ravel(),y.ravel()]
    clear=(disk_margin(pts,rects,bounds,radius)>RES/math.sqrt(2)).reshape(x.shape)
    # Connect continuous endpoints to certified nearby cells, never move start truth.
    def connect(point):
        indices=np.argwhere(clear)
        xy=origin+indices[:,::-1]*RES
        order=np.argsort(np.linalg.norm(xy-point,axis=1),kind='stable')
        for k in order:
            if np.linalg.norm(xy[k]-point)>.10:break
            if path_certificate([point,xy[k]],rects,bounds,radius)['continuous_clearance_lower_m']>0:
                return tuple(int(v) for v in indices[k,::-1])
        return None
    a,b=connect(start),connect(goal)
    cells=None if a is None or b is None else astar(clear,a,b,RES)
    if cells is None:return dict(found=False,reason='no_disk_grid_witness_not_impossibility_proof',radius_m=radius)
    path=np.vstack([start,origin+np.asarray(cells)*RES,goal])
    cert=path_certificate(path,rects,bounds,radius)
    assert cert['continuous_clearance_lower_m']>0
    return dict(found=True,radius_m=radius,path_world_m=path.tolist(),**cert,
                length_m=float(np.linalg.norm(np.diff(path,axis=0),axis=1).sum()))


def costmap_for(actor,pose):
    cm=from_grid(actor.grid,pose,actor.latest,actor.static_hits)
    for cell in actor.static_hits:
        ij=cm.world_to_map(actor.grid.point(cell))
        if ij is not None:cm.raw[ij[1],ij[0]]=254
    cm.costs=cm.inflate()
    return cm


def projection_samples(cm,pose,plan):
    twist=issued_twist(command_from_twist(regulated_twist(plan['path_m'],np.asarray(pose),plan['heading_rad']),0.))
    remaining=np.linalg.norm(np.asarray(plan['path_m'][-1])-pose[:2]) if plan['path_m'] else math.inf
    limit=min(.20,remaining) if abs(twist[0])>1e-9 else math.inf
    q=np.array(pose,float)
    samples=[q.copy()]
    for _ in range(20):
        c,s=math.cos(q[2]),math.sin(q[2])
        q+=np.array([c*twist[0]-s*twist[1],s*twist[0]+c*twist[1],twist[2]])*.05
        if np.linalg.norm(q[:2]-pose[:2])>limit:break
        samples.append(q.copy())
    blocked=next((q for q in samples if not cm.pose_clear(q)),None)
    return samples,blocked,twist


def snapshot(actor,log,world,stage):
    pose=np.asarray(log['pose_odom'])
    cm=costmap_for(actor,pose)
    rects,bounds=world.rects,world.static['bounds_m']
    wpose=world_pose(pose)
    samples,blocked,twist=projection_samples(cm,pose,log['plan'])
    check=pose if blocked is None else blocked
    mask,_=cm.footprint_mask(check)
    cells=np.argwhere(mask&(cm.raw>=254))
    blockers=[]
    for y,x in cells:
        own=cm.map_to_world([x,y])
        gc=actor.grid.cell(own)
        blockers.append(dict(cell=[int(x),int(y)],raw=int(cm.raw[y,x]),
            source='static' if gc in actor.static_hits else 'observed' if actor.latest.get(gc) else 'unknown',
            center_world_m=transform([own],START)[0].tolist()))
    result=dict(stage=stage,t=log['t'],frame=log['frame'],pose_odom=pose.tolist(),pose_world=wpose.tolist(),
        raw_pose_clear=cm.pose_clear(pose),navfn_path_points=len(log['plan']['path_m']),
        requested_twist=twist.tolist(),projected_blocked_pose_odom=None if blocked is None else blocked.tolist(),
        blockers=blockers,geometry={},widths={})
    for name,half in [('bare',BARE),('padded_v3',HALF),('nav2_padding_on_same_body',BARE+.01),
                      ('official_body_plus_nav2_padding',np.array([.185,.162])/2+.01)]:
        result['geometry'][name]=dict(half_m=half.tolist(),
            stop_contacts=rectangle_contacts(wpose,rects,bounds,half),
            projected_contacts=[] if blocked is None else rectangle_contacts(world_pose(blocked),rects,bounds,half))
    for passage in world.static['passages']:
        if 'width_m' not in passage:continue
        angle=wpose[2]-(0 if passage['axis']=='x' else math.pi/2)
        width=float(2*(abs(math.sin(angle))*HALF[0]+abs(math.cos(angle))*HALF[1]))
        result['widths'][passage['id']]=dict(passage_width_m=passage['width_m'],
            bare_aligned_width_m=.20,padded_aligned_width_m=.24,padded_at_stop_width_m=width,
            padded_max_rotation_width_m=float(2*np.linalg.norm(HALF)),
            minimum_rotated_width_margin_m=float(passage['width_m']-2*np.linalg.norm(HALF)),
            soft_inflation_radius_m=.5,inscribed_lethal_radius_m=.12)
    for name,half in [('bare',BARE),('padded_v3',HALF)]:
        result['geometry'][name]['witness']=witness(wpose,world.static['regions']['zone_B']['center_m'],rects,bounds,half)
    return result,cm


def rectangles(ax,rects,own=False):
    from matplotlib.patches import Polygon
    for r in rects:
        poly=transform(np.array([[-1,-1],[1,-1],[1,1],[-1,1]])*r['half'],(*r['center'],r['yaw']))
        if own:poly=inverse(poly,START)
        ax.add_patch(Polygon(poly,fc='.55' if r.get('kind')=='wall' else '.2',ec='.1',alpha=.6))


def plot(case,world,records,costmaps,path):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon
    from matplotlib.colors import ListedColormap
    fig,axes=plt.subplots(2,2,figsize=(11,8),layout='constrained')
    ax=axes[0,0]
    rectangles(ax,world.rects)
    ax.plot(path[:,0],path[:,1],color='royalblue',label='Recorded v3 path')
    goal=world.static['regions']['zone_B']['center_m']
    ax.scatter(*goal,marker='*',color='blue',s=90,label='B (evaluation)')
    wit=records[0]['geometry']['bare']['witness']
    if wit['found']:
        wp=np.array(wit['path_world_m'])
        ax.plot(wp[:,0],wp[:,1],color='green',lw=1,label='Certified disk witness (GT only)')
    ax.set_title(case+': exact scene and route existence')
    ax.legend(fontsize=7)
    ax.set_xlim(world.static['bounds_m'][:2]);ax.set_ylim(world.static['bounds_m'][2:])
    ax=axes[0,1]
    rectangles(ax,world.rects)
    for rec,color in zip(records,['red','purple']):
        p=rec['pose_world']
        poly=transform(np.array([[-1,-1],[1,-1],[1,1],[-1,1]])*HALF,p)
        ax.add_patch(Polygon(poly,fill=False,ec=color,lw=1.5,label=rec['stage']+' padded'))
        body=transform(np.array([[-1,-1],[1,-1],[1,1],[-1,1]])*BARE,p)
        ax.add_patch(Polygon(body,fc=color,alpha=.2))
    passage=next(p for p in world.static['passages'] if 'width_m' in p)
    x,y=passage['center_m']
    ax.plot([x,x],[y-passage['width_m']/2,y+passage['width_m']/2],color='cyan',lw=3)
    ax.text(x+.04,y,'width %.2f m'%passage['width_m'],fontsize=8)
    first=records[0]['pose_world']
    ax.set_xlim(first[0]-.6,max(first[0]+.7,x+.15));ax.set_ylim(first[1]-.6,first[1]+.6)
    ax.set_title('Exact walls, body and padded footprint');ax.legend(fontsize=7)
    for ax,rec,cm in zip(axes[1],records,costmaps):
        extent=[cm.origin[0],cm.origin[0]+cm.raw.shape[1]*.1,cm.origin[1],cm.origin[1]+cm.raw.shape[0]*.1]
        im=ax.imshow(cm.costs,origin='lower',extent=extent,cmap='magma_r',vmin=0,vmax=255)
        p=np.array(rec['pose_odom'])
        _,poly=cm.footprint_mask(p)
        ax.add_patch(Polygon(poly,fill=False,ec='lime',lw=2,label='Padded footprint'))
        if rec['projected_blocked_pose_odom'] is not None:
            _,bad=cm.footprint_mask(rec['projected_blocked_pose_odom'])
            ax.add_patch(Polygon(bad,fill=False,ec='cyan',ls='--',label='First rejected projection'))
        rectangles(ax,world.rects,own=True)
        ax.set_xlim(p[0]-.55,p[0]+.65);ax.set_ylim(p[1]-.55,p[1]+.65)
        ax.set_title(f"{rec['stage']} t={rec['t']:.1f}s, raw clear={rec['raw_pose_clear']}")
        ax.set_xlabel('Own x (m)');ax.set_ylabel('Own y (m)');ax.legend(fontsize=7)
        fig.colorbar(im,ax=ax,label='Cost: 0 free, 253 inscribed, 254 lethal, 255 unknown',shrink=.8)
    for ax in axes.flat:ax.set_aspect('equal')
    out=EXP/'figures';out.mkdir(exist_ok=True)
    fig.savefig(out/(case+'.png'),dpi=150);plt.close(fig)


def main():
    dest=OUT/'audit-v2';dest.mkdir(exist_ok=False)
    results=[];inputs={}
    for i in (4,5):
        for seed in (4701,4702):
            case=f's{i}-G-{seed}-static_map';folder=OLD/case
            logs=rows(folder/'actor.jsonl');events=rows(folder/'navigation_events.jsonl')
            for p in folder.iterdir():
                if p.is_file():inputs[str(p)]=digest(p)
            first=next(e for e in events if e['reason']=='predicted_footprint_collision')
            firstframe=max(r['frame'] for r in logs if r['t']<=first['t']+1e-7)
            scenario,static,rects,source=load_layout(i)
            world=SimpleNamespace(start=START,static=static,rects=rects)
            actor=PersistentActor('static_map',*static_inputs(world),navigation='public_ros_v3')
            records=[];costmaps=[]
            for log in logs:
                replay_observation(actor,log)
                if log['frame'] in (firstframe,logs[-1]['frame']):
                    stage='first_rejection' if log['frame']==firstframe else 'terminal'
                    record,cm=snapshot(actor,log,world,stage)
                    records.append(record);costmaps.append(cm)
                    np.savez_compressed(dest/(case+'-'+stage+'.npz'),raw=cm.raw,costs=cm.costs,origin=cm.origin)
            final=dict(resolution_m=.1,cells=[[*c,v] for c,v in sorted(actor.grid.odds.items())])
            assert final==load(folder/'own_grid.json'),'OWN_GRID_RECONSTRUCTION_MISMATCH'
            result=dict(case=case,source_result=load(folder/'result.json'),snapshots=records,
                terminal_event=next(e for e in events if e['reason']=='navigation_action_aborted'),
                own_grid_exact=True)
            write(dest/(case+'.json'),result);results.append(result)
            if seed==4701:plot(case,world,records,costmaps,np.array(load(folder/'eval_path.json')))
            print(case,[(r['stage'],r['raw_pose_clear'],r['geometry']['bare']['witness']['found'],r['geometry']['padded_v3']['stop_contacts']) for r in records],flush=True)
    assert 'mujoco' not in sys.modules
    write(dest/'results.json',results)
    write(dest/'source.json',dict(sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        audit_sha256=digest(Path(__file__)),inputs=inputs,physics=0,model_calls=0,confirmation_opened=0))


if __name__=='__main__':main()
