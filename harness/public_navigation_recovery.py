"""Opt-in Nav2 recovery adapter. No scene, simulator, truth, or provider inputs.

Nav2 BT ordering and RPP regulation are ports, not a ROS server deployment.
Pinned Apache-2.0 sources: third_party/mapfree_navigation_recovery/SOURCES.json.
"""
import copy
import math

import numpy as np

from harness.public_navigation.actor import PublicActor
from harness.public_navigation.costmap import from_grid
from harness.public_navigation.follower import follow_twist, command_from_twist, wrap
from harness.public_navigation.stack import PublicNavigator
from harness.self_odom_grid import motion_profiles

OPTION = 'public_ros_v2'
RECOVERY = ('clear', 'spin', 'wait', 'backup')


def navigation_output_v2(legacy, *, navigation='off', navigator=None, **kwargs):
    if navigation == 'off':
        return legacy
    if navigation != OPTION or navigator is None:
        raise ValueError('EXPLICIT_PUBLIC_ROS_V2_REQUIRED')
    return navigator.update(**kwargs)


def regulated_twist(path, pose, heading):
    twist = follow_twist(path, pose, heading)
    if abs(twist[0]) > 1e-9:
        # Nav2 regulation_functions::curvatureConstraint: v *= radius/min_radius.
        # UGRP scale: minimum turning radius equals .24m chassis length.
        radius = abs(twist[0]/twist[2]) if abs(twist[2]) > 1e-9 else math.inf
        twist *= min(1., radius/.24)
    return twist


def issued_twist(command):
    return np.asarray(motion_profiles()['motion']['gain']) @ np.array(
        [command['forward'], command['left'], command['turn']])


def projection_clear(costmap, pose, twist, *, distance_limit=math.inf, horizon=1.):
    """RPP checks current footprint and stops projection at the carrot, never beyond it."""
    predicted = np.array(pose, float)
    if not costmap.pose_clear(predicted):
        return False
    for _ in range(math.ceil(horizon/.05)):
        c, s = math.cos(predicted[2]), math.sin(predicted[2])
        predicted += np.array([c*twist[0]-s*twist[1], s*twist[0]+c*twist[1], twist[2]])*.05
        if np.linalg.norm(predicted[:2]-pose[:2]) > distance_limit:
            break
        if not costmap.pose_clear(predicted):
            return False
    return True


class RecoveryNavigator(PublicNavigator):
    def __init__(self):
        super().__init__()
        self.context_used = set()
        self.retry = 0
        self.round_index = 0
        self.phase = None
        self.phase_start = None
        self.phase_pose = None
        self.clear_requested = False
        self.failed = False

    def event(self, t, reason, **detail):
        self.events.append(dict(t=float(t), reason=reason, **detail))

    def failure(self, t, reason, context='controller'):
        if self.phase or self.failed:
            return
        self.event(t, reason)
        if context not in self.context_used:
            self.context_used.add(context)
            self.phase = 'context_clear'
            self.clear_requested = True
            self.event(t, 'context_clear_'+context)
        elif self.retry < 6:
            self.phase = RECOVERY[self.round_index % len(RECOVERY)]
            self.round_index += 1
            self.retry += 1
            self.clear_requested = self.phase == 'clear'
            self.event(t, 'recovery_'+self.phase, retry=self.retry)
            # Each whole pipeline retry admits its one contextual retry again.
            self.context_used.clear()
        else:
            self.failed = True
            self.abort(t, 'recovery_exhausted')
        self.phase_start, self.phase_pose = t, None

    def update(self, costmap, pose, t, static_goal=None):
        if self.failed:
            return dict(status='recovery_exhausted', path_m=[], heading_rad=float(pose[2]), doors=[])
        if self.phase:
            if self.phase_pose is None:
                self.phase_pose = np.array(pose, float)
            elapsed = t-self.phase_start
            done = ((self.phase in ('clear', 'context_clear') and not self.clear_requested)
                    or (self.phase == 'wait' and elapsed >= 5.)
                    or (self.phase == 'spin' and abs(wrap(pose[2]-self.phase_pose[2])) >= 1.57-.02)
                    or (self.phase == 'backup' and np.linalg.norm(np.asarray(pose[:2])-self.phase_pose[:2]) >= .30-.01))
            if done or (self.phase in ('spin','backup') and elapsed > 10.):
                self.event(t, 'recovery_done' if done else 'recovery_timeout', action=self.phase)
                self.phase = None
                self.last_progress = t
            else:
                return dict(status='recover_'+self.phase, path_m=[], heading_rad=float(pose[2]), doors=[])
        before = len(self.events)
        result = super().update(costmap, pose, t, static_goal)
        reasons = {e['reason'] for e in self.events[before:]}
        if 'ABORTED_no_path' in reasons:
            self.failure(t, 'planner_failed', 'planner')
        elif 'progress_timeout' in reasons:
            self.failure(t, 'controller_no_progress')
        return result

    def command(self, costmap, pose, plan, t):
        if self.failed:
            return command_from_twist(np.zeros(3), t)
        if self.phase:
            if self.phase_pose is None:
                self.phase_pose = np.array(pose, float)
            twist = np.zeros(3)
            if self.phase == 'spin':
                twist[2] = .5
            elif self.phase == 'backup':
                twist[0] = -.15
            limit, horizon = math.inf, 2.
        else:
            twist = regulated_twist(plan['path_m'], pose, plan['heading_rad'])
            remaining = np.linalg.norm(np.asarray(plan['path_m'][-1])-pose[:2]) if plan['path_m'] else math.inf
            limit = min(.20, remaining) if abs(twist[0]) > 1e-9 else math.inf
            horizon = 1.
        command = command_from_twist(twist, t)
        actual = issued_twist(command)  # include command saturation before collision prediction
        if np.any(abs(actual) > 1e-9) and not projection_clear(costmap, pose, actual, distance_limit=limit, horizon=horizon):
            self.event(t, 'predicted_footprint_collision', action=self.phase or 'follow')
            if self.phase in ('spin','backup'):
                self.event(t, 'recovery_collision_rejected', action=self.phase)
                self.phase = None
                self.failure(t, 'controller_failed_after_recovery')
            else:
                self.failure(t, 'controller_collision')
            return command_from_twist(np.zeros(3), t)
        return command


class RecoveryActor(PublicActor):
    def __init__(self, condition, static_grid=None, static_goal=None, *, navigation='off'):
        if navigation != OPTION:
            raise ValueError('EXPLICIT_PUBLIC_ROS_V2_REQUIRED')
        super().__init__(condition, static_grid, static_goal, navigation='public_ros_v1')
        self.option = OPTION
        self.navigator = RecoveryNavigator()
        self.current_observation = None
        self.current_patches = []

    def receive(self, observation, patches):
        self.current_observation = copy.deepcopy(observation)
        self.current_patches = copy.deepcopy(patches)
        return super().receive(observation, patches)

    def clear_obstacles(self):
        # Nav2 ClearCostmap resets the resettable obstacle layer, not the static layer.
        # Preserve measured free support; forgotten occupied cells return to unknown.
        for cell in list(self.grid.odds):
            if self.grid.odds[cell] > 0 and cell not in self.static_hits:
                self.grid.odds.pop(cell)
                self.grid.wall_frames.pop(cell, None)
        self.latest.clear()
        if self.current_observation is not None:
            # Reinsert current sensor data without a second B temporal observation.
            from harness.self_odom_grid import transform
            for field, hit in [('floor_xy',False),('wall_xy',True)]:
                for point in transform(np.asarray(self.current_observation[field]).reshape(-1,2), self.odom.pose):
                    self.latest[self.grid.cell(point)] = hit
        self.navigator.clear_requested = False

    def plan(self):
        if self.navigator.clear_requested:
            self.clear_obstacles()
        pose = np.asarray(self.odom.pose)
        self.costmap = from_grid(self.grid, pose, self.latest, self.static_hits)
        # Footprint clearing must not erase authored walls or measured obstacle hits.
        for cell in self.static_hits | {c for c, hit in self.latest.items() if hit}:
            ij = self.costmap.world_to_map(self.grid.point(cell))
            if ij is not None:
                self.costmap.raw[ij[1],ij[0]] = 254
        self.costmap.costs = self.costmap.inflate()
        plan = navigation_output_v2(None, navigation=self.option, navigator=self.navigator,
            costmap=self.costmap, pose=pose, t=self.t, static_goal=self.static_goal)
        # Same detector/confirmation thresholds for both conditions, including baseline.
        if self.last_patches and not self.navigator.phase and not self.navigator.failed:
            target = np.asarray(self.last_patches[-1]['center_odom_m'])
            delta = target-pose[:2]
            point = pose[:2]+.12*delta/max(np.linalg.norm(delta),1e-9)
            path = self.navigator.plan_to(self.costmap,pose,point)
            if path:
                plan = dict(status='goal_reobserve',path_m=path,
                    heading_rad=math.atan2(delta[1],delta[0]),doors=[])
        plan['doors'] = self.doors.update(self.grid,pose)
        self.counts[plan['status']] = self.counts.get(plan['status'],0)+1
        return plan
