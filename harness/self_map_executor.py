"""Opt-in own-RGB exploration; optional authored map, never plant/evaluator inputs."""
import math
from collections import Counter

import numpy as np

from harness.active_wall_mapping import pulse_command
from harness.own_map_navigation import Footprint, astar, footprint_clearance, frontier_candidates
from harness.public_navigation.costmap import Costmap
from harness.public_navigation.follower import follow_twist
from harness.public_navigation_recovery import issued_twist
from harness.public_navigation_unknown import UnknownCostmap
from harness.self_map_integration import OPTION as MAP_OPTION, Options, make_mapper

OPTION = 'frontier_drive_v1'
# Overlapping command-only pan views, retaining the existing SEARCH arm/camera.
PANS = (1500, 1750, 2000, 1750, 1500, 1250, 1000, 1250, 1500)


class SweepFrame:
    """Check map-frame footprints while counting command-frame yaw progress."""
    def __init__(self, costmap, yaw_offset):
        self.costmap, self.yaw_offset = costmap, yaw_offset

    def pose_clear(self, pose):
        pose = np.array(pose, float)
        pose[2] += self.yaw_offset
        return self.costmap.pose_clear(pose)


def make_executor(legacy=None, *, self_map_executor='off', **kwargs):
    if self_map_executor == 'off':
        return legacy
    if self_map_executor != OPTION:
        raise ValueError('UNKNOWN_SELF_MAP_EXECUTOR')
    return SelfMapExecutor(**kwargs)


class SelfMapExecutor:
    def __init__(self, robot_id, *, start_time=0., cap_s=180., mapper=None, sweep=None,
                 bootstrap='off', initial_sweep='off', recovery_profile='off', static_map=None):
        if not math.isfinite(cap_s) or not 1. <= cap_s <= 300.:
            raise ValueError('FINITE_SELF_MAP_CAP_1_TO_300_REQUIRED')
        self.robot_id, self.started, self.cap_s = robot_id, float(start_time), float(cap_s)
        if initial_sweep not in ('off', 'required_360_v1'):
            raise ValueError('UNKNOWN_INITIAL_SWEEP')
        self.initial_sweep = initial_sweep
        self.initial_sweep_complete = initial_sweep == 'off'
        self.mapper = mapper if mapper is not None else make_mapper(robot_id=robot_id,
            start_time=start_time, options=Options(self_map_integration=MAP_OPTION,
                pose_rebuild='refit_history_v1', navigation_support='current_footprint_v1',
                bootstrap=bootstrap, recovery_profile=recovery_profile), static_map=static_map)
        self.recovery = self.mapper.options.recovery_profile != 'off'
        if sweep is None:
            # Existing E2E18/egomap arrival -> bounded full-body observation sweep.
            from harness.active_frontier_cycle import CycleNavigator
            sweep = CycleNavigator()
        self.sweep = sweep
        self.stage, self.stop_reason = 'pan', None
        self.pan_index, self.next_pan = 0, start_time+1.
        self.next_control = start_time
        self.target = None
        self.goal_start = self.progress_t = start_time
        self.progress_xy = None
        self.visited, self.events = [], []
        self.attempts = Counter()
        self.last_rebuild = 0
        self.recovery_started = None
        self.recovery_pans = None
        self.recovery_attempts = 0

    @property
    def done(self):
        return self.stop_reason is not None

    def command(self, row):
        """Only call after the plant accepted this issued command."""
        self.mapper.command(row)

    def event(self, t, reason, **kw):
        self.events.append(dict(t=float(t), reason=reason, **kw))

    def look(self, t, reason):
        if self.recovery and self.stage in ('pan', 'spin'):
            return  # an in-flight observation is never restarted by a revision
        self.target = None
        self.stage, self.pan_index, self.next_pan = 'pan', 0, t
        self.event(t, 'lookaround_requested', cause=reason)

    def relocalize(self, t, row, reason):
        if not self.recovery:
            return self.look(t, reason)
        if self.recovery_started is None:
            self.recovery_started = t
        self.recovery_attempts += 1
        candidate = row.get('recovery_candidate') or {}
        self.recovery_pans = candidate.get('pans', [1500, 1000, 2000, 1500])
        self.look(t, reason)
        self.event(t, 'selfmap4_relocalization', cause=reason,
                   pans=self.recovery_pans, attempt=self.recovery_attempts)

    def costmap(self, pose, *, spin=False):
        grid = self.mapper.planning_grid()
        state, lo = grid.dense(pose, pad_m=1.)
        raw = np.where(state == 0, 255, np.where(state > 0, 254, 0)).astype(np.uint8)
        # Existing unknown policy is confined to in-place observation rotations.
        # Translation requires an entirely observed swept footprint.
        return (UnknownCostmap if spin else Costmap)(raw, lo*grid.resolution, grid.resolution)

    def path_to(self, pose, target):
        grid = self.mapper.planning_grid()
        _, clear, distance, lo = footprint_clearance(grid, Footprint(),
            self.mapper.nav_options.pose_margin_m, yaw=pose[2])
        path = astar(clear, np.asarray(grid.cell(pose[:2]))-lo,
                     np.asarray(grid.cell(target))-lo, grid.resolution, distance)
        return [] if path is None else [grid.point(np.asarray(c)+lo).tolist() for c in path]

    def receive(self, *, robot_id, t, frame_id, rgb, sha256=''):
        if self.done:
            return dict(t=float(t), kind='hold'), dict(stage='stopped', stop_reason=self.stop_reason)
        row = self.mapper.receive(robot_id=robot_id, t=t, frame_id=frame_id, rgb=rgb, sha256=sha256)
        pose = np.asarray(row['pose'])
        command = None
        if self.recovery and self.recovery_started is not None:
            # A deadline belongs to the recovery episode, not each pan/rebuild.
            if t-self.recovery_started >= 20. or self.recovery_attempts > 3:
                self.stop_reason = 'selfmap4_relocalization_exhausted'
                self.stage = 'stopped'
                command = dict(t=float(t), kind='hold')
                self.event(t, self.stop_reason, elapsed_s=t-self.recovery_started)
                return command, dict(**row, stage=self.stage,
                    executor_stop_reason=self.stop_reason, issued_command=command,
                    frontier_arrivals=len(self.visited))
        # A terminal observation may arrive halfway through a calibrated pulse.
        # Let its <=0.2s interval finish before the normal completion hold.
        complete = row['complete'] and self.initial_sweep_complete and t >= self.next_control-1e-8
        if complete or t-self.started >= self.cap_s-1e-8:
            self.stop_reason = 'self_map_complete' if complete else 'sim_time_cap'
            self.stage = 'stopped'
            command = dict(t=float(t), kind='hold')
        elif t >= self.next_control-1e-8:
            self.next_control = t+.2  # preserve calibrated 0.2s pulse/tail intervals
            command = dict(t=float(t), kind='hold')
            if self.started+self.cap_s-t < .2-1e-8:
                return command, dict(**row, stage=self.stage, executor_stop_reason=None,
                                     issued_command=command, frontier_arrivals=len(self.visited))
            revision = row.get('rebuild_commits', 0) if self.recovery else row['rebuild_count']
            if revision != self.last_rebuild:
                self.last_rebuild = revision
                if not self.recovery:
                    self.attempts.clear()  # legacy targets belong to the old revision
                    self.visited.clear()
                self.target = None
                if self.initial_sweep_complete:
                    self.look(t, 'pose_map_revision')
            if self.stage == 'pan':
                if t >= self.next_pan-1e-8:
                    pans = self.recovery_pans or PANS
                    if self.pan_index < len(pans):
                        command = dict(t=float(t), kind='look', pan_pulse=pans[self.pan_index])
                        self.pan_index += 1
                        self.next_pan = t+1.
                    else:
                        self.stage = 'spin'
                        self.sweep.request_sweep(t, 'selfmap_observe')
                        self.sweep.start_sweep(np.asarray(self.mapper.odom.pose), t)
            elif self.stage == 'spin':
                # Rotation progress uses issued-command odometry, never SLAM jumps.
                odom_pose = np.asarray(self.mapper.odom.pose)
                spin_pose = pose.copy()
                spin_pose[2] = odom_pose[2]
                costmap = self.costmap(pose, spin=True)
                sweep_frame = SweepFrame(costmap, pose[2]-odom_pose[2])
                request = self.sweep.command(sweep_frame, spin_pose, {}, t)
                twist = issued_twist(request)
                command, _ = pulse_command(twist, t, costmap=costmap,
                    pose=pose, motion_model=self.mapper.options.motion_model)
                if self.sweep.phase != 'sensor_sweep':
                    receipt = self.sweep.events[-1]
                    if self.initial_sweep != 'off' and receipt.get('reason') != 'sensor_sweep_completed':
                        if self.recovery:
                            self.stage = 'select'
                        self.look(t, 'incomplete_sweep_retry')
                    else:
                        self.initial_sweep_complete = True
                        self.stage = 'select'
                        self.event(t, 'lookaround_finished', sweep=receipt)
            elif self.stage in ('select', 'drive'):
                if not self.initial_sweep_complete:
                    self.look(t, 'initial_sweep_required')
                elif not row['map_updated']:
                    if not self.recovery or row['insertion_blockers'] != ['camera_unsettled']:
                        self.relocalize(t, row, 'visual_pose_unavailable')
                else:
                    if self.target is None:
                        candidates = frontier_candidates(self.mapper.planning_grid(), pose,
                            self.mapper.nav_options, recent=self.visited)
                        candidates = [c for c in candidates if self.attempts[tuple(c['target_m'])] < 3]
                        if candidates:
                            self.target = candidates[0]
                            self.attempts[tuple(self.target['target_m'])] += 1
                            self.goal_start = self.progress_t = t
                            self.progress_xy = pose[:2].copy()
                            self.stage = 'drive'
                            self.event(t, 'frontier_selected', target=self.target)
                        else:
                            self.relocalize(t, row, 'no_reachable_frontier_not_completion')
                    if self.target is not None:
                        target = self.target['target_m']
                        if np.linalg.norm(pose[:2]-target) <= .05:
                            self.visited.append([*target, self.target['heading_rad']])
                            self.event(t, 'frontier_arrival', target=target)
                            self.look(t, 'arrival')
                        else:
                            if np.linalg.norm(pose[:2]-self.progress_xy) >= .05:
                                self.progress_xy, self.progress_t = pose[:2].copy(), t
                                if self.recovery:
                                    self.recovery_started = None
                                    self.recovery_attempts = 0
                                    self.recovery_pans = None
                            path = self.path_to(pose, target)
                            if not path or t-self.progress_t >= 10. or t-self.goal_start >= 30.:
                                self.relocalize(t, row, 'path_blocked_or_no_progress')
                            else:
                                twist = follow_twist(path, pose, self.target['heading_rad'])
                                command, pulse = pulse_command(twist, t, costmap=self.costmap(pose),
                                    pose=pose, motion_model=self.mapper.options.motion_model,
                                    translation_policy='forward_only_v1')
                                row['executed_path_m'], row['pulse'] = path, pulse
        if self.initial_sweep != 'off':
            row = dict(row, initial_sweep_complete=self.initial_sweep_complete)
            if not self.initial_sweep_complete:
                row.update(complete=False, stop_reason=None,
                           completion_blockers=[*row['completion_blockers'], 'initial_sweep_required'])
        return command, dict(**row, stage=self.stage, executor_stop_reason=self.stop_reason,
                             issued_command=command, frontier_arrivals=len(self.visited))
