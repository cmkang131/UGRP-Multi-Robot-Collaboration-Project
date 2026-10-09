"""S2-only fixed finite-pulse motion model and stopped-feedback navigation.

No evaluation data or live state enters this module. The committed calibration
is exploratory; missing loaded fine strafes are declared transfers. Default off
delegates the entire existing stack without changing commands or records.
"""
import copy
import math
import numpy as np
from harness.zone_solo_cyan_inhand import Runtime as Previous
from harness import zone_solo_cyan_v106 as legacy

OPTION = 'v7_pulse_cal_v1'
AXES = ('forward','left','turn')


def profile_key(action, loaded):
    u = [float(action.get(k,0.)) for k in AXES]
    if sum(v!=0 for v in u)!=1:
        raise ValueError('calibrated motion requires one axis')
    axis = int(np.argmax(np.abs(u)))
    return f"{int(loaded)}:{AXES[axis]}:{u[axis]:.2f}:{float(action['duration_s']):.2f}"


def response(profile, t):
    curve=np.asarray(profile['mean_curve'])
    return np.array([np.interp(t,profile['times'],curve[:,i]) for i in range(3)])


def action_of(profile):
    out=dict(kind='mecanum',forward=0.,left=0.,turn=0.,duration_s=profile['duration_s'])
    out[profile['axis']]=profile['u']
    return out


def install(pf, model):
    """Instance-local PF replacement; own command queue and RGB update stay intact."""
    if model['option']!=OPTION:raise ValueError('wrong pulse model')
    profiles=copy.deepcopy(model['profiles'])
    for p in profiles.values():
        ts=np.asarray(p['times']);curve=np.asarray(p['mean_curve']);var=np.asarray(p['prediction_variance'])
        if (len(ts)<2 or ts[0]!=0 or np.any(np.diff(ts)<=0) or curve.shape!=(len(ts),3)
            or not np.isfinite(curve).all() or not np.isfinite(var).all() or np.any(var<0)):
            raise ValueError('invalid fixed pulse response')
        if 'prediction_covariance' in p:
            cov=np.asarray(p['prediction_covariance'])
            if (cov.shape!=(3,3) or not np.isfinite(cov).all() or not np.allclose(cov,cov.T)
                    or np.linalg.eigvalsh(cov).min() < -1e-12):
                raise ValueError('invalid measured pulse covariance')
    old_command=pf.command
    active=None

    def predict_to(t):
        nonlocal active
        while pf.t<t-1e-9:
            dt=min(.05,t-pf.t)
            if active is not None:
                started,p=active
                a=max(0.,pf.t-started);b=max(0.,pf.t+dt-started)
                va,vb=response(p,a),response(p,b)
                delta=vb-va
                # Response curve is expressed in the pulse's initial body
                # frame; convert each increment to the current body frame.
                c,s=math.cos(va[2]),math.sin(va[2])
                delta[:2]=np.array([[c,s],[-s,c]])@delta[:2]
                fraction=max(0.,min(b,p['times'][-1])-min(a,p['times'][-1]))/p['times'][-1]
                pf.vel=delta/dt
                if pf.initialized and fraction>0:
                    if 'prediction_covariance' in p:
                        # Explicit measured profile only; retain radial scale
                        # covariance instead of converting it to axis noise.
                        noise=pf.rng.multivariate_normal(np.zeros(3),np.asarray(p['prediction_covariance'])*fraction,size=pf.n)
                        noise[:,:2]=noise[:,:2]@np.array([[c,s],[-s,c]]).T
                        d=delta+noise
                    elif model.get('noise_model') == 'nav2_omni_v1':
                        from harness.zone_solo_cyan_load_height import omni_noise
                        noise=omni_noise(p,model['noise_alpha_1_to_5'][str(int(p['loaded']))],
                            pf.rng.normal(size=(pf.n,3)),fraction)
                        noise[:,:2]=noise[:,:2]@np.array([[c,s],[-s,c]]).T
                        d=delta+noise
                    else:
                        sd=np.sqrt(np.asarray(p['prediction_variance'])*fraction)
                        d=delta+pf.rng.normal(size=(pf.n,3))*sd
                    c,s=np.cos(pf.px[:,2]),np.sin(pf.px[:,2])
                    pf.px[:,0]+=c*d[:,0]-s*d[:,1]
                    pf.px[:,1]+=s*d[:,0]+c*d[:,1]
                    pf.px[:,2]=(pf.px[:,2]+d[:,2]+math.pi)%(2*math.pi)-math.pi
                    pf.logw+=pf._map_logprior(pf.px)
                if b>=p['times'][-1]-1e-9:active=None
            else:
                pf.vel=np.zeros(3)
            pf.t+=dt

    def command(row):
        nonlocal active
        old_command(row)  # predicts previous pulse first, then tracks own grip
        if row['kind'] in ('mecanum','drive') and any(row.get(k,0) for k in AXES):
            k=profile_key(row,pf.load.loaded)
            if k not in profiles:raise ValueError('uncalibrated pulse '+k)
            active=(float(row['t']),profiles[k])
        elif active is not None and float(row['t'])<active[0]+active[1]['duration_s']-1e-8:
            # Normal native expiry/hold preserves the calibrated stopping tail.
            # Unexpected early interruption stops prediction rather than invent
            # a completed pulse; normal controller never takes this path.
            active=None;pf.vel=np.zeros(3)

    pf.predict_to=predict_to
    pf.command=command
    pf.pulse_calibration=copy.deepcopy(model)
    return profiles


def select_pulse(profiles, loaded, error_xy, yaw, yaw_tolerance=.06):
    """One finite-pulse lookahead, coarse if it fits, otherwise measured trim.

    This implements the real stack's stop/remeasure coarse-to-fine rule using
    fixed response predictions. It is not a full DWA collision planner.
    """
    error=np.asarray(error_xy,float)
    def cost(xy,angle):
        return float(xy@xy)+(.6*max(0.,abs(angle)-yaw_tolerance))**2
    start_cost=cost(error,yaw);best=None;best_cost=start_cost
    for p in profiles.values():
        if p['loaded']!=loaded:continue
        # Keep the calibrated .10 straight/turn and .06/.65 lateral vocabulary.
        if (p['axis']!='left' and p['duration_s']!=.10):continue
        d=np.array(p['mean_delta'])
        # Never cross a target with a coarse strafe, even if a weighted score
        # prefers it. Small errors use the ~7 mm fine pulse.
        if p['axis']=='left' and abs(p['u'])==.65 and abs(error[1])<abs(d[1])+.035:
            continue
        value=cost(error-d[:2],yaw+d[2])
        if value<best_cost-1e-12:
            best,best_cost=p,value
    return best,dict(before=start_cost,after=best_cost,body_error_m=error.tolist(),yaw_rad=yaw)


class Runtime(Previous):
    def __init__(self,*args,pulse_motion_model='off',pulse_calibration=None,**kwargs):
        if pulse_motion_model not in ('off',OPTION):raise ValueError('unsupported pulse_motion_model')
        if pulse_motion_model!='off' and (pulse_calibration is None or kwargs.get('min_wheel_cmd')!='real_v1'):
            raise ValueError('pulse model requires explicit real output and fixed calibration')
        super().__init__(*args,**kwargs)
        self.pulse_option=pulse_motion_model
        if pulse_motion_model!='off':
            self.pulse_model=copy.deepcopy(pulse_calibration)
            self.pulse_profiles=install(self.pose.provider.loc._pf,pulse_calibration)
            self.cal_until=None;self.cal_settled_at=-float('inf');self.cal_rows=[]
            inner=self.pose.provider
            inner.runtime_contract['s2_pulse_motion_model']=self.pulse_model
            inner.identity_sha256=legacy.hp.base.digest(inner.runtime_contract)
            inner.source='owncam_pf_s2_pulse_cal:'+inner.identity_sha256[:8]
            self.pose.source=inner.source

    def estimated_at_checkpoint(self):
        if self.pulse_option=='off':return super().estimated_at_checkpoint()
        r=self.last_report
        yaw=(r.yaw_rad+math.pi)%(2*math.pi)-math.pi
        return math.dist((r.x_m,r.y_m),self.route[self.route_i])<=.03 and abs(yaw)<=.06

    def drive(self,xy,now,*,tolerance=.03):
        if self.pulse_option=='off':return super().drive(xy,now,tolerance=tolerance)
        from harness.map_goto import plan_path
        r=self.last_report
        if not r.initialized or not all(math.isfinite(v) for v in (r.x_m,r.y_m,r.yaw_rad)):
            return self.fail('POSE_NOT_INITIALIZED',now),False
        if r.std_xy_m>.05 or r.std_yaw_rad>math.radians(5) or r.last_fix_t is None:
            self.soft('POSE_UNCERTAIN',now)
        here=(r.x_m,r.y_m);yaw=(r.yaw_rad+math.pi)%(2*math.pi)-math.pi
        if math.dist(here,xy)<=tolerance and abs(yaw)<=.06:
            self.path,self.path_goal=[],None
            return [dict(kind='hold')],True
        if self.path_goal!=tuple(xy):
            plan=plan_path(self.map,here,xy,legacy.ENVELOPE,escape_start_m=.10)
            if plan is None:
                self.soft('PATH_COLLISION_GUARD',now);self.path=[list(xy)]
            else:
                self.path=plan['waypoints_m'][1:] or [list(xy)]
                self.event('path',now,plan=plan)
            self.path_goal=tuple(xy)
        while len(self.path)>1 and math.dist(here,self.path[0])<.035:self.path.pop(0)
        c,s=math.cos(yaw),math.sin(yaw)
        error=np.array([[c,s],[-s,c]])@(np.array(self.path[0])-here)
        loaded=self.pose.provider.loc._pf.load.loaded
        p,score=select_pulse(self.pulse_profiles,loaded,error,yaw)
        if p is None:
            self.soft('PULSE_RESOLUTION_LIMIT',now)
            return [dict(kind='hold')],False
        action=action_of(p)
        self.cal_rows.append(dict(t=now,state=self.state,waypoint=list(self.path[0]),
            issued=action,profile_key=profile_key(action,loaded),predicted_delta=p['mean_delta'],
            prediction_variance=p['prediction_variance'],transfer=p['transfer'],score=score))
        return [action],False

    def step(self,now):
        if self.pulse_option=='off' or self.terminal:return super().step(now)
        if self.cal_until is not None:
            if now<self.cal_until-1e-8:return []
            self.cal_until=None
            return [(self.robot_id,dict(kind='hold'))]
        if self.state not in ('carry','search_move'):return super().step(now)
        if self.real_pulse_until is not None or self.fine_until is not None:return super().step(now)
        # Released estimate is delayed by 160 ms. Wait for its own command
        # prediction time to cover the entire pulse+stop response, too.
        if now<self.cal_settled_at or self.last_report.t_est<self.cal_settled_at-1e-8:return []
        rows=legacy.Runtime.step(self,now)
        for _,action in rows:
            if action['kind']=='mecanum' and any(action[k] for k in AXES):
                p=self.pulse_profiles[profile_key(action,self.pose.provider.loc._pf.load.loaded)]
                self.cal_until=now+p['duration_s']
                self.cal_settled_at=now+p['times'][-1]
        return rows

    def record(self):
        out=super().record()
        if self.pulse_option!='off':
            out['pulse_motion_model']=dict(option=self.pulse_option,model=self.pulse_model,
                transformations=self.cal_rows,scope='S2 instance only; shared camera port and other controllers unchanged',
                previous_gain_used_for_navigation=False,previous_pf_predictor_used=False)
        return out
