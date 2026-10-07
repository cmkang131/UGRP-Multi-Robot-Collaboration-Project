"""Secondary evaluation-only clearance certificates; runtime frozen, no replay."""
from pathlib import Path
import math
import json
import subprocess
import numpy as np
import audit as a
from harness.public_navigation.costmap import Costmap
from harness.public_navigation_persistent import raytrace_cells


def rectangle_margin(pose,rects,bounds,half):
    """SAT separating-axis gap, a lower bound on Euclidean rectangle separation."""
    c,s=math.cos(pose[2]),math.sin(pose[2])
    axes=np.array([[c,s],[-s,c]])
    points=a.transform(np.array([[-1,-1],[-1,1],[1,1],[1,-1]])*half,pose)
    x0,x1,y0,y1=bounds
    margin=float(np.min(np.c_[points[:,0]-x0,x1-points[:,0],points[:,1]-y0,y1-points[:,1]]))
    for r in rects:
        c,s=math.cos(r['yaw']),math.sin(r['yaw'])
        other=np.array([[c,s],[-s,c]])
        normals=np.vstack([axes,other])
        radius=np.abs(normals@axes.T)@half+np.abs(normals@other.T)@r['half']
        gaps=np.abs(normals@(np.asarray(pose[:2])-r['center']))-radius
        margin=min(margin,float(np.max(gaps)))
    return margin


def rectangle_certificate(path,rects,bounds,half):
    radius=float(np.linalg.norm(half))
    sample=[];bound=0.
    for p,q in zip(path,path[1:]):
        p,q=np.asarray(p),np.asarray(q)
        length=np.linalg.norm(q[:2]-p[:2])+radius*abs(q[2]-p[2])
        n=max(1,math.ceil(length/.001))
        sample.extend(np.linspace(p,q,n+1));bound=max(bound,float(length/n))
    if not sample:sample=list(path)
    minimum=min(rectangle_margin(p,rects,bounds,half) for p in sample)
    return dict(samples=len(sample),sample_sat_gap_m=minimum,continuous_clearance_lower_m=minimum-bound/2)


def original_outline_collision(cm,pose):
    _,poly=cm.footprint_mask(pose)
    cells=[cm.world_to_map(p) for p in poly]
    if None in cells:return True
    for p,q in zip(cells,cells[1:]+cells[:1]):
        if any(cm.raw[y,x]>=254 for x,y in raytrace_cells(p,q)):return True
    return False


def projection_prefix(pose,twist):
    # Same first requested, saturated v3 twist for 1s. Geometric counterfactual
    # only: no physics, no change to recorded commands or B outcomes.
    q=np.array(pose,float);out=[q.copy()]
    for _ in range(20):
        c,s=math.cos(q[2]),math.sin(q[2])
        q+=np.array([c*twist[0]-s*twist[1],s*twist[0]+c*twist[1],twist[2]])*.05
        out.append(q.copy())
    return np.array(out)


def main():
    dest=a.OUT/'certificates';dest.mkdir(exist_ok=False)
    rows=a.load(a.OUT/'audit-v2/results.json')
    report=[]
    for row in rows:
        i=int(row['case'][1]);_,static,rects,_=a.load_layout(i)
        bounds=static['bounds_m'];first=row['snapshots'][0];items=[]
        for rec in row['snapshots']:
            z=np.load(a.OUT/'audit-v2'/(row['case']+'-'+rec['stage']+'.npz'))
            cm=Costmap(z['raw'],z['origin'])
            assert np.array_equal(cm.costs,z['costs'])
            prefix=np.array([a.world_pose(p) for p in projection_prefix(rec['pose_odom'],first['requested_twist'])])
            cert=rectangle_certificate(prefix,rects,bounds,a.HALF)
            tail=a.witness(prefix[-1],static['regions']['zone_B']['center_m'],rects,bounds,a.HALF)
            if tail['found'] and cert['continuous_clearance_lower_m']>0:
                complete=dict(found=True,continuous_clearance_lower_m=min(cert['continuous_clearance_lower_m'],tail['continuous_clearance_lower_m']),
                    rectangle_prefix_world=prefix.tolist(),disk_tail=tail)
            else:complete=dict(found=False,reason='sufficient_certificate_not_found',prefix=cert,tail=tail)
            blocked=rec['projected_blocked_pose_odom']
            it=dict(stage=rec['stage'],padded_projection_prefix=cert,padded_complete_route=complete,
                    nav2_original_outline_rejects=None if blocked is None else original_outline_collision(cm,np.array(blocked)))
            items.append(it)
        report.append(dict(case=row['case'],snapshots=items))
        if '4701' in row['case']:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            from types import SimpleNamespace
            plt.rcParams['axes.titlesize']=10
            costmaps=[]
            for rec in row['snapshots']:
                z=np.load(a.OUT/'audit-v2'/(row['case']+'-'+rec['stage']+'.npz'))
                costmaps.append(Costmap(z['raw'],z['origin']))
            a.plot(row['case'],SimpleNamespace(static=static,rects=rects),row['snapshots'],costmaps,
                   np.array(a.load(a.OLD/row['case']/'eval_path.json')))
        print(row['case'],[(x['stage'],x['padded_complete_route']['found'],x['nav2_original_outline_rejects']) for x in items],flush=True)
    a.write(dest/'results.json',report)
    a.write(dest/'source.json',dict(sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        report_hash=a.digest(Path(__file__)),original_results_hash=a.digest(a.OUT/'audit-v2/results.json'),
        control_changes=0,new_episode_runs=0))


if __name__=='__main__':main()
