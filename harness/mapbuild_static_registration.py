"""Default-off CSM registration: own-map gauge -> authored static wall map.

Olson ICRA2009 global correlation search. Reuses CSMOptions sensor cost,
resolution, observability and rejection constants; no spawn/evaluation pose or
scale fit. All lattice cells are examined; work is candidate/point counts,
never elapsed wall time. A single wall or a symmetric map stays unregistered.
"""
import math
import numpy as np
from harness.self_map_csm import CSMOptions,DistanceField
from harness.self_odom_grid import transform

OPTION='mapbuild_static_csm_v1'


def wall_segments(static_map):
    """Only authored wall rectangles; no live bodies or camera inventory."""
    result=[]
    for record in static_map['obstacles']:
        if 'wall' not in record['id']:continue
        cx,cy=record['center_m'];a,b=record['half_extents_m'];yaw=record.get('yaw_rad',0.)
        c,s=math.cos(yaw),math.sin(yaw);r=np.array([[c,-s],[s,c]])
        corners=np.array([[-a,-b],[a,-b],[a,b],[-a,b]])@r.T+[cx,cy]
        result.extend([[corners[k].tolist(),corners[(k+1)%4].tolist()] for k in range(4)])
    return result


class StaticRegistration:
    def __init__(self,static_map,*,option='off'):
        if option not in ('off',OPTION):raise ValueError('UNKNOWN_STATIC_REGISTRATION')
        self.option=option;self.options=CSMOptions()
        self.bounds=tuple(static_map['bounds_m']);self.reference=np.asarray(wall_segments(static_map))
        if len(self.bounds)!=4 or not np.isfinite(self.bounds).all() or self.bounds[0]>=self.bounds[1] or self.bounds[2]>=self.bounds[3]:
            raise ValueError('INVALID_STATIC_BOUNDS')
        if not len(self.reference):raise ValueError('STATIC_WALLS_REQUIRED')
        self.field=DistanceField(self.reference,self.options.field_resolution_m,1.) if option!= 'off' else None

    def register(self,own_segments,*,camera_origins=None,diagnostic_callback=None,pose_covariances=None,body_origins=None):
        """own_segments are observed wall contacts already in own-map gauge.

        Result transform composes on the LEFT of any own-map SE2 pose. No
        implicit identity success, prior world pose, scale or hidden reset.
        """
        o=self.options
        work=dict(candidates=0,point_checks=0,wall_seconds_used_as_gate=0)
        def out(reason,**kw):
            return dict(status='accepted' if reason=='accepted' else 'off' if reason=='off' else 'rejected',reason=reason,
                static_from_own=None,category='static_wall_registration',blocked_object='authored_wall_geometry',
                minimum_gap_m=None,gap_status='not_measured',work=work,truth_inputs=0,scale=1,**kw)
        if self.option=='off':return out('off')
        seg=np.asarray(own_segments,float)
        if not seg.size:return out('no_observed_wall_segments')
        if seg.ndim!=3 or seg.shape[1:]!=(2,2) or not np.isfinite(seg).all():raise ValueError('INVALID_OWN_SEGMENTS')
        # The original CSM sigma depends on SENSOR range, not distance from
        # the arbitrary own-map gauge. Missing source origins cannot silently
        # become a noiseless map observation (mapbuild7 R1 source diagnosis).
        if camera_origins is None:return out('source_camera_origins_required')
        origins=np.asarray(camera_origins,float)
        if origins.shape!=(len(seg),2) or not np.isfinite(origins).all():raise ValueError('INVALID_SOURCE_CAMERAS')
        covariance_supplied=pose_covariances is not None
        if covariance_supplied:
            covariances=np.asarray(pose_covariances,float);body=np.asarray(body_origins,float)
            if covariances.shape!=(len(seg),3,3) or body.shape!=(len(seg),2) or not np.isfinite(np.r_[covariances.ravel(),body.ravel()]).all():raise ValueError('SOURCE_POSE_COVARIANCE_REQUIRED')
            if not np.allclose(covariances,covariances.transpose(0,2,1)) or np.linalg.eigvalsh(covariances).min()<-1e-12:raise ValueError('SOURCE_POSE_COVARIANCE_PSD_REQUIRED')
        elif body_origins is not None:raise ValueError('BODY_ORIGIN_WITHOUT_COVARIANCE')
        parts=[];sources=[];pose_sources=[];body_sources=[]
        for j,(s,origin) in enumerate(zip(seg,origins)):
            if np.linalg.norm(s[1]-s[0])<=1e-6:continue # verbatim sample_segments
            part=np.linspace(s[0],s[1],max(2,int(math.ceil(np.linalg.norm(s[1]-s[0])/.10))+1))
            parts.append(part);sources.append(np.repeat(origin[None],len(part),axis=0))
            if covariance_supplied:
                pose_sources.append(np.repeat(covariances[j][None],len(part),axis=0));body_sources.append(np.repeat(body[j][None],len(part),axis=0))
        if not parts:return out('insufficient_near_points',points=0)
        points=np.vstack(parts);sources=np.vstack(sources)
        _,idx=np.unique(np.floor(points/.10).astype(int),axis=0,return_index=True);idx=np.sort(idx)
        points=points[idx];sources=sources[idx]
        if len(points)<o.min_points:return out('insufficient_near_points',points=len(points))
        # Existing .05m/1deg CSM lattice is the global search resolution.
        # Two-level search is only an exact batch partition, NOT a top-K prune.
        x=np.arange(math.ceil(self.bounds[0]/o.field_resolution_m),math.floor(self.bounds[1]/o.field_resolution_m)+1)*o.field_resolution_m
        y=np.arange(math.ceil(self.bounds[2]/o.field_resolution_m),math.floor(self.bounds[3]/o.field_resolution_m)+1)*o.field_resolution_m
        xy=np.stack(np.meshgrid(x,y,indexing='ij'),-1).reshape(-1,2)
        yaw=np.arange(-180,180,o.yaw_step_deg)*math.pi/180
        radii=np.linalg.norm(points-sources,axis=1)
        # Exact CorrelativeMatcher.match formula and frozen CSMOptions.
        sigma=np.sqrt(o.calibration_floor_m**2+o.field_resolution_m**2/12+
                      (o.pixel_sigma*radii**2/(o.focal_y_px*o.height_lower_bound_m))**2)
        if covariance_supplied:
            P=np.vstack(pose_sources)[idx];lever=points-np.vstack(body_sources)[idx]
            J=np.zeros((len(points),2,3));J[:,0,0]=1;J[:,1,1]=1;J[:,0,2]=-lever[:,1];J[:,1,2]=lever[:,0]
            # Same marginal ray-position propagation as self_map_prob.py
            # insertion_weight: trace(J P J.T)/2. No fitted multiplier.
            # Common odometry bias remains correlated; effective_points cap is
            # unchanged, and this is NOT a calibrated global posterior claim.
            variance=np.einsum('nai,nij,naj->n',J,P,J)/2
            sigma=np.sqrt(sigma**2+np.maximum(0,variance))
        poses=[];costs=[]
        # Per yaw table: no candidate truncation and no wall-clock exit.
        for angle in yaw:
            c,s=math.cos(angle),math.sin(angle);rot=points@np.array([[c,s],[-s,c]])
            for begin in range(0,len(xy),1024): # memory-only chunk, no gate
                chunk=xy[begin:begin+1024];dist=self.field.query(rot[None]+chunk[:,None])
                z=dist/sigma;cost=np.where(z<=1.5,z*z,3*z-2.25).sum(1)*min(1.,o.effective_points/len(points))
                poses.append(np.column_stack([chunk,np.full(len(chunk),angle)]));costs.append(cost)
                work['candidates']+=len(chunk);work['point_checks']+=dist.size
        poses=np.vstack(poses);cost=np.concatenate(costs);index=int(cost.argmin());best=poses[index]
        # Offline inspection only. No evaluation labels, prior anchor or change
        # to the frozen search/cost/admission contract enters this callback.
        if diagnostic_callback is not None:diagnostic_callback(poses,cost,points,sigma)
        difference=poses-best;difference[:,2]=np.arctan2(np.sin(difference[:,2]),np.cos(difference[:,2]))
        # Existing CSM metric scales yaw to displacement at 2m.
        separated=np.linalg.norm(difference*[1,1,2],axis=1)>=o.mode_distance_m-1e-9
        second=float(cost[separated].min()) if separated.any() else math.inf
        gap=second-float(cost[index]);world=transform(points,best);dist=self.field.query(world)
        relative=world-best[:2]
        H=self.field.information(world,relative,sigma,o.overlap_distance_m,o.effective_points)
        S=np.diag([1.,1.,.5]);eigen=np.linalg.eigvalsh(S@H@S)
        observed=eigen>max(.5,o.hessian_ratio*eigen[-1]) # verbatim inherited CSM
        overlap=float(np.mean(dist<=o.overlap_distance_m));residual=float(np.sqrt(np.mean(dist**2)))
        reason=('unobservable_global_SE2' if not observed.all() else 'low_overlap' if overlap<o.min_overlap else
                'high_residual' if residual>o.max_residual_m else 'ambiguous_modes' if gap<o.mode_gap else 'accepted')
        result=out(reason,points=len(points),best_candidate=best.tolist(),residual_m=residual,overlap=overlap,
            second_sensor_gap=gap,hessian_eigenvalues=eigen.tolist(),observable_rank=int(observed.sum()),
            sensor_sigma_min_max_m=[float(sigma.min()),float(sigma.max())],
            source_pose_covariance_supplied=covariance_supplied,
            source_constants='unchanged CSMOptions: .05m/1deg, .08m floor + original range pixel variance, overlap .60/.20m, residual .15m, mode .15/.50, rank3 mathematical SE2 requirement')
        if reason=='accepted':
            result['static_from_own']=best.tolist();result['covariance']=(np.linalg.inv(H)+o.floor()).tolist()
        return result
