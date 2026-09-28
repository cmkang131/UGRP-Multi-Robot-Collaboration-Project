"""V3 command-space FK/IK and camera pose, reusing the frozen SDK math.

Only owned PWM and camera-derived targets enter this module. The v3 physical
pad centre (86.85 mm) is the IK target, not the SDK's 100 mm virtual tool tip.
No simulator state, measured joint state, contact or tag observation is read.
"""
from __future__ import annotations

import math
from dataclasses import replace

from harness import visual_arm as sdk
from sim.masterpi_geometry_v3 import PHYSICAL_V3

CONTROLLER_GEOMETRY_ID = 'masterpi-v3-command-geometry-v1'
ROBOT_MODEL = 'masterpi_v3'
MOUNT_X_M = PHYSICAL_V3.yaw_axis_x_m
SHOULDER_DELTA_Z_M = PHYSICAL_V3.shoulder_axis_z_floor_m - (
    sdk.ROBOT_BASE_FLOOR_HEIGHT_CM + sdk.LINK_1_CM) / 100.
GRIPPER_LINK_CM = PHYSICAL_V3.pad_center_from_wrist_m * 100.
MOUNT_XYZ_M = (MOUNT_X_M, 0., SHOULDER_DELTA_Z_M)


def tool_pose(servo_pose, *, tool_length_cm=GRIPPER_LINK_CM):
    value = sdk.tool_pose(servo_pose, tool_length_cm=tool_length_cm)
    return replace(value, x_m=value.x_m + MOUNT_X_M, z_m=value.z_m + SHOULDER_DELTA_Z_M)


def forward_grip(pose):
    value = tool_pose(pose)
    return value.x_m, value.y_m, value.z_m


def camera_optical_to_robot_base(servo_pose, optical_xyz_m):
    x, y, z = sdk.camera_optical_to_robot_base(servo_pose, optical_xyz_m)
    return x + MOUNT_X_M, y, z + SHOULDER_DELTA_Z_M


def camera_to_base(optical_xyz, pose):
    return camera_optical_to_robot_base(pose, optical_xyz)


def camera_extrinsics(pose):
    origin, axes = sdk.camera_extrinsics(pose)
    return (origin[0] + MOUNT_X_M, origin[1], origin[2] + SHOULDER_DELTA_Z_M), axes


def solve_grip_site_ik(target_xyz_m, *, preferred_pitch_deg=-66., calibrated_grasp_only=True):
    if len(target_xyz_m) != 3:
        raise ValueError('target_xyz_m must contain x, y, z')
    x, y, z = (sdk._finite('target coordinate', v) for v in target_xyz_m)
    preferred = sdk._finite('preferred_pitch_deg', preferred_pitch_deg)
    x -= MOUNT_X_M
    z -= SHOULDER_DELTA_Z_M
    radius = math.hypot(x, y) * 100.
    lo, hi = sdk.CALIBRATED_GRASP_RADIUS_CM
    if calibrated_grasp_only and not lo - 1e-10 <= radius <= hi + 1e-10:
        raise ValueError('target radius is outside the calibrated arm-axis envelope')
    pan = round(sdk.BASE_CENTER + math.degrees(math.atan2(y, x)) * sdk.PULSE_PER_DEGREE)
    if not sdk.CALIBRATED_PAN_MIN <= pan <= sdk.CALIBRATED_PAN_MAX:
        raise ValueError('target yaw is outside the calibrated servo-6 grasp sector')
    candidates = []
    # Move the target along its requested tool axis to the SDK virtual tip.
    # This leaves the original triangle solver unchanged, with no global edits.
    extra = sdk.GRIPPER_LINK_CM - GRIPPER_LINK_CM
    for pitch in range(-90, -39):
        alpha = math.radians(pitch)
        arm = sdk._ik_at_pitch(radius + extra * math.cos(alpha),
                               z * 100. - sdk.ROBOT_BASE_FLOOR_HEIGHT_CM + extra * math.sin(alpha),
                               float(pitch))
        if arm is not None:
            candidates.append((abs(pitch - preferred), {**arm, 6: pan}))
    if not candidates:
        raise ValueError('target has no safe v3 physical-pad IK solution')
    return min(candidates, key=lambda row: row[0])[1]


def solve_grip_ik(x_forward_m, y_left_m, z_above_floor_m, pitch_deg=-90.):
    return solve_grip_site_ik((x_forward_m, y_left_m, z_above_floor_m), preferred_pitch_deg=pitch_deg)
