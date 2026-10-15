"""Two-stage pre-grasp approach, on own admitted observations only.

A blocked grasp station is not a blocked navigation task. Find a collision-
checked staging view first, then re-evaluate the original grasp poses. Never
promote a staging view to READY. No shared peer coordinates or simulator.
"""
import math
from sim.grasp_act_goal_set import geometry

MODE = 'crate_candidates_v1'
MAX_RECOVERY_S = 12.


def staging_view(world, teacher, excluded=()):
    nav = teacher._navigation(world)
    pose = world['robots'][teacher.rid]['pose']
    end = world['beam']['ends'][teacher.end]
    choices = []
    # Distances outside the IK grasp window are navigation goals only.
    for angle in (0, -30, 30, -60, 60, -85, 85):
        for distance in (.35, .50, .70):
            key = (angle, distance)
            if key in excluded:
                continue
            _, _, heading, goal = geometry(world, teacher.rid, teacher.end,
                                           (math.radians(angle), distance))
            if math.dist(pose[:2], goal) < .04 or not nav.free(goal, heading):
                continue
            choices.append((math.dist(pose[:2], goal), key, heading, goal))
    # Reachability is validated after sorting, not just goal occupancy.
    for _, key, heading, goal in sorted(choices):
        path = nav.path(pose[:2], goal, heading)
        if not path:
            continue
        target = nav.waypoint(pose[:2], path, end)
        if target is not None:
            return {'key': key, 'goal': goal, 'heading': heading, 'path': path, 'target': target}
    return None
