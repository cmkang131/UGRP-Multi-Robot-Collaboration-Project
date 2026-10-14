"""Own-camera contact-plane range check; fixed calibration and issued servo only."""
import numpy as np
from harness.self_odom_grid import transform
from harness.active_wall_mapping import inverse


def foot_point(servo,bbox):
    import cv2
    from harness.visual_arm import camera_extrinsics
    from sim.masterpi_camera_profile import CAMERA_FISHEYE_D,scaled_camera_matrix
    x0,y0,x1,y1=bbox
    if x0<=1 or x1>=639 or y1>=479:return None # feet clipped: range unknown
    uv=np.array([[[(x0+x1)/2,y1]]],dtype=float)
    xy=cv2.fisheye.undistortPoints(uv,scaled_camera_matrix(640,480),np.asarray(CAMERA_FISHEYE_D)).reshape(2)
    origin,axes=camera_extrinsics(servo);origin=np.asarray(origin);axes=np.asarray(axes)
    ray=xy[0]*axes[0]+xy[1]*axes[1]+axes[2]
    if not np.isfinite(ray).all() or ray[2]>=-1e-5:return None
    point=origin-ray*(origin[2]/ray[2])
    return point[:2] if np.isfinite(point).all() else None


def occupied(candidates,pose,servo,regions):
    # Unlike a projected 3D volume overlapping a 2D robot box, contact-plane
    # inversion distinguishes another robot further along the same image ray.
    found={c['id']:[] for c in candidates}
    for region in regions:
        foot=foot_point(servo,region['bbox_px'])
        if foot is None:continue
        for c in candidates:
            local=transform([c['station_own_m'][:2]],inverse(pose))[0]
            distance=float(np.linalg.norm(foot-local))
            if distance<=.25:
                found[c['id']].append(dict(region,foot_base_m=foot.tolist(),stance_distance_m=distance,
                    method='fisheye_ray_floor_intersection',range_scope='visible compound region bottom; unknown if clipped'))
    return found
