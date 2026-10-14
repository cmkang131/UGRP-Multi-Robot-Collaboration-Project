"""Heavy-crate grasp teacher: the visible_only beam grasp teacher plus a lift barrier.

Differences from the beam (docs: experiments/2026-10-14-crate-teacher/README.md):
- the grasp markers are the crate lugs (sim/cargo_teacher_profile.CRATE);
- the start skew (0..1.5 s, GraspStartSync) only delays the descent and close;
- after the close the robot reports its own READY-TO-LIFT (own issued close sequence
  complete + settle, no contact, no object height) and waits for a second code
  READY/GO/ACK barrier; only then the lift is queued. 0.9 kg is above one robot's
  measured capacity (0.66-0.68 kg), so a lift by one robot is a tip-over, not a
  harmless early start.
Everything else (approach, alignment, observation, route, pick poses) is the
unchanged ``VisibleOnlyGraspTeacher``.
"""
from __future__ import annotations
from harness.visual_arm_v3 import solve_grip_site_ik, tool_pose
from sim.grasp_act_teacher_v3 import VisibleOnlyGraspTeacher
from sim.grasp_act_teacher import local
from sim.cargo_teacher_profile import CRATE
from sim.crate_lift_pose import MODES as LIFT_POSE_MODES, select_lift_prefix

LIFT_WAIT_LIMIT_S = 20.


class CrateGraspTeacher(VisibleOnlyGraspTeacher):
    def __init__(self, *args, profile=CRATE, crate_lift_pose='off', **kwargs):
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

    # --- phase bookkeeping ---
    def _set(self, phase, now):
        # The beam teacher ends at 'complete' right after its lift; here the close ends at
        # 'closed' and only the lift (after the barrier) ends at 'complete'.
        if phase == 'complete' and not self.lift_done:
            phase = 'closed'
            self.closed_at = now
            if self.crate_lift_pose != 'off':
                self.lift_prefix, self.lift_selection = select_lift_prefix(self.sink.pwm, self.lift_pose)
                if self.lift_prefix is None:
                    self.outcome = 'crate_lift_pose_no_candidate'
        super()._set(phase, now)

    def lift_ready(self):
        """Own READY-TO-LIFT: the issued close sequence has completed (own command history only)."""
        return self.phase == 'closed' and self.outcome is None

    # --- picking: hover, descent, close (no lift yet) ---
    def _queue_pick(self, truth, now):
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
            # Retain the exact interpolation samples/timing, truncating only
            # the original lift's tail. A newly interpolated path is not used.
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
                'closed_at': self.closed_at, 'lift_done': self.lift_done,
                'crate_lift_pose': self.crate_lift_pose, 'lift_pose_selection': self.lift_selection,
                'done_semantics': 'own issued close+lift sequence complete after the lift barrier; physical evaluation separate'}
