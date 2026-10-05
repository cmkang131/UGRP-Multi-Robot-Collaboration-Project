"""Instance-scoped b-v6h1 guard policy over v3 static command geometry.

The p2f monitor's missing moved-fix stall coverage is retained and recorded;
it is not a physical safety qualification. No process-global patches.
"""
from __future__ import annotations

import math
from dataclasses import replace

from harness import zone_own_guards as g
from harness.zone_own_guards_v3 import SweepGuardV3
from harness.zone_pair_geometry import PairSweepGuard
from harness.zone_pair_guards import PairCommandGuard, _PairRecheck
from harness.zone_own_sweep import SweepRecheck
from harness.zone_final_pair_binding import bind
from harness import visual_arm_v3 as arm

LOADED_GATE = replace(g.GATE_LOADED, high_yaw_rad=math.radians(5.), low_yaw_rad=math.radians(4.))


def margin(self, pose, lever_m):
    return (g.BASE_MARGIN_M + self.residual + min(pose.std_xy, g.SIGMA_CAP_XY_M)
            + min(pose.std_yaw, g.SIGMA_CAP_YAW_RAD) * lever_m)


class PairArmGuard(SweepGuardV3):
    # b-v6h1's probe_all_sweeps = kxy=kyaw=1, including unloaded arm sweeps.
    margin = margin


class PairGeometry(PairSweepGuard):
    margin = margin

    def beam_spheres(self, servo):
        tool = arm.tool_pose(servo)
        # _beam_spheres adds mount, while v3 FK already includes it.
        return self._beam_spheres((tool.x_m-self.mount[0], tool.y_m-self.mount[1],
                                   tool.z_m-self.mount[2]), math.radians(tool.yaw_left_deg))

    def stationary_beam_clearance(self, beam, pose):
        # Measured rays are already in the actual base frame. Avoid adding the
        # v3 shoulder offset twice to an unattached, camera-estimated beam.
        from harness.zone_own_guards import _rect_distance, K_SIGMA
        grip = (*beam['grip_base_m'], self.grasp['xyz_m'][2])
        local = tuple(grip[i]-self.mount[i] for i in range(3))
        best, hit = math.inf, None
        c, s = math.cos(pose.yaw), math.sin(pose.yaw)
        for bx, by, bz, radius in self._beam_spheres(local, beam['axis_heading_rad']):
            x, y = pose.x+c*bx-s*by, pose.y+s*bx+c*by
            lever = math.hypot(bx-grip[0], by-grip[1])+radius
            reserve = self.margin(pose, math.hypot(bx, by)+radius) + K_SIGMA*(
                beam['std_xy_m'] + beam['std_yaw_rad']*lever)
            for box in self.boxes:
                if bz-radius >= box['height']+reserve:
                    continue
                clearance = _rect_distance(box, x, y)-radius-reserve
                if clearance < best:
                    best, hit = clearance, box['id']
        return best, hit


class MovedFixMonitor(g.ProgressMonitor):
    """PR #292 p2f semantics: loaded pair only, first fix must follow motion."""
    def __init__(self, report_source, approach=lambda: False):
        super().__init__()
        self.report_source = report_source
        self.approach = approach
        self.move_t0 = None
        self.armed_count = self.ignored_count = 0

    def note_command(self, row):
        t = row.get('t')
        if (self.move_t0 is None and g.commanded_step_m(row) > 0 and isinstance(t, (int, float))
                and not isinstance(t, bool) and math.isfinite(t)):
            self.move_t0 = float(t)

    def reset(self):
        super().reset()
        self.move_t0 = None

    def trusted(self, xy, goal_dist):
        if self.approach():
            return super().trusted(xy, goal_dist)
        if self.baseline is None:
            fix = getattr(self.report_source(), 'last_fix_t', None)
            if (self.move_t0 is None or not isinstance(fix, (int, float)) or isinstance(fix, bool)
                    or not math.isfinite(fix) or fix <= self.move_t0):
                self.ignored_count += 1
                return None
            self.armed_count += 1
        return super().trusted(xy, goal_dist)


_recheck = bind(SweepRecheck.check, GATE_LOADED=LOADED_GATE)


class PairRecheck(_PairRecheck):
    def check(self, now, *args, **kwargs):
        result = _recheck(self, now, *args, **kwargs)
        self.sweep_waiting = result == 'wait'
        if result == 'clear' and self.uncertain and self._wait(now) == 'blocked':
            return 'blocked'
        return result


class CommandGuard(PairCommandGuard):
    before_control = bind(PairCommandGuard.before_control, GATE_LOADED=LOADED_GATE)
    check = bind(PairCommandGuard.check, GATE_LOADED=LOADED_GATE)

    def __init__(self, execution, vision):
        super().__init__(execution)
        self.beam_track = vision.beam_track()
        self.monitor = MovedFixMonitor(lambda: self.ep.own.last_report, lambda: self.approach)
        self.recheck = PairRecheck()
        execution.controller.driver.sweep_recheck = self.recheck

    def sweep_guard(self):
        return PairGeometry(self.ep.own.guard, self.ep.plan['beam_geometry'], self.ep.arguments['role'])

    def on_command(self, row):
        super().on_command(row)
        if not self.approach:
            self.monitor.note_command(row)

    def preclose_check(self, now, obs):
        from harness.zone_pair_grasp import FIX_STD_XY_M, FIX_STD_YAW_RAD
        from harness.zone_own_contract import pose_report_fresh
        from harness.zone_pair_vision import frame_gate
        own = self.ep.own
        pose = g.OwnPose.from_report(own.last_report)
        if (not pose_report_fresh(own.last_report, now) or pose is None or not own.gate.ok
                or not 0 <= pose.std_xy <= FIX_STD_XY_M or not 0 <= pose.std_yaw <= FIX_STD_YAW_RAD
                or now < self.motion_until or not frame_gate(self.ep.policy)(obs, own.robot_id, now)
                or not self._same_camera_commands(obs)):
            return False
        beam = self.beam_track.estimate(now, obs, own.servo, self.ep.controller.seg)
        if beam is None:
            self.ep.log(own.robot_id, 'preclose_beam_guard', now, clear=False, reason='BEAM_UNCERTAIN')
            return False
        clearance, wall = self.sweep_guard().stationary_beam_clearance(beam, pose)
        self.ep.log(own.robot_id, 'preclose_beam_guard', now, clear=clearance >= 0.,
                    clearance_after_margin_m=clearance, wall_id=wall,
                    frame_id=obs['frame_id'], sha256=obs['sha256'], beam=beam)
        return clearance >= 0.
