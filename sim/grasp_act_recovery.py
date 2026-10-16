"""Visible-only dynamic-goal recovery; no simulator or peer message side channel.

Follow a collision-checked prefix, pause, and replan as a temporary peer moves.
The nominal grasp stance and every original keep-out remain unchanged.
"""
import math
from scripts.zone_teacher import PeerDisc, plan_path
from sim.grasp_act_visible_route import free, segment_free

# A narrow goal neighbourhood along the SAME beam axis. Every distance must
# pass the existing full descent IK and original obstacle/peer margins.
# No sideways grasp, footprint reduction or measured-state input.
AXIAL_CHOICES = tuple((0., d) for d in (.203, .198, .208, .196, .210))


def peer_goal_blocked(goal, discs, rects, radius):
    peers = [d for d in discs if isinstance(d, PeerDisc)]
    fixed = [d for d in discs if not isinstance(d, PeerDisc)]
    return (free(goal, fixed, rects, radius)
            and not free(goal, peers, (), radius))


def safe_prefix(start, goal, bounds, discs, rects, radius):
    """Truncate the geometric route before its first occupied segment.

    Ignoring peers is ONLY for proposing the route; every returned segment is
    checked with ALL peers. No pose inside a peer margin is an execution goal.
    """
    fixed = [d for d in discs if not isinstance(d, PeerDisc)]
    route = ([goal] if segment_free(start, goal, fixed, rects, radius) else
             plan_path(start, goal, bounds, fixed, rects=rects, radius=radius))
    prefix = [tuple(start)]
    for end in route or ():
        begin = prefix[-1]
        n = max(1, math.ceil(math.dist(begin, end) / .01))
        for i in range(1, n + 1):
            point = tuple(a + (b-a)*i/n for a, b in zip(begin, end))
            if not free(point, discs, rects, radius) or not segment_free(prefix[-1], point, discs, rects, radius):
                # Leave another 20 mm before the inflated boundary.
                return prefix[:-2] if len(prefix) > 3 else [tuple(start)]
            prefix.append(point)
    return prefix
