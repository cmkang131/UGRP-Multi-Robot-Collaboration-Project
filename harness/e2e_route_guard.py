"""Default-off DEV nominal-envelope retry with explicit strict-path diagnostics.

Reuses observed-grid footprint dilation/A*: unknown/occupied cells stay blocked.
Only the stochastic pose margin may be bypassed in an explicitly DEV bundle.
"""
import math
import numpy as np
from harness.own_map_navigation import PAIR_FOOTPRINT,footprint_clearance,astar

OPTION='dev_nominal_v1'
WORKFLOW='configs/simulation_workflows.d/e2e18_v221.json'


def search(goal,grid,tf,beam,first,last,strict_margin,strict_result=None):
    if not goal.dev_light:raise ValueError('DEV_ROUTE_GUARD_REQUIRED')
    attempts=[];result=None
    for index,margin in enumerate((strict_margin,.02)):
        if index==0 and strict_result is not None:
            allowed,clearance,lo,cells=strict_result
        else:
            _,allowed,clearance,lo=footprint_clearance(grid,PAIR_FOOTPRINT,margin,yaw=float(tf[2])+beam['pose_own_m'][2])
        start=np.asarray(grid.cell(first))-lo;end=np.asarray(grid.cell(last))-lo
        def clear(cell):
            x,y=cell;return bool(0<=y<allowed.shape[0] and 0<=x<allowed.shape[1] and allowed[y,x])
        if index or strict_result is None:cells=astar(allowed,start,end,grid.resolution,clearance)
        attempts.append(dict(margin_m=margin,allowed_cells=int(allowed.sum()),total_cells=int(allowed.size),start_clear=clear(start),target_clear=clear(end),path_cells=len(cells) if cells else 0))
        result=allowed,clearance,lo,cells
        if cells:break
    bypass=len(attempts)==2 and bool(result[-1])
    goal.e2e_route_diagnostics.update(attempts=attempts,would_stop_sigma=bypass,applied_margin_m=attempts[-1]['margin_m'],pair_dimensions_m=[1.25,.40])
    if bypass:goal.event(goal.e2e_route_diagnostics['t'],'would_stop_route_sigma',strict_margin_m=strict_margin,applied_margin_m=.02)
    return result


def compose(bundle,option):
    if option=='off':return ()
    if option!=OPTION or bundle['execution_bundle_id']!='e2e18-v220' or not bundle['e2e_options']['dev_light']:
        raise ValueError('ROUTE_GUARD_REQUIRES_DEV_V220')
    bundle['e2e_options']['route_guard']=option
    bundle.update(schema='ugrp.e2e_ownmap_live.v221',execution_bundle_id='e2e18-v221',workflow_version='7.114.0')
    return (WORKFLOW,)
