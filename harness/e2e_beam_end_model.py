"""Resolve a grip band's inward direction from the observed long beam side.

PCA gives an undirected axis. A visible far band must not be interpreted as
the near end merely because the near band is outside the current image.
"""
import math
import numpy as np
from harness import owncam_pair_beam as v1

OPTION='long_side_v1'
WORKFLOW='configs/simulation_workflows.d/e2e18_v234.json'


def inward_sign(along):
    values=np.asarray(along,float);values=values[np.isfinite(values)]
    if len(values)<25:return None,dict(points=len(values))
    lo,hi=np.quantile(values,[.02,.98])
    before=int(np.sum(values<-.12));after=int(np.sum(values>.12))
    # End band is 30 mm inside the 600 mm beam. The long side must have
    # appreciable observed support; a short colored end cap is insufficient.
    neg=before>=25 and lo<=-.12 and hi<=.10
    pos=after>=25 and hi>=.12 and lo>=-.10
    return (-1 if neg else 1 if pos else None),dict(points=len(values),q02_m=float(lo),q98_m=float(hi),long_before=before,long_after=after)


def refine(observation,image,servo,rays,option='off'):
    if option=='off':return observation
    if option!=OPTION:raise ValueError('UNKNOWN_BEAM_END_MODEL')
    if not observation.get('visible') or not observation.get('end_visible'):return observation
    frame=v1.decode(image);origin,directions,xs,ys,valid=rays(servo,v1.RAY_STEP)
    down=directions[:,2]<-1e-6
    scale=np.where(down,(v1.BEAM_TOP_Z_M-origin[2])/np.where(down,directions[:,2],-1.),np.nan)
    points=origin[:2]+scale[:,None]*directions[:,:2]
    heading=observation['axis_heading_rad'];u=np.array([math.cos(heading),math.sin(heading)])
    n=np.array([-u[1],u[0]]);grip=np.asarray(observation['grip_base_m'])
    along=(points-grip)@u;across=(points-grip)@n
    mask=down&valid&v1.lime_mask(frame)[ys.astype(int),xs.astype(int)]&(abs(across)<=.03)
    sign,diag=inward_sign(along[mask])
    out=dict(observation,endpoint_model=OPTION,endpoint_side_evidence=diag)
    if sign is None:return dict(out,end_visible=False,reason='BAND_INWARD_SIDE_UNRESOLVED')
    # A fallback geometric edge is not a measured band at the far end.
    if sign<0 and observation.get('grip_source')!='band_centre':
        return dict(out,end_visible=False,reason='FAR_EDGE_WITHOUT_MEASURED_BAND')
    angle=heading+(math.pi if sign<0 else 0.)
    angle=math.atan2(math.sin(angle),math.cos(angle))
    end=grip-v1.GRIP_INSET_M*sign*u
    return dict(out,axis_heading_rad=angle,near_end_base_m=end.tolist(),
                observed_band_side='far' if sign<0 else 'near',
                provenance=out.get('provenance','')+'+observed_long_side_inward')


def compose(bundle,option,avoidance):
    if option=='off' and avoidance=='off':return ()
    if option!=OPTION or avoidance!='own_obstacle_v1' or bundle['execution_bundle_id']!='e2e18-v233':
        raise ValueError('BEAM_END_MODEL_REQUIRES_V233')
    bundle['e2e_options'].update(beam_end_model=option,beam_avoidance=avoidance)
    bundle.update(schema='ugrp.e2e_ownmap_live.v234',execution_bundle_id='e2e18-v234',workflow_version='7.127.0')
    return (WORKFLOW,)
