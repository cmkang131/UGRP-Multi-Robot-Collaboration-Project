"""Opt-in full-pose PBVS with measured >=100ms single-axis primitives."""
import copy,math
from types import SimpleNamespace,MethodType
import numpy as np
from harness.zone_final_pair_binding import bind
from harness.zone_final_pair_vision import GRASP_RADIUS_M,ALIGN_TOL_X_M,ALIGN_TOL_Y_M
from harness.owncam_pair_beam import ALIGN_TOL_RAD
from harness.zone_s3_pair_alignment import project as previous
from harness.zone_solo_cyan_pulse_cal import action_of
from harness.zone_solo_cyan_path_heading import command_reason

OPTION='measured_pose_mpc_v1'
HORIZON,BEAM=6,128


class Selector:
    def __init__(self,profiles):
        self.pool=[copy.deepcopy(profiles[k]) for k in sorted(profiles)
            if profiles[k].get('s3_trim_measured') and not profiles[k]['loaded']]
        if len(self.pool)!=18 or any(command_reason(action_of(p)) for p in self.pool):
            raise ValueError('18 qualified measured primitives required')
        self.delta=np.array([p['mean_delta'] for p in self.pool])
        self.scale=np.array([ALIGN_TOL_X_M,ALIGN_TOL_Y_M,ALIGN_TOL_RAD])

    def residual(self,errors,poses):
        ex,ey,ea=errors;dx=GRASP_RADIUS_M+ex-poses[:,0];dy=ey-poses[:,1]
        c,s=np.cos(poses[:,2]),np.sin(poses[:,2])
        return np.column_stack((c*dx+s*dy-GRASP_RADIUS_M,-s*dx+c*dy,
            np.arctan2(np.sin(ea-poses[:,2]),np.cos(ea-poses[:,2]))))

    def cost(self,errors):
        return np.sum(np.maximum(np.abs(errors)/self.scale-1.,0.)**2,axis=-1)

    def __call__(self,profiles,errors):
        if not all(math.isfinite(v) for v in errors): raise ValueError('finite own RGB fit required')
        distance=math.hypot(*errors[:2])
        if distance>.10: return previous(profiles,errors)
        before=float(self.cost(np.array(errors)));best=before;chosen=None;terminal=list(errors);depth=0
        q=np.zeros((1,3));first=np.array([-1]);count=len(self.pool)
        for n in range(1,HORIZON+1):
            c,s=np.cos(q[:,2,None]),np.sin(q[:,2,None]);d=self.delta
            candidate=np.stack((q[:,0,None]+c*d[:,0]-s*d[:,1],
                q[:,1,None]+s*d[:,0]+c*d[:,1],q[:,2,None]+np.broadcast_to(d[:,2],(len(q),count))),axis=-1).reshape(-1,3)
            fs=np.arange(count) if n==1 else np.repeat(first,count)
            # Equivalent predicted endpoints do not exhaust the bounded beam.
            _,unique=np.unique(np.round(candidate,9),axis=0,return_index=True)
            candidate=candidate[unique];fs=fs[unique]
            residual=self.residual(errors,candidate);cost=self.cost(residual)
            order=np.argsort(cost,kind='stable')[:BEAM]
            j=order[0]
            if cost[j]<best-1e-12:
                best=float(cost[j]);chosen=int(fs[j]);terminal=residual[j].tolist();depth=n
            q=candidate[order];first=fs[order]
            if best==0: break
        p=None if chosen is None else self.pool[chosen]
        action=dict(kind='mecanum',forward=0.,left=0.,turn=0.,duration_s=.1) if p is None else action_of(p)
        return action,p,dict(phase=OPTION,goal_distance_m=distance,before=before,after=best,
            horizon=HORIZON,beam=BEAM,selected_length=depth,terminal_errors=terminal,
            thresholds_changed=False,error_source='own RGB fit')


def attach_endpoint(ep,model=None,*,option='off'):
    if option=='off': return ep
    if option!=OPTION or not model or not model.get('qualified'):raise ValueError('qualified trim model required')
    own=ep.own.pose.localizer;profiles=own.pulse_profiles
    # The pulse predictor and port-admission wrappers retain this same instance
    # dictionary. Never replace the global filter/GO/loaded predictor wrappers.
    profiles.update(copy.deepcopy(model['profiles']))
    own.pulse_model['profiles'].update(copy.deepcopy(model['profiles']))
    own.pose.provider.loc._pf.pulse_calibration['profiles'].update(copy.deepcopy(model['profiles']))
    selector=Selector(profiles);ctl=ep.controller;old=ctl._align.__func__;ob=old.__globals__['ob']
    private=SimpleNamespace(**{**vars(ob),'align_command':bind(ob.align_command,project=selector)})
    ctl._align=MethodType(bind(old,ob=private),ctl)
    ctl.s3_measured_visual=dict(option=option,model=copy.deepcopy(model),gt_inputs=False)
    return ep
