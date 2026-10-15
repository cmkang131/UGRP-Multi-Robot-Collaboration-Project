"""Default-off deterministic line RANSAC; inputs are own RGB and command odometry.

The enlarged covariance remains the NIS model. A finite count budget, never
wall time, limits search. Two separated solutions reject; exhausted search
cannot authorize registration. This is a finite proposal search, not a proof
of continuous-space global uniqueness.
"""
import math
from itertools import combinations
import numpy as np
from harness.natural_floor_slam import compose, wrap
from harness.selfmap4_geometry import inverse

MIN_INLIERS = 3
MIN_FRACTION = .7
MAX_GENERATORS = 16
MAX_PROPOSALS = 4096


def serial(value):
    if isinstance(value, dict): return {k: serial(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)): return [serial(v) for v in value]
    if isinstance(value, np.ndarray): return value.tolist()
    if isinstance(value, np.generic): return value.item()
    return value


def replay_packet(evidence, own_pose, observation, t):
    # Full buffered lines are necessary: old traces only saved counts.
    return serial(dict(t=t, own_odometry_pose=own_pose, lines=observation['features'],
        frames=evidence.frames, active=evidence.active, rolling=evidence.rolling,
        started=evidence.started))


def ransac_hypotheses(evidence, edges, own_pose, covariance, *, max_proposals=MAX_PROPOSALS):
    lines=[]
    for frame in evidence.frames:
        rel=compose(inverse(own_pose), frame['pose']); c,s=math.cos(rel[2]),math.sin(rel[2])
        R=np.array([[c,-s],[s,c]])
        for line in frame['lines']:
            lines.append(dict(hue=line['hue'], endpoints=np.asarray(line['endpoints'])@R.T+rel[:2],
                              normal=np.asarray(line['normal'])@R.T))
    result=dict(candidate_count=0, unique=False, candidates=[], search_complete=True,
        method='deterministic_line_ransac_v1', min_inliers=MIN_INLIERS,
        min_fraction=MIN_FRACTION, line_count=len(lines), proposals=0,
        budget_kind='proposal_count', max_proposals=max_proposals, support=[])
    if len(lines)<MIN_INLIERS: return dict(result, reason='insufficient_lines')
    # Cover distinct lines throughout the buffer instead of privileging lines[0].
    distinct={}
    for i,l in enumerate(lines):
        key=(round(l['hue']/3), *np.round(l['normal']/.05).astype(int),
             *np.round(np.mean(l['endpoints'],axis=0)/.05).astype(int))
        distinct.setdefault(key,i)
    ids=list(distinct.values())
    if len(ids)>MAX_GENERATORS:
        ids=[ids[i] for i in np.linspace(0,len(ids)-1,MAX_GENERATORS,dtype=int)]
    result['generator_count']=len(ids)
    normals=np.asarray([l['normal'] for l in lines]); ends=np.asarray([l['endpoints'] for l in lines])
    hues=np.asarray([l['hue'] for l in lines]); bearings=np.arctan2(normals[:,1],normals[:,0])
    angle_tol=3*math.sqrt(covariance[2,2]+(math.radians(5)/3)**2)
    def hue_ok(a,b):
        d=abs(a-b);return min(d,180-d)<=12
    def bearing(n): return math.atan2(n[1],n[0])
    def support(pose,R):
        world=ends@R.T+pose[:2]; fits=np.zeros(len(lines),bool)
        matched=np.full(len(lines),-1,int)
        offset=world-pose[:2]; J=np.zeros((len(lines),2,2,3))
        J[:,:,0,0]=1;J[:,:,1,1]=1;J[:,:,0,2]=-offset[:,:,1];J[:,:,1,2]=offset[:,:,0]
        S=J@covariance@np.swapaxes(J,-1,-2)+np.eye(2)*(.05/3)**2
        inv=np.linalg.inv(S)
        for k,e in enumerate(edges):
            d=np.abs(hues-e['hue']); hd=np.minimum(d,180-d)
            compatible=(hd<=12)&(np.abs((bearing(e['normal'])-bearings-pose[2]+np.pi)%(2*np.pi)-np.pi)<=angle_tol)
            a,b=np.asarray(e['a']),np.asarray(e['b']);v=b-a
            error=world-a-np.clip((world-a)@v/(v@v),0,1)[:,:,None]*v
            nis=np.einsum('nki,nkij,nkj->nk',error,inv,error).max(axis=1)
            good=compatible&(nis<=9.); matched[good&~fits]=k;fits|=good
        ns=normals[fits]
        rank=len(ns)>=2 and np.linalg.eigvalsh(ns.T@ns).min()>=.5
        return dict(inliers=int(fits.sum()),total=len(lines),independent_axes=bool(rank),
                    distinct_map_edges=len(set(matched[fits].tolist())))
    for i,j in combinations(ids,2):
        first,second=lines[i],lines[j]
        if abs(np.linalg.det([first['normal'],second['normal']]))<.5:continue
        for e1 in edges:
            if not hue_ok(e1['hue'],first['hue']):continue
            yaw=wrap(bearing(e1['normal'])-bearing(first['normal']));c,s=math.cos(yaw),math.sin(yaw)
            R=np.array([[c,-s],[s,c]])
            for e2 in edges:
                if not hue_ok(e2['hue'],second['hue']) or abs(wrap(bearing(e2['normal'])-bearing(second['normal'])-yaw))>angle_tol:continue
                A=np.asarray([e1['normal'],e2['normal']])
                if abs(np.linalg.det(A))<.5:continue
                if result['proposals']>=max_proposals:
                    return dict(result,unique=False,search_complete=False,reason='proposal_budget_exhausted')
                result['proposals']+=1
                b=[np.asarray(e['normal'])@(np.asarray(e['a'])-R@np.mean(l['endpoints'],axis=0)) for e,l in [(e1,first),(e2,second)]]
                pose=np.r_[np.linalg.solve(A,b),yaw]
                if any(np.linalg.norm(pose[:2]-np.asarray(p)[:2])<.15 and abs(wrap(pose[2]-p[2]))<math.radians(10) for p in result['candidates']):continue
                fit=support(pose,R)
                if fit['inliers']<max(MIN_INLIERS,math.ceil(MIN_FRACTION*len(lines))) or not fit['independent_axes'] or fit['distinct_map_edges']<2:continue
                result['candidates'].append(pose.tolist());result['support'].append(fit);result['candidate_count']+=1
                if result['candidate_count']>=2:
                    return dict(result,search_complete=False,reason='multiple_separated_solutions')
    return dict(result,unique=result['candidate_count']==1,
                reason='single_sampled_solution' if result['candidate_count']==1 else 'no_supported_solution')
