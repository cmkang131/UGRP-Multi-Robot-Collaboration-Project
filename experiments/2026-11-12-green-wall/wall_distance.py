"""Design-scale wall-foot distances and observed motion direction, not wheel odometry."""
import math
import numpy as np
from green_wall_mapper import camera_geometry


def design_scale():
    origin,_=camera_geometry()
    if not np.isfinite(origin).all() or origin[2]<=0:raise ValueError('invalid design camera height')
    return dict(camera_height_cm=float(origin[2]*100),camera_origin_design_m=origin.tolist(),
                source='own arm PWM + PR405 frozen mechanical chain',
                independently_measured=False)


def distance_from_contact(points,camera_xy,height_cm):
    """Perpendicular floor-plane gap from camera nadir to observed wall foot.

    Contacts are in initial-camera ground coordinates, measured in initial
    camera-height units. Neither wheel speed nor motor duration enters here.
    A robust line describes this visible green-wall foot, NOT proof of a
    vertical wall plane. Line scatter is not an accuracy confidence interval.
    """
    p=np.asarray(points,float).reshape(-1,2)-np.asarray(camera_xy,float)
    p=p[np.isfinite(p).all(1)]
    if len(p)<12:raise ValueError('few_visible_contact_samples')
    # Least-median two-point hypotheses tolerate isolated bad contact columns.
    # MAD estimates line scatter;2.45 multiplies scatter, not a calibrated CI.
    rng=np.random.default_rng(405);best=None;score=float('inf')
    for _ in range(128):
        a,b=p[rng.choice(len(p),2,replace=False)];v=b-a;length=np.linalg.norm(v)
        if length<1e-8:continue
        normal=np.array([-v[1],v[0]])/length
        residual=abs((p-a)@normal);candidate=float(np.median(residual))
        if candidate<score:score=candidate;best=residual
    if best is None:raise ValueError('degenerate_contact')
    mad=float(np.median(abs(best-np.median(best))))
    keep=best<=max(1e-8,float(np.median(best))+2.45*1.4826*mad)
    if keep.sum()<12:raise ValueError('few_consistent_contacts')
    p=p[keep];centre=p.mean(0);_,_,vt=np.linalg.svd(p-centre,full_matrices=False)
    normal=vt[-1];d=float(normal@centre)
    if d<0:normal=-normal;d=-d
    along=p@vt[0];rms=float(np.sqrt(np.mean(((p-centre)@normal)**2)))
    if np.ptp(along)<.10:raise ValueError('contact_not_spread')
    return dict(wall_gap_cm=d*height_cm,line_rms_cm=rms*height_cm,
                nearest_wall_cm=(normal*d*height_cm).tolist(),
                wall_normal=normal.tolist(),contact_points_cm=(p*height_cm).tolist(),
                scale='design-based cm estimate',metric_accuracy_verified=False)


def infer_wall_actions(before,after,action='left'):
    """Require observed normal translation, not a direction name or head yaw.

    45deg defines mostly wall-normal vs tangential motion; the .2cm DEV floor
    and 3x observed line scatter require a resolvable change, not a claimed CI.
    """
    delta=after['wall_gap_cm']-before['wall_gap_cm']
    threshold=max(.2,3*max(before['line_rms_cm'],after['line_rms_cm']))
    shift=np.linalg.norm(np.array(after['camera_xy_cm'])-before['camera_xy_cm'])
    if abs(delta)<=threshold or shift<=threshold:raise ValueError('wall_distance_change_unresolved')
    if abs(delta)/shift<math.cos(math.radians(45)):raise ValueError('motion_mostly_tangential')
    opposite={'left':'right','right':'left','forward':'backward','backward':'forward'}[action]
    return dict(away=action if delta>0 else opposite,toward=opposite if delta>0 else action,
                observed_gap_change_cm=float(delta),normal_fraction=float(abs(delta)/shift))
