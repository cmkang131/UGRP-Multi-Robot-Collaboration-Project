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
    def __init__(self, static, zone, *, start=None, now=0., robot_id='r1', amcl_option='off', recovery_profile='off', drive_model_deadband_v1=False,
                 carry5_rank_aware_views_v1=False, carry5_trim_yaw_calibration_v1=False, trim_calibration=None,
                 carry7_robust_recovery_v1=False, reloc9_rotation_calibration_v1=False, reloc10_rotation_calibration_v1=False):
        if recovery_profile not in ('off', 'carry5_active_localization_v1'):
            raise ValueError('unknown carry recovery profile')
        self.recovery_profile = recovery_profile
        self.active_recovery = recovery_profile != 'off'
        if type(carry5_rank_aware_views_v1) is not bool or (carry5_rank_aware_views_v1 and not self.active_recovery):
            raise ValueError('rank-aware views require carry5 recovery and bool toggle')
        self.rank_aware_v1 = carry5_rank_aware_views_v1
        if type(carry7_robust_recovery_v1) is not bool or (carry7_robust_recovery_v1 and not self.rank_aware_v1):
            raise ValueError('carry7 requires carry6 rank-aware recovery and bool toggle')
        self.robust_recovery_v1 = carry7_robust_recovery_v1
        self.recovery_reason = None
        self.recovery_events = []
        self.recovery_count = 0
        self.recovery_anchor = None
        self.stalled_recoveries = 0
        if zone not in ('A', 'B', 'C') or 'zone_'+zone not in static['regions']:
            raise ValueError('destination must be an authored zone')
        self.static, self.zone = static, zone
        self.region = static['regions']['zone_'+zone]
        self.rects = keepout_rects(static, perimeter=True)
        self.radius = .26  # chassis + upright small box/arm envelope + clearance
        self.path = None
        from sim.solo_carry_obstacles import RGBObstacleMemory
        self.obstacles = RGBObstacleMemory(managed=self.active_recovery)
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
                               map_sha256=self.map_sha256, amcl_option=amcl_option,
                               drive_model_deadband_v1=drive_model_deadband_v1,
                               carry5_trim_yaw_calibration_v1=carry5_trim_yaw_calibration_v1,
                               trim_calibration=trim_calibration,
                               reloc9_rotation_calibration_v1=reloc9_rotation_calibration_v1,
                               reloc10_rotation_calibration_v1=reloc10_rotation_calibration_v1)

    def issue(self, issued, dt):
        self.loc.issue(issued, dt)

    def observe(self, tops, now):
        raise ValueError('top RGB forbidden for carry control (#366)')

    def observe_own(self, bgr, now, *, camera):
        self.loc.observe_own(bgr, now, camera=camera)

    def refresh_obstacles(self, bgr, pwm, now, *, holding, kind, grasp_pwm):
        self.obstacles.observe(bgr, pwm, self.loc.pose, now, holding=holding,
                               kind=kind, grasp_pwm=grasp_pwm, pose_sigma=self.loc.sigmas())
        self.last_plan = -math.inf  # a newly visible obstacle invalidates the route

    def start(self, now, grip_xy):
        self.started = now
        self.grip_xy = tuple(grip_xy)
        self.travel_heading = self.loc.pose[2] if self.active_recovery else 0.
        if self.active_recovery and self.needs_recovery(now):
            return
        if not self.loc.ready(now):
            self.failure = 'carry_self_pose_unavailable'
            return
        # Fixed map slot candidates, nearest reachable stand-off first. No
        # pickup position or current cargo world position is consulted.
        discs = self.obstacles.discs(now)
        cx, cy = self.region['center_m']; hx, hy = self.region['half_extents_m']
        candidates = [(cx+sx*max(0., hx-.20), cy+sy*max(0., hy-.20))
                      for sx, sy in ((0, 0), (-1, 0), (1, 0), (0, -1), (0, 1))]
        for slot in sorted(candidates, key=lambda p: math.dist(self.loc.pose[:2], p)):
            # Final heading east; grip relation comes from own issued low pose.
            goal = (slot[0]-grip_xy[0]-self.advance_m, slot[1]-grip_xy[1])
            final = (goal[0]+self.advance_m, goal[1])
            retreat = (final[0]-.15, final[1])
            if not (free(goal, discs, self.rects, self.radius) and
                    segment_free(goal, final, discs, self.rects, self.radius) and
                    segment_free(final, retreat, discs, self.rects, self.radius)):
                continue
            path = plan_path(self.loc.pose[:2], goal, self.static['bounds_m'], discs, rects=self.rects, radius=self.radius)
            if path:
                self.slot, self.goal, self.path = slot, goal, path
                break
        if self.path is None:
            if self.active_recovery:
                self.request_recovery(now, 'carry_no_route')
            else:
                self.failure = 'carry_no_static_route'

    def step(self, now):
        if self.active_recovery and self.needs_recovery(now):
            return (0., 0., 0.), False, self.failure
        if self.failure:
            return (0., 0., 0.), False, self.failure
        if not self.loc.ready(now):
            return (0., 0., 0.), False, 'carry_self_pose_stale'
        pose = self.loc.pose
        discs = self.obstacles.discs(now)
        if self.active_recovery and (self.goal is None or not free(self.goal, discs, self.rects, self.radius)):
            self.path = None
            self.start(now, self.grip_xy)  # reselect all five authored slots
            if self.recovery_reason or self.failure:
                return (0., 0., 0.), False, self.failure
        elif not free(self.goal, discs, self.rects, self.radius):
            return (0., 0., 0.), False, 'carry_goal_obstructed'
        distance = math.dist(pose[:2], self.goal)
        if distance <= .025 and abs(wrap(pose[2])) <= .04:
            self.arrived = now
            return (0., 0., 0.), True, None
        if distance <= .025:
            return (0., 0., max(-.1, min(.1, -.6*wrap(pose[2])))), False, None
        if now-self.last_plan >= 1.:
            self.path = plan_path(pose[:2], self.goal, self.static['bounds_m'], discs, rects=self.rects, radius=self.radius)
            self.last_plan = now
        target = waypoint(pose[:2], self.path, discs, self.rects, self.radius)
        if target is None:
            if self.active_recovery:
                self.request_recovery(now, 'carry_no_route')
                return (0., 0., 0.), False, self.failure
            return (0., 0., 0.), False, 'carry_no_static_route'
        if self.active_recovery:
            return self.heading_drive(pose, target, self.travel_heading), False, None
        cmd = proportional_drive(pose, self.goal, target, 0.)
        return (max(-.05, min(.08, cmd['forward'])), max(-.06, min(.06, cmd['left'])),
                max(-.1, min(.1, cmd['turn']))), False, None

    @staticmethod
    def heading_drive(pose, target, heading):
        """Mecanum translation while retaining the current travel heading."""
        x, y, a = pose; dx, dy = target[0]-x, target[1]-y
        forward = math.cos(a)*dx+math.sin(a)*dy
        left = -math.sin(a)*dx+math.cos(a)*dy
        return (max(-.05, min(.08, .9*forward)), max(-.06, min(.06, .9*left)),
                max(-.1, min(.1, .6*wrap(heading-a))))

    def needs_recovery(self, now):
        if self.recovery_reason:
            return True
        sigma = self.loc.sigmas()
        # Reserve 20% of unchanged hard limits for stopping/setdown/backoff.
        if not self.loc.ready(now) or max(sigma[:2]) >= .40 or sigma[2] >= math.radians(16.):
            self.request_recovery(now, 'pose_budget')
            return True
        return False

    def request_recovery(self, now, reason):
        if not self.active_recovery or self.recovery_reason or self.failure:
            return
        self.recovery_reason = reason
        self.recovery_count += 1
        if self.recovery_anchor is not None and math.dist(self.loc.pose[:2], self.recovery_anchor) < .15:
            self.stalled_recoveries += 1
        else:
            self.stalled_recoveries = 0
        self.recovery_anchor = self.loc.pose[:2]
        self.recovery_events.append({'t': now, 'event': 'stop_reobserve', 'reason': reason,
                                     'pose': self.loc.record()})
        if self.recovery_count > 12 or self.stalled_recoveries >= 2:
            self.failure = 'carry_recovery_no_progress'

    def finish_recovery(self, now, fixes_before):
        if self.loc.fixes <= fixes_before or not self.loc.ready(now) or self.needs_budget():
            if self.rank_aware_v1 and self.recovery_count < 12:
                self.recovery_count += 1
                self.recovery_events.append({'t': now, 'event': 'retry_body_views',
                                             'attempt': self.recovery_count})
                return False
            self.failure = 'carry_relocalization_unconfirmed'
            return False
        self.recovery_events.append({'t': now, 'event': 'accepted_replan', 'fixes': self.loc.fixes})
        self.recovery_reason = None
        self.path = None; self.last_plan = -math.inf
        return True

    def needs_budget(self):
        s = self.loc.sigmas()
        return max(s[:2]) >= .40 or s[2] >= math.radians(16.)

    def pickup_route(self, goal, target, kind, now):
        """Allowed body goal; single matching target exemption, no world target memory."""
        if self.needs_recovery(now):
            return (0., 0., 0.)
        x, y, a = self.loc.pose; c, s = math.cos(a), math.sin(a)
        discs = self.obstacles.pickup_discs(now, self.loc.pose, kind, target)
        rects = [(c*(ox-x)+s*(oy-y), -s*(ox-x)+c*(oy-y), hx, hy, angle-a)
                 for ox, oy, hx, hy, angle in self.rects]
        path = plan_path((0., 0.), goal[:2], (-2., 2., -2., 2.), discs, rects=rects, radius=.17)
        if not path:
            self.request_recovery(now, 'pickup_no_route')
            return (0., 0., 0.)
        point = next((p for p in path if math.hypot(*p) >= .06), goal[:2])
        return self.heading_drive((0., 0., 0.), point, goal[2])

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
                'path': self.path, 'static_route_only': False, 'obstacles': self.obstacles.record(),
                'held_world_reads': 0, 'physical_success': None,
                **({'carry7_robust_recovery_v1': True} if self.robust_recovery_v1 else {}),
                **({'carry5_rank_aware_views_v1': True, 'recovery_count': self.recovery_count}
                   if self.rank_aware_v1 else {}),
                **({'recovery_profile': self.recovery_profile, 'recovery_reason': self.recovery_reason,
                    'recovery_events': self.recovery_events} if self.active_recovery else {})}
