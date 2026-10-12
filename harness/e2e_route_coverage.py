"""Default-off DEV unknown-space planner view, following NavFn allow_unknown.

Never mutates observations or manufactures floor provenance. Occupied cells and
finite grid limits remain blocked. A native-only route is not map completion.
"""
import math
import numpy as np
from harness.own_map_navigation import PAIR_FOOTPRINT

OPTION='native_v1'
WORKFLOW='configs/simulation_workflows.d/e2e18_v223.json'


class NativeView:
    def __init__(self,grid):self.grid=grid;self.resolution=grid.resolution
    @property
    def _clearance_bounds_v1(self):return getattr(self.grid,'_clearance_bounds_v1',False)
    def cell(self,p):return self.grid.cell(p)
    def dense(self):
        state,lo=self.grid.dense();view=state.copy();view[view==0]=-1
        return view,lo


def counts(grid,point,yaw,margin):
    state,lo=grid.dense();r=grid.resolution
    n=math.ceil((PAIR_FOOTPRINT.radius+margin)/r+.71)
    ys,xs=np.mgrid[-n:n+1,-n:n+1];c,s=math.cos(yaw),math.sin(yaw)
    mask=(abs(c*xs*r+s*ys*r)<=PAIR_FOOTPRINT.half_length_m+margin+r*.71)&(abs(-s*xs*r+c*ys*r)<=PAIR_FOOTPRINT.half_width_m+margin+r*.71)
    center=np.asarray(grid.cell(point))-lo;x=xs[mask]+center[0];y=ys[mask]+center[1]
    inside=(x>=0)&(y>=0)&(x<state.shape[1])&(y<state.shape[0]);v=state[y[inside],x[inside]]
    return dict(free=int((v==-1).sum()),unknown=int((v==0).sum()),occupied=int((v==1).sum()),outside=int((~inside).sum()))


def fully_observed(packet):return bool(packet and packet.get('observed_coverage_complete',True))


def map_completed(events):
    return any(e['event']=='own_map_B_route_generated' and e.get('observed_coverage_complete',True) for e in events)


def compose(bundle,option):
    if option=='off':return ()
    if option!=OPTION or bundle['execution_bundle_id']!='e2e18-v222' or not bundle['e2e_options']['dev_light']:
        raise ValueError('DEV_ROUTE_COVERAGE_REQUIRES_V222')
    bundle['e2e_options']['route_coverage']=option
    bundle.update(schema='ugrp.e2e_ownmap_live.v223',execution_bundle_id='e2e18-v223',workflow_version='7.116.0')
    return (WORKFLOW,)
