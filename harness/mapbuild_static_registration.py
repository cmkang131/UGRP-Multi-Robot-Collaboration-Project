"""Default-off CSM registration: own-map gauge -> authored static wall map.

Olson ICRA2009 global correlation search. Reuses CSMOptions sensor cost,
resolution, observability and rejection constants; no spawn/evaluation pose or
scale fit. All lattice cells are examined; work is candidate/point counts,
never elapsed wall time. A single wall or a symmetric map stays unregistered.
"""
import math
import numpy as np
from harness.self_map_csm import CSMOptions,DistanceField,sample_segments
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

    def register(self,own_segments):
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
        points=sample_segments(seg) # existing CSM .10m sample spacing
        if len(points)<o.min_points:return out('insufficient_near_points',points=len(points))
        # Existing .05m/1deg CSM lattice is the global search resolution.
        # Two-level search is only an exact batch partition, NOT a top-K prune.
        x=np.arange(math.ceil(self.bounds[0]/o.field_resolution_m),math.floor(self.bounds[1]/o.field_resolution_m)+1)*o.field_resolution_m
        y=np.arange(math.ceil(self.bounds[2]/o.field_resolution_m),math.floor(self.bounds[3]/o.field_resolution_m)+1)*o.field_resolution_m
        xy=np.stack(np.meshgrid(x,y,indexing='ij'),-1).reshape(-1,2)
        yaw=np.arange(-180,180,o.yaw_step_deg)*math.pi/180
        sigma=np.sqrt(o.calibration_floor_m**2+o.field_resolution_m**2/12)
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
        difference=poses-best;difference[:,2]=np.arctan2(np.sin(difference[:,2]),np.cos(difference[:,2]))
        # Existing CSM metric scales yaw to displacement at 2m.
        separated=np.linalg.norm(difference*[1,1,2],axis=1)>=o.mode_distance_m-1e-9
        second=float(cost[separated].min()) if separated.any() else math.inf
        gap=second-float(cost[index]);world=transform(points,best);dist=self.field.query(world)
        relative=world-best[:2]
        H=self.field.information(world,relative,np.full(len(points),sigma),o.overlap_distance_m,o.effective_points)
        S=np.diag([1.,1.,.5]);eigen=np.linalg.eigvalsh(S@H@S)
        observed=eigen>max(.5,o.hessian_ratio*eigen[-1]) # verbatim inherited CSM
        overlap=float(np.mean(dist<=o.overlap_distance_m));residual=float(np.sqrt(np.mean(dist**2)))
        reason=('unobservable_global_SE2' if not observed.all() else 'low_overlap' if overlap<o.min_overlap else
                'high_residual' if residual>o.max_residual_m else 'ambiguous_modes' if gap<o.mode_gap else 'accepted')
        result=out(reason,points=len(points),best_candidate=best.tolist(),residual_m=residual,overlap=overlap,
            second_sensor_gap=gap,hessian_eigenvalues=eigen.tolist(),observable_rank=int(observed.sum()),
            source_constants='unchanged CSMOptions: .05m/1deg, .08m sigma, overlap .60/.20m, residual .15m, mode .15/.50, rank3 mathematical SE2 requirement')
        if reason=='accepted':
            result['static_from_own']=best.tolist();result['covariance']=(np.linalg.inv(H)+o.floor()).tolist()
        return result
