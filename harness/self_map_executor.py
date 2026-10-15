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
                 bootstrap='off', initial_sweep='off', recovery_profile='off', static_map=None, revision_gate='off', multiframe_registration='off', correction_safety='off', active_relocalization='off',
                 reloc9_rotation_calibration_v1=False, reloc9_wall_height_guard_v1=False,
                 reloc10_settle_v1=False, reloc10_registration_v1=False, reloc11_wall_field_v1=False, reloc11_low_contrast_v1=False, reloc12_raw_cov_gate_v1=False, reloc12_ransac_hypotheses_v1=False, reloc13_execution_cov_v1=False, reloc13_execution_frame_v1=False, reloc13_live_r7_v1=False, reloc14_continuous_tracking_v1=False, reloc14_compute_budget_v1=False, reloc15_pose_handoff_v1=False, reloc15_update_budget_v1=False, reloc17_servo_wait_v1=False, reloc18_innovation_v1=False):
        if not math.isfinite(cap_s) or not 1. <= cap_s <= 300.:
            raise ValueError('FINITE_SELF_MAP_CAP_1_TO_300_REQUIRED')
        if type(reloc10_settle_v1) is not bool:
            raise ValueError('reloc10 settle must be bool')
        if type(reloc17_servo_wait_v1) is not bool:
            raise ValueError('reloc17 servo wait must be bool')
        from harness.reloc17_servo_wait import ServoWait
        self.servo_wait = ServoWait() if reloc17_servo_wait_v1 else None
        self.compute_budget = reloc14_compute_budget_v1
        self.reloc10_settle = reloc10_settle_v1
        self.turn_settler = None
        self.robot_id, self.started, self.cap_s = robot_id, float(start_time), float(cap_s)
        if initial_sweep not in ('off', 'required_360_v1'):
            raise ValueError('UNKNOWN_INITIAL_SWEEP')
        self.initial_sweep = initial_sweep
        self.initial_sweep_complete = initial_sweep == 'off'
        self.mapper = mapper if mapper is not None else make_mapper(robot_id=robot_id,
            start_time=start_time, options=Options(self_map_integration=MAP_OPTION,
                pose_rebuild='refit_history_v1', navigation_support='current_footprint_v1',
                bootstrap=bootstrap, recovery_profile=recovery_profile,
                revision_gate=revision_gate, multiframe_registration=multiframe_registration,
                correction_safety=correction_safety, active_relocalization=active_relocalization,
                reloc9_rotation_calibration_v1=reloc9_rotation_calibration_v1,
                reloc9_wall_height_guard_v1=reloc9_wall_height_guard_v1,
                reloc10_registration_v1=reloc10_registration_v1,
                reloc11_wall_field_v1=reloc11_wall_field_v1,
                reloc11_low_contrast_v1=reloc11_low_contrast_v1,
                reloc12_raw_cov_gate_v1=reloc12_raw_cov_gate_v1,
                reloc12_ransac_hypotheses_v1=reloc12_ransac_hypotheses_v1,
                reloc13_execution_cov_v1=reloc13_execution_cov_v1,
                reloc13_execution_frame_v1=reloc13_execution_frame_v1, reloc13_live_r7_v1=reloc13_live_r7_v1,
                reloc14_continuous_tracking_v1=reloc14_continuous_tracking_v1,
                reloc14_compute_budget_v1=reloc14_compute_budget_v1,reloc15_pose_handoff_v1=reloc15_pose_handoff_v1,reloc15_update_budget_v1=reloc15_update_budget_v1,reloc18_innovation_v1=reloc18_innovation_v1), static_map=static_map)
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
        self.active_view = None
        self.active_headings = []
        self.active_count = 0
        self.active_stage = 'arm'
        self.active_until = start_time

    @property
    def done(self):
        return self.stop_reason is not None

    def command(self, row):
        """Only call after the plant accepted this issued command."""
        if self.servo_wait is not None:
            self.servo_wait.issued(row, self.mapper.servo)
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
        if self.mapper.options.active_relocalization != 'off':
            self.stage = 'active_reloc8'
            self.active_view = None; self.active_count = 0; self.active_stage = 'arm'
            self.mapper.registration.begin_sweep(t)
        self.event(t, 'selfmap4_relocalization', cause=reason,
                   pans=self.recovery_pans, attempt=self.recovery_attempts)

    def costmap(self, pose, *, spin=False):
        grid = self.mapper.planning_grid()
        state, lo = grid.dense(pose, pad_m=1.)
        raw = np.where(state == 0, 255, np.where(state > 0, 254, 0)).astype(np.uint8)
        # Existing unknown policy is confined to in-place observation rotations.
        # Translation requires an entirely observed swept footprint.
        return (UnknownCostmap if spin else Costmap)(raw, lo*grid.resolution, grid.resolution)

    def active_look(self, t, pose):
        """One map/hypothesis-chosen view at a time; existing pulse safety stays."""
        from harness.active_relocalization import next_view, LOOK, wrap
        hold = dict(t=float(t), kind='hold')
        if t < self.active_until-1e-8:
            return hold
        if self.active_stage == 'arm':
            for servo in (1, 4, 5, 3):
                if self.mapper.servo.get(servo) != LOOK[servo]:
                    self.active_until = t+1.
                    return dict(t=float(t), kind='arm', servo_id=servo, pulse=LOOK[servo])
            self.active_stage = 'plan'
        if self.active_view is None:
            reg = self.mapper.registration
            row = reg.last
            world = row.get('world_pose')
            covariance = row.get('covariance')
            if world is None or covariance is None:
                self.stage = 'select'
                return hold
            self.active_view = next_view(reg.static, world, covariance,
                hypotheses=reg.active_hypotheses, previous_headings=self.active_headings)
            self.active_target = float(self.mapper.odom.pose[2])+math.radians(self.active_view['body_yaw_deg'])
            if self.reloc10_settle:
                from sim.settle_pulse import PulseSettler
                self.turn_settler = PulseSettler(math.radians(2))
            self.active_stage = 'turn'
            self.event(t, 'reloc8_view_planned', view=self.active_view)
            self.active_until = t+.8
            return dict(t=float(t), kind='look', pan_pulse=self.active_view['pan_pulse'])
        if self.active_stage == 'turn':
            error = float(wrap(self.active_target-self.mapper.odom.pose[2]))
            if self.reloc10_settle:
                from harness.reloc10_settle import settle_turn
                command, receipt = settle_turn(self.turn_settler, error, t,
                    costmap=self.costmap(pose, spin=True), pose=pose,
                    motion_model=self.mapper.options.motion_model,
                    native_primitives=self.mapper.options.reloc14_continuous_tracking_v1)
                self.event(t, 'reloc10_settle', settle_reason=receipt.get('reason'),
                           **{k:v for k,v in receipt.items() if k != 'reason'})
                if not receipt['settled']:
                    return command
            elif abs(error) > math.radians(2):
                costmap = self.costmap(pose, spin=True)
                command, _ = pulse_command(np.array([0., 0., math.copysign(.35, error)]), t,
                    costmap=costmap, pose=pose, motion_model=self.mapper.options.motion_model,
                    native_primitives=self.mapper.options.reloc14_continuous_tracking_v1)
                return command
            self.active_stage = 'dwell'; self.active_until = t+.8
            return hold
        self.active_headings = (self.active_headings+[self.active_view['heading_rad']])[-6:]
        self.event(t, 'reloc8_view_observed', view=self.active_view, predictions_are_observations=False)
        self.active_view = None; self.active_count += 1; self.active_stage = 'plan'
        if self.active_count >= 3:
            self.mapper.registration.end_sweep()
            self.stage = 'select'
        return hold

    def path_to(self, pose, target):
        grid = self.mapper.planning_grid()
        _, clear, distance, lo = footprint_clearance(grid, Footprint(),
            self.mapper.nav_options.pose_margin_m, yaw=pose[2])
        path = astar(clear, np.asarray(grid.cell(pose[:2]))-lo,
                     np.asarray(grid.cell(target))-lo, grid.resolution, distance, compute_budget_v1=self.compute_budget)
        return [] if path is None else [grid.point(np.asarray(c)+lo).tolist() for c in path]

    def receive(self, *, robot_id, t, frame_id, rgb, sha256=''):
        if self.done:
            return dict(t=float(t), kind='hold'), dict(stage='stopped', stop_reason=self.stop_reason)
        row = self.mapper.receive(robot_id=robot_id, t=t, frame_id=frame_id, rgb=rgb, sha256=sha256)
        if row.get('quarantine_release') is not None:
            self.recovery_started = None; self.recovery_attempts = 0; self.recovery_pans = None
            self.target = None; self.stage = 'select'
            self.event(t, 'selfmap6_quarantine_released', receipt=row['quarantine_release'])
        pose = np.asarray(row['pose'])
        command = None
        if self.recovery and self.recovery_started is not None:
            # A deadline belongs to the recovery episode, not each pan/rebuild.
            from harness.selfmap5_revision import RECOVERY_DEADLINE_S, RECOVERY_ATTEMPTS
            v2 = self.mapper.options.revision_gate != 'off'
            deadline = RECOVERY_DEADLINE_S if v2 else 20.
            attempts = RECOVERY_ATTEMPTS if v2 else 3
            if t-self.recovery_started >= deadline or self.recovery_attempts > attempts:
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
            if self.stage == 'active_reloc8':
                command = self.active_look(t, pose)
            elif self.stage == 'pan':
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
                        if self.mapper.options.multiframe_registration != 'off':
                            self.mapper.registration.begin_sweep(t)
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
                    pose=pose, motion_model=self.mapper.options.motion_model,
                    native_primitives=self.mapper.options.reloc14_continuous_tracking_v1)
                if self.sweep.phase != 'sensor_sweep':
                    if self.mapper.options.multiframe_registration != 'off':
                        self.mapper.registration.end_sweep()
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
                                    native_primitives=self.mapper.options.reloc14_continuous_tracking_v1,
                                    translation_policy='forward_only_v1')
                                row['executed_path_m'], row['pulse'] = path, pulse
        if self.initial_sweep != 'off':
            row = dict(row, initial_sweep_complete=self.initial_sweep_complete)
            if not self.initial_sweep_complete:
                row.update(complete=False, stop_reason=None,
                           completion_blockers=[*row['completion_blockers'], 'initial_sweep_required'])
        if self.servo_wait is not None:
            before = command
            command = self.servo_wait.command(command, t=t, terminal=self.done)
            row = dict(row, reloc17_servo_wait=dict(until=self.servo_wait.until if math.isfinite(self.servo_wait.until) else None,
                replaced_wait=command is not before, source='own_issued_command_schedule'))
        return command, dict(**row, stage=self.stage, executor_stop_reason=self.stop_reason,
                             issued_command=command, frontier_arrivals=len(self.visited))
