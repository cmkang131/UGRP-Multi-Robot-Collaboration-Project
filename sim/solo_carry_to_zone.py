"""Opt-in solo map carry: static map + RGB self pose + own command integration.

No simulator, setup pose, cargo world pose, measured joints or score is accepted.
Carry2 uses an authored task start and own commands. Legacy top RGB code is
retained below for provenance only and rejects execution under issue #366.
"""
from __future__ import annotations

from collections import deque
import hashlib
import json
import math

from harness.grasp_act_visible_world import command_delta
from harness.static_keepouts import keepout_rects
from sim.grasp_act_visible_route import free, segment_free, waypoint
from scripts.zone_teacher import plan_path, proportional_drive

OPTION = 'solo_carry_to_zone_v1'
TRAVEL_PHASES = ('carry_prepare', 'carry_to_zone')
LOCAL_PHASES = ('zone_place_view', 'zone_place_advance', 'lower', 'open', 'retract', 'backoff')


def wrap(a):
    return math.atan2(math.sin(a), math.cos(a))


def integrate(pose, issued, dt):
    dx, dy, da = command_delta(issued, dt)
    x, y, a = pose
    return [x+math.cos(a)*dx-math.sin(a)*dy,
            y+math.sin(a)*dx+math.cos(a)*dy, wrap(a+da)]


def chassis_candidates(tops, static):
    """Existing yellow-chassis grouping method; never detects any cargo pose.

    Use the fixed TOP calibration and 9 cm feature plane from
    KnownMapNavigator. Require a chassis-sized group of multiple yellow parts;
    compact yellow boxes alone are not a robot. Overlapping camera views dedupe.
    """
    raise ValueError('top RGB forbidden for control/localization (#366); legacy code retained only')
    import cv2
    import numpy as np
    from harness.zone_perception import _decode, pixel_to_floor
    candidates = []
    for camera in static['top_cameras']:
        frame = _decode(tops[camera['name']])
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, np.array([12, 60, 30], np.uint8), np.array([42, 255, 255], np.uint8))
        n, _, stats, centers = cv2.connectedComponentsWithStats(mask, 8)
        parts = []
        for i in range(1, n):
            if stats[i, cv2.CC_STAT_AREA] < 3:
                continue
            x, y, w, h, _ = stats[i]
            corners = [pixel_to_floor(u, v, camera, frame.shape, height=.09)
                       for u, v in ((x, y), (x+w-1, y+h-1))]
            if math.dist(*corners) > .18:
                continue
            parts.append((pixel_to_floor(*centers[i], camera, frame.shape, height=.09), corners))
        pending = set(range(len(parts)))
        while pending:
            group = {pending.pop()}
            while True:
                adjacent = {j for j in pending if any(math.dist(parts[j][0], parts[i][0]) <= .22 for i in group)}
                if not adjacent:
                    break
                group |= adjacent
                pending -= adjacent
            corners = [p for i in group for p in parts[i][1]]
            x0, x1 = min(p[0] for p in corners), max(p[0] for p in corners)
            y0, y1 = min(p[1] for p in corners), max(p[1] for p in corners)
            if len(group) < 2 or not .10 <= max(x1-x0, y1-y0) <= .36:
                continue
            xy = ((x0+x1)/2, (y0+y1)/2)
            if not any(math.dist(xy, p) < .10 for p in candidates):
                candidates.append(xy)
    return candidates


class RGBCommandPose:
    """Motion association bootstraps SE(2), never an assumed spawn or zero pose.

    Zero in `odom` is an arbitrary local frame. Map pose remains None until
    exactly one image track moves in agreement with own issued translation.
    Missing/ambiguous observations cannot renew the freshness clock.
    """
    def __init__(self):
        raise ValueError('top RGB localizer forbidden (#366); use CommandPose')
        self.odom = [0., 0., 0.]
        self.pose = None
        self.last_fix = None
        self.history = deque(maxlen=12)
        self.fixes = 0
        self.reason = 'awaiting_rgb_motion_association'

    def issue(self, issued, dt):
        self.odom = integrate(self.odom, issued, dt)
        if self.pose is not None:
            self.pose = integrate(self.pose, issued, dt)

    def observe(self, points, now):
        points = [tuple(p) for p in points if len(p) == 2 and all(math.isfinite(v) for v in p)]
        old_pose = self.pose
        if self.pose is None:
            matches = []
            for at, odom, before in self.history:
                dx, dy = self.odom[0]-odom[0], self.odom[1]-odom[1]
                distance = math.hypot(dx, dy)
                if now-at < .5 or not .06 <= distance <= .25:
                    continue
                moving = []
                for p in before:
                    ranked = sorted((math.dist(p, q), q) for q in points)
                    if not ranked or ranked[0][0] > .30:
                        continue
                    d, q = ranked[0]
                    if len(ranked) > 1 and ranked[1][0]-d < .08:
                        continue
                    if d >= .04 and .4 <= d/distance <= 1.8:
                        yaw0 = math.atan2(q[1]-p[1], q[0]-p[0])-math.atan2(dy, dx)
                        moving.append([*q, wrap(yaw0+self.odom[2])])
                if len(moving) == 1:
                    matches.append(moving[0])
            if len(matches) >= 2 and all(math.dist(p[:2], matches[-1][:2]) < .06 and
                    abs(wrap(p[2]-matches[-1][2])) < .20 for p in matches):
                self.pose = matches[-1]
                self.reason = 'rgb_motion_associated'
        else:
            ranked = sorted((math.dist(self.pose[:2], q), q) for q in points)
            if ranked and ranked[0][0] <= .10 and (len(ranked) == 1 or ranked[1][0]-ranked[0][0] >= .08):
                # Position corrected by image. Yaw remains command-integrated;
                # no cargo orientation, true yaw or commanded-success assumption.
                self.pose = [*ranked[0][1], self.pose[2]]
                self.reason = 'rgb_position_command_yaw'
            else:
                self.reason = 'rgb_lost_or_ambiguous'
        if self.pose is not old_pose:
            self.last_fix = now
            self.fixes += 1
        self.history.append((now, tuple(self.odom), points))

    def ready(self, now):
        return self.pose is not None and self.last_fix is not None and now-self.last_fix <= 2.

    def record(self):
        return {'pose_estimate': self.pose, 'source': 'top_rgb_motion_association_then_command_yaw',
                'last_rgb_fix_t': self.last_fix, 'rgb_fixes': self.fixes, 'reason': self.reason,
                'yaw_correction': 'bootstrap only; subsequent yaw is issued-command integration',
                'localization_verified': False}


class CarryToZone:
    def __init__(self, static, zone, *, start=None, now=0., robot_id='r1', amcl_option='off'):
        if zone not in ('A', 'B', 'C') or 'zone_'+zone not in static['regions']:
            raise ValueError('destination must be an authored zone')
        self.static, self.zone = static, zone
        self.region = static['regions']['zone_'+zone]
        self.rects = keepout_rects(static, perimeter=True)
        self.radius = .26  # chassis + upright small box/arm envelope + clearance
        self.path = None
        self.slot = self.goal = None
        self.started = None
        self.arrived = None
        self.last_plan = -math.inf
        self.failure = None
        self.grip_xy = None
        self.advance_m = .15
        self.map_sha256 = hashlib.sha256(json.dumps(static, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        from sim.solo_carry_pose import CommandPose, task_start
        expected = task_start(static)
        if start != expected:
            raise ValueError('carry requires the declared static task start; no spawn-derived prior')
        self.loc = CommandPose(start, now=now, robot_id=robot_id,
                               map_sha256=self.map_sha256, amcl_option=amcl_option)

    def issue(self, issued, dt):
        self.loc.issue(issued, dt)

    def observe(self, tops, now):
        raise ValueError('top RGB forbidden for carry control (#366)')

    def observe_own(self, bgr, now, *, camera):
        self.loc.observe_own(bgr, now, camera=camera)

    def start(self, now, grip_xy):
        self.started = now
        self.grip_xy = tuple(grip_xy)
        if not self.loc.ready(now):
            self.failure = 'carry_self_pose_unavailable'
            return
        # Fixed map slot candidates, nearest reachable stand-off first. No
        # pickup position or current cargo world position is consulted.
        cx, cy = self.region['center_m']; hx, hy = self.region['half_extents_m']
        candidates = [(cx+sx*max(0., hx-.20), cy+sy*max(0., hy-.20))
                      for sx, sy in ((0, 0), (-1, 0), (1, 0), (0, -1), (0, 1))]
        for slot in sorted(candidates, key=lambda p: math.dist(self.loc.pose[:2], p)):
            # Final heading east; grip relation comes from own issued low pose.
            goal = (slot[0]-grip_xy[0]-self.advance_m, slot[1]-grip_xy[1])
            final = (goal[0]+self.advance_m, goal[1])
            retreat = (final[0]-.15, final[1])
            if not (free(goal, [], self.rects, self.radius) and
                    segment_free(goal, final, [], self.rects, self.radius) and
                    segment_free(final, retreat, [], self.rects, self.radius)):
                continue
            path = plan_path(self.loc.pose[:2], goal, self.static['bounds_m'], [], rects=self.rects, radius=self.radius)
            if path:
                self.slot, self.goal, self.path = slot, goal, path
                break
        if self.path is None:
            self.failure = 'carry_no_static_route'

    def step(self, now):
        if self.failure:
            return (0., 0., 0.), False, self.failure
        if not self.loc.ready(now):
            return (0., 0., 0.), False, 'carry_self_pose_stale'
        pose = self.loc.pose
        distance = math.dist(pose[:2], self.goal)
        if distance <= .025 and abs(wrap(pose[2])) <= .04:
            self.arrived = now
            return (0., 0., 0.), True, None
        if distance <= .025:
            return (0., 0., max(-.1, min(.1, -.6*wrap(pose[2])))), False, None
        if now-self.last_plan >= 1.:
            self.path = plan_path(pose[:2], self.goal, self.static['bounds_m'], [], rects=self.rects, radius=self.radius)
            self.last_plan = now
        target = waypoint(pose[:2], self.path, [], self.rects, self.radius)
        if target is None:
            return (0., 0., 0.), False, 'carry_no_static_route'
        cmd = proportional_drive(pose, self.goal, target, 0.)
        return (max(-.05, min(.08, cmd['forward'])), max(-.06, min(.06, cmd['left'])),
                max(-.1, min(.1, cmd['turn']))), False, None

    def place_visible(self, bgr, pwm, low, kind):
        """Floor footprint must actually be visible and have destination paint.

        Same FK/ray/held occlusion mask as solo lookback; prediction alone is
        insufficient. After this check only 15 cm of issued translation is used.
        """
        import cv2
        import numpy as np
        from sim.grasp_act_solo_lookback import regions
        from harness.zone_own_perception import PAINT_HUE
        if bgr is None or self.slot is None or self.grip_xy is None:
            return False
        x, y = self.grip_xy
        roi, _, geometry = regions(kind, {1: 1500, **low}, pwm,
            (bgr.shape[1], bgr.shape[0]), site=(x+self.advance_m, y, 0.))
        if not geometry['qualified'] or int(roi.sum()) < 30:
            return False
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)[roi]
        lo, hi = PAINT_HUE[self.zone]
        painted = (hsv[:, 0] >= lo-5) & (hsv[:, 0] <= hi+5) & (hsv[:, 1] >= 30) & (hsv[:, 2] >= 30)
        return bool(np.mean(painted) >= .6)

    def record(self):
        return {'toggle': OPTION, 'destination_zone': self.zone, 'slot_xy': self.slot,
                'stand_off_xy': self.goal, 'radius_m': self.radius, 'map_sha256': self.map_sha256,
                'self_pose': self.loc.record(), 'carry_started_t': self.started,
                'map_arrival_estimated_t': self.arrived, 'failure': self.failure,
                'path': self.path, 'static_route_only': True,
                'held_world_reads': 0, 'physical_success': None}
