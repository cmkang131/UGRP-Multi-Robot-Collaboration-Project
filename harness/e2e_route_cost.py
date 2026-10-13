"""Default-off binary morphology backend with an exact finite-grid bound."""
import cv2
import numpy as np
OPTION='bounded_morphology_v1'


def blocked(state,kernel):
    # The symmetric centered footprint must fit wholly inside the finite grid.
    # Outside is occupied, so if its nonzero extent is larger, every cell blocks.
    ys,xs=np.nonzero(kernel)
    if xs.max()-xs.min()+1>state.shape[1] or ys.max()-ys.min()+1>state.shape[0]:
        return np.ones(state.shape,dtype=bool)
    return cv2.dilate(np.asarray(state!=-1,np.uint8),np.asarray(kernel,np.uint8),
        iterations=1,borderType=cv2.BORDER_CONSTANT,borderValue=1)!=0


def configure(goal,option='off'):
    if option=='off':return
    if option!=OPTION:raise ValueError('UNKNOWN_ROUTE_COST')
    goal.e2e_route_cost=option
    goal.explorer.grid._clearance_bounds_v1=True


def compose(bundle,option):
    if option=='off':return
    if option!=OPTION or bundle['execution_bundle_id']!='e2e18-v228':raise ValueError('ROUTE_COST_REQUIRES_V228')
    bundle['e2e_options']['route_cost']=option
