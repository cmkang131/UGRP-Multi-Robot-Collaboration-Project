"""Default-off S2 own-ground-RGB velocity EKF and finite progress recovery.

Seegmiller IROS 2011 II-C--F; robot_localization ekf.cpp/ekf.yaml (ros2);
Nav2 SimpleProgressChecker and DriveOnHeading. See preregistered s2v24.
Only own RGB, issued commands and immutable geometry enter this adapter.
"""
import copy
import math
import numpy as np
from harness.zone_solo_cyan_progress_noise import Runtime as Previous, pair, ground, rigid
from harness.zone_solo_cyan_pulse_cal import install as install_pulses, profile_key, response, action_of
from harness.zone_solo_cyan_amcl_update import install as install_amcl

VO='ground_flow_ekf_v1'
RECOVERY='nav2_progress_v1'
PARAMS=dict(frame_max_gap_s=.06,minimum_expected_m=.05,
    velocity_process_diagonal=[.025,.025,.02],pitch_common_bound_deg=2.8,
    pitch_independent_bound_deg=.9,pitch_bound_distribution='uniform +/- bound; sigma=bound/sqrt(3)',
    pitch_difference_step_rad=.0001,min_information_rank=3,minimum_pulse_coverage=.8,
    progress_radius_m=.035,progress_allowance_s=1.5,consecutive_low_progress=2,
    escape_distance_m=.10,escape_max_pulses=20,escape_timeout_s=10.,confidence_sigma=2.)


def rot(angle):
    c,s=np.cos(angle),np.sin(angle)
    return np.array([[c,-s],[s,c]])


def compose(a,b):
    return np.r_[a[:2]+rot(a[2])@b[:2],a[2]+b[2]]


def pitch_camera(cm,angle):
    out=copy.copy(cm);c,s=np.cos(angle),np.sin(angle)
    out._rot=cm._rot@np.array([[1,0,0],[0,c,-s],[0,s,c]])
    return out


def pitch_uncertainty(measurement,cm):
    """Nuisance camera rotation propagated without reading actual camera pose."""
    p,q=np.array(measurement['before_uv']),np.array(measurement['after_uv'])
    def fit(a,b):
        r,d=rigid(ground(pitch_camera(cm,a),p)[0],ground(pitch_camera(cm,b),q)[0])
        return np.r_[d,math.atan2(r[1,0],r[0,0])]
    eps=PARAMS['pitch_difference_step_rad']
    jb=(fit(eps,0)-fit(-eps,0))/(2*eps)
    ja=(fit(0,eps)-fit(0,-eps))/(2*eps)
    jc=(fit(eps,eps)-fit(-eps,-eps))/(2*eps)
    sc=np.radians(PARAMS['pitch_common_bound_deg'])/np.sqrt(3)
    si=np.radians(PARAMS['pitch_independent_bound_deg'])/np.sqrt(3)
    cov=np.array(measurement['covariance'])+np.outer(jc,jc)*sc**2+(np.outer(jb,jb)+np.outer(ja,ja))*si**2
    return {**measurement,'covariance':cov.tolist(),
        'pitch_jacobian_common':jc.tolist(),'pitch_jacobian_before':jb.tolist(),'pitch_jacobian_after':ja.tolist(),
        'pitch_common_sigma_delta':(jc*sc).tolist(),
        'pitch_scale_at_bounds':{str(deg):(fit(np.radians(deg),np.radians(deg))-measurement['delta']).tolist()
                               for deg in (-2.8,-.9,.9,2.8)}}


class VelocityEKF:
    """Differential velocity subset; same correction/Joseph formula as ROS EKF.

    Commands are a fallback predictor, never an independent measurement. A gap
    resets the differential chain; initial measured state copies z and R.
    """
    def __init__(self):self.x=None;self.p=None
    def update(self,delta,cov,dt):
        z=np.asarray(delta)/dt;r=np.asarray(cov)/dt**2
        if self.x is None:
            self.x=z.copy();self.p=r.copy();gain=np.eye(3)
        else:
            prior=self.p+np.diag(PARAMS['velocity_process_diagonal'])*dt
            gain=np.linalg.solve((prior+r).T,prior.T).T
            self.x+=gain@(z-self.x)
            a=np.eye(3)-gain
            self.p=a@prior@a.T+gain@r@gain.T
            self.p=(self.p+self.p.T)/2
        return self.x*dt,self.p*dt**2,gain


def pulse_observation(item,frames,table):
    """Completed pulse response; missing intervals retain the fixed command model."""
    p=item['profile'];cm=item['cm'];start=item['t'];horizon=p['times'][-1]
    curve=[np.zeros(3)];times=[0.];rows=[];covered=0.;ekf=VelocityEKF()
    # Sum marginal standard deviations before squaring: conservative with
    # shared images/pitch, not falsely independent frame averages.
    sigma_sum=np.zeros(3);common_sum=np.zeros(3);fallback_var=np.zeros(3)
    before_t,before_rgb=item['before'];last_t=start
    for now,rgb in frames:
        dt=now-last_t
        if dt<=1e-9:continue
        a,b=max(0.,last_t-start),min(horizon,now-start)
        if b<=a:continue
        obs=dict(status='unknown_frame_gap')
        if (rgb is not None and before_rgb is not None and 0<now-before_t<=PARAMS['frame_max_gap_s']+1e-8
                and abs(before_t-last_t)<1e-7):
            obs=pair(before_rgb,rgb,cm,item['pose'],table,metric_observation=True)
            if obs['status']=='measured':obs=pitch_uncertainty(obs,cm)
        if obs['status']=='measured':
            d,cov,gain=ekf.update(obs['delta'],obs['covariance'],dt)
            tr=np.eye(3);tr[:2,:2]=rot(curve[-1][2])
            sigma_sum+=np.sqrt(np.maximum(0,np.diag(tr@cov@tr.T)))
            common_sum+=tr@gain@np.array(obs['pitch_common_sigma_delta'])
            covered+=b-a
        else:
            ekf=VelocityEKF()
            va,vb=response(p,a),response(p,b)
            d=vb-va;d[:2]=rot(-va[2])@d[:2]
            fallback_var+=np.array(p['prediction_variance'])*(b-a)/horizon
        curve.append(compose(curve[-1],d));times.append(b)
        rows.append(dict(t=now,dt=dt,estimate_delta=d.tolist(),**obs))
        last_t=now;before_t,before_rgb=now,rgb
    # A missing final frame does not fabricate zero movement.
    if times[-1]<horizon-1e-8:
        va,vb=response(p,times[-1]),response(p,horizon);d=vb-va;d[:2]=rot(-va[2])@d[:2]
        fallback_var+=np.array(p['prediction_variance'])*(horizon-times[-1])/horizon
        times.append(horizon);curve.append(compose(curve[-1],d))
    variance=sigma_sum**2+common_sum**2+fallback_var
    # Common term also resides in per-frame R: adding it again is deliberately
    # conservative; never claim statistically calibrated independent samples.
    out=copy.deepcopy(p);out.update(times=times,mean_curve=np.array(curve).tolist(),
        mean_delta=curve[-1].tolist(),prediction_variance=variance.tolist())
    return out,dict(t=start,key=item['key'],end=start+horizon,coverage=covered/horizon,
        status='measured' if covered>=horizon-1e-8 else 'partial_or_unknown',
        expected_delta=p['mean_delta'],delta=out['mean_delta'],variance=variance.tolist(),
        common_pitch_sigma_sum=common_sum.tolist(),intervals=rows,
        direction=[float(item['command'].get(k,0)) for k in ('forward','left')])


class PulseBuffer:
    """Bounded delayed measurement, original input order retained exactly once.

    While collecting <=.75 s the provider reports the pulse-start timestamp.
    No future capture or backdated externally visible estimate is published.
    """
    def __init__(self,inner,profiles,supported,table):
        self.inner=inner;self.profiles=profiles;self.supported=supported;self.table=table
        self.command0,self.frame0,self.report0=inner.on_command,inner.on_frame,inner.report
        self.pending=None;self.last=None;self.measure_small=False
        self.audit=dict(option=VO,parameters=copy.deepcopy(PARAMS),rows=[],gt_inputs=False,
            command_double_counted=False,wall_frames_dropped=0,buffered_frames=0,
            scope='S2 loaded coarse translations only; fine/turn/unloaded retain fixed pulse model',
            covariance='Joseph EKF full R; conservative correlated pulse marginal covariance')
        inner.on_command=self.command;inner.on_frame=self.frame;inner.report=self.report
    def flush(self,completed=True):
        item=self.pending
        if item is None:return
        self.pending=None
        key=item['key'];old=self.profiles[key]
        if completed:
            profile,row=pulse_observation(item,item['frames'],self.table)
            row['prediction_replaced']=item['replace']
            if item['replace']:self.profiles[key]=profile
            self.audit['rows'].append(row)
        else:self.audit['rows'].append(dict(t=item['t'],key=key,status='interrupted',coverage=0.))
        try:
            for kind,args in item['events']:
                if kind=='command':self.command0(*args)
                else:self.frame0(*args)
        finally:self.profiles[key]=old
    def command(self,row):
        moving=row['kind'] in ('mecanum','drive') and any(row.get(k,0) for k in ('forward','left','turn'))
        if self.pending is not None:
            if moving or row['kind'] in ('arm','look','initial_servo_command'):
                self.flush(False)
            else:
                self.pending['events'].append(('command',(copy.deepcopy(row),)));return
        pf=self.inner.loc._pf
        if moving and pf.load.loaded and self.supported(self.inner.servo):
            key=profile_key(row,True);p=self.profiles[key]
            replace=np.linalg.norm(p['mean_delta'][:2])>=PARAMS['minimum_expected_m']
            if (p['axis'] in ('forward','left') and (replace or self.measure_small)
                    and self.last is not None and abs(row['t']-self.last[0])<1e-7):
                self.pending=dict(t=float(row['t']),key=key,profile=copy.deepcopy(p),command=copy.deepcopy(row),
                    pose=dict(self.inner.servo),cm=pf.column_model_for(self.inner.servo),before=self.last,replace=replace,
                    frames=[],events=[('command',(copy.deepcopy(row),))])
                return
        return self.command0(row)
    def frame(self,now,rgb):
        if self.pending is not None:
            self.pending['frames'].append((float(now),None if rgb is None else rgb.copy()))
            self.pending['events'].append(('frame',(float(now),None if rgb is None else rgb.copy())))
            self.audit['buffered_frames']+=1
            end=self.pending['t']+self.pending['profile']['times'][-1]
            if now>=end-1e-8:self.flush(now-end<=PARAMS['frame_max_gap_s']+1e-8)
        else:self.frame0(now,rgb)
        self.last=(float(now),None if rgb is None else rgb.copy())
        return self.report(now)
    def report(self,now):
        return self.report0(min(now,self.pending['t']) if self.pending is not None else now)


class ProgressRecovery:
    """Own-VO progress timeout and directional inhibition; no map truth input."""
    def __init__(self):
        self.rows=[];self.low=[];self.blocked=None;self.escape_start=None;self.attempts=0;self.finished=False
        self.escape_progress=0.;self.escape_since=None
    def observe(self,row):
        if row.get('coverage',0)<PARAMS['minimum_pulse_coverage']:
            self.low=[];return
        if self.blocked is not None:
            self.escape_progress+=max(0.,float(np.dot(-self.blocked,row['delta'][:2])))
            if self.escape_progress>=PARAMS['escape_distance_m']:self.finished=True
            return
        direction=np.array(row['direction'],float);direction/=np.linalg.norm(direction)
        upper=float(np.linalg.norm(row['delta'][:2])+PARAMS['confidence_sigma']*np.sqrt(sum(row['variance'][:2])))
        if upper>=PARAMS['progress_radius_m']:
            self.low=[];return
        if self.low and (np.dot(direction,self.low[-1][1])<.95 or
                        row['t']-self.low[-1][0]>PARAMS['progress_allowance_s']):self.low=[]
        self.low.append((row['t'],direction))
        if (self.blocked is None and len(self.low)>=PARAMS['consecutive_low_progress'] and
                row['end']-self.low[0][0]>=PARAMS['progress_allowance_s']):
            self.blocked=direction.copy();self.escape_since=row['end']
            self.rows.append(dict(t=row['end'],event='inhibit_direction',direction=direction.tolist(),upper_m=upper))
    def forbidden(self,action):
        d=np.array([action.get('forward',0),action.get('left',0)])
        return bool(self.blocked is not None and np.linalg.norm(d)>0 and np.dot(d/np.linalg.norm(d),self.blocked)>.95)
    def override(self,action,now,xy,yaw,profiles,static,envelope):
        from harness.map_goto import plan_path
        if self.blocked is None:return action
        if self.escape_start is None:self.escape_start=np.array(xy)
        # Fine escape flow measures progress, but leaves baseline fine-pulse
        # prediction unchanged. Missing flow never releases inhibition.
        if self.escape_since is None:self.escape_since=now
        if self.attempts>=PARAMS['escape_max_pulses'] or now-self.escape_since>PARAMS['escape_timeout_s']:
            self.finished=True
        if not self.finished:
            target=np.array(xy)-rot(yaw)@self.blocked*PARAMS['escape_distance_m']
            path=plan_path(static,xy,target,envelope,escape_start_m=.10)
            if path is None:
                self.finished=True;self.rows.append(dict(t=now,event='escape_map_guard'))
            else:
                axis='forward' if abs(self.blocked[0])>.5 else 'left'
                choices=[p for p in profiles.values() if p['loaded'] and p['axis']==axis and
                    p['u']*self.blocked[0 if axis=='forward' else 1]<0 and abs(p['u'])==.35]
                if choices:
                    chosen=min(choices,key=lambda p:p['duration_s']);self.attempts+=1
                    self.rows.append(dict(t=now,event='bounded_inverse_pulse',attempt=self.attempts))
                    return action_of(chosen)
                self.finished=True
        if self.forbidden(action):
            self.rows.append(dict(t=now,event='blocked_command_suppressed'))
            return dict(kind='hold')
        return action


class Runtime(Previous):
    def __init__(self,*args,visual_odometry='off',stall_recovery='off',**kwargs):
        if visual_odometry not in ('off',VO) or stall_recovery not in ('off',RECOVERY):raise ValueError('unknown flow/recovery option')
        if stall_recovery!='off' and visual_odometry!=VO:raise ValueError('recovery requires measured RGB odometry')
        if visual_odometry!='off':
            if kwargs.get('pulse_motion_model')!='v7_pulse_cal_v1' or kwargs.get('amcl_update')!='ros_motion_v1':
                raise ValueError('flow requires S2 pulse model and motion-triggered AMCL')
            if kwargs.get('visual_progress','off')!='off' or kwargs.get('load_motion','off')!='off':
                raise ValueError('do not stack rejected motion/noise candidates')
            from harness.zone_solo_cyan_floor_contact import validate
            validate(kwargs.get('floor_appearance') or {})
        self.visual_odometry,self.stall_recovery=visual_odometry,stall_recovery
        super().__init__(*args,**kwargs)
        if visual_odometry!='off':
            inner=self.pose.provider;pf=inner.loc._pf
            live=install_pulses(pf,self.pulse_model)
            self.amcl_audit=install_amcl(pf,self.map,preset=self.amcl_update,
                visibility=self.visibility,pose_supported=self.visual_pose_supported)
            self.flow=PulseBuffer(inner,live,self.visual_pose_supported,copy.deepcopy(kwargs['floor_appearance']))
            self.recovery=ProgressRecovery();self.flow_cursor=0;self.recovery_replanned=False
            from harness.zone_solo_cyan_v106 import hp
            inner.runtime_contract['s2_flow_fusion']=dict(visual_odometry=visual_odometry,
                stall_recovery=stall_recovery,parameters=copy.deepcopy(PARAMS),gt_inputs=False)
            inner.identity_sha256=hp.base.digest(inner.runtime_contract)
            inner.source='owncam_pf_s2_flow_fusion:'+inner.identity_sha256[:8];self.pose.source=inner.source
    def drive(self,xy,now,*,tolerance=.03):
        if self.stall_recovery=='off':return super().drive(xy,now,tolerance=tolerance)
        from harness.map_goto import plan_path,rect
        from harness.zone_solo_cyan_v106 import ENVELOPE
        for row in self.flow.audit['rows'][self.flow_cursor:]:self.recovery.observe(row)
        self.flow_cursor=len(self.flow.audit['rows']);r=self.last_report
        self.flow.measure_small=self.recovery.blocked is not None and not self.recovery.finished
        if self.recovery.blocked is not None and not self.recovery_replanned:
            # Direction learned in body coordinates, mapped using own estimate.
            d=rot(r.yaw_rad)@self.recovery.blocked
            failed=np.array([r.x_m,r.y_m])+d*.10
            keep=rect('own_vo_failed_target',failed,[.04,.04],'inferred_failed_direction')
            plan=plan_path(self.map,(r.x_m,r.y_m),xy,ENVELOPE,point_keepouts=[keep],escape_start_m=.10)
            self.path=[] if plan is None else plan['waypoints_m'][1:]
            self.path_goal=None if plan is None else tuple(xy)
            self.recovery.rows.append(dict(t=now,event='replan',path_found=plan is not None,keepout=keep))
            self.recovery_replanned=True
        actions,done=super().drive(xy,now,tolerance=tolerance)
        if done:return actions,done
        out=[self.recovery.override(a,now,(r.x_m,r.y_m),r.yaw_rad,self.pulse_profiles,self.map,ENVELOPE) for a in actions]
        if self.recovery.finished and not getattr(self,'recovery_finished_replanned',False):
            self.recovery_replanned=False;self.path_goal=None
            self.recovery_finished_replanned=True
        return out,False
    def record(self):
        out=super().record()
        if self.visual_odometry!='off':out['visual_odometry']=copy.deepcopy(self.flow.audit)
        if self.stall_recovery!='off':out['stall_recovery']=dict(option=RECOVERY,rows=copy.deepcopy(self.recovery.rows),gt_inputs=False)
        return out
