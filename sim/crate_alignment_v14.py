"""Opt-in crate14 command-space geometry; no simulator or measured joints.

The feasible window is checked on the exact pitch-preserving descent endpoint
that _queue_pick issues, then on the existing constant-XY lift. The centre and
bands are a candidate, not a measured physical stability guarantee.
"""
import math
from functools import lru_cache
from itertools import product
from harness.visual_arm_v3 import solve_grip_site_ik, tool_pose
from sim.grasp_act_teacher import local

PROFILE = 'crate14_v1'
MODE = 'crate_alignment_v14'
STATION_M = .1974
INNER = (.0005, .002, .005)
OUTER = (.001, .004, .01)
DISTANCES_M = (STATION_M,)


def pick_closed_pwm(x, y, z):
    grip = solve_grip_site_ik((x, y, z))
    pitch = tool_pose(grip).pitch_deg
    # Exactly the eighth/final descent command followed by close PWM 1500.
    return {1: 1500, **solve_grip_site_ik((x, y, z), preferred_pitch_deg=pitch)}


@lru_cache(maxsize=4096)
def lift_feasible(x, y, z):
    from sim.crate_cartesian_lift import plan_lift
    try:
        return plan_lift(pick_closed_pwm(x, y, z))[0] is not None
    except ValueError:
        return False


def grasp_valid(world, rid, end, pose):
    from sim.crate_antipodal import visible_grasp
    if not visible_grasp(world, rid, end, pose=pose)['valid']:
        return False
    g = world['beam']['ends'][end]
    x, y = local(pose, g)
    return lift_feasible(x, y, g[2])


def stance_valid(world, rid, end, pose):
    """Require centre + all 8 outer-deadband corners to keep descent/lift valid."""
    if not grasp_valid(world, rid, end, pose):
        return False
    g = world['beam']['ends'][end]
    for dx, dy, da in product(*[(-b, b) for b in OUTER]):
        yaw = pose[2]-da
        x, y = STATION_M+dx, dy
        c, s = math.cos(yaw), math.sin(yaw)
        edge = (g[0]-c*x+s*y, g[1]-s*x-c*y, yaw)
        if not grasp_valid(world, rid, end, edge):
            return False
    return True


def peer_blocks_stances(world, teacher):
    """Counterfactual with visible peer discs removed, used ONLY for the clock.

    All actual goals, paths and pulses keep every peer and wall constraint.
    A static/IK/excluded failure alone never pauses the staging deadline.
    """
    from sim.grasp_act_goal_set import geometry
    if world['beam'] is None or world['visibility'][teacher.rid]['visible_probes'] < 5:
        return False
    if len(world['robots']) <= 1:
        return False
    solo = {**world, 'robots': {teacher.rid: world['robots'][teacher.rid]}}
    nav = teacher._navigation(world)
    without = teacher._navigation(solo)
    start = world['robots'][teacher.rid]['pose'][:2]
    for angle in teacher.approach_angles:
        choice = (math.radians(angle), STATION_M)
        if choice in teacher.approach_excluded:
            continue
        _, _, heading, goal = geometry(world, teacher.rid, teacher.end, choice)
        if not teacher.approach_grasp_filter(world, (*goal, heading)):
            continue
        if without.free(goal, heading) and without.path(start, goal, heading):
            if not nav.free(goal, heading) or not nav.path(start, goal, heading):
                return True
    return False
