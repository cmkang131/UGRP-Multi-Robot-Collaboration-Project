"""Own contact points -> split-and-merge lines, CI fusion, own Manhattan axes.

Algorithm adaptation of BSD-3-Clause kam3k/laser_line_extraction (NOTICE under
third_party/wall_segments). Camera covariances replace laser polar noise.
Neither this module nor its inputs contain a static map or ground truth.
"""
import math
from collections import Counter
import numpy as np
from scipy.optimize import least_squares
from harness.rbpf_manhattan import axis_observation
from harness.self_odom_grid import transform

OPTION='segments_v1'
PARAMETERS=dict(split_m=.05,gap_m=.4,min_length_m=.5,min_points=9,outlier_m=.05,
                merge_chi2=3.,range_min_m=.4,range_max_m=4.,fit_tolerance=1e-4,ci_weight=.5)


def endpoints(mean, points):
    rho,theta=mean
    n=np.array([math.cos(theta),math.sin(theta)])
    tangent=np.array([-n[1],n[0]])
    along=np.asarray(points)@tangent
    return np.array([rho*n+along.min()*tangent,rho*n+along.max()*tangent])


def fit(points, covariances):
    p,q=np.asarray(points),np.asarray(covariances)
    delta=p[-1]-p[0]
    theta=math.atan2(delta[1],delta[0])+math.pi/2
    start=[float(p.mean(0)@np.array([math.cos(theta),math.sin(theta)])),theta]
    def residual(x):
        n=np.array([math.cos(x[1]),math.sin(x[1])])
        return (p@n-x[0])/np.sqrt(np.einsum('i,nij,j->n',n,q,n))
    opt=least_squares(residual,start,ftol=1e-4,xtol=1e-4,gtol=1e-4,max_nfev=100)
    if not opt.success:raise ValueError('SEGMENT_FIT_DID_NOT_CONVERGE')
    info=opt.jac.T@opt.jac
    if np.linalg.eigvalsh(info).min()<=0:raise ValueError('DEGENERATE_LINE')
    return dict(mean=opt.x,covariance=np.linalg.inv(info),ends=endpoints(opt.x,p),points=len(p))


def extract(points,covariances,camera):
    """Ordered actual contact columns, not interpolated endpoint samples."""
    p,q=np.asarray(points,float).reshape(-1,2),np.asarray(covariances,float).reshape(-1,2,2)
    if len(p)!=len(q) or not np.isfinite(p).all() or not np.isfinite(q).all():
        raise ValueError('INVALID_SEGMENT_POINTS')
    if len(q) and np.linalg.eigvalsh(q).min()<=0:raise ValueError('INVALID_POINT_COVARIANCE')
    r=np.linalg.norm(p-np.asarray(camera),axis=1)
    keep=(r>=.4)&(r<4.)
    p,q,r=p[keep],q[keep],r[keep]
    if len(p)<3:return []
    good=[]
    for i in range(len(p)):
        j,k=(1,2) if i==0 else ((i-1,i-2) if i==len(p)-1 else (i-1,i+1))
        d=p[k]-p[j]
        norm=np.linalg.norm(d)
        perpendicular=abs(d[0]*(p[i,1]-p[j,1])-d[1]*(p[i,0]-p[j,0]))/norm if norm else np.linalg.norm(p[i]-p[j])
        if not (abs(r[i]-r[j])>.05 and abs(r[i]-r[k])>.05 and perpendicular>.05):good.append(i)
    p,q=p[good],q[good]
    groups=[]
    def split(a,b):
        x=p[a:b]
        if len(x)<2:return
        d=x[-1]-x[0]
        norm=np.linalg.norm(d)
        distance=abs(d[0]*(x[:,1]-x[0,1])-d[1]*(x[:,0]-x[0,0]))/norm if norm else np.linalg.norm(x-x[0],axis=1)
        gap=np.linalg.norm(np.diff(x,axis=0),axis=1)
        if distance.max()<.05 and gap.max()<.4:
            if len(x)>=9 and norm>=.5:groups.append(fit(x,q[a:b]))
            return
        if distance.max()>=.05:
            cut=int(np.argmax(distance))
            if cut in (0,len(x)-1):return
            split(a,a+cut+1)
            split(a+cut,b)
        else:
            cut=int(np.argmax(gap))+1
            split(a,a+cut)
            split(a+cut,b)
    split(0,len(p))
    # Original within-scan covariance-weighted consecutive line merge.
    merged=[]
    for line in groups:
        if merged and compatible(merged[-1],line):merged[-1]=merge(merged[-1],line,ci=False)
        else:merged.append(line)
    return merged


def aligned(a,b):
    b={**b,'mean':b['mean'].copy(),'covariance':b['covariance'].copy()}
    delta=(b['mean'][1]-a['mean'][1]+math.pi)%(2*math.pi)-math.pi
    if abs(delta)>math.pi/2:
        b['mean'][0]*=-1
        b['covariance']=np.diag([-1.,1.])@b['covariance']@np.diag([-1.,1.])
        delta=(delta+math.pi+math.pi)%(2*math.pi)-math.pi
    b['mean'][1]=a['mean'][1]+delta
    return b


def compatible(a,b):
    b=aligned(a,b)
    d=a['mean']-b['mean']
    chi=float(d@np.linalg.solve(a['covariance']+b['covariance'],d))
    tangent=np.array([-math.sin(a['mean'][1]),math.cos(a['mean'][1])])
    aa,bb=a['ends']@tangent,b['ends']@tangent
    gap=max(0.,max(aa.min(),bb.min())-min(aa.max(),bb.max()))
    return chi<3. and gap<=.4


def merge(a,b,*,ci=True):
    b=aligned(a,b)
    ia,ib=np.linalg.inv(a['covariance']),np.linalg.inv(b['covariance'])
    weight=.5 if ci else 1.
    covariance=np.linalg.inv(weight*(ia+ib))
    mean=covariance@(weight*(ia@a['mean']+ib@b['mean']))
    return dict(mean=mean,covariance=covariance,ends=endpoints(mean,np.vstack([a['ends'],b['ends']])),
        points=a['points']+b['points'],frames=a.get('frames',set())|b.get('frames',set()))


def world_line(line,pose,pose_covariance,axis,axis_variance):
    rho,theta=line['mean']
    angle=theta+pose[2]
    n=np.array([math.cos(angle),math.sin(angle)])
    dn=np.array([-n[1],n[0]])
    mean=np.array([rho+n@pose[:2],angle])
    jl=np.array([[1.,dn@pose[:2]],[0.,1.]])
    jp=np.array([[*n,dn@pose[:2]],[0.,0.,1.]])
    covariance=jl@line['covariance']@jl.T+jp@pose_covariance@jp.T
    ends=transform(line['ends'],pose)
    target=axis+math.pi/2+round((angle-axis-math.pi/2)/(math.pi/2))*(math.pi/2)
    nn=np.array([math.cos(target),math.sin(target)])
    mean=np.array([nn@ends.mean(0),target])
    # Do not let axis snapping erase orientation uncertainty.
    spread=float(np.linalg.norm(ends[1]-ends[0])/2)
    covariance=np.diag([covariance[0,0]+spread**2*(covariance[1,1]+axis_variance),
                        covariance[1,1]+axis_variance])+np.eye(2)*1e-12
    return {**line,'mean':mean,'covariance':covariance,'ends':endpoints(mean,ends)}


def build_segment_map(rows,observations,*,robot_id,wall_map='off'):
    if wall_map=='off':return None
    if wall_map!=OPTION:raise ValueError('UNKNOWN_WALL_MAP')
    lines=[]
    axis=None
    counts=Counter()
    seen=set()
    for row in rows:
        if row.get('robot_id')!=robot_id:raise ValueError('SELF_MAP_PEER_INPUT_FORBIDDEN')
        key=row['frame_id']
        if key in seen:raise ValueError('DUPLICATE_SEGMENT_FRAME')
        seen.add(key)
        obs=observations[key]
        pose=np.asarray(row['pose'],float)
        pose_cov=np.asarray(obs['pose_covariance'],float)
        if pose_cov.shape!=(3,3) or not np.isfinite(pose_cov).all() or np.linalg.eigvalsh(pose_cov).min()<-1e-10:
            raise ValueError('INVALID_POSE_COVARIANCE')
        groups=extract(obs['points'],obs['covariances'],row['camera'])
        counts['input_frames']+=1
        counts['input_points']+=len(obs['points'])
        counts['extracted_lines']+=len(groups)
        if not groups:continue
        if axis is None:
            moment=axis_observation([g['ends'] for g in groups],math.radians(2.))
            axis=moment['angle_rad']+pose[2]
            axis_variance=moment['variance_rad2']+float(pose_cov[2,2])
        for group in groups:
            line=world_line(group,pose,pose_cov,axis,axis_variance)
            line['frames']={key}
            candidate=next((i for i,a in enumerate(lines) if compatible(a,line)),None)
            if candidate is None:lines.append(line)
            else:
                lines[candidate]=merge(lines[candidate],line)
                counts['temporal_merges']+=1
    output=[]
    for line in lines:
        output.append(dict(endpoints_m=line['ends'].tolist(),normal_rho_theta=line['mean'].tolist(),
            covariance=line['covariance'].tolist(),observations=len(line['frames']),
            frame_ids=sorted(line['frames']),point_support=line['points']))
    return dict(schema='ugrp.own_wall_segments.v1',robot_id=robot_id,frame='own start chassis: x forward, y left, metres',
        confidence_semantics='covariance and distinct-frame support; NOT calibrated wall probability',
        parameters=PARAMETERS,axis_rad=axis,counts=dict(counts),segments=output)
