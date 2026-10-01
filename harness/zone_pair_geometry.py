"""Pair-only static swept geometry, from own estimates and issued PWM.

Each carrier reconstructs the WHOLE horizontal beam independently from its
own grip and fixed role. No peer pose, measured joint, contact or world state.
This rigid two-grip envelope does not estimate beam flex, slip or tilt.
"""
from __future__ import annotations

import math
from dataclasses import replace

from harness import visual_arm as va
from harness.zone_own_guards import BACKOFF_GAIN_MAX, K_SIGMA, SweepGuard, _rect_distance, body_spheres

BEAM_SAMPLE_M = .02
MOTION_SAMPLE_S = .05


class PairSweepGuard(SweepGuard):
    def __init__(self, arm_guard, geometry, role, *, loaded_k_xy=K_SIGMA, loaded_k_yaw=K_SIGMA,
                 door_relax_sigma_scope='loaded_base_motion'):
        self.boxes, self.mount, self.residual = arm_guard.boxes, arm_guard.mount, arm_guard.residual
        self.geometry, self.grasp = geometry, geometry['grasps'][role]
        self.loaded_k_xy, self.loaded_k_yaw = loaded_k_xy, loaded_k_yaw
        if door_relax_sigma_scope not in ('loaded_base_motion', 'probe_all_sweeps'):
            raise ValueError('unknown door-relax sigma scope')
        self.door_relax_sigma_scope = door_relax_sigma_scope
        self._loaded_motion = False

    def margin(self, pose, lever_m):
        # b-v6h1 matches the probe's process-wide margin replacement in this
        # policy instance. Older policies keep the original selection/signature.
        relaxed = self._loaded_motion or self.door_relax_sigma_scope == 'probe_all_sweeps'
        if not relaxed or (self.loaded_k_xy == K_SIGMA and self.loaded_k_yaw == K_SIGMA):
            return super().margin(pose, lever_m)  # unchanged call signature for historical probe wrappers
        return super().margin(pose, lever_m, loaded=True)

    def beam_spheres(self, servo):
        """Conservative covering of the complete 600x40x32 mm bar, in own base coordinates.

        The tool point is the own commanded grip point, 30 mm in from the end.
        Subtract the role's catalogue grip before rotating the entire bar. The
        sphere radius includes half the sample interval: there are no spatial
        gaps, including at the bar ends. Beam height is relative to that grip.
        """
        tool = va.tool_pose(servo)
        return self._beam_spheres((tool.x_m, tool.y_m, tool.z_m), math.radians(tool.yaw_left_deg))

    def _beam_spheres(self, grip_xyz, heading):
        yaw = heading - self.grasp['yaw_rad']
        c, s = math.cos(yaw), math.sin(yaw)
        gx, gy, gz = self.grasp['xyz_m']
        cx, cy, cz = self.geometry['center_m']
        hx, hy, hz = self.geometry['half_extents_m']
        count = max(1, math.ceil(2 * hx / BEAM_SAMPLE_M))
        radius = math.sqrt(hy * hy + hz * hz + (hx / count) ** 2)
        mx, my, mz = self.mount
        return [(mx + grip_xyz[0] + c * (cx - hx + 2 * hx * i / count - gx) - s * (cy - gy),
                 my + grip_xyz[1] + s * (cx - hx + 2 * hx * i / count - gx) + c * (cy - gy),
                 mz + grip_xyz[2] + cz - gz, radius) for i in range(count + 1)]

    def stationary_beam_clearance(self, beam, pose):
        """Floor-supported beam from own RGB, independent of commanded tool attachment.

        Return clearance AFTER the unchanged 35 mm reserve and own-pose
        inflation, plus the beam fit's positional/angular uncertainty. The
        local RGB fit uses the same fixed floor/top plane as observe_beam.
        """
        grip = (*beam['grip_base_m'], self.grasp['xyz_m'][2])
        best, hit = math.inf, None
        c, s = math.cos(pose.yaw), math.sin(pose.yaw)
        for bx, by, bz, radius in self._beam_spheres(grip, beam['axis_heading_rad']):
            x, y = pose.x + c * bx - s * by, pose.y + s * bx + c * by
            lever = math.hypot(bx - self.mount[0] - grip[0], by - self.mount[1] - grip[1]) + radius
            margin = (self.margin(pose, math.hypot(bx, by) + radius)
                      + K_SIGMA * (beam['std_xy_m'] + beam['std_yaw_rad'] * lever))
            for box in self.boxes:
                if bz - radius >= box['height'] + margin:
                    continue
                clearance = _rect_distance(box, x, y) - radius - margin
                if clearance < best:
                    best, hit = clearance, box['id']
        return best, hit

    def arm_clearance(self, servo, pose, *, loaded):
        # The pair cargo is the full bar; the shared guard's small held box is
        # deliberately not used as a substitute for this geometry.
        best, hit = super().arm_clearance(servo, pose, loaded=False)
        if not loaded:
            return best, hit
        c, s = math.cos(pose.yaw), math.sin(pose.yaw)
        for bx, by, bz, radius in self.beam_spheres(servo):
            x, y = pose.x + c * bx - s * by, pose.y + s * bx + c * by
            margin = self.margin(pose, math.hypot(bx, by) + radius)
            for box in self.boxes:
                if bz - radius >= box['height'] + margin:
                    continue
                clearance = _rect_distance(box, x, y) - radius - margin
                if clearance < best:
                    best, hit = clearance, box['id']
        return best, hit

    def motion_clear(self, servo, pose, cmd, *, loaded):
        """Check through command expiry, including curved paths and sample gaps.

        Use the existing conservative command gain in both translation and
        turn. Check either turn sign and the straight (understeer) trajectory.
        A displacement bound inflates each sample to cover the intervening
        interval, so a long command cannot skip a thin post between samples.
        """
        duration = cmd.get('duration_s')
        if not isinstance(duration, (int, float)) or not math.isfinite(duration) or not 0 <= duration <= 1.:
            return False
        f, l, w = (cmd.get(k, 0.) * BACKOFF_GAIN_MAX for k in ('forward', 'left', 'turn'))
        if not all(math.isfinite(v) for v in (f, l, w)):
            return False
        n = max(1, math.ceil(duration / MOTION_SAMPLE_S))
        spheres = body_spheres(servo, loaded=False, mount_xyz_m=self.mount)
        if loaded:
            spheres += self.beam_spheres(servo)
        lever = max(.2, *(math.hypot(x, y) + r for x, y, _, r in spheres))
        pad = (math.hypot(f, l) + abs(w) * lever) * duration / n / 2.
        original_residual = self.residual
        original_loaded_motion = self._loaded_motion
        self.residual += pad
        self._loaded_motion = bool(loaded)
        try:
            for omega in sorted({-abs(w), 0., abs(w)}):
                for i in range(n + 1):
                    t = duration * i / n
                    a = omega * t
                    if omega:
                        dx = (f * math.sin(a) + l * (math.cos(a) - 1.)) / omega
                        dy = (f * (1. - math.cos(a)) + l * math.sin(a)) / omega
                    else:
                        dx, dy = f * t, l * t
                    moved = replace(pose.moved(dx, dy), yaw=pose.yaw + a)
                    if (self.chassis_clearance(moved)[0] < 0.
                            or self.arm_clearance(servo, moved, loaded=loaded)[0] < 0.):
                        return False
            return True
        finally:
            self.residual = original_residual
            self._loaded_motion = original_loaded_motion
