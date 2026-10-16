"""V3 own-command sweep guard. Static geometry only, no simulator feedback."""
from harness import zone_own_guards as legacy
from harness.visual_arm_v3 import MOUNT_XYZ_M, CONTROLLER_GEOMETRY_ID


def body_spheres(servo, *, loaded):
    # V2 samples extend to 120 mm; the v3 tip is shorter (94 mm). Keep that
    # conservative envelope and translate its arm axis/shoulder, not each yaw.
    return legacy.body_spheres(servo, loaded=loaded, mount_xyz_m=MOUNT_XYZ_M)


class SweepGuardV3(legacy.SweepGuard):
    geometry_id = CONTROLLER_GEOMETRY_ID

    def __init__(self, static_map):
        super().__init__(static_map, mount_xyz_m=MOUNT_XYZ_M,
                         residual_m=max(legacy.BODY_COVERAGE_RESIDUAL_M, .015))

    def transition_clear(self, current, target, pose, *, loaded):
        # V3 has no validated blind bootstrap sweep. Hold until own pose exists.
        if pose is None:
            return False
        return super().transition_clear(current, target, pose, loaded=loaded)

    def plan(self, current, look_pose, pans, pose, *, loaded, allow_backoff=False):
        if pose is None:
            return {'pans': [], 'dropped': list(pans), 'backoff': None,
                    'reason': 'v3_requires_own_estimate', 'interval': None, 'transition_clear': False}
        return super().plan(current, look_pose, pans, pose, loaded=loaded, allow_backoff=allow_backoff)
