"""Default-off axis fusion / consistency gate on the existing scalar channel.

No world/evaluation/partner pose or RGB. CI eq.10, Noack et al. Automatica
2017 https://isas.iar.kit.edu/pdf/Automatica17_Noack.pdf. Equal CI mixing
weights give inverse-MSE mean weights; do not assume independent sensors.
Empirical MSEs are calibration estimates, not proven covariance bounds.
"""
from __future__ import annotations
import math
from sim import release23

FUSION='axis_fusion_v1'
REOBSERVE='axis_disagree_reobserve_v1'
OPTIONS=dict(axis_fusion=FUSION,axis_disagree_reobserve=REOBSERVE)
# release24-baseline-rejections.json, release21 80 runs / 194 same-round
# pairs only. E[e^2] includes bias: r1=.78026767, r2=.70794465 deg^2.
MSE_RAD2=tuple(v*(math.pi/180)**2 for v in (.7802676717621957,.7079446501165835))
# Higher empirical p95 |r1-r2|, same 194 pairs. DEV excluded from fitting.
# This is a consistency trigger, not a relaxed physical acceptance angle.
DISAGREE_RAD=math.radians(2.3145519571195257)
AXIS_LIMIT_RAD=math.radians(10)  # unchanged legacy target; provenance unresolved


def wrap(a):return (a+math.pi/2)%math.pi-math.pi/2


def validate(options):
    for key,mode in OPTIONS.items():
        if options.get(key,'off') not in ('off',mode):raise ValueError('unknown '+key)
    if options.get('axis_disagree_reobserve','off')!='off' and options.get('axis_fusion')!=FUSION:
        raise ValueError('axis consistency requires fusion')
    if options.get('axis_fusion','off')!= 'off':
        if options.get('release_plan_budget')!=release23.COMPUTE or options.get('margin_common_mode')!=release23.MARGIN:
            raise ValueError('release24 requires compute budget and same-round margins')


def pair_choice(reports,robots,now,*,axis_fusion='off',axis_disagree_reobserve='off',**kwargs):
    if axis_fusion=='off':return release23.pair_choice(reports,robots,now,**kwargs)
    rows=[reports[r] or {} for r in robots]
    values=[r.get('axis_error_rad') for r in rows]
    epochs=[r.get('observation_epoch') for r in rows];times=[r.get('observed_at') for r in rows]
    def reject(reason,obj,gap=None,unit='rad',**extra):
        return dict(action='observe',reason=reason,t=now,**release23.rejection(reason,obj,gap,unit),**extra)
    if (len(rows)!=2 or any(r.get('kind')!='localized_margin' for r in rows)
            or any(v is None or not math.isfinite(v) for v in values)):
        return reject('axis_pair_unobserved','delivered own-RGB axis reports')
    if None in epochs or len(set(epochs))!=1 or None in times or len(set(times))!=1 or times[0]>now:
        return reject('axis_epoch_mismatch','same-round scalar reports')
    delta=wrap(values[1]-values[0]);precision=[1/p for p in MSE_RAD2]
    weights=[p/sum(precision) for p in precision]
    fused=wrap(values[0]+weights[1]*delta)
    meta=dict(raw_axis_errors_rad=values,fused_axis_error_rad=fused,axis_weights=weights,
        axis_disagreement_rad=abs(delta),axis_ci_variance_rad2=2/sum(precision),
        axis_observation_epoch=epochs[0],axis_fusion=axis_fusion)
    if axis_disagree_reobserve==REOBSERVE and abs(delta)>DISAGREE_RAD:
        return reject('axis_disagreement_reobserve','rigid beam scalar consistency',DISAGREE_RAD-abs(delta),**meta)
    if abs(fused)>AXIS_LIMIT_RAD:
        return dict(action='axis_correct',reason='release_axis_unaligned',t=now,
            axis_errors_rad=[fused,fused],**meta)
    # Both endpoint margins retain each robot's OWN geometry and angle.
    # Defer only the axis decision to the common rigid-body estimate; keep
    # lateral, slack, 4cm lower bound, all map/FOV/cap checks unchanged.
    kwargs['axis_recovery']=False
    return dict(release23.pair_choice(reports,robots,now,**kwargs),**meta)
