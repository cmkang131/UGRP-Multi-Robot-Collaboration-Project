"""Heavy-crate grasp teacher: the visible_only beam grasp teacher plus a lift barrier.

Differences from the beam (docs: experiments/2026-10-14-crate-teacher/README.md):
- the grasp markers are the crate lugs (sim/cargo_teacher_profile.CRATE);
- the start skew (0..1.5 s, GraspStartSync) only delays the descent and close;
- after the close the robot reports its own READY-TO-LIFT (own issued close sequence
  complete + settle, no contact, no object height) and waits for a second code
  READY/GO/ACK barrier; only then the lift is queued. The 0.25 kg scene keeps
  the same two-robot barrier; historical 0.66-0.68 kg solo limits predate the
  current servo limits and are not applicable.
The default reuses ``VisibleOnlyGraspTeacher``; opt-in crate modes add the
pre-grasp checks and command-space lift described in crate8.md / crate9.md.
"""
from __future__ import annotations
import math
from harness.visual_arm_v3 import solve_grip_site_ik, tool_pose
from sim.grasp_act_teacher_v3 import VisibleOnlyGraspTeacher
from sim.grasp_act_teacher import local
from sim.cargo_teacher_profile import CRATE
from sim.crate_lift_pose import MODES as LIFT_POSE_MODES, CARTESIAN_MODES, ANTIPODAL_OPTION, select_lift_prefix

LIFT_WAIT_LIMIT_S = 20.


class CrateGraspTeacher(VisibleOnlyGraspTeacher):
    def __init__(self, *args, profile=CRATE, crate_lift_pose='off', crate_approach_recovery='off', **kwargs):
        from sim.crate_approach_recovery import MODES, OPTION
        if crate_approach_recovery not in MODES:
            raise ValueError(f'crate_approach_recovery: {crate_approach_recovery}')
        if crate_approach_recovery == OPTION:
            if crate_lift_pose != ANTIPODAL_OPTION:
                raise ValueError('crate approach recovery requires antipodal grasp')
            kwargs.update(approach_progress='approach_progress_v1', approach_recovery='approach_recovery_v1')
        if crate_lift_pose not in LIFT_POSE_MODES:
            raise ValueError(f'crate_lift_pose: {crate_lift_pose}')
        super().__init__(*args, **kwargs)
        self.cargo_profile = profile
        self.lift_done = False
        self.lift_pose = None
        self.closed_at = None
        self.crate_lift_pose = crate_lift_pose
        self.lift_selection = None
        self.lift_prefix = None
        self.approach_excluded = set()
        # Separate from the common parent's approach_progress mode string.
        self.crate_visible_progress = None
        self.crate_last_visible_t = None
        self.crate_approach_recovery = crate_approach_recovery
        self.crate_recovery_log = []
        if crate_lift_pose == ANTIPODAL_OPTION:
            from sim.crate_antipodal import visible_grasp
            self.approach_grasp_filter = lambda world, pose: visible_grasp(
                world, self.rid, self.end, pose=pose)['valid']
        if crate_lift_pose in CARTESIAN_MODES:
            if self.teacher_stability == 'off' or self.approach_goal_set == 'off':
                raise ValueError('Cartesian crate lift requires alignment and approach goal set')
            from sim.crate_cartesian_lift import STATION_M
            self.staging_distance = STATION_M
            self.approach_choice = (0., STATION_M)
            self.approach_distances = (STATION_M,)

    def _begin_relook(self, now, reason):
        if self.crate_lift_pose in CARTESIAN_MODES:
            # Finite recovery: retain the failed stance, re-observe, then use
            # the existing collision-checked alternative-goal planner.
            self.approach_excluded.add(self.approach_choice)
            self.approach_plan_valid = False
            self.crate_visible_progress = None
            self.next_plan = now
        return super()._begin_relook(now, reason)

    def _approach(self, truth, now):
        if (self.crate_lift_pose in CARTESIAN_MODES and self.phase == 'approach'
                and truth['beam'] is not None and truth['visibility'][self.rid]['visible_probes'] >= 5):
            pose, _, _, goal = self._geometry(truth)
            error = math.dist(pose[:2], goal)
            if (self.crate_approach_recovery != 'off'
                    and (self.crate_last_visible_t is None or now-self.crate_last_visible_t > .15)):
                self.crate_visible_progress = None
            self.crate_last_visible_t = now
            if self.crate_visible_progress is None or error < self.crate_visible_progress[0]-.005:
                self.crate_visible_progress = (error, now)
            elif now-self.crate_visible_progress[1] >= 3.:
                return self._begin_relook(now, 'crate_approach_no_visible_progress_3s')
        return super()._approach(truth, now)

    def _plan_approach(self, world, now):
        valid = super()._plan_approach(world, now)
        if (self.crate_approach_recovery != 'off' and not valid and self.goal_set_log
                and self.goal_set_log[-1]['t'] == now):
            candidates = self.goal_set_log[-1]['candidates']
            # Every geometrically legal stance is statically occupied: give
            # navigation an explicit handoff, rather than scanning for 30 s.
            # Never call a peer, path/grid failure or excluded stance static.
            from sim.grasp_act_visible_route import constraints, free
            from scripts.zone_teacher import PeerDisc
            radius, discs, rects = constraints(world, self.rid, self.folded_ready, self.cargo_profile)
            fixed = [d for d in discs if not isinstance(d, PeerDisc)]
            legal = [c for c in candidates if c['reason'] != 'grasp_geometry']
            if legal and all(c['reason'] == 'blocked_goal' and not free(c['goal'], fixed, rects, radius)
                             for c in legal):
                self._approach_handoff(now)
                self.crate_recovery_log.append({'t': now, 'recovery': 'static_stances_blocked_handoff'})
        return valid

    def _check_navigation_pulse(self, truth, value, now):
        # A held or invisible assigned lug is never read by this correction.
        if (self.crate_approach_recovery == 'off' or self.phase not in ('approach', 'align', 'ready')
                or truth['visibility'][self.rid]['visible_probes'] < 5 or truth['beam'] is None):
            return value
        from sim.crate_approach_recovery import safe_pulse
        from sim.grasp_act_visible_route import constraints, waypoint, drive
        pose, g, _, goal = self._geometry(truth)
        radius, discs, rects = constraints(truth, self.rid, self.folded_ready, self.cargo_profile)
        if safe_pulse(value, pose, discs, rects, radius):
            return value
        # Use the same collision-checked route with yaw decoupled. Recheck
        # the quantized wheel pulse too; no untested fallback can be issued.
        target = waypoint(pose[:2], self.path, discs, rects, radius)
        if target is not None:
            effort = drive(pose, goal, target, g)
            effort['turn'] = 0.
            candidate = self._continuous(now, **effort)
            if any(candidate['wheels']) and safe_pulse(candidate, pose, discs, rects, radius):
                self.crate_recovery_log.append({'t': now, 'recovery': 'safe_translation_without_yaw'})
                return candidate
        self.crate_recovery_log.append({'t': now, 'recovery': 'unsafe_pulse_hold_replan'})
        self.path = []; self.path_goal = None; self.next_plan = now
        return self._hold(now)

    def ready_geometry(self, truth):
        if not super().ready_geometry(truth):
            return False
        if self.crate_lift_pose not in CARTESIAN_MODES:
            return True
        if self.crate_lift_pose == ANTIPODAL_OPTION:
            from sim.crate_antipodal import visible_grasp
            if not visible_grasp(truth, self.rid, self.end)['valid']:
                return False
        # This runs only before the pick, on the currently visible assigned lug.
        from sim.crate_cartesian_lift import plan_lift
        pose, g, _, _ = self._geometry(truth)
        x, y = local(pose, g)
        grip = {1: 1500, **solve_grip_site_ik((x, y, g[2]))}
        best, _ = plan_lift(grip)
        return best is not None

    # --- phase bookkeeping ---
    def _set(self, phase, now):
        # The beam teacher ends at 'complete' right after its lift; here the close ends at
        # 'closed' and only the lift (after the barrier) ends at 'complete'.
        if phase == 'complete' and not self.lift_done:
            phase = 'closed'
            self.closed_at = now
            if self.crate_lift_pose != 'off':
                if self.crate_lift_pose in CARTESIAN_MODES:
                    from sim.crate_cartesian_lift import plan_lift
                    self.lift_prefix, self.lift_selection = plan_lift(self.sink.pwm)
                else:
                    self.lift_prefix, self.lift_selection = select_lift_prefix(self.sink.pwm, self.lift_pose)
                if self.lift_prefix is None:
                    self.outcome = 'crate_lift_pose_no_candidate'
        super()._set(phase, now)

    def lift_ready(self):
        """Own READY-TO-LIFT: the issued close sequence has completed (own command history only)."""
        return self.phase == 'closed' and self.outcome is None

    # --- picking: hover, descent, close (no lift yet) ---
    def _queue_pick(self, truth, now):
        if self.crate_lift_pose == ANTIPODAL_OPTION:
            from sim.crate_antipodal import visible_grasp
            if not visible_grasp(truth, self.rid, self.end)['valid']:
                # READY can become stale during the asynchronous start delay.
                # Replan from current visible inputs before any grasp command.
                self._begin_relook(now, 'crate_grasp_geometry_changed')
                return
        pose = truth['robots'][self.rid]['pose']
        g = truth['beam']['ends'][self.end]
        x, y = local(pose, g)
        self.grasp_xyz = (x, y, g[2])
        self.initial_end_z = g[2]
        grip = solve_grip_site_ik(self.grasp_xyz)
        pitch = tool_pose(grip).pitch_deg
        hover = solve_grip_site_ik((x, y, .095), preferred_pitch_deg=pitch)
        self.arm.queue({**hover, 1: 2000}, now, duration=1.)
        for i in range(1, 9):
            z = .095+(g[2]-.095)*i/8
            self.arm.queue(solve_grip_site_ik((x, y, z), preferred_pitch_deg=pitch), now, duration=.15, settle=.04)
        self.arm.queue({1: 1500}, now, duration=.8, settle=.5)
        self.lift_pose = solve_grip_site_ik((x, y, .095), preferred_pitch_deg=pitch)
        self._set('pick', now)

    def _queue_lift(self, now):
        if self.crate_lift_pose == 'off':
            self.arm.queue(self.lift_pose, now, duration=1.2, settle=.5)
        else:
            if self.lift_prefix is None:
                self.outcome = 'crate_lift_pose_no_candidate'
                return
            # Issue the already checked command samples at their planned times.
            # v1 is a legacy prefix; Cartesian v1 shares the same rise/time law.
            start = max(now, self.arm.until)
            self.arm.events.extend((start+t, sid, pulse) for t, sid, pulse in self.lift_prefix['events'])
            self.arm.commanded.update(self.lift_prefix['issued_pwm'])
            self.arm.until = start+self.lift_prefix['prefix_duration_s']+.5
        self._set('lift', now)

    # --- stepping ---
    def step(self, truth, now, *, permit_pick=False, permit_lift=False):
        # Same own-command propagation as the parent, but with the extra permit.
        from sim.grasp_act_teacher_v3 import propagate_owned
        from copy import deepcopy
        if self.local_seen is not None and self.last_command is not None and self.last_tick is not None:
            self.local_seen = propagate_owned(self.local_seen, self.last_command, min(.1, now-self.last_tick))
        value, done = self._step(truth, now, permit_pick=permit_pick, permit_lift=permit_lift)
        value = self._check_navigation_pulse(truth, value, now)
        if self.phase in ('align', 'ready', 'pick', 'closed', 'lift', 'complete'):
            self.progress.reset()
        self.last_command = deepcopy(value)
        self.last_tick = now
        return value, done

    def _step(self, truth, now, *, permit_pick, permit_lift=False):
        if self.outcome is not None:
            return self._hold(now), False
        if self.phase in ('closed', 'lift'):
            arms_done = self.arm.tick(now)
            if self.phase == 'closed':
                if permit_lift:
                    self._queue_lift(now)
                elif now-self.phase_t > LIFT_WAIT_LIMIT_S:
                    self.outcome = 'lift_barrier_timeout'
                return self._hold(now), False
            if arms_done:
                self.lift_done = True
                self.command_complete = True
                self._set('complete', now)
                return self._hold(now), True
            return self._hold(now), False
        value, done = super()._step(truth, now, permit_pick=permit_pick)
        if self.phase == 'closed':
            # the parent flagged completion at the end of the close; here that is not the end
            self.command_complete = False
            return value, False
        return value, done

    def diagnostic(self):
        return {**super().diagnostic(), 'profile': 'visible_only_crate', 'lift_barrier': True,
                'crate_approach_recovery': self.crate_approach_recovery,
                'crate_recovery_log': self.crate_recovery_log,
                'closed_at': self.closed_at, 'lift_done': self.lift_done,
                'crate_lift_pose': self.crate_lift_pose, 'lift_pose_selection': self.lift_selection,
                **({'excluded_stalled_stances': sorted(self.approach_excluded)}
                   if self.crate_lift_pose in CARTESIAN_MODES else {}),
                'done_semantics': 'own issued close+lift sequence complete after the lift barrier; physical evaluation separate'}
