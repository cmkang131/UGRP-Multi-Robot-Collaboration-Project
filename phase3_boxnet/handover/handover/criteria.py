"""Numerical criteria shared by the referee and offline re-scoring of measurements."""
import math

from handover import layout


def held(pose, rid, *, ignore_tilt=False):
    return (pose["clearance_m"] >= layout.LIFT_FLOOR and min(pose["finger_n"][rid]) >= layout.FINGER_N
            and (ignore_tilt or pose["tilt_deg"] <= layout.TILT_TOL))


def free(pose):
    return all(max(forces) < 0.05 for forces in pose["finger_n"].values())


def resting(pose):
    return (free(pose) and abs(pose["clearance_m"]) <= layout.FLOOR_EPS
            and pose["speed_m_s"] <= layout.REST_SPEED and pose["tilt_deg"] <= layout.TILT_TOL)


def aligned_with_mark(trial, pose):
    return (math.hypot(pose["x"], pose["y"]) <= layout.RELEASE_RADIUS
            and layout.yaw_error(pose["yaw"], trial["mark"][2]) <= layout.YAW_TOL)


def at_mark(trial, pose):
    return aligned_with_mark(trial, pose) and pose["tilt_deg"] <= layout.TILT_TOL


def at_sign(trial, pose):
    depth, lateral = layout.sign_relative(trial, pose["x"], pose["y"])
    return 0 <= depth <= .65 and abs(lateral) <= .5
