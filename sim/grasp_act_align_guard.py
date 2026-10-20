"""pairact P1 cand-1: align-phase pulse guard with the real chassis rectangle.

Basis:
* beampair9 (CPU) seed 8328015: 90 x ``alignment_axes_blocked``; the existing 40 ms
  align pulse was rejected by the CIRCULAR guard (folded radius 0.13 m) against
  ``cyan_1`` with a start gap of 1.925 mm and a pulse-path minimum of -1.538 mm
  (nominal) / -0.699 mm (calibrated).  ``beampair_box_geometry_v1`` only changed
  body navigation, not this pulse guard (README "remaining fix (2)").
* beamact5 r13diag world 27 FAIL: from SIM 17.6 s 91 x ``alignment_axes_blocked``;
  the final segment/pulse safety check replaced every align pulse with hold.

The 185 x 160 mm body has a 0.1223 m half diagonal and a 0.0925 m longitudinal
half extent, while the circle uses 0.13 m in every direction.  This mode keeps
every obstacle exactly as ``constraints()`` builds it (cargo discs with their
existing padding, peer discs, wall rectangles) and only replaces the robot's
circle with the existing exact body rectangle (``search18.body_clearance``),
swept along the issued pulse at the existing 2 mm / 0.5 deg resolution of
``search19.BodyNavigation.pose_segment``.  No new distance, margin or time constant.

Scope (fail-safe to the unchanged circle):
* phase ``align`` only, folded radius (0.13 m) only (an unfolded arm is not
  inside the rectangle), not when the search19 body path is already active
  (that path already uses the rectangle);
* if the start pose is not strictly clear (gap <= 0), return None so the
  existing circular no-closer rule decides.
Default off.
"""
import math

MODE_KEY = 'search26_align_rect_guard'
MODE = 'search26_align_rect_guard_v1'
FOLDED_RADIUS_M = .13  # existing visible_route.constraints folded radius (not new)


def enabled(teacher):
    return teacher.search15_modes.get(MODE_KEY, 'off') != 'off'


def _sweep_clear(pose, value, discs, rects, mode):
    from harness.grasp_act_visible_world import command_delta
    from sim.grasp_act_search18 import body_clearance
    if body_clearance(tuple(pose), discs, rects) <= 0.:
        return None
    times = sorted({0., .1, *(max(0., min(.1, d)) for d in value['duration_s'])})
    current = tuple(pose)
    for t0, t1 in zip(times, times[1:]):
        a, b = (command_delta(value, tt, mode=mode) for tt in (t0, t1))
        dx, dy, da = (y-x for x, y in zip(a, b))
        si = math.sin(da)/da if abs(da) > 1e-10 else 1.
        co = (1-math.cos(da))/da if abs(da) > 1e-10 else 0.
        x, y = si*dx-co*dy, co*dx+si*dy
        c, s = math.cos(current[2]), math.sin(current[2])
        end = (current[0]+c*x-s*y, current[1]+s*x+c*y, current[2]+da)
        n = max(1, math.ceil(math.dist(current[:2], end[:2])/.002), math.ceil(abs(da)/math.radians(.5)))
        for i in range(1, n+1):
            p = (current[0]+(end[0]-current[0])*i/n, current[1]+(end[1]-current[1])*i/n, current[2]+da*i/n)
            if body_clearance(p, discs, rects) <= 0.:
                return False
        current = end
    return True


def rect_pulse_free(pose, value, discs, rects, *, modes=('off',)):
    """Pure: True/False under the rectangle body, None if the start is not strictly clear."""
    result = True
    for mode in dict.fromkeys(modes):
        clear = _sweep_clear(pose, value, discs, rects, mode)
        if clear is None:
            return None
        result &= clear
    return result


def rect_clear(teacher, pose, value, discs, rects, radius):
    """Teacher hook. None means: not applicable, keep the existing circular guard."""
    if (not enabled(teacher) or teacher.phase != 'align' or teacher.search19_body_active
            or radius > FOLDED_RADIUS_M + 1e-9):
        return None
    return rect_pulse_free(pose, value, discs, rects,
                           modes=('off', teacher.search15_modes['search17_odometry']))
