"""DEV planning window includes the own-observed route endpoints and carrier.

The sparse observation map is unchanged. Added cells remain unobserved; only
the existing explicit native allow-unknown planner interprets them as passable.
"""
import math
import numpy as np
from harness.e2e_route_coverage import NativeView
from harness.own_map_navigation import PAIR_FOOTPRINT

OPTION='goal_envelope_v1'
WORKFLOW='configs/simulation_workflows.d/e2e18_v225.json'


class GoalEnvelopeView(NativeView):
    def __init__(self,grid,first,last,margin=.02):
        super().__init__(grid)
        self.endpoints=np.asarray([first,last],float)
        if self.endpoints.shape!=(2,2) or not np.isfinite(self.endpoints).all():
            raise ValueError('OWN_ROUTE_ENDPOINTS_REQUIRED')
        self.pad=math.ceil((PAIR_FOOTPRINT.radius+margin)/grid.resolution+.71)+1
        self.bounds=None

    def dense(self):
        state,lo=self.grid.dense();hi=lo+np.asarray(state.shape[::-1])
        ends=np.asarray([self.grid.cell(p) for p in self.endpoints])
        newlo=np.minimum(lo,ends.min(0)-self.pad)
        newhi=np.maximum(hi,ends.max(0)+self.pad+1)
        shape=newhi-newlo
        if np.prod(shape)>1_000_000:raise ValueError('NAV_GRID_RESOURCE_LIMIT')
        expanded=np.zeros(tuple(shape[::-1]),np.int8)
        offset=lo-newlo
        expanded[offset[1]:offset[1]+state.shape[0],offset[0]:offset[0]+state.shape[1]]=state
        self.bounds=dict(old_lo=lo.tolist(),old_hi=hi.tolist(),new_lo=newlo.tolist(),new_hi=newhi.tolist(),
                         added_unknown_cells=int(expanded.size-state.size),endpoint_pad_cells=self.pad)
        expanded[expanded==0]=-1
        return expanded,newlo


def compose(bundle,option,records='off'):
    if option=='off' and records=='off':return ()
    if option!=OPTION or records!='python_v1' or bundle['execution_bundle_id']!='e2e18-v224' or not bundle['e2e_options'].get('dev_light'):
        raise ValueError('DEV_ROUTE_EXTENT_REQUIRES_V224')
    bundle['e2e_options']['route_extent']=option
    bundle['e2e_options']['record_scalars']=records
    bundle.update(schema='ugrp.e2e_ownmap_live.v225',execution_bundle_id='e2e18-v225',workflow_version='7.118.0')
    return (WORKFLOW,)
