"""Goal tolerance over a filled oriented footprint; default off, no world input.

NavFn nearest reachable tolerance goal and Nav2 oriented-footprint checking,
adapted to a fixed-yaw carrier. Filled cell intersections are stricter than
Nav2's perimeter raster alone. Swept connectors are checked continuously.
"""
import copy
import math
import numpy as np
from scipy.ndimage import binary_dilation,distance_transform_edt,label
from harness.own_map_navigation import astar,PAIR_FOOTPRINT

OPTION='footprint_v2'
PARAMETERS=dict(goal_tolerance_m=.125,tolerance_region='navfn_square',
    footprint='filled_oriented_rectangle',carrier_dimensions_m=[1.25,.4],
    nominal_margin_m=.02,cell_intersection='four_axis_SAT',connector='continuous_swept_SAT',
    shifted_goal_requires_observed_B=True,cargo_half_extents_m=[.30,.02])


def clearance(view,footprint,margin,yaw=None):
    if yaw is None:raise ValueError('FIXED_CARRIER_YAW_REQUIRED')
    state,lo=view.dense();r=view.resolution
    c,s=math.cos(yaw),math.sin(yaw);a,b=footprint.half_length_m+margin,footprint.half_width_m+margin
    nx,ny=math.ceil((abs(c)*a+abs(s)*b+r/2)/r),math.ceil((abs(s)*a+abs(c)*b+r/2)/r)
    if 2*nx+1>state.shape[1] or 2*ny+1>state.shape[0]:
        return state,np.zeros_like(state,bool),distance_transform_edt(state==-1)*r,lo
    yy,xx=np.mgrid[-ny:ny+1,-nx:nx+1]*r
    h=r/2;projection=h*(abs(c)+abs(s))
    kernel=((abs(c*xx+s*yy)<=a+projection+1e-10)&(abs(-s*xx+c*yy)<=b+projection+1e-10)
            &(abs(xx)<=abs(c)*a+abs(s)*b+h+1e-10)&(abs(yy)<=abs(s)*a+abs(c)*b+h+1e-10))
    blocked=binary_dilation(state!=-1,structure=kernel,border_value=1)
    return state,~blocked,distance_transform_edt(state==-1)*r,lo


def sweep_checker(state,lo,resolution,yaw,margin):
    c,s=math.cos(yaw),math.sin(yaw);u=np.array([c,s]);v=np.array([-s,c])
    corners=np.array([i*(.625+margin)*u+j*(.2+margin)*v for i,j in [(-1,-1),(1,-1),(1,1),(-1,1)]])
    yy,xx=np.nonzero(state!=-1);centers=(np.column_stack((xx,yy))+lo+.5)*resolution
    low=lo*resolution;high=(lo+np.array(state.shape[::-1]))*resolution
    def clear(a,b):
        cloud=np.vstack((corners+a,corners+b));minimum=cloud.min(0);maximum=cloud.max(0)
        if np.any(minimum<low) or np.any(maximum>high):return False
        selected=centers[np.all((centers+resolution/2>=minimum)&(centers-resolution/2<=maximum),axis=1)]
        if not len(selected):return True
        delta=np.asarray(b)-a;normal=np.array([-delta[1],delta[0]])
        axes=np.vstack((np.eye(2),u,v,normal if np.linalg.norm(normal)>1e-12 else u))
        overlap=np.ones(len(selected),bool)
        for axis in axes:
            extent=resolution/2*np.abs(axis).sum();projection=cloud@axis;q=selected@axis
            overlap&=(q+extent>=projection.min()-1e-10)&(q-extent<=projection.max()+1e-10)
        return not overlap.any()
    return clear


def goal_filter(boundary,yaw):
    """Only cargo must fit in B; the 1.25m pair need not fit the .8m goal region."""
    import cv2
    if not boundary or not boundary.get('complete') or 'polygon' not in boundary:return lambda point:False
    poly=np.asarray(boundary['polygon'],np.float32)
    if poly.shape!=(4,2) or not np.isfinite(poly).all() or not cv2.isContourConvex(poly):return lambda point:False
    c,s=math.cos(yaw),math.sin(yaw);rot=np.array([[c,-s],[s,c]])
    corners=np.array([[-.30,-.02],[.30,-.02],[.30,.02],[-.30,.02]])@rot.T
    return lambda point:all(cv2.pointPolygonTest(poly,tuple(map(float,p)),False)>=0 for p in corners+point)


def nearest(allowed,clearance,start,target,last,lo,resolution,tolerance,*,accept,exact_accept=lambda p:True):
    from harness.e2e_route_recovery import valid
    if not valid(allowed,start):return None,np.asarray(last)
    components,_=label(allowed);component=components[start[1],start[0]]
    if valid(allowed,target) and components[target[1],target[0]]==component and exact_accept(last):
        cells=astar(allowed,start,target,resolution,clearance)
        if cells:return cells,np.asarray(last)
    yy,xx=np.nonzero(components==component)
    points=(np.column_stack((xx,yy))+lo+.5)*resolution
    offsets=points-last
    # NavFn visits the tolerance square and minimizes squared Euclidean distance.
    within=np.all(abs(offsets)<=tolerance+1e-10,axis=1)
    candidates=np.flatnonzero(within)
    for i in sorted(candidates,key=lambda j:(float(offsets[j]@offsets[j]),int(yy[j]),int(xx[j]))):
        if not accept(points[i]):continue
        cells=astar(allowed,start,(int(xx[i]),int(yy[i])),resolution,clearance)
        if cells:return cells,points[i]
    return None,np.asarray(last)


def search(grid,first,last,yaw,margin,*,dev_light,tolerance,boundary):
    from harness.e2e_route_recovery import search as base
    accept=goal_filter(boundary,yaw)
    checker=None
    def calculate(view,footprint,margin,yaw=None):
        nonlocal checker
        state,lo=view.dense()
        checker=sweep_checker(state,lo,view.resolution,yaw,margin)
        return clearance(view,footprint,margin,yaw=yaw)
    def choose(*args):
        return nearest(*args,accept=lambda p:accept(p) and checker(p,p),exact_accept=lambda p:checker(p,p))
    result,diag,focus=base(grid,first,last,yaw,margin,dev_light=dev_light,tolerance=tolerance,
        clearance_fn=calculate,nearest_fn=choose)
    diag.update(footprint_method=PARAMETERS['footprint'],cell_intersection='four_axis_SAT',
                goal_tolerance_region='navfn_square',B_boundary_map=boundary,
                nominal_footprint_area_m2=(1.25+.04)*(.4+.04),sweep_validated=False)
    return result,diag,focus


def compose(bundle):
    if bundle['execution_bundle_id']!='e2e18-v375':raise ValueError('FOOTPRINT_REQUIRES_V375')
    bundle['footprint_parent']='e2e18-v375';bundle['footprint_parameters']=copy.deepcopy(PARAMETERS)
    bundle['e2e_options']['route_recovery']=OPTION
    bundle.update(execution_bundle_id='e2e18-v389',schema='ugrp.e2e_ownmap_live.v389',workflow_version='7.282.0')
    return ('harness/e2e_route_footprint.py','harness/e2e_route_recovery.py','configs/simulation_workflows.d/e2e18_v389.json')


def parent_for_validation(bundle):
    b=copy.deepcopy(bundle)
    if b.get('footprint_parent')!='e2e18-v375' or b.get('footprint_parameters')!=PARAMETERS or b['e2e_options'].get('route_recovery')!=OPTION:
        raise ValueError('REGISTERED_FOOTPRINT_REQUIRED')
    b['execution_bundle_id']=b.pop('footprint_parent');b.pop('footprint_parameters');b['e2e_options'].pop('route_recovery');return b
