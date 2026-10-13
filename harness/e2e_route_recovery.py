"""Opt-in observed C-space route recovery; unknown paths are exploration hints only.

All coordinates are robot-private. No simulator, static truth or peer input.
The pair keeps a fixed beam yaw: translations may turn, the carrier may not.
"""
from __future__ import annotations
import copy
import math
import numpy as np
from scipy.ndimage import binary_dilation, label
from harness.own_map_navigation import PAIR_FOOTPRINT, Footprint, footprint_clearance, astar
from harness.self_odom_grid import transform
from harness.active_wall_mapping import inverse

OPTION = 'frontier_v1'
VERSION = 381
PARAMETERS = dict(goal_tolerance_m=.125, nominal_margin_m=.02,
                  intermediate_sigma_fraction=.5, information_radius_m=1.,
                  focus_weight=2., max_focus_cells=256, hint_lifetime_s=15.,
                  carrier_dimensions_m=[1.25,.40], allow_unknown='hint_only',
                  start_snap=False, goal_snap='reachable_within_tolerance',
                  fixed_carrier_yaw=True)


class View:
    def __init__(self, state, lo, resolution):
        self.state_array, self.lo, self.resolution = state, lo, resolution
        self._clearance_bounds_v1 = True
    def dense(self):
        return self.state_array, self.lo


def expanded(grid, first, last, margin):
    state, lo = grid.dense()
    pad = math.ceil((PAIR_FOOTPRINT.radius+margin)/grid.resolution+.71)+1
    ends = np.asarray([grid.cell(first), grid.cell(last)])
    hi = lo+np.asarray(state.shape[::-1])
    newlo, newhi = np.minimum(lo, ends.min(0)-pad), np.maximum(hi, ends.max(0)+pad+1)
    shape = newhi-newlo
    if np.prod(shape) > 1_000_000:
        raise ValueError('NAV_GRID_RESOURCE_LIMIT')
    out = np.zeros(tuple(shape[::-1]), np.int8)
    offset = lo-newlo
    out[offset[1]:offset[1]+state.shape[0], offset[0]:offset[0]+state.shape[1]] = state
    return out, newlo


def valid(allowed, cell):
    x, y = cell
    return bool(0 <= y < allowed.shape[0] and 0 <= x < allowed.shape[1] and allowed[y,x])


def nearest_path(allowed, clearance, start, target, last, lo, resolution, tolerance):
    """Nearest reachable cell, not a jump across an obstacle at the start."""
    cells = astar(allowed, start, target, resolution, clearance)
    if cells:
        return cells, np.asarray(last, float)
    if not tolerance or not valid(allowed, start):
        return None, np.asarray(last, float)
    # Four-connected components agree with A*'s prohibition on corner cutting.
    components, _ = label(allowed)
    component = components[start[1],start[0]]
    ys, xs = np.nonzero(components == component)
    points = (np.column_stack((xs,ys))+lo+.5)*resolution
    distances = np.linalg.norm(points-last, axis=1)
    for i in np.argsort(distances, kind='stable'):
        if distances[i] > tolerance+1e-10:
            break
        end = (int(xs[i]), int(ys[i]))
        cells = astar(allowed, start, end, resolution, clearance)
        if cells:
            return cells, points[i]
    return None, np.asarray(last, float)


def search(grid, first, last, yaw, strict_margin, *, dev_light, tolerance=None):
    """Return observed route, diagnostics and a non-executable unknown-space hint."""
    if grid.robot_id != 'r1':
        raise ValueError('R1_PRIVATE_GRID_REQUIRED')
    if not np.isfinite([*first,*last,yaw,strict_margin]).all() or strict_margin < .02:
        raise ValueError('INVALID_OWN_ROUTE_GEOMETRY')
    tolerance = PARAMETERS['goal_tolerance_m'] if tolerance is None else tolerance
    if not 0 <= tolerance <= PARAMETERS['goal_tolerance_m']:
        raise ValueError('BOUNDED_GOAL_TOLERANCE_REQUIRED')
    # A huge uncertain pose must not turn morphology into an unbounded allocation.
    state, lo = expanded(grid, first, last, .02)
    start, target = np.asarray(grid.cell(first))-lo, np.asarray(grid.cell(last))-lo
    margins = [strict_margin]
    if dev_light:
        margins += [.02+(strict_margin-.02)*.5, .02]
    diag = dict(attempts=[], start_state=int(state[start[1],start[0]]),
                target_state=int(state[target[1],target[0]]),
                pair_dimensions_m=[1.25,.4], goal_requested_map_m=list(last),
                map_lo=lo.tolist(), map_shape=list(state.shape), frame_registration='unverified',
                would_stop_unknown=False, observed_coverage_complete=False)
    result = None
    for margin in dict.fromkeys(margins):
        _, allowed, clearance, _ = footprint_clearance(View(state,lo,grid.resolution), PAIR_FOOTPRINT, margin, yaw=yaw)
        cells, endpoint = nearest_path(allowed,clearance,start,target,last,lo,grid.resolution,tolerance)
        diag['attempts'].append(dict(margin_m=margin, start_clear=valid(allowed,start),
            target_clear=valid(allowed,target), allowed_cells=int(allowed.sum()), path_cells=len(cells or [])))
        result = allowed,clearance,lo,cells,endpoint
        if cells:
            diag.update(reason='OBSERVED_ROUTE', applied_margin_m=margin,
                would_stop_sigma=margin < strict_margin, observed_coverage_complete=True,
                goal_selected_map_m=endpoint.tolist(), goal_shift_m=float(np.linalg.norm(endpoint-last)))
            return result, diag, []
    diag['point_path_in_observed_free'] = bool(astar(state == -1,start,target,grid.resolution))
    diag['carrier_blocks_observed_point_path'] = bool(diag['point_path_in_observed_free'] and not result[3])
    # Diagnostic-only allow_unknown with exactly the same physical envelope.
    optimistic = state.copy(); optimistic[optimistic==0] = -1
    _, possible, clearance, _ = footprint_clearance(View(optimistic,lo,grid.resolution), PAIR_FOOTPRINT,.02,yaw=yaw)
    hint, _ = nearest_path(possible,clearance,start,target,last,lo,grid.resolution,tolerance)
    diag.update(allow_unknown_path_cells=len(hint or []), applied_margin_m=.02 if dev_light else strict_margin,
                would_stop_sigma=False)
    if state[start[1],start[0]] == 1:
        reason='START_OCCUPIED'
    elif not valid(possible,start):
        reason='START_CARRIER_COLLISION'
    elif not valid(possible,target):
        reason='GOAL_CARRIER_COLLISION'
    elif hint:
        reason='UNKNOWN_CORRIDOR' if dev_light else 'UNCERTAINTY_OR_UNKNOWN_CORRIDOR'
    else:
        # Point-robot connectivity distinguishes a narrow gap from a solid wall.
        point = astar(optimistic == -1,start,target,grid.resolution)
        reason='CARRIER_WIDTH_DISCONNECTED' if point else 'OCCUPIED_DISCONNECTED'
    diag['reason']=reason
    # Unknown cells in the swept carrier corridor, rather than all map frontiers.
    mask=np.zeros_like(state,dtype=bool)
    for x,y in hint or [tuple(start),tuple(target)]: mask[y,x]=True
    n=math.ceil((PAIR_FOOTPRINT.radius+.02)/grid.resolution+.71)
    yy,xx=np.mgrid[-n:n+1,-n:n+1]*grid.resolution
    c,s=math.cos(yaw),math.sin(yaw)
    kernel=(abs(c*xx+s*yy)<=.625+.02+grid.resolution*.71)&(abs(-s*xx+c*yy)<=.20+.02+grid.resolution*.71)
    ys,xs=np.nonzero(binary_dilation(mask,structure=kernel)&(state==0))
    focus=(np.column_stack((xs,ys))+lo+.5)*grid.resolution
    diag['blocking_unknown_cells']=len(focus)
    if len(focus)>PARAMETERS['max_focus_cells']:
        focus=focus[np.linspace(0,len(focus)-1,PARAMETERS['max_focus_cells'],dtype=int)]
    return result,diag,focus.tolist()


def install(goal, option='off'):
    if option == 'off': return
    if option != OPTION or goal.robot_id != 'r1': raise ValueError('INVALID_ROUTE_RECOVERY')
    goal.e2e_route_recovery = option
    goal.e2e_route_focus = None
    navigator=goal.explorer.navigator
    frontiers=navigator.core.frontiers
    def focused(*args,**kwargs):
        rows=frontiers(*args,**kwargs)
        hint=goal.e2e_route_focus
        if not hint: return rows
        # Store hints in own odom and transform on use: graph corrections move map frame.
        current_t=goal.e2e_observed[-1]['t_sim'] if goal.e2e_observed else math.inf
        if current_t-hint['t'] > PARAMETERS['hint_lifetime_s']: return rows
        focus=transform(hint['own_points'],goal.explorer.map_to_odom)
        pose=args[3] if len(args)>3 else kwargs['position']
        return rank_frontiers(rows,focus,pose,goal.explorer.grid)
    navigator.core.frontiers=focused


def rank_frontiers(rows, focus, pose, grid):
    """Information gain proxy with observed-wall occlusion; reachability stays native."""
    if not len(focus): return rows
    def score(row):
        gain=0
        for p in focus:
            distance=np.linalg.norm(p-row[:2])
            if distance>PARAMETERS['information_radius_m']: continue
            points=np.linspace(row[:2],p,max(2,math.ceil(distance/(grid.resolution/2))+1))
            if any(grid.state(grid.cell(q))==1 for q in points): continue
            gain+=1
        # Normalize by sampled focus count, then retain native cost as tie breaker.
        utility=gain/len(focus)/(1+np.linalg.norm(np.asarray(row[:2])-pose))
        return float(row[6])-PARAMETERS['focus_weight']*utility
    return sorted(rows,key=score)


def compose(bundle,option='off'):
    if option=='off':return ()
    if option!=OPTION or bundle['execution_bundle_id']!='e2e18-v375':
        raise ValueError('ROUTE_RECOVERY_REQUIRES_V375')
    bundle['route_recovery_parent']='e2e18-v375'
    bundle['route_recovery_parameters']=copy.deepcopy(PARAMETERS)
    bundle['e2e_options']['route_recovery']=option
    bundle.update(execution_bundle_id='e2e18-v381',schema='ugrp.e2e_ownmap_live.v381',workflow_version='7.274.0')
    return ('harness/e2e_route_recovery.py','configs/simulation_workflows.d/e2e18_v381.json')


def parent_for_validation(bundle):
    old=copy.deepcopy(bundle)
    if (old.get('route_recovery_parent')!='e2e18-v375' or old['execution_bundle_id']!='e2e18-v381'
            or old.get('route_recovery_parameters')!=PARAMETERS or old['e2e_options'].get('route_recovery')!=OPTION):
        raise ValueError('REGISTERED_ROUTE_RECOVERY_REQUIRED')
    old['execution_bundle_id']=old.pop('route_recovery_parent')
    old.pop('route_recovery_parameters');old['e2e_options'].pop('route_recovery')
    return old
