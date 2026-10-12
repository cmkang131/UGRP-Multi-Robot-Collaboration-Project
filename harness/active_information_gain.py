"""RSS2005 equations 11-22, one representative-map roll-out, private RBPF copies.

Finite camera views replace laser scans. No truth, simulator, peer or static map.
Unknown-beam gain uses the exact one-hit Bernoulli entropy change of this grid's
inverse sensor model, rather than a fitted laser statistic. Resolution-area scaled.
"""
import copy
import math
import numpy as np
from harness.self_odom_grid import transform
from harness.self_map_rbpf import GridField,improved_proposal
from harness.self_map_prob import wrap
from harness.public_navigation_persistent import raytrace_cells


def binary_entropy(logodds):
    p=1/(1+np.exp(-np.clip(np.asarray(logodds,float),-40,40)))
    return -(p*np.log(p)+(1-p)*np.log1p(-p))


def pose_entropy(cloud, weights, covariance=None):
    p=np.asarray(cloud,float).copy()
    yaw=math.atan2(weights@np.sin(p[:,2]),weights@np.cos(p[:,2]))
    p[:,2]=wrap(p[:,2]-yaw)
    delta=p-weights@p
    cov=(delta.T*weights)@delta
    if covariance is not None:
        cov+=np.einsum('n,nij->ij',weights,covariance)
    sign,ld=np.linalg.slogdet(cov+np.eye(3)*1e-10)
    return .5*(3*math.log(2*math.pi*math.e)+ld)


def trajectory_entropy(grid):
    # Common frame ancestry only; average over unique visited 0.1 m places.
    common=set(r['frame_id'] for r in grid.histories[0])
    for h in grid.histories[1:]:
        common.intersection_update(r['frame_id'] for r in h)
    tables=[{r['frame_id']:r['pose'] for r in h} for h in grid.histories]
    places={}
    for fid in sorted(common):
        cloud=np.array([h[fid] for h in tables])
        cell=tuple(np.floor((grid.weights@cloud[:,:2])/.1).astype(int))
        places[cell]=pose_entropy(cloud,grid.weights)
    cell=tuple(np.floor(np.asarray(grid.odom.pose[:2])/.1).astype(int))
    places[cell]=pose_entropy(grid.poses,grid.weights,grid.pending_cov)
    return float(np.mean(list(places.values())))


def entropy(grid,domain):
    map_h=sum(w*float(binary_entropy([g.cells.get(c,0.) for c in domain]).sum())*.01
              for w,g in zip(grid.weights,grid.maps))
    return trajectory_entropy(grid)+map_h


def sample_path(path, start_yaw, spacing=.5):
    p=np.asarray(path,float).reshape(-1,2)
    if len(p)<2:return np.empty((0,3))
    distances=np.r_[0.,np.cumsum(np.linalg.norm(np.diff(p,axis=0),axis=1))]
    targets=np.unique(np.r_[np.arange(0,distances[-1],spacing),distances[-1]])
    xy=np.column_stack([np.interp(targets,distances,p[:,k]) for k in range(2)])
    yaw=np.r_[start_yaw,np.arctan2(np.diff(xy[:,1]),np.diff(xy[:,0]))]
    return np.column_stack([xy,yaw])


def cell(point):
    return tuple(np.floor(np.asarray(point)/.1).astype(int))


def cast(grid,pose):
    camera=np.array([.124,0.])
    origin=transform([camera],pose)[0]
    start=cell(origin)
    hits=[]
    unknown=set()
    for bearing in np.linspace(-math.radians(54.5/2),math.radians(54.5/2),41):
        angle=pose[2]+bearing
        end=origin+4*np.array([math.cos(angle),math.sin(angle)])
        first_unknown=False
        for c in raytrace_cells(start,cell(end)):
            value=grid.cells.get(c,0.)
            if not first_unknown and value>0:
                point=(np.array(c)+.5)*.1
                d=point-pose[:2]
                co,si=math.cos(pose[2]),math.sin(pose[2])
                hits.append([co*d[0]+si*d[1],-si*d[0]+co*d[1]])
                break
            if c not in grid.cells:
                first_unknown=True
                unknown.add(c)
    return np.asarray(hits).reshape(-1,2),unknown


def forecast(grid,path,*,seed=22001):
    """One sampled-map sensor rollout; the real filter/RNG never change."""
    # CloudOdometry proxies __getattr__; allocate its cyclic owner explicitly
    # (Python copy reconstruction probes __setstate__ before driver exists).
    odom=object.__new__(type(grid.odom))
    hypothetical=copy.deepcopy(grid,{id(grid.odom):odom})
    odom.owner=hypothetical
    odom.driver=copy.deepcopy(grid.odom.driver,{id(grid):hypothetical,id(grid.odom):odom})
    odom.driver.step_callback=hypothetical.propagate
    rng=np.random.default_rng(seed)
    representative=int(rng.choice(len(grid.weights),p=grid.weights))
    source=copy.deepcopy(grid.maps[representative])
    poses=sample_path(path,grid.odom.pose[2])
    if len(poses)<2:return dict(gain=0.,cost=0.,utility=0.,views=0,representative=representative)
    unknown=set()
    for index,(a,b) in enumerate(zip(poses,poses[1:])):
        delta=b-a;delta[2]=wrap(delta[2])
        co,si=math.cos(a[2]),math.sin(a[2])
        delta[:2]=np.array([[co,si],[-si,co]])@delta[:2]
        # Original v122 displacement variance per motion distance/angle; no fit.
        from harness.self_pulse_odom import model
        profiles=model()['profiles']
        f=profiles['0:forward:0.35:0.10'];r=profiles['0:turn:0.35:0.10']
        variance=(np.asarray(f['prediction_variance'])*np.linalg.norm(delta[:2])/abs(f['mean_curve'][-1][0])+
                  np.asarray(r['prediction_variance'])*abs(delta[2])/abs(r['mean_curve'][-1][2]))
        hypothetical.propagate(delta,variance)
        best=np.asarray(grid.odom.pose)
        representative_pose=grid.poses[representative]
        R=np.array([[math.cos(best[2]),math.sin(best[2])],[-math.sin(best[2]),math.cos(best[2])]])
        relative=R@(b[:2]-best[:2])
        expected_xy=transform([relative],representative_pose)[0]
        expected_pose=[*expected_xy,wrap(representative_pose[2]+b[2]-best[2])]
        points,new=cast(source,expected_pose)
        unknown.update(new)
        # Virtual measurements stay in copied particles; exact improved proposal.
        for i,g in enumerate(hypothetical.maps):
            prior=hypothetical.poses[i].copy()
            cov=hypothetical.pending_cov[i]+np.eye(3)*1e-10
            past=g.occupied_points()
            if len(points)>=hypothetical.options.min_points and len(past)>=hypothetical.options.min_points:
                pose,inc,event=improved_proposal(GridField(past),points,[.124,0.],prior,cov,rng,hypothetical.options)
                hypothetical.poses[i]=pose
                hypothetical.log_weights[i]+=inc
            else:
                hypothetical.poses[i]=rng.multivariate_normal(prior,cov)
            hypothetical.pending_cov[i]=np.eye(3)*1e-10
            pose=hypothetical.poses[i]
            if len(points):
                g.insert(transform([[.124,0.]],pose)[0],[transform([p,p],pose) for p in points])
            hypothetical.histories[i].append(dict(frame_id=10_000_000+index,pose=pose.tolist()))
        from scipy.special import logsumexp
        hypothetical.log_weights-=logsumexp(hypothetical.log_weights)
        hypothetical.weights=np.exp(hypothetical.log_weights)
        hypothetical.best=int(np.argmax(hypothetical.weights))
        hypothetical.resample_if_needed()
    domain=set().union(*(g.cells for g in grid.maps),*(g.cells for g in hypothetical.maps))
    gain=entropy(grid,domain)-entropy(hypothetical,domain)
    # Sec V unknown-ray approximation, area scaling, no GT predictions.
    unseen_gain=len(unknown)*.01*float(math.log(2)-binary_entropy(math.log(.7/.3)))
    cost=0.
    for a,b in zip(poses,poses[1:]):
        p=1/(1+math.exp(-source.cells.get(cell(b[:2]),0.)))
        cost+=float(np.linalg.norm(b[:2]-a[:2]))*p
    gain+=unseen_gain
    return dict(gain=float(gain),cost=cost,utility=float(gain-.35*cost),views=len(poses)-1,
                representative=representative,unknown_cells=len(unknown),unknown_gain=unseen_gain)
