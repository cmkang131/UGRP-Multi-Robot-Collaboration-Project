"""Issued-pulse collision projection for the crate demonstration teacher.

Nav2 rotation shim checks projected commands before execution. Here the model
is only the student's issued-wheel kinematics, never measured motion/physics.
Legacy margins are unchanged with options off. The new mode permits only
non-decreasing clearance inside cargo/peer margins; optional wall checks use
the rectangular chassis envelope. Neither establishes physical grasp success.
"""
import math

from harness.grasp_act_visible_world import command_delta
from sim.grasp_act_visible_route import free, segment_free

OPTION = 'crate_approach_recovery_v1'
MODES = ('off', OPTION)
PULSE_MODES = ('off', 'crate_no_closer_v1')


def safe_pulse(value, pose, discs, rects, radius, *, mode='off', wall_footprint=False):
    """Check the 100 ms lease at every wheel deadline and <=5 ms substep.

    Legacy mode rejects turning inside an inflated obstacle. The opt-in mode
    permits it only when the entire pulse never reduces initial clearance.
    With wall_footprint, sampled oriented chassis checks replace wall circles.
    """
    if mode not in PULSE_MODES:raise ValueError('unknown pulse mode')
    if not any(value['wheels']):
        return True
    _, _, turn = command_delta(value, .1)
    if mode == 'off' and abs(turn) > 1e-9 and not free(pose[:2], discs, rects, radius):
        return False
    # One limit per entire lease. Do not reset the 1 mm _no_closer slack at
    # every 5 ms substep (that would accumulate penetration across a pulse).
    limits = [min(math.dist(pose[:2],d[:2]), d[2]+radius) for d in discs]
    from harness.static_keepouts import rect_distance, swept_clear
    wall_limits = [min(rect_distance(pose[:2],r),radius) for r in rects]
    times = sorted({0., .1, *(i*.005 for i in range(1, 20)),
                    *(min(.1, d) for d in value['duration_s'])})
    x, y, yaw = pose
    for a, b in zip(times, times[1:]):
        step = {**value, 'duration_s': [max(0., d-a) for d in value['duration_s']]}
        dx, dy, da = command_delta(step, b-a)
        co, si = math.cos(yaw+da/2), math.sin(yaw+da/2)
        end = (x+co*dx-si*dy, y+si*dx+co*dy)
        if mode == 'off':
            if not segment_free((x, y), end, discs, rects, radius):return False
        else:
            vx,vy=end[0]-x,end[1]-y; norm=vx*vx+vy*vy
            for d,limit in zip(discs,limits):
                u=max(0.,min(1.,((d[0]-x)*vx+(d[1]-y)*vy)/max(norm,1e-30)))
                if math.hypot(x+u*vx-d[0],y+u*vy-d[1]) < limit-1e-9:return False
            if not wall_footprint and any(rect_distance(end,r)<limit-1e-9 for r,limit in zip(rects,wall_limits)):
                return False
        if wall_footprint:
            from sim.crate_navigation_v12 import FOOTPRINT,PAD_M
            if not swept_clear((x,y,yaw),(*end,yaw+da),FOOTPRINT,rects,margin=PAD_M,
                               step_m=.001,step_rad=math.radians(.25)):return False
        x, y = end
        yaw += da
    return True
