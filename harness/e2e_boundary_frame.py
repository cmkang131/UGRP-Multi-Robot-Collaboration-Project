"""Whole-outline view hypotheses from own RGB center and fixed board dimensions.

No authored position, obstacle map or initial world pose enters this planner.
Framing a circumscribed disk covers all board orientations, but is only a view
hypothesis: the existing fresh RGB boundary gate still decides confirmation.
"""
from functools import lru_cache
import math
import cv2
import numpy as np

OPTION='observed_own_v1'
HALF_SIZE=(.4,.7)


@lru_cache(maxsize=8)
def framing(radius):
    from harness.e2e_b_standoff import project_floor,usable,W,H,CFG
    # Extra half-degree chord margin encloses the disk despite finite sampling.
    angles=np.arange(360)*2*math.pi/360
    extent=math.hypot(*HALF_SIZE)/math.cos(math.pi/360)
    outline=extent*np.column_stack((np.cos(angles),np.sin(angles)))
    uv,ok=project_floor(outline,[-radius,0.,0.])
    if not ok.all():return False
    ij=np.rint(uv).astype(int)
    if not ((ij[:,0]>=0)&(ij[:,0]<W)&(ij[:,1]>=0)&(ij[:,1]<H)).all():return False
    _,body,dist=usable()
    if float(dist[ij[:,1],ij[:,0]].min())<CFG['margin_px']:return False
    region=np.zeros((H,W),np.uint8);cv2.fillPoly(region,[ij.reshape(-1,1,2)],1)
    return not bool(np.any(body & (cv2.dilate(region,np.ones((5,5),np.uint8))!=0)))


def poses(center,pose):
    from harness.e2e_boundary_views import RADII_M,N_ANGLES
    center,pose=np.asarray(center,float),np.asarray(pose,float)
    if center.shape!=(2,) or pose.shape!=(3,) or not np.isfinite(np.r_[center,pose]).all():
        raise ValueError('FINITE_OWN_VIEW_INPUTS_REQUIRED')
    # Rotate the finite ring with the observer; arbitrary private-frame rotation
    # cannot change which relative view is considered first.
    base=pose[2]
    return [[*(center+r*np.array([math.cos(a),math.sin(a)])),a+math.pi]
            for r in RADII_M if framing(r)
            for a in base+np.arange(N_ANGLES)*2*math.pi/N_ANGLES]


def compose(bundle,option):
    if option=='off':return
    if option!=OPTION or bundle['execution_bundle_id']!='e2e18-v233':
        raise ValueError('OWN_BOUNDARY_FRAME_REQUIRES_V233')
    bundle['e2e_options']['boundary_frame']=option
    bundle['boundary_view_source']='own_rgb_center_known_dimensions_fixed_camera'
