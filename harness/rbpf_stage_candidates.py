"""Independent egomap60 candidates. Off performs no mutation or RNG draws.

Sources and frozen DEV limits: experiments/2026-10-10-own-route-particle-stages.
Only own hypotheses/maps/current wall points enter this module.
"""
import copy
from functools import partial
from types import MethodType
import numpy as np
from harness.self_map_rbpf import RBPFOptions, improved_proposal

POPULATION='particles_500_v1'
LOCAL='cartographer_window_v1'
GATE='observed_sample_v1'


def local_reference(past, points, prior):
    # Enclose all points rotated within +/-20 degrees, translated +/-0.1m,
    # plus 1m EDT margin. Camera range stays unchanged. No future/GT cells.
    from harness.self_odom_grid import transform
    if not len(points):return past[:0]
    angles=prior[2]+np.linspace(-np.deg2rad(20),np.deg2rad(20),41)
    envelope=np.concatenate([transform(points, [*prior[:2], a]) for a in angles])
    lo,hi=envelope.min(0)-1.1,envelope.max(0)+1.1
    return past[np.all((past>=lo)&(past<=hi),axis=1)]


def install(grid, *, rbpf_population='off', rbpf_local_search='off', rbpf_candidate_gate='off'):
    options=dict(rbpf_population=rbpf_population,rbpf_local_search=rbpf_local_search,
                 rbpf_candidate_gate=rbpf_candidate_gate)
    if all(v=='off' for v in options.values()):return grid
    for name,allowed in [('rbpf_population',POPULATION),('rbpf_local_search',LOCAL),('rbpf_candidate_gate',GATE)]:
        if options[name] not in ('off',allowed):raise ValueError('UNKNOWN_STAGE_CANDIDATE')
    if not hasattr(grid,'_selective_proposal') or hasattr(grid,'_stage_candidates'):
        raise ValueError('STAGE_CANDIDATE_REQUIRES_WIDE_SELECTIVE_ONCE')
    if rbpf_population==POPULATION:
        if len(grid.poses)!=100:raise ValueError('POPULATION_REQUIRES_100_PARENT_PARTICLES')
        ids=np.repeat(np.arange(100),5)
        grid.maps=[copy.copy(grid.maps[i]) for i in ids]
        for m in grid.maps:m.cells=m.cells.copy()
        grid.histories=[grid.histories[i].copy() for i in ids]
        grid.poses=grid.poses[ids].copy();grid.pending_cov=grid.pending_cov[ids].copy()
        grid.weights=grid.weights[ids]/5;grid.log_weights=grid.log_weights[ids]-np.log(5)
        grid.best*=5;grid.rbpf_options=RBPFOptions(particles=500,seed=grid.rbpf_options.seed)
        if getattr(grid,'_manhattan_axes',None) is not None:
            grid._manhattan_axes=grid._manhattan_axes[ids].copy()
    if rbpf_local_search==LOCAL:grid._local_reference=local_reference
    grid._selective_proposal=partial(improved_proposal,yaw_window_deg=20.,
        translation_window_m=.1 if rbpf_local_search==LOCAL else .5,observed_sample=rbpf_candidate_gate==GATE)
    grid._stage_candidates=options
    grid._stage_export=grid.export
    grid.export=MethodType(_export,grid)
    return grid


def _export(self):
    return {**self._stage_export(), 'stage_candidates':self._stage_candidates,
            'particle_population':len(self.poses)}
