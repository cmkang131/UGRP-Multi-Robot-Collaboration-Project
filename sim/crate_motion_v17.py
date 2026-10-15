"""Crate17 local pulse sampling, from admitted geometry/issued odometry only.

Keep crate16 immutable for replay. This is a finite local sampler, not a
complete planner or calibrated prediction of physical wheel motion.
"""
import math
from harness.grasp_act_contract import command, wheel_mix
from harness.grasp_act_visible_world import command_delta
from sim.crate_motion_v16 import Navigation as Navigation16
from sim.crate_navigation_v12 import HALF_X, HALF_Y

MODE = 'crate_motion_v17'
NO_CLEARANCE = 'crate_motion_v17_no_clearance'
MODES = (MODE, NO_CLEARANCE)
MIN_PULSE_S = .025
MIN_FACE_ERROR = math.radians(2.)


def translation(value, dx, dy):
    """Same nominal xy displacement, zero yaw, no phase-dependent 40ms floor."""
    gain = .0325*150*2*math.pi/60
    integrals = wheel_mix((dx/gain, dy/gain, 0.))
    scale = min(1., .035/max(max(map(abs, integrals)), 1e-12))
    return command({**value, 'wheels': [math.copysign(.35, v) if v else 0. for v in integrals],
                    'duration_s': [abs(v)*scale/.35 for v in integrals]})


def advance(pose, value):
    """Issued-world odometry, exactly as VisibleWorld.observe (not physics)."""
    dx, dy, da = command_delta(value, .1)
    c, s = math.cos(pose[2]), math.sin(pose[2])
    return (pose[0]+c*dx-s*dy, pose[1]+s*dx+c*dy, pose[2]+da)


class Navigation(Navigation16):
    def __init__(self, world, rid, folded, profile, bounds, end=None, *, search=False, budget=None):
        super().__init__(world, rid, folded, profile, bounds, end, search=search, budget=budget)
        # Expired cargo does not revoke a currently seen peer. Other admitted
        # peers already obey the producer's 5.2s expiry outside walls-only mode.
        if self.walls_only:
            self.rectangles += [('peer', (*v['pose'][:2], HALF_X, HALF_Y, v['pose'][2]))
                                for key, v in world['robots'].items()
                                if key != rid and key in world['visibility'][rid]['peers']]
        self.stats.update(attempted_pads_m=[], waypoint_constant_yaw_rejects=0, waypoint_first_node_fallbacks=0)

    def _path(self, start, goal, heading, pad):
        self.stats['attempted_pads_m'].append(pad)
        return super()._path(start, goal, heading, pad)

    def waypoint(self, start, path, target):
        if not path:
            return None
        nearest = min(range(len(path)), key=lambda i: math.dist(start, path[i]))
        best = None
        # Lookahead cannot borrow the hypothetical yaw interpolation in A*.
        # If smoothing fails, the first reachable route node remains the target;
        # the exact, independently timed wheel pulse is checked before issuance.
        # The nearest lattice node is the route's anchor, often already behind
        # the robot. Start at its successor rather than retreating to that node.
        first = min(nearest+1, len(path)-1)
        for p in path[first:]:
            distance = math.dist(start, p)
            if distance < .001:
                continue
            if self.segment(start, p, self.pose[2], self.pose[2]):
                best = p
                if distance >= .12:
                    break
            else:
                self.stats['waypoint_constant_yaw_rejects'] += 1
                if best is None:
                    # Do not smooth across the route. The first A* connector
                    # may require yaw; target that node, with the actual pulse
                    # sampler enforcing safety instead of assuming interpolation.
                    yaw = math.atan2(target[1]-p[1], target[0]-p[0])
                    if self.segment(start, p, self.pose[2], yaw):
                        self.stats['waypoint_first_node_fallbacks'] += 1
                        return p
                break
        return best

    def escape_candidates(self, value):
        for factor in (.75, .5, .25):
            candidate = {**value, 'duration_s': [d*factor for d in value['duration_s']]}
            if max(candidate['duration_s']) >= MIN_PULSE_S-1e-9:
                yield f'scale_{factor:g}', command(candidate)
        dx, dy, _ = command_delta(value, .1)
        if math.hypot(dx, dy) > 1e-6:
            for degrees in (15, -15, 30, -30):
                a = math.radians(degrees); c, s = math.cos(a), math.sin(a)
                yield f'direction_{degrees:+d}', translation(value, c*dx-s*dy, s*dx+c*dy)
        if self.focus is not None:
            error = math.atan2(math.sin(self.heading_at(self.pose, self.pose[2])-self.pose[2]),
                               math.cos(self.heading_at(self.pose, self.pose[2])-self.pose[2]))
            if abs(error) >= MIN_FACE_ERROR:
                # Half the observed/remembered bearing error, <= old 28ms.
                yaw_gain = .0325*150*2*math.pi/60*.35/.1255
                width = min(.028, .5*abs(error)/yaw_gain)
                sign = math.copysign(.35, error)
                yield 'face_lug', command({**value, 'wheels': [-sign, sign, -sign, sign],
                                            'duration_s': [width]*4})
        yield 'retreat', translation(value, -.0045, 0.)

    def preferred_escape(self, value):
        """Inside 15mm, prefer checked retreat/tangent that restores clearance."""
        before = min(v for _, v in self.clearances(self.pose[:2], self.pose[2], .015))
        if before >= 0.:
            return None
        dx, dy, _ = command_delta(value, .1)
        candidates = [('preferred_retreat', translation(value, -.0045, 0.))]
        if self.focus is not None:
            a = self.heading_at(self.pose, self.pose[2])-self.pose[2]
            tangent = (-math.sin(a)*.0045, math.cos(a)*.0045)
            for sign in (1, -1):
                candidates.append(('preferred_tangent', translation(value, tangent[0]*sign, tangent[1]*sign)))
        good = []
        for kind, candidate in candidates:
            if not self.pulse_safe(candidate):
                continue
            end = advance(self.pose, candidate)
            after = min(v for _, v in self.clearances(end[:2], end[2], .015))
            cx, cy, _ = command_delta(candidate, .1)
            if after > before+1e-5 or (after >= before-1e-9 and cx*dx+cy*dy > 1e-9):
                good.append((after-before, cx*dx+cy*dy, kind, candidate))
        if not good:
            return None
        _, _, kind, candidate = max(good, key=lambda v: v[:2])
        return kind, candidate
