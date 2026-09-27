"""Bounded active wrist looks before/during align; own inputs, no plant access."""
from __future__ import annotations

import math

import numpy as np

from harness.zone_own_contract import finite_number, pose_report_fresh
from harness.zone_own_guards import OwnPose

# Scheduling reserves, NOT changes to the 70/50 mm, 3 degree safety gates.
# dev08 own reports: age=6 at 166.3, sigma_xy=.05486; HIGH at 175.6.
MAX_TAG_GAP_S = 6.
RELOOK_XY_M = .055
RELOOK_YAW_RAD = math.radians(2.5)
MAX_LOOKS = 8                 # cumulative across the job, including entry looks
MAX_LOOK_S = 8.               # includes stop, arm settling and return posture
MAX_TOTAL_LOOK_S = 40.
MAX_DIRECTIONS = 3
RELOOK_STATES = ('align_relook_stop', 'align_relook', 'align_relook_return')


def relook_reason(report, now):
    if not pose_report_fresh(report, now) or not report.initialized:
        return 'pose_missing'
    age = report.since_tag_s
    if not finite_number(age) or age < 0 or now - report.t_est + age >= MAX_TAG_GAP_S - 1e-8:
        return 'tag_gap'
    if report.std_xy_m >= RELOOK_XY_M or report.std_yaw_rad >= RELOOK_YAW_RAD:
        return 'sigma_reserve'
    return None


def ranked_look_pans(static_map, report, servo, guard):
    """Rank collision-safe LOOK_P20 directions by projected mapped tag area.

    Projection is a proposal, not a visibility/fix claim: occlusion and pose
    bias can invalidate it. Only a subsequent accepted own RGB tag permits
    resumption. The existing calibrated camera and PWM FK are reused.
    """
    from harness.owncam_drive import LOOK_P20
    from harness.owncam_view import project_base_points, valid_pixel_mask
    from harness.wall_tags import tag_world_frame
    from scripts.run_m2_pair import PREGRASP_PANS_V2

    pose = OwnPose.from_report(report)
    if pose is None:
        return []
    c, s = math.cos(pose.yaw), math.sin(pose.yaw)
    rot = np.array([[c, -s, 0.], [s, c, 0.], [0., 0., 1.]])
    valid = valid_pixel_mask()
    candidates = []
    for pan in dict.fromkeys(PREGRASP_PANS_V2):
        target = {**LOOK_P20, 1: servo[1], 6: pan}
        plan = guard.plan(servo, target, [pan], pose, loaded=False, allow_backoff=False)
        if plan['reason'] != 'clear' or not plan.get('transition_clear'):
            continue
        score, ids = 0., []
        for tag in static_map.get('landmarks', {}).get('tags', []):
            center, axes = tag_world_frame(tag)
            if np.dot(np.array([pose.x, pose.y]) - center[:2], tag['normal_xy']) <= 0:
                continue
            h = tag['size_m'] / 2
            corners = np.array([[-h, h, 0.], [h, h, 0.], [h, -h, 0.], [-h, -h, 0.]]) @ axes.T + center
            points = (corners - np.array([pose.x, pose.y, 0.])) @ rot
            px = project_base_points(target, points)
            if not np.isfinite(px).all() or not ((px >= 1).all() and (px < [639, 479]).all()):
                continue
            uv = px.astype(int)
            side = float(np.mean(np.linalg.norm(px - np.roll(px, 1, axis=0), axis=1)))
            if side >= 8. and valid[uv[:, 1], uv[:, 0]].all():
                score += side * side
                ids.append(int(tag['id']))
        if ids:
            candidates.append({'pan': pan, 'score_px2': score, 'predicted_tag_ids': ids})
    return sorted(candidates, key=lambda x: (-x['score_px2'], abs(x['pan'] - servo[6]), x['pan']))


class PairAlignRelook:
    """Adapter mixin; frozen M2 beam alignment itself is unchanged."""

    def set(self, state, now, **detail):
        if state == 'align':
            self.align_started_at = now
            return self._begin_align_relook(now, 'align_entry')
        return super().set(state, now, **detail)

    def _begin_align_relook(self, now, reason):
        from scripts.study_owncam_pair_beam import OPEN

        self.port.hold(now)
        # Drop queued beam-view interpolation; restart from issued PWM only.
        self.arm.events.clear()
        self.arm.until = now
        self.arm.commanded = dict(self.port.own.servo)
        peer_holding = any(v['state'] in ('ready', 'lift', 'carry')
                           for v in self.status[0].partner_view(self.rid, now).values())
        if self.beam_grasp_confirmed or self.port.own.servo.get(1) != OPEN or peer_holding:
            return self.fail('ALIGN_RELOOK_WHILE_CLOSED', now)
        self.align_look_count = getattr(self, 'align_look_count', 0)
        self.align_look_total_s = getattr(self, 'align_look_total_s', 0.)
        if self.align_look_count >= MAX_LOOKS or self.align_look_total_s >= MAX_TOTAL_LOOK_S:
            return self.fail('ALIGN_RELOOK_LIMIT', now)
        self.align_look_count += 1
        self.align_look_started_at = now
        self.align_started_at = getattr(self, 'align_started_at', self.state_t)
        self.align_resume_name = self.look_name
        self.aligned_streak = 0
        self.vo_pose = None
        report = self.port.own.last_report
        self.log(self.rid, 'align_relook_trigger', now, reason=reason,
                 count=self.align_look_count, since_tag_s=report.since_tag_s,
                 std_xy_m=report.std_xy_m, std_yaw_rad=report.std_yaw_rad)
        super().set('align_relook_stop', now)
        self.status[1].tick('aligning', now)

    def align_relook_expired(self, now):
        if self.state not in RELOOK_STATES:
            return False
        elapsed = now - self.align_look_started_at
        return elapsed >= MAX_LOOK_S - 1e-8 or self.align_look_total_s + elapsed >= MAX_TOTAL_LOOK_S - 1e-8

    def _align_fix_ready(self, now):
        from harness.zone_pair_grasp import FIX_STD_XY_M, FIX_STD_YAW_RAD

        own, start = self.port.own, self.align_look_started_at
        r = own.last_report
        return bool(self.driver.loc is own.pose.loc and pose_report_fresh(r, now)
                    and r.initialized and own.gate.ok
                    and all(finite_number(v) for v in (r.x_m, r.y_m, r.yaw_rad))
                    and 0 <= r.std_xy_m <= FIX_STD_XY_M and 0 <= r.std_yaw_rad <= FIX_STD_YAW_RAD
                    and relook_reason(r, now) is None
                    and finite_number(r.since_tag_s) and r.since_tag_s >= 0
                    and start < r.t_est - r.since_tag_s <= now
                    and own.pose.loc.last_tag_t is not None
                    and start < own.pose.loc.last_tag_t <= r.t_est)

    def _align_relook_stop(self, now, arm_idle):
        from harness.owncam_localizer import OwnCamLocalizer
        from harness.owncam_drive import LOOK_P20

        # Wait for the hold to reach the pose provider and for a valid bounded
        # post-stop report to populate the guard's stationary cache. A next
        # control tick alone is too early for the 0.16 s delayed provider.
        if not self.align_stop_ready(now):
            return
        choices = self.align_look_choices()
        if not choices:
            return self.fail('ALIGN_RELOOK_NO_SAFE_VIEW', now)
        self.align_pans = [row['pan'] for row in choices[:MAX_DIRECTIONS]]
        self.log(self.rid, 'align_view_selection', now, candidates=choices,
                 source='static map + own pose + issued PWM; predicted visibility only')
        self.log(self.rid, 'align_relook_stopped_pose', now,
                 stopped_at_s=self.align_look_started_at, report_t=self.port.own.last_report.t_est)
        drv = self.driver
        drv.loc = OwnCamLocalizer(drv.map, drv.loc.params, seed=int(drv.loc.rng.integers(1 << 30)))
        drv.loc.command({'t': now, 'kind': 'initial_servo_command', 'pulses': dict(self.port.own.servo)})
        self.arm.queue({**LOOK_P20, 1: self.port.own.servo[1], 6: self.align_pans.pop(0)},
                       now, duration=.8, settle=.6)
        super().set('align_relook', now)

    def _align_relook(self, now, arm_idle):
        from harness.owncam_pair_beam_v2 import pose_of

        if not arm_idle:
            return
        obs = self.look(now)
        if self._align_fix_ready(now) and obs['sim_time'] >= self.arm.until - 1e-8:
            self.log(self.rid, 'align_relook_fix', now, report_t=self.port.own.last_report.t_est,
                     frame_id=obs['frame_id'], sha256=obs['sha256'], source='shared own.pose/last_report')
            self.arm.queue(pose_of(self.align_resume_name), now, duration=.6, settle=.3)
            return super().set('align_relook_return', now)
        if not self.align_pans:
            return self.fail('ALIGN_RELOOK_NO_FIX', now)
        self.arm.queue({6: self.align_pans.pop(0)}, now, duration=.4, settle=.6)

    def _align_relook_return(self, now, arm_idle):
        if not arm_idle:
            return
        if not self._align_fix_ready(now):
            return self.fail('ALIGN_RELOOK_FIX_EXPIRED', now)
        self.align_look_total_s += now - self.align_look_started_at
        self.next_look = now
        super().set('align', now, resumed=True)
        # Keep the original align deadline; looks cannot refill it.
        self.state_t = self.align_started_at

    def tick(self, now):
        if self.state == 'align':
            reason = relook_reason(self.port.own.last_report, now)
            if reason:
                return self._begin_align_relook(now, reason)
        if self.state not in RELOOK_STATES:
            return super().tick(now)
        self.status[1].tick('aligning', now)
        self.port.hold(now)
        if any(v['state'] == 'abort' for v in self.status[0].partner_view(self.rid, now).values()):
            return self.fail('PARTNER_ABORT', now)
        if self.align_relook_expired(now):
            return self.fail('ALIGN_RELOOK_TIMEOUT', now)
        idle = now >= self.arm.until and not self.arm.events
        return getattr(self, '_' + self.state)(now, idle)
