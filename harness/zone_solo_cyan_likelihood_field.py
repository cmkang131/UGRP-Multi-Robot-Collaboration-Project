"""S2-only optional Nav2 likelihood-field measurement, no residual hard veto.

Algorithm reference (LGPL-2.1-or-later, Brian Gerkey / Kasper Stoy):
navigation2 235fc5ce55bdf94d9be360fdbca39d89dc0e4f74,
nav2_amcl/src/sensors/laser/likelihood_field_model.cpp, sensorFunction.
Same nearest occupied-cell distance, hit/random mixture and 1+sum(pz**3).
This is a measurement port, not a ROS/KLD/laser sensor emulation. The camera
adapter projects own RGB floor boundaries with fixed, explicit calibration.
No evaluation poses, live joints or simulator handles are accepted.
"""
import copy
import math
import numpy as np
from scipy.ndimage import distance_transform_edt
from harness.zone_solo_cyan_visual_fix import Runtime as Previous
from harness import zone_pair_highpose as high

OPTION='amcl_likelihood_field_v1'
PARAMS=dict(z_hit=.5,z_rand=.5,sigma_hit_m=.2,max_occ_dist_m=2.,max_beams=60,
            range_max_m=100.,grid_resolution_m=.01,update_min_d_m=.25,
            update_min_a_rad=.2,do_beamskip=False)


class Field:
    """Metric occupancy raster; Euclidean cell-center distance, as AMCL cspace."""
    def __init__(self,static_map):
        rects=[]
        for o in static_map['obstacles']:
            if o.get('kind')!='wall':continue
            if o.get('yaw_rad',0):raise ValueError('axis-aligned S2 walls required')
            x,y=o['center_m'];dx,dy=o['half_extents_m']
            rects.append((x-dx,x+dx,y-dy,y+dy))
        if not rects:raise ValueError('static occupied walls required')
        r=np.array(rects);self.res=PARAMS['grid_resolution_m']
        self.origin=np.floor(r[:,[0,2]].min(0)/self.res)*self.res
        end=np.ceil(r[:,[1,3]].max(0)/self.res)*self.res
        self.shape=tuple((np.rint((end-self.origin)/self.res).astype(int)+1)[::-1])
        iy,ix=np.indices(self.shape);x=self.origin[0]+ix*self.res;y=self.origin[1]+iy*self.res
        occupied=np.zeros(self.shape,bool)
        for a,b,c,d in rects:occupied|=(x>=a-1e-12)&(x<=b+1e-12)&(y>=c-1e-12)&(y<=d+1e-12)
        self.dist=np.minimum(distance_transform_edt(~occupied)*self.res,PARAMS['max_occ_dist_m'])

    def distances(self,points):
        points=np.asarray(points,float)
        ij=np.floor((points-self.origin)/self.res+.5).astype(int)
        x,y=ij[...,0],ij[...,1]
        good=(x>=0)&(y>=0)&(x<self.shape[1])&(y<self.shape[0])
        out=np.full(x.shape,PARAMS['max_occ_dist_m'])
        out[good]=self.dist[y[good],x[good]]
        return out


def endpoints(cm,obs):
    """Own undistorted boundary pixels -> planar metric endpoints.

    ABOVE/no return is missing data, never an artificial max-range return.
    AMCL's integer stride is preserved (it is not a strict max_beams cap).
    """
    step=max(1,(len(obs.columns)-1)//(PARAMS['max_beams']-1))
    idx=np.arange(0,len(obs.columns),step)
    t=cm.t_of_row(obs.b_lo);points=cm.floor_point(t)
    ranges=np.linalg.norm(points-cm.origin[:2],axis=1)
    # Forward optical depth and a downward floor intersection are required.
    camera_points=(np.c_[points,np.zeros(len(points))]-cm.origin)@cm._rot
    valid=(obs.b_kind==1)&np.isfinite(points).all(1)&(camera_points[:,2]>0)&(ranges<PARAMS['range_max_m'])
    idx=idx[valid[idx]]
    return points[idx]


def likelihood(field,px,points):
    px=np.asarray(px,float);points=np.asarray(points,float).reshape(-1,2)
    if not len(points):return np.ones(len(px))
    c,s=np.cos(px[:,2,None]),np.sin(px[:,2,None])
    x=px[:,0,None]+c*points[None,:,0]-s*points[None,:,1]
    y=px[:,1,None]+s*points[None,:,0]+c*points[None,:,1]
    d=field.distances(np.stack((x,y),axis=-1))
    pz=PARAMS['z_hit']*np.exp(-d*d/(2*PARAMS['sigma_hit_m']**2))+PARAMS['z_rand']/PARAMS['range_max_m']
    return 1.+np.sum(pz*pz*pz,axis=1)


def install(pf,static_map,*,visibility=None,pose_supported=high.at_high):
    field=Field(static_map);previous=pf.update_obs;predict=pf.predict_to
    state=dict(odom=np.zeros(3),anchor=None,observation=None)
    audit=dict(option=OPTION,parameters=copy.deepcopy(PARAMS),scope='S2 loaded HIGH only',
               absolute_fix=False,candidates=0,updates=0,rows=[])

    def predict_to(t):
        t0=float(pf.t);out=predict(t);dt=float(pf.t)-t0
        if dt>0:
            # Integrate only the existing command model's nominal velocity.
            # Prediction, its random draws, and particle propagation unchanged.
            vx,vy,w=np.asarray(pf.vel,float);theta=state['odom'][2]
            co,si=math.cos(theta),math.sin(theta)
            state['odom']+=np.array([co*vx-si*vy,si*vx+co*vy,w])*dt
        return out

    def update(t,obs,pose):
        scope=bool(pf.load.loaded and pose_supported(pose))
        if not scope:
            state['anchor']=None;state['observation']=None
            return previous(t,obs,pose)
        predict_to(t)
        anchor=state['anchor']
        delta=None if anchor is None else state['odom']-anchor
        moved=(delta is None or np.any(abs(delta[:2])>PARAMS['update_min_d_m'])
               or abs((delta[2]+math.pi)%(2*math.pi)-math.pi)>PARAMS['update_min_a_rad'])
        if not (pf.initialized and obs is not None and pf.settled(t) and moved
                and int(obs.informative.sum())>=int(pf.measurement['min_columns'])):
            return previous(t,None,pose)
        signature=(obs.b_kind.tobytes(),obs.b_lo.tobytes())
        if signature==state['observation']:
            return previous(t,None,pose)
        if visibility is not None:
            obs=visibility.apply(pf,obs,pose,t)
            if obs is None:return previous(t,None,pose)
        points=endpoints(pf.column_model_for(pose),obs)
        if not len(points):return previous(t,None,pose)
        state['anchor']=state['odom'].copy();state['observation']=signature
        audit['candidates']+=1
        w0=pf._weights();multiplier=likelihood(field,pf.px,points)
        posterior=w0*multiplier;posterior/=posterior.sum()
        kl=float(np.sum(posterior*np.log(np.maximum(posterior,1e-300)/np.maximum(w0,1e-300))))
        used=bool(kl>1e-12)
        pf.logw+=np.log(multiplier)
        # Nav2 default recovery alphas are zero. The legacy measurement's
        # unrelated pixel-fit recovery average is not mixed with this score.
        pf._inject=0.
        q=dict(t=float(t),informative=used,accepted=True,reason='soft_weight_update' if used else 'constant_likelihood',
               visual_weight_update=used,absolute_fix=False,model=OPTION,columns=len(points),kl=kl,
               multiplier_min=float(multiplier.min()),multiplier_max=float(multiplier.max()))
        if used:
            pf.last_scan_t=float(t);pf.v3_last_fix_quality=copy.deepcopy(q)
            pf.stats['scan_updates']+=1;pf.stats['scan_columns']+=len(points);audit['updates']+=1
            for key,gain in pf._gains(w0,posterior).items():
                if gain>=pf.robust['info_gain_min']:pf.last_info_t[key]=float(t)
        pf.diag=dict(soft_measurement=copy.deepcopy(q))
        pf.partial_fix_last=copy.deepcopy(q);audit['rows'].append(copy.deepcopy(q))
        pf._normalize_and_resample()
        est=pf.estimate();est['since_scan_s']=None if pf.last_scan_t is None else round(t-pf.last_scan_t,3)
        est['measured']=used
        return est

    pf.predict_to=predict_to;pf.update_obs=update
    return audit


class Runtime(Previous):
    def __init__(self,*args,measurement_model='off',visibility_mask='off',**kwargs):
        if measurement_model not in ('off',OPTION):raise ValueError('unknown S2 measurement model')
        if visibility_mask not in ('off','command_geometry_v1'):raise ValueError('unknown S2 visibility mask')
        if visibility_mask!='off' and measurement_model!=OPTION:raise ValueError('visibility candidate requires S2 likelihood field')
        super().__init__(*args,**kwargs)
        self.measurement_model=measurement_model
        self.visibility=None
        if visibility_mask!='off':
            from harness.zone_solo_cyan_visibility import Visibility
            self.visibility=Visibility()
            previous_frame=self.pose.provider.on_frame
            def frame(now,rgb):
                self.visibility.on_rgb(rgb)
                return previous_frame(now,rgb)
            self.pose.provider.on_frame=frame
        if measurement_model!='off':
            static=args[0] if args else kwargs['static']
            self.soft_measurement=install(self.pose.provider.loc._pf,static,visibility=self.visibility,
                                          pose_supported=self.visual_pose_supported)
            inner=self.pose.provider
            inner.runtime_contract['s2_measurement_model']=dict(option=OPTION,parameters=copy.deepcopy(PARAMS))
            if self.visibility is not None:inner.runtime_contract['s2_visibility']=copy.deepcopy(self.visibility.audit)
            from harness.zone_solo_cyan_v106 import hp
            inner.identity_sha256=hp.base.digest(inner.runtime_contract)
            inner.source='owncam_pf_s2_likelihood_field:'+inner.identity_sha256[:8]
            self.pose.source=inner.source

    def record(self):
        out=super().record()
        if self.measurement_model!='off':out['soft_measurement']=copy.deepcopy(self.soft_measurement)
        if self.visibility is not None:out['visibility_mask']=copy.deepcopy(self.visibility.audit)
        return out
