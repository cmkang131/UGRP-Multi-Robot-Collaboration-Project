"""Preregistered constrained selection, and unchanged egomap34 gap criterion."""
import math


def select(candidates):
    valid=[c for c in candidates if c['metrics']['full']['precision_015'] is not None]
    if not valid:return dict(status='empty',operating_point=None)
    feasible=[c for c in valid if c['metrics']['full']['precision_015']>=.9]
    def rank(c):
        q=c['metrics']['full'];p,r=q['precision_015'],q['wall_coverage']
        return (-r,-p,q['wall_error_rmse_m'],c['min_views'],c['min_angle_deg']) if feasible else (-p,-r,q['wall_error_rmse_m'],c['min_views'],c['min_angle_deg'])
    best=min(feasible or valid,key=rank)
    return dict(status='precision_feasible' if feasible else 'no_precision_feasible_diagnostic_only',
        feasible_points=len(feasible),nonempty_points=len(valid),operating_point={k:best[k] for k in ('min_views','min_angle_deg')},
        development_metrics=best['metrics'])


def gate(q):
    return dict(precision=q['precision_015'] is not None and q['precision_015']>=.9,
        recall=q['wall_coverage']>=.7,wall_rmse=q['wall_error_rmse_m'] is not None and q['wall_error_rmse_m']<=.15)


def closer(before,after):
    def gaps(q):
        if q['precision_015'] is None or q['wall_error_rmse_m'] is None:return None
        return [max(0.,.9-q['precision_015']),max(0.,.7-q['wall_coverage']),max(0.,q['wall_error_rmse_m']-.15)]
    a,b=gaps(before),gaps(after)
    ok=b is not None and (all(gate(after).values()) or (a is not None and all(y<=x for x,y in zip(a,b)) and any(y<x for x,y in zip(a,b))))
    return dict(before_gaps=a,after_gaps=b,export_start=bool(ok))
