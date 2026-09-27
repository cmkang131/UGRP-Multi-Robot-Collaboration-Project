"""Pair adapter's pre-close rendezvous; own RGB and issued commands only.

The frozen M2 CLI remains unchanged. A grip-view receipt is a conservative
attachment hypothesis for the sweep, not a physical success measurement;
M2's independent post-lift co-motion check still applies.
"""
from __future__ import annotations

import math

from harness.zone_own_contract import finite_number, pose_report_fresh
from harness.zone_pair_vision import valid_frame
from harness.zone_pair_align import PairAlignRelook

PROFILE = 'zone_pair_grasp_relook_v2'
FIX_STD_XY_M = .05
FIX_STD_YAW_RAD = math.radians(3.)
CLOSE_WAIT_S = 20.


def stationary_beam_estimate(obs, servo):
    """Fresh own RGB fit, never the planned/stored grip or a commanded tool pose.

    Reject clipped/partial end fits. Use transverse fit scatter as a position
    uncertainty and its angle over visible length as an axis uncertainty.
    These are dev geometry bounds, not calibrated localization accuracy.
    """
    from harness.owncam_pair_beam_v2 import observe_beam

    beam = observe_beam(obs['image'], servo)
    grip = beam.get('grip_base_m')
    spread, length = beam.get('lateral_spread_m'), beam.get('visible_length_m')
    if (not beam.get('visible') or not beam.get('end_visible')
            or beam.get('grip_source') != 'band_centre'
            or not isinstance(grip, (list, tuple)) or len(grip) != 2
            or not all(finite_number(v) for v in (*grip, beam.get('axis_heading_rad'), spread, length))
            or spread < 0 or length <= 0):
        return None
    syaw = math.atan2(spread, length)
    if spread > FIX_STD_XY_M or syaw > FIX_STD_YAW_RAD:
        return None
    return {**beam, 'std_xy_m': spread, 'std_yaw_rad': syaw}


class PairGraspRelook(PairAlignRelook):
    """Mixin before M2DoorStudent. All live inputs come from the own port."""

    def look(self, now):
        obs = super().look(now)
        if self.state == 'align':
            self.record_standoff(now, obs)
        return obs

    @property
    def beam_grasp_confirmed(self):
        receipt = getattr(self, 'beam_grasp_receipt', None)
        return bool(receipt and receipt['segment'] == self.seg
                    and self.port.own.servo.get(1, 2000) < 2000)

    def on_issued_command(self, row):
        if row['kind'] == 'arm' and int(row['servo_id']) == 1:
            if row['pulse'] >= 2000:
                self.beam_grasp_receipt = None
                self.close_issued_at = None
            elif row['pulse'] == 1500:
                self.close_issued_at = row['t']

    def _grasp_pose_ready(self, now):
        own = self.port.own
        report = own.last_report
        start = getattr(self, 'pregrasp_started_at', None)
        # No VO-only bypass, old low-sigma report, or a different localizer.
        return bool(start is not None and self.driver.loc is own.pose.loc
                    and pose_report_fresh(report, now) and report.initialized
                    and all(finite_number(v) for v in (report.x_m, report.y_m, report.yaw_rad))
                    and own.gate.ok
                    and 0 <= report.std_xy_m <= FIX_STD_XY_M
                    and 0 <= report.std_yaw_rad <= FIX_STD_YAW_RAD
                    and report.since_tag_s is not None and report.since_tag_s >= 0
                    and report.t_est - report.since_tag_s >= start
                    and own.pose.loc.last_tag_t is not None
                    and start <= own.pose.loc.last_tag_t <= report.t_est)

    def _queue_grasp(self, now):
        from harness.owncam_drive import LOOK_P20
        from harness.owncam_localizer import OwnCamLocalizer
        from scripts import run_m2_pair as m2

        peer_holding = any(v['state'] in ('ready', 'lift', 'carry')
                           for v in self.status[0].partner_view(self.rid, now).values())
        if self.beam_grasp_confirmed or self.port.own.servo.get(1) != m2.study.OPEN or peer_holding:
            return self.fail('PREGRASP_RELOOK_WHILE_CLOSED', now)
        self.port.hold(now)
        self.vo_pose = None  # never overwrite shared PF with uncalibrated VO
        self.pregrasp_done = False
        self.pregrasp_started_at = now
        self.beam_grasp_receipt = None
        drv = self.driver
        drv.loc = OwnCamLocalizer(drv.map, drv.loc.params, seed=int(drv.loc.rng.integers(1 << 30)))
        drv.loc.command({'t': float(now), 'kind': 'initial_servo_command', 'pulses': dict(drv.servo)})
        self.pregrasp_sweeps += 1
        self.pg_pans = list(m2.PREGRASP_PANS_V2)
        self.arm.queue({**LOOK_P20, 6: self.pg_pans.pop(0)}, now, duration=.8, settle=.6)
        self.set('pregrasp_look', now, sweep=self.pregrasp_sweeps, profile=PROFILE)

    def _pregrasp_look(self, now, arm_idle):
        from scripts import run_m2_pair as m2

        if not arm_idle:
            return
        # Host on_frame has already fed this own RGB to the SAME pose source
        # read by PairCommandGuard. Do not run a second independent estimate.
        self.look(now)
        if self.pg_pans:
            self.arm.queue({6: self.pg_pans.pop(0)}, now, duration=.4, settle=.6)
            return
        ok = self._grasp_pose_ready(now)
        report = self.port.own.last_report
        self.log(self.rid, 'pregrasp_fix', now, ok=ok, sweep=self.pregrasp_sweeps,
                 std_xy_m=report.std_xy_m if report.initialized else None,
                 std_yaw_rad=report.std_yaw_rad if report.initialized else None,
                 report_t=report.t_est, source='shared own.pose/last_report')
        if not ok:
            if self.pregrasp_sweeps >= m2.PREGRASP_MAX_SWEEPS:
                return self.fail('DOOR_POSE_NOT_LOCALIZED', now)
            return self._queue_grasp(now)
        self.pregrasp_done = True
        self.grasp_estimate = [report.x_m, report.y_m, report.yaw_rad]
        self.claims['grasp_pose_estimate'] = {'xyyaw': list(self.grasp_estimate),
                                            'source': 'shared own.pose/last_report', 'sim_time': now}
        self.arm.queue(m2.ob2.pose_of(self.look_name), now, duration=.8, settle=.3)
        # Capture again after the look sweep, before lowering the open wrist.
        # This also supplies a NEW segment anchor at stored-grip checkpoints.
        self.set('pregrasp_standoff', now)

    def _pregrasp_standoff(self, now, arm_idle):
        if not arm_idle:
            return
        obs = self.look(now)
        if not self.record_standoff(now, obs):
            return self.fail('PREGRASP_BEAM_UNCERTAIN', now)
        self._queue_open_descent(now)

    def _queue_open_descent(self, now):
        from harness.visual_arm import solve_grip_ik, tool_pose
        from scripts import study_owncam_pair_beam as study
        import numpy as np

        bx, by = self.grip_base
        try:
            grasp = solve_grip_ik(bx, by, study.GRASP_Z_M, -90)
            pitch = tool_pose(grasp).pitch_deg
            self.hover = solve_grip_ik(bx, by, study.HOVER_Z_M, pitch)
            path = [solve_grip_ik(bx, by, float(h), pitch)
                    for h in np.linspace(study.HOVER_Z_M, study.GRASP_Z_M, 8)[1:]]
        except Exception as exc:
            return self.fail(f'IK_UNAVAILABLE:{exc}', now)
        self.grasp_pose = path[-1]
        self.arm.queue({**self.hover, 1: study.OPEN}, now, duration=1.)
        for pose in path:
            self.arm.queue(pose, now, duration=.12, settle=0.)
        # Deliberately no close in this queue. Each robot must first publish
        # fresh readiness and consume the same close GO on the control grid.
        self.set('pregrasp_descend', now)

    def tick(self, now):
        if self.state not in ('pregrasp_standoff', 'pregrasp_descend', 'wait_close'):
            return super().tick(now)
        channel, publisher = self.status
        publisher.tick('aligning', now)
        if any(v['state'] == 'abort' for v in channel.partner_view(self.rid, now).values()):
            self.port.hold(now)
            return self.fail('PARTNER_ABORT', now)
        idle = now >= self.arm.until and not self.arm.events
        return getattr(self, '_' + self.state)(now, idle)

    def _pregrasp_descend(self, now, arm_idle):
        if arm_idle:
            self.set('wait_close', now)
            self._wait_close(now, True)

    def _wait_close(self, now, arm_idle):
        from scripts import run_m2_pair as m2

        if not arm_idle:
            return
        obs = self.look(now)
        own = self.port.own
        ready = (self.pregrasp_done and self._grasp_pose_ready(now)
                 and own.servo.get(1) == m2.study.OPEN
                 and all(own.servo.get(k) == v for k, v in self.grasp_pose.items() if k != 1)
                 and valid_frame(obs, self.rid, now) and m2.grip_view_m2(obs['image'])['seen']
                 and self.preclose_check(now, obs))
        self.report('close', obs, now, ready=ready, reason='own relook + open grip view + stationary beam clearance')
        if not ready:
            return self.fail('PREGRASP_NOT_READY', now)
        if now - self.state_t > CLOSE_WAIT_S:
            return self.fail('BARRIER_CLOSE_TIMEOUT', now)
        decision = self.sync_for('close').authorize(now)
        if decision['phase'] == 'ABORT':
            return self.fail('BARRIER_CLOSE_ABORT', now)
        if decision['phase'] == 'GO':
            at = decision['go_at_s']
            self.close_started_at = at
            self.close_issued_at = None
            self.log(self.rid, 'barrier_go', now, barrier='close')
            self.arm.queue({1: m2.study.CLOSED}, at, duration=.5, settle=.4)
            self.set('grasp', now)

    def _grasp(self, now, arm_idle):
        from scripts import run_m2_pair as m2

        if not arm_idle:
            return
        own = self.port.own
        closed = getattr(self, 'close_issued_at', None)
        if (closed is None or closed < getattr(self, 'close_started_at', math.inf)
                or own.servo.get(1) != m2.study.CLOSED
                or not valid_frame(own.last_obs, self.rid, now)
                or own.last_obs['sim_time'] <= closed):
            return self.fail('GRIP_NOT_CONFIRMED', now)
        super()._grasp(now, arm_idle)  # unchanged own-RGB grip check + lift anchor
        if self.state == 'wait_lift':
            self.beam_grasp_receipt = {'segment': self.seg, 'frame_id': own.last_obs['frame_id'],
                                       'sha256': own.last_obs['sha256'], 'observed_at_s': own.last_obs['sim_time'],
                                       'closed_command_at_s': closed, 'source': 'own RGB + issued close'}
            self.log(self.rid, 'beam_grasp_confirmed', now, **self.beam_grasp_receipt)
