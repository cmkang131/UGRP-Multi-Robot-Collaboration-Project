"""Opt-in own-observation Nav2/explore_lite port, default off.

Pinned upstream, retained copyright/license notices and exact line comparison:
third_party/mapfree_navigation_persistence and experiment REFERENCES.md.
No world/scene/truth/model inputs. Contact port is strictly (t, pressed).
"""
import math
import numpy as np
from harness.grid_acceleration import enabled as scalar_rays_enabled, bresenham as scalar_bresenham

from harness.public_navigation.actor import PublicActor
from harness.public_navigation.costmap import from_grid
from harness.public_navigation.follower import command_from_twist, wrap
from harness.public_navigation.stack import PublicNavigator
from harness.public_navigation_recovery import regulated_twist, issued_twist, projection_clear
from harness.self_odom_grid import transform

OPTION = 'public_ros_v3'
RECOVERY = ('clear', 'spin', 'wait', 'backup')


def navigation_output_v3(legacy, *, navigation='off', navigator=None, **kwargs):
    if navigation == 'off':
        return legacy
    if navigation != OPTION or navigator is None:
        raise ValueError('EXPLICIT_PUBLIC_ROS_V3_REQUIRED')
    return navigator.update(**kwargs)


def raytrace_cells(start, end):
    """Nav2 raytraceLine/Bresenham, no clipping, min=0/max=unbounded.

    Tuple coordinates replace flattened unsigned offsets (unbounded own grid).
    Copyright Willow Garage 2008/2013, BSD-3; notice in vendored header.
    """
    if scalar_rays_enabled():
        yield from scalar_bresenham(start,end)
        return
    point = np.array(start, int)
    delta = np.array(end, int)-point
    a = 0 if abs(delta[0]) >= abs(delta[1]) else 1
    b = 1-a
    da, db = abs(int(delta[a])), abs(int(delta[b]))
    sign = np.where(delta > 0, 1, -1)
    error = da//2
    for _ in range(da):
        yield tuple(int(v) for v in point)
        point[a] += sign[a]
        error += db
        if error >= da:
            point[b] += sign[b]
            error -= da
    yield tuple(int(v) for v in point)


class ProgressChecker:
    """Nav2 SimpleProgressChecker (.5m/10s), on FollowPath active clock."""
    def __init__(self):
        self.reset()

    def reset(self):
        self.baseline = None
        self.baseline_t = 0.

    def check(self, pose, active_t):
        xy = np.asarray(pose[:2], float)
        if self.baseline is None or np.linalg.norm(xy-self.baseline) > .5:
            self.baseline, self.baseline_t = xy.copy(), active_t
            return True
        return active_t-self.baseline_t <= 10.


class PersistentNavigator(PublicNavigator):
    def __init__(self):
        super().__init__()
        self.checker = ProgressChecker()
        self.active_t = 0.
        self.context_used = set()
        self.retry = self.round_index = 0
        self.phase = self.phase_pose = None
        self.phase_start = 0.
        self.clear_requested = self.failed = self.finished = False
        self.static_mode = False
        self.last_plan_t = -math.inf

    def event(self, t, reason, **detail):
        self.events.append(dict(t=float(t), reason=reason, **detail))

    def restart_follow(self):
        self.checker.reset()
        self.last_plan_t = -math.inf

    def reset_action(self):
        self.context_used.clear()
        self.retry = self.round_index = 0
        self.phase = self.phase_pose = None
        self.clear_requested = False
        self.restart_follow()

    def action_failed(self, t, reason):
        self.event(t, 'navigation_action_aborted', cause=reason)
        if self.static_mode:
            self.failed = True
            self.phase = None
        else:
            self.abort(t, 'ABORTED_'+reason)
            self.reset_action()  # explore_lite reachedGoal -> makePlan, not global failure

    def begin_phase(self, phase, t):
        self.phase, self.phase_start, self.phase_pose = phase, t, None
        self.clear_requested = phase in ('clear', 'context_clear')
        self.event(t, 'recovery_'+phase, completed_retries=self.retry)

    def failure(self, t, reason, context='controller'):
        if self.phase or self.failed:
            return
        self.event(t, reason)
        if context not in self.context_used:
            self.context_used.add(context)
            self.begin_phase('context_clear', t)
            self.event(t, 'context_clear_'+context)
        elif self.retry >= 6 or self.round_index >= len(RECOVERY):
            self.action_failed(t, 'recovery_exhausted')
        else:
            self.begin_phase(RECOVERY[self.round_index], t)

    def phase_result(self, t, success):
        phase = self.phase
        self.event(t, 'recovery_success' if success else 'recovery_failure', action=phase)
        self.phase = None
        if phase == 'contact_backup':
            if not success:
                self.action_failed(t, 'contact_backup_failed')
            else:
                self.event(t, 'contact_replan')
                self.context_used.clear()
                self.restart_follow()
            return
        if phase == 'context_clear':
            if not success:
                self.action_failed(t, 'context_clear_failed')
            self.restart_follow()
            return
        # Pinned RoundRobin increments index before status dispatch. With default
        # wrap_around=false, reaching the last child returns FAILURE even if that
        # child succeeded. Preserve this source behavior, do not silently repair it.
        self.round_index += 1
        if self.round_index == len(RECOVERY):
            self.action_failed(t, 'round_robin_exhausted')
        elif success:
            self.retry += 1  # RecoveryNode counts only SUCCESS, never RUNNING/FAILURE
            self.context_used.clear()
            self.restart_follow()
        else:
            self.begin_phase(RECOVERY[self.round_index], t)

    def advance_phase(self, pose, t):
        if not self.phase:
            return
        if self.phase_pose is None:
            self.phase_pose = np.array(pose, float)
        elapsed = t-self.phase_start
        done = ((self.phase in ('clear', 'context_clear') and not self.clear_requested)
                or (self.phase == 'wait' and elapsed >= 5.)
                or (self.phase == 'spin' and abs(wrap(pose[2]-self.phase_pose[2])) >= 1.57-.02)
                or (self.phase in ('backup', 'contact_backup') and
                    np.linalg.norm(np.asarray(pose[:2])-self.phase_pose[:2]) >= .30-.01))
        if done:
            self.phase_result(t, True)
        elif self.phase in ('spin', 'backup', 'contact_backup') and elapsed > 10.:
            self.event(t, 'recovery_timeout', action=self.phase)
            self.phase_result(t, False)

    def select_frontier(self, costmap, pose, t):
        # explore.cpp makePlan: re-search each tick; lowest-cost nonblacklist.
        for f in self.core.frontiers(costmap.raw, costmap.origin, costmap.resolution, pose[:2]):
            centre = f[:2]
            if self.blocked(centre, costmap.resolution):
                continue
            same = self.frontier is not None and np.linalg.norm(centre-self.frontier) < .01
            if not same or self.best_distance > f[4]:
                self.best_distance, self.last_progress = f[4], t
            if t-self.last_progress > 30.:
                self.blacklist.append(centre.copy())
                self.event(t, 'progress_timeout_blacklist', target=centre.tolist())
                self.target = self.frontier = None
                self.reset_action()
                continue
            if same:
                return
            yy, xx = np.nonzero(costmap.costs < 253)
            points = costmap.map_to_world(np.column_stack([xx, yy]))
            for idx in np.argsort(np.linalg.norm(points-centre, axis=1), kind='stable'):
                if np.linalg.norm(points[idx]-centre) > .5:
                    break
                path = self.plan_to(costmap, pose, points[idx])
                if path:
                    self.reset_action()
                    self.target, self.path, self.frontier = points[idx], path, centre.copy()
                    self.heading = math.atan2(centre[1]-self.target[1], centre[0]-self.target[0])
                    self.event(t, 'frontier_selected', target=centre.tolist())
                    return
            self.blacklist.append(centre.copy())
            self.event(t, 'ABORTED_unreachable', target=centre.tolist())
        self.target = self.frontier = None
        self.finished = True
        self.event(t, 'exploration_finished_no_frontier')

    def update(self, costmap, pose, t, static_goal=None):
        pose = np.asarray(pose, float)
        self.static_mode = static_goal is not None
        if self.failed or self.finished:
            return self.idle(pose, 'recovery_exhausted' if self.failed else 'exploration_finished')
        # Frontier manager continues its 30s timer during the navigation action.
        if not self.static_mode:
            self.select_frontier(costmap, pose, t)
        elif self.target is None:
            self.target = np.asarray(static_goal, float)
            self.restart_follow()
        self.advance_phase(pose, t)
        if self.phase or self.failed or self.finished:
            return self.idle(pose, 'recover_'+self.phase if self.phase else 'navigation_stopped')
        if self.target is None:
            return self.idle(pose, 'next_frontier')
        if self.static_mode:
            self.heading = math.atan2(self.target[1]-pose[1], self.target[0]-pose[0])
        self.path = self.plan_to(costmap, pose, self.target)
        self.last_plan_t = t
        if not self.path:
            self.failure(t, 'planner_failed', 'planner')
            return self.idle(pose, 'no_path')
        # A successful planner tick halts its contextual RecoveryNode.
        self.context_used.discard('planner')
        return dict(status='public_static' if self.static_mode else 'public_frontier',
                    path_m=self.path, heading_rad=float(self.heading), doors=[])

    @staticmethod
    def idle(pose, status):
        return dict(status=status, path_m=[], heading_rad=float(pose[2]), doors=[])

    def contact(self, t):
        if self.failed:
            return
        self.event(t, 'binary_contact_stop')
        self.begin_phase('contact_backup', t)

    def command(self, costmap, pose, plan, t):
        self.advance_phase(pose, t)
        zero = command_from_twist(np.zeros(3), t)
        if self.failed or self.finished:
            return zero
        if not self.phase:
            if t-self.last_plan_t >= 1.-1e-8:
                updated = self.update(costmap, pose, t, self.target if self.static_mode else None)
                if plan['status'] != 'goal_reobserve':
                    plan = updated
            if not self.phase:
                self.active_t += .1
                if not self.checker.check(pose, self.active_t):
                    self.failure(t, 'controller_no_progress')
        if self.phase:
            twist = np.zeros(3)
            if self.phase == 'spin':
                twist[2] = .5
            elif self.phase in ('backup', 'contact_backup'):
                twist[0] = -.15
            horizon, limit = 2., math.inf
        else:
            twist = regulated_twist(plan['path_m'], pose, plan['heading_rad'])
            remaining = np.linalg.norm(np.asarray(plan['path_m'][-1])-pose[:2]) if plan['path_m'] else math.inf
            horizon, limit = 1., min(.20, remaining) if abs(twist[0]) > 1e-9 else math.inf
        cmd = command_from_twist(twist, t)
        actual = issued_twist(cmd)
        if np.any(abs(actual) > 1e-9) and not projection_clear(costmap, pose, actual, distance_limit=limit, horizon=horizon):
            self.event(t, 'predicted_footprint_collision', action=self.phase or 'follow')
            if self.phase in ('spin', 'backup', 'contact_backup'):
                self.phase_result(t, False)
            else:
                self.failure(t, 'controller_collision')
            return zero
        return cmd


class PersistentActor(PublicActor):
    def __init__(self, condition, static_grid=None, static_goal=None, *, navigation='off'):
        if navigation != OPTION:
            raise ValueError('EXPLICIT_PUBLIC_ROS_V3_REQUIRED')
        super().__init__(condition, static_grid, static_goal, navigation='public_ros_v1')
        self.option, self.navigator = OPTION, PersistentNavigator()
        self.navigator.static_mode = static_goal is not None
        self.contact_pressed = False

    def receive(self, observation, patches):
        self.grid.observe(**observation, pose=self.odom.pose)  # schema, identity, duplicate checks
        cells = {}
        for field in ('floor_xy', 'wall_xy'):
            points = transform(np.asarray(observation[field], float).reshape(-1, 2), self.odom.pose)
            cells[field] = {self.grid.cell(p) for p in points}
        # Nav2 clear-before-mark. Camera adaptation: only current visible-floor
        # support is cleared, NOT every unobserved cell on a synthetic lidar ray.
        origin = self.grid.cell(self.odom.pose[:2])
        free, hits = cells['floor_xy'], cells['wall_xy']
        cleared = set()
        for endpoint in free:
            for cell in raytrace_cells(origin, endpoint):
                if cell in hits:
                    break
                if cell in free:
                    cleared.add(cell)
        for cell in cleared-self.static_hits:
            self.latest[cell] = False
            self.grid.odds[cell] = -abs(self.grid.odds.get(cell, 1.)) or -1.
        for cell in hits:
            self.latest[cell] = True
            self.grid.odds[cell] = max(1., self.grid.odds.get(cell, 0.))
        for cell, occupied in self.latest.items():
            if occupied:
                self.grid.odds[cell] = max(1., self.grid.odds.get(cell, 0.))
        self.last_patches = self.goal.add(patches, self.t, observation['frame_id'], self.odom.pose)
        return self.last_patches

    def receive_contact(self, sample):
        if set(sample) != {'t', 'pressed'} or type(sample['pressed']) is not bool or not math.isfinite(sample['t']):
            raise ValueError('BINARY_CONTACT_ONLY')
        if abs(sample['t']-self.t) > 1e-6:
            raise ValueError('CONTACT_TIME_MISMATCH')
        rising = sample['pressed'] and not self.contact_pressed
        self.contact_pressed = sample['pressed']
        if rising:
            # Kobuki bumper2pc: fixed front bumper geometry + OWN DR only.
            cell = self.grid.cell(transform([[.12, 0.]], self.odom.pose)[0])
            self.latest[cell] = True
            self.grid.odds[cell] = max(1., self.grid.odds.get(cell, 0.))
            self.grid.wall_frames.setdefault(cell, set()).add(('bumper', self.t))
            self.navigator.contact(self.t)
            self.odom.command(dict(t=self.t, kind='stop'))
        return rising

    def clear_obstacles(self):
        # Reset derived layer only. Persistent evidence survives per user requirement.
        self.navigator.clear_requested = False
        self.navigator.event(self.t, 'costmap_rebuilt_persistent_reapplied',
                             observed_hits=sum(self.latest.values()))

    def plan(self):
        if self.navigator.clear_requested:
            self.clear_obstacles()
        pose = np.asarray(self.odom.pose)
        self.costmap = from_grid(self.grid, pose, self.latest, self.static_hits)
        # ObstacleLayer footprint clear is temporary; only authored static hits restored.
        for cell in self.static_hits:
            ij = self.costmap.world_to_map(self.grid.point(cell))
            if ij is not None:
                self.costmap.raw[ij[1], ij[0]] = 254
        self.costmap.costs = self.costmap.inflate()
        plan = navigation_output_v3(None, navigation=self.option, navigator=self.navigator,
            costmap=self.costmap, pose=pose, t=self.t, static_goal=self.static_goal)
        if self.last_patches and not self.navigator.phase and not self.navigator.failed:
            target = np.asarray(self.last_patches[-1]['center_odom_m'])
            delta = target-pose[:2]
            point = pose[:2]+.12*delta/max(np.linalg.norm(delta), 1e-9)
            path = self.navigator.plan_to(self.costmap, pose, point)
            if path:
                plan = dict(status='goal_reobserve', path_m=path,
                    heading_rad=math.atan2(delta[1], delta[0]), doors=[])
        plan['doors'] = self.doors.update(self.grid, pose)
        self.counts[plan['status']] = self.counts.get(plan['status'], 0)+1
        return plan

    def command(self, plan):
        if self.navigator.clear_requested:
            plan = self.plan()  # synchronous service completes before retrying FollowPath
        return self.navigator.command(self.costmap, self.odom.pose, plan, self.t)
