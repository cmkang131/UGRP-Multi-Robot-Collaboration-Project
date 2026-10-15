"""Timestamped map measurement -> execution pose, with one odom replay."""
import numpy as np
from harness.natural_floor_slam import compose, _motion_covariance
from harness.selfmap4_geometry import inverse


def deliver(pose, covariance, *, map_from_execution, exposure_t, release_t,
            odom_at_exposure, odom_at_release, replay_covariance):
    if release_t < exposure_t:
        raise ValueError('measurement released before exposure')
    motion=compose(inverse(odom_at_exposure),odom_at_release)
    a=map_from_execution[2];c,s=np.cos(a),np.sin(a)
    R=np.array([[c,s,0],[-s,c,0],[0,0,1]])
    local=compose(inverse(map_from_execution),pose)
    P=R@np.asarray(covariance)@R.T
    return (compose(local,motion),_motion_covariance(local,motion,P,replay_covariance)),dict(
        exposure_sim_t=exposure_t,release_sim_t=release_t,
        measurement_frame='authored_map',execution_frame='robot/natural_floor_origin',
        odometry_frame='own_issued_commands',map_from_execution=np.asarray(map_from_execution).tolist(),
        replay_delta=motion.tolist(),replay_count=1 if release_t>exposure_t else 0)
