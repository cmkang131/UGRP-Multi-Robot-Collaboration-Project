"""Pair adapter's pre-close rendezvous; own RGB and issued commands only.

The frozen M2 CLI remains unchanged. A grip-view receipt is a conservative
attachment hypothesis for the sweep, not a physical success measurement;
M2's independent post-lift co-motion check still applies.
"""
from __future__ import annotations

import math

from harness.zone_own_contract import finite_number
from harness.zone_pair_vision import valid_frame, valid_frame_ob
from harness.zone_pair_align import PairAlignRelook
from harness.owncam_time import accepted_fix_checks

PROFILE = 'zone_pair_grasp_relook_v3'
FIX_STD_XY_M = .05
FIX_STD_YAW_RAD = math.radians(3.)
CLOSE_WAIT_S = 20.


def _frame_gate(controller):
    """The own-image gate for this controller's policy, resolved from this module's names at call time."""
    return valid_frame_ob if getattr(getattr(controller, 'policy', None), 'own_image_ob', False) else valid_frame


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



# Final review P2-3. Input-validity outcomes that carry no alignment verdict:
TRANSIENT_INPUT_REASONS = frozenset(('DUPLICATE_IMAGE', 'OUT_OF_ORDER', 'STALE_OR_CAMERA_MISMATCH',
                                     'IDENTICAL_PIXELS_NO_NEW_COMMAND',
                                     'IMAGE_PRECEDES_ISSUED_COMMAND', 'CAMERA_COMMAND_MISMATCH',
                                     'BEAM_MOVED_OR_ASSOCIATION_LOST', 'PARTIAL_INCONSISTENT_OR_BEAM_MOVED'))
# Identity outcomes another fixed view can resolve (bounded by the posture list):
VIEW_DEPENDENT_REASONS = frozenset(('SHAPE_AMBIGUOUS', 'END_ID_AMBIGUOUS', 'PAIRED_EDGES_UNOBSERVABLE'))

class PairGraspRelook(PairAlignRelook):
    """Mixin before M2DoorStudent. All live inputs come from the own port."""

    def look(self, now):
        obs = super().look(now)
        if self.state == 'align':
            self.record_standoff(now, obs)
        return obs

    def _align(self, now, arm_idle):
        if not getattr(getattr(self,'policy',None),'beam_relative',False):
            return super()._align(now,arm_idle)
        from harness import owncam_pair_beam as ob
        from harness import owncam_pair_beam_v2 as postures
        from scripts.study_owncam_pair_beam import LOOK_EVERY_S, STATE_LIMIT_S
        if not arm_idle or now < self.next_look:
            return
        self.next_look = now+LOOK_EVERY_S
        if now-self.state_t > STATE_LIMIT_S['align']:
            return self.fail('ALIGN_TIMEOUT',now)
        obs = self.look(now)
        relative = self.relative_report(now,obs)
        key = (relative.frame_id,relative.sha256)
        if key == getattr(self,'aligned_frame',None):
            return  # a repeated JPEG is not a second aligned receipt
        self.aligned_frame = key
        if not relative.ready(now):
            self.aligned_streak = 0
            if set(relative.reasons) & TRANSIENT_INPUT_REASONS:
                # Final review P2-3: a stale/duplicate/out-of-order input or a
                # track just dropped for re-identification carries no verdict.
                # Wait for the next own frame; the align deadline bounds this.
                self.log(self.rid,'relative_input_skipped',now,reasons=list(relative.reasons))
                return
            if relative.closing_ready(now):
                # Review 3: identified complete shape, bound too large only
                # from range. Approach under the global envelope, then re-fit.
                command = relative.closing_command()
                if command is not None:
                    if not self.global_certificate(now,relative.beam())['clear']:
                        return self._begin_align_relook(now,'global_safety')
                    self.relative_views_tried = {}
                    self.log(self.rid,'relative_close_in',now,bound_m=relative.std_xy_m+relative.bias_bound_m,
                             grip_base_m=list(relative.grip_base_m),command=command)
                    return self.drive(command,now)
            # Missing longitudinal/depth/identity information is not zero
            # alignment error. A new camera branch will require new images.
            # A view counts as tried only while its image can still be fused
            # (MULTIVIEW_KEEP_S); an interrupted/expired window is retried.
            from harness.zone_pair_relative import MULTIVIEW_KEEP_S
            order = postures.order()
            tried = getattr(self,'relative_views_tried',{})
            if not isinstance(tried, dict):
                tried = {}
            tried = {k:t for k,t in tried.items() if now-t <= MULTIVIEW_KEEP_S}
            tried[self.look_name] = now
            self.relative_views_tried = tried
            choices = [name for name in order if name not in tried]
            if 'END_CLIPPED' in relative.reasons and choices:
                return self._set_look(choices[0],now,reason='relative_end_clipped')
            if 'DISCONNECTED_SHAPE_OR_OCCLUSION' in relative.reasons and choices:
                # Review 3: an adjacent/ambiguous second component is an
                # occluder candidate; another fixed view may separate it.
                return self._set_look(choices[0],now,reason='relative_occluder_candidate')
            if set(relative.reasons) & VIEW_DEPENDENT_REASONS and choices:
                # Final review P2-3: identity not established from this view
                # (e.g. a peer gripper joined to the far end); try the rest.
                return self._set_look(choices[0],now,reason='relative_identity_unknown')
            return self.fail('BEAM_RELATIVE_UNCERTAIN',now)
        if not self.global_certificate(now,relative.beam())['clear']:
            return self._begin_align_relook(now,'global_safety')
        command = ob.align_command(relative.beam())
        if command is not None:
            self.aligned_streak = 0
            self.relative_views_tried = {}
            return self.drive(command,now)
        self.aligned_streak += 1
        self.grip_base = list(relative.grip_base_m)
        if self.aligned_streak >= 2:
            self.claims['aligned'] = {'relative_report':relative.as_dict(),
                                      'errors':ob.align_errors(relative.beam()),'sim_time':now}
            return self._queue_grasp(now)

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

    def _grasp_pose_checks(self, now):
        own = self.port.own
        report = own.last_report
        start = getattr(self, 'pregrasp_started_at', None)
        if getattr(getattr(self,'policy',None),'beam_relative',False):
            relative = self.relative_report(now,own.last_obs)
            return {'relative_ready':relative.ready(now),
                    'global_safety':self.global_certificate(now,relative.beam())['clear']}
        # No VO-only bypass, old low-sigma report, or a different localizer.
        checks = {**accepted_fix_checks(report, now, start, strict_start=False),
                'shared_localizer': self.driver.loc is own.pose.loc,
                'initialized': report is not None and report.initialized,
                'pose_finite': report is not None and all(finite_number(v) for v in (report.x_m, report.y_m, report.yaw_rad)),
                'gate_ok': own.gate.ok,
                'std_xy': report is not None and 0 <= report.std_xy_m <= FIX_STD_XY_M,
                'std_yaw': report is not None and 0 <= report.std_yaw_rad <= FIX_STD_YAW_RAD}
        if getattr(getattr(self,'policy',None),'posterior_relook',False):
            from harness.zone_pair_v6_policy import informative_fix
            checks['informative_fix'] = informative_fix(report)
        return checks

    def _grasp_pose_ready(self, now):
        return all(self._grasp_pose_checks(now).values())

    def _queue_grasp(self, now):
        from harness.owncam_drive import LOOK_P20
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
        if getattr(getattr(self,'policy',None),'beam_relative',False):
            if not self._grasp_pose_ready(now):
                return self.fail('PREGRASP_RELATIVE_OR_GLOBAL_UNCERTAIN',now)
            self.pregrasp_done = True
            r = self.port.own.last_report
            self.grasp_estimate = [r.x_m,r.y_m,r.yaw_rad]  # navigation remains global
            return self._queue_open_descent(now)
        drv = self.driver
        if getattr(getattr(self,'policy',None),'posterior_relook',False):
            from harness.zone_pair_align import MAX_LOOKS, MAX_TOTAL_LOOK_S
            previous = getattr(self,'pregrasp_look_started_at',None)
            if previous is not None and self.state == 'pregrasp_look':
                self.align_look_total_s = getattr(self,'align_look_total_s',0.)+now-previous
            count,total = getattr(self,'align_look_count',0),getattr(self,'align_look_total_s',0.)
            if count>=MAX_LOOKS or total>=MAX_TOTAL_LOOK_S:
                return self.fail('ALIGN_RELOOK_LIMIT',now)
            self.align_look_count=count+1
            self.pregrasp_look_started_at=now
        self._begin_provider_look(now)
        self.pregrasp_sweeps += 1
        self.pg_pans = list(m2.PREGRASP_PANS_V2)
        if getattr(getattr(self,'policy',None),'posterior_relook',False):
            self.relook_excluded = set()
            self.pg_pans = [r['pan'] for r in self.align_look_choices()[:3]]
            if not self.pg_pans:
                return self.fail('PREGRASP_NO_SAFE_VIEW',now)
        self.active_relook_pan = self.pg_pans.pop(0)
        self.relook_directions_used = 1
        self.arm.queue({**LOOK_P20, 6: self.active_relook_pan}, now, duration=.8, settle=.6)
        self.set('pregrasp_look', now, sweep=self.pregrasp_sweeps, profile=PROFILE)

    def _pregrasp_look(self, now, arm_idle):
        from scripts import run_m2_pair as m2

        if not arm_idle:
            return
        # Host on_frame has already fed this own RGB to the SAME pose source
        # read by PairCommandGuard. Do not run a second independent estimate.
        self.look(now)
        if getattr(getattr(self,'policy',None),'posterior_relook',False):
            checks = self._grasp_pose_checks(now)
            if all(checks.values()):
                self.pg_pans.clear()
                self.relook_cancelled = False
            elif [k for k,v in checks.items() if not v] == ['gate_ok']:
                return
            else:
                self.relook_excluded = getattr(self,'relook_excluded',set())
                self.relook_excluded.add(getattr(self,'active_relook_pan',self.port.own.servo[6]))
                if getattr(self,'relook_directions_used',0)>=3:
                    self.pg_pans.clear()
            if (getattr(self,'relook_cancelled',False)
                    and getattr(self,'relook_directions_used',0)<3):
                self.pg_pans = [r['pan'] for r in self.align_look_choices()[:3]]
                self.relook_cancelled = False
                if not self.pg_pans:
                    return self.fail('PREGRASP_NO_SAFE_VIEW',now)
        if self.pg_pans:
            self.active_relook_pan = self.pg_pans.pop(0)
            self.relook_directions_used = getattr(self,'relook_directions_used',0)+1
            self.arm.queue({6: self.active_relook_pan}, now, duration=.4, settle=.6)
            return
        ok = self._grasp_pose_ready(now)
        report = self.port.own.last_report
        self.log(self.rid, 'pregrasp_fix', now, ok=ok, sweep=self.pregrasp_sweeps,
                 checks=self._grasp_pose_checks(now),
                 failed_checks=[k for k, v in self._grasp_pose_checks(now).items() if not v],
                 std_xy_m=report.std_xy_m if report.initialized else None,
                 std_yaw_rad=report.std_yaw_rad if report.initialized else None,
                 report_t=report.t_est, source='shared own.pose/last_report')
        if not ok:
            if self.pregrasp_sweeps >= m2.PREGRASP_MAX_SWEEPS:
                return self.fail('DOOR_POSE_NOT_LOCALIZED', now)
            return self._queue_grasp(now)
        self.pregrasp_done = True
        if getattr(getattr(self,'policy',None),'posterior_relook',False):
            self.align_look_total_s = getattr(self,'align_look_total_s',0.)+now-self.pregrasp_look_started_at
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
        if getattr(getattr(self,'policy',None),'grasp_range_entry',False):
            # v6c: the first READY frame must show the settled grasp pose.
            from harness.zone_pair_grasp_entry_v6c import FINAL_DESCENT_SETTLE_S
            self.arm.until += FINAL_DESCENT_SETTLE_S
        # Deliberately no close in this queue. Each robot must first publish
        # fresh readiness and consume the same close GO on the control grid.
        self.set('pregrasp_descend', now)

    def tick(self, now):
        if self.state == 'pregrasp_look' and getattr(getattr(self,'policy',None),'posterior_relook',False):
            from harness.zone_pair_align import MAX_LOOK_S, MAX_TOTAL_LOOK_S
            elapsed=now-self.pregrasp_look_started_at
            if elapsed>=MAX_LOOK_S or elapsed+getattr(self,'align_look_total_s',0.)>=MAX_TOTAL_LOOK_S:
                return self.fail('PREGRASP_RELOOK_TIMEOUT',now)
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
                 and _frame_gate(self)(obs, self.rid, now)
                 and (getattr(getattr(self,'policy',None),'beam_relative',False)
                      or m2.grip_view_m2(obs['image'])['seen'])
                 and self.preclose_check(now, obs))
        self.report('close', obs, now, ready=ready, reason='own relook + open grip view + stationary beam clearance')
        if not ready:
            checks = self._grasp_pose_checks(now)
            self.log(self.rid, 'pregrasp_fix_rejected', now, checks=checks,
                     failed_checks=[k for k, v in checks.items() if not v],
                     last_fix_t=own.last_report.last_fix_t, report_t=own.last_report.t_est)
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
                or not _frame_gate(self)(own.last_obs, self.rid, now)
                or own.last_obs['sim_time'] <= closed):
            return self.fail('GRIP_NOT_CONFIRMED', now)
        super()._grasp(now, arm_idle)  # unchanged own-RGB grip check + lift anchor
        if self.state == 'wait_lift':
            self.beam_grasp_receipt = {'segment': self.seg, 'frame_id': own.last_obs['frame_id'],
                                       'sha256': own.last_obs['sha256'], 'observed_at_s': own.last_obs['sim_time'],
                                       'closed_command_at_s': closed, 'source': 'own RGB + issued close'}
            self.log(self.rid, 'beam_grasp_confirmed', now, **self.beam_grasp_receipt)
