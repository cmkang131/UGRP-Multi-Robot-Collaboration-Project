"""Default-off fixed forward calibration and PR2005 likelihood attenuation.

No GT/runtime fitting. Only calibration constants and own-command arm/load
history select a profile. Original v133 files remain frozen.
"""
import copy
import hashlib
import json
import math
from pathlib import Path
from types import FunctionType
import numpy as np
from harness.zone_final_pair_binding import bind

SCALE = 'forward_scale_v1'
TEMPER = 'pr_likelihood_half_v1'
ALPHA = .5
BASE = Path(__file__).resolve().parents[1]/'configs/s2_motion_v7_pulse_cal_v1.json'


def group(servo, key):
    return ','.join(str(servo.get(k)) for k in (3,4,5,6))+'|'+key


def scaled(profile, gain):
    p=copy.deepcopy(profile)
    curve=np.array(p['mean_curve']);curve[:,0]*=gain
    p['mean_curve']=curve.tolist();p['mean_delta'][0]*=gain
    return p


def closure(function):
    return dict(zip(function.__code__.co_freevars,(c.cell_contents for c in function.__closure__ or ())))


def replace_cell(function, name, value):
    names=function.__code__.co_freevars
    if name not in names:raise ValueError('unsupported runtime closure')
    cell=(lambda:value).__closure__[0]
    cells=tuple(cell if k==name else c for k,c in zip(names,function.__closure__))
    out=FunctionType(function.__code__,function.__globals__,function.__name__,function.__defaults__,cells)
    out.__kwdefaults__=function.__kwdefaults__
    return out


def moments(px,w):
    """Overall covariance reported by Nav2 best-cluster adapter, pre delay."""
    center=w@px[:,:2];delta=px[:,:2]-center
    yaw=math.atan2(w@np.sin(px[:,2]),w@np.cos(px[:,2]))
    cov=np.zeros((3,3));cov[:2,:2]=(delta*w[:,None]).T@delta
    cov[2,2]=max(0.,-2*math.log(max(math.hypot(w@np.sin(px[:,2]),w@np.cos(px[:,2])),1e-300)))
    return dict(mean=[*center.tolist(),yaw],cov=cov.tolist(),ess=float(1/(w@w)),
        xy_trace=float(np.trace(cov[:2,:2])),unique_poses=len(np.unique(px[:,:3],axis=0)))


def instrument(runtime, alpha=1.):
    """Read-only audit at alpha1; no RNG draws, no extra PF estimate calls.

    Save prior after prediction, posterior before resampling, resampled moments.
    ESS=N after resampling does not establish recovered diversity.
    """
    pf=runtime.pose.provider.loc._pf;wrapper=pf.update_obs
    cells=closure(wrapper);update=cells.get('selected')
    if update is None or update.__module__!='harness.zone_solo_cyan_amcl_update':
        raise ValueError('requires frozen v133 landmark AMCL stack')
    original=update.__globals__['likelihood'];resample=update.__globals__['resample']
    from harness.zone_solo_cyan_landmarks import landmark_likelihood,wall_likelihood
    mapped=closure(original)['mapped'];audit=[]
    def likelihood(field,px,packet):
        score=original(field,px,packet)
        value=score if alpha==1. else np.power(score,alpha)
        w=pf._weights();ll=np.log(value);post=w*np.exp(ll-ll.max());post/=post.sum()
        wall=np.log(wall_likelihood(field,px,packet.wall));land=np.log(landmark_likelihood(mapped,px,packet.features))
        corr=float(np.corrcoef(wall,land)[0,1]) if np.std(wall)>1e-12 and np.std(land)>1e-12 else None
        audit.append(dict(t=float(pf.t),alpha=alpha,prior=moments(px,w),posterior=moments(px,post),
            wall_count=len(packet.wall),features=len(packet.features),log_score_correlation=corr))
        return value
    def resample_audit(p):
        resample(p)
        audit[-1]['resampled']=moments(p.px,p._weights())
    selected=bind(update,likelihood=likelihood,resample=resample_audit)
    pf.update_obs=replace_cell(wrapper,'selected',selected)
    runtime.measurement_consistency_audit=audit
    return audit


def attach(runtime, *, forward_scale='off', likelihood_tempering='off', calibration=None,
           servo_stiffness='off', audit=False):
    if forward_scale=='off' and likelihood_tempering=='off' and not audit:return runtime
    if forward_scale not in ('off',SCALE) or likelihood_tempering not in ('off',TEMPER):
        raise ValueError('unknown bias/tempering option')
    inner=runtime.pose.provider;pf=inner.loc._pf
    receipt=dict(forward_scale=forward_scale,likelihood_tempering=likelihood_tempering,
                 alpha=ALPHA if likelihood_tempering!= 'off' else 1.,gt_inputs=False,rows=[])
    if forward_scale!= 'off':
        table=copy.deepcopy(calibration or {})
        if (servo_stiffness!='real_v1' or table.get('base_sha256')!=hashlib.sha256(BASE.read_bytes()).hexdigest()
            or len(table.get('fit_seeds',[]))!=2 or table.get('holdout') in table['fit_seeds']):
            raise ValueError('fixed two-run stiff calibration required')
        replacements={}
        for g,v in table['groups'].items():
            key=g.split('|')[1];p=runtime.flow.profiles[key];gain=v['gain']
            if p['axis']!='forward' or p['u']<=0 or not np.isfinite(gain) or gain<=0:
                raise ValueError('positive forward calibration only')
            replacements[g]=scaled(p,gain)
        live=runtime.flow.profiles;old_command,old_drive=pf.command,runtime.drive
        def selection(key):return replacements.get(group(inner.servo,key))
        def command(row):
            from harness.zone_solo_cyan_pulse_cal import profile_key
            moving=row['kind'] in ('drive','mecanum') and any(row.get(k,0) for k in ('forward','left','turn'))
            key=profile_key(row,pf.load.loaded) if moving else None;p=selection(key) if key else None
            old=live.get(key)
            if p is not None:
                live[key]=p;receipt['rows'].append(dict(t=row['t'],group=group(inner.servo,key),gain=table['groups'][group(inner.servo,key)]['gain']))
            try:return old_command(row)
            finally:
                if p is not None:live[key]=old
        def drive(*args,**kwargs):
            saved={}
            for key in runtime.pulse_profiles:
                p=selection(key)
                if p is not None:saved[key]=runtime.pulse_profiles[key];runtime.pulse_profiles[key]=p
            try:return old_drive(*args,**kwargs)
            finally:runtime.pulse_profiles.update(saved)
        pf.command,runtime.drive=command,drive
        receipt['calibration']=table
    if audit or likelihood_tempering!='off':instrument(runtime,receipt['alpha'])
    runtime.bias_tempering_audit=receipt
    if forward_scale!='off' or likelihood_tempering!='off':
        previous=runtime.record
        runtime.record=lambda:{**previous(),'bias_tempering':copy.deepcopy(receipt)}
        from harness.zone_solo_cyan_v106 import hp
        inner.runtime_contract['s2_bias_tempering']={k:v for k,v in receipt.items() if k!='rows'}
        inner.identity_sha256=hp.base.digest(inner.runtime_contract)
        inner.source='owncam_pf_s2_bias_tempering:'+inner.identity_sha256[:8];runtime.pose.source=inner.source
    return runtime
