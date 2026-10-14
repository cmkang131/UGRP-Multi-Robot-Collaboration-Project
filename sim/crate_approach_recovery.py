"""Issued-pulse collision projection for the crate demonstration teacher.

Nav2 rotation shim checks projected commands before execution. Here the model
is only the student's issued-wheel kinematics, never measured motion/physics.
All original cargo/peer/wall margins remain in force. This is navigation, not
a replacement grasp, and cannot establish that an unreachable lug is reachable.
"""
import math

from harness.grasp_act_visible_world import command_delta
from sim.grasp_act_visible_route import free, segment_free

OPTION = 'crate_approach_recovery_v1'
MODES = ('off', OPTION)


def safe_pulse(value, pose, discs, rects, radius):
    """Check the 100 ms lease at every wheel deadline and <=5 ms substep.

    Existing margin-escape translation is allowed, but turning while already
    inside an inflated obstacle is not treated as a completed search rotation.
    A circumscribed disc uses the original radius; no body shrink is applied.
    """
    if not any(value['wheels']):
        return True
    _, _, turn = command_delta(value, .1)
    if abs(turn) > 1e-9 and not free(pose[:2], discs, rects, radius):
        return False
    times = sorted({0., .1, *(i*.005 for i in range(1, 20)),
                    *(min(.1, d) for d in value['duration_s'])})
    x, y, yaw = pose
    for a, b in zip(times, times[1:]):
        step = {**value, 'duration_s': [max(0., d-a) for d in value['duration_s']]}
        dx, dy, da = command_delta(step, b-a)
        co, si = math.cos(yaw+da/2), math.sin(yaw+da/2)
        end = (x+co*dx-si*dy, y+si*dx+co*dy)
        if not segment_free((x, y), end, discs, rects, radius):
            return False
        x, y = end
        yaw += da
    return True
