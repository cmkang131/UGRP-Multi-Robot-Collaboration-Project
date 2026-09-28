"""Bounded active wrist looks before/during align; own inputs, no plant access."""
from __future__ import annotations

import math

from harness.zone_own_contract import finite_number, pose_report_fresh
from harness.zone_own_guards import OwnPose
from harness.owncam_time import accepted_fix_checks

# Scheduling reserves, NOT changes to the 70/50 mm, 3 degree safety gates.
# dev08 own reports: age=6 at 166.3, sigma_xy=.05486; HIGH at 175.6.
MAX_FIX_GAP_S = 6.
RELOOK_XY_M = .055
RELOOK_YAW_RAD = math.radians(2.5)
MAX_LOOKS = 8                 # per alignment attempt (final review P2-2), including entry looks
MAX_LOOK_S = 8.               # includes stop, arm settling and return posture
MAX_TOTAL_LOOK_S = 40.
MAX_DIRECTIONS = 3
RELOOK_STATES = ('align_relook_stop', 'align_relook', 'align_relook_return')


def relook_reason(report, now):
    if not pose_report_fresh(report, now) or not report.initialized:
        return 'pose_missing'
    age = report.fix_age_s
    fix_age = now - report.last_fix_t if finite_number(report.last_fix_t) else math.inf
    if not finite_number(age) or age < 0 or fix_age < 0 or fix_age >= MAX_FIX_GAP_S - 1e-8:
        return 'fix_gap'
    if report.std_xy_m >= RELOOK_XY_M or report.std_yaw_rad >= RELOOK_YAW_RAD:
        return 'sigma_reserve'
    return None


def ranked_look_pans(static_map, report, servo, guard, provider, *, recovery_v6=False, excluded=(), safety_pose=None):
    """Rank collision-safe LOOK_P20 directions by the provider's proposal score.

    A prediction never qualifies as a fix. Only a subsequent accepted own
    observation can permit resumption, through the common report contract.
    """
    from harness.owncam_drive import LOOK_P20
    from scripts.run_m2_pair import PREGRASP_PANS_V2

    pose = safety_pose if safety_pose is not None else OwnPose.from_report(report)
    if pose is None:
        return []
    candidates = []
    for pan in dict.fromkeys(PREGRASP_PANS_V2):
        if pan in excluded:
            continue
        target = {**LOOK_P20, 1: servo[1], 6: pan}
        plan = guard.plan(servo, target, [pan], pose, loaded=False, allow_backoff=False)
        if plan['reason'] != 'clear' or not plan.get('transition_clear'):
            continue
        score = provider.expected_observability(pose, pan, static_map)
        if recovery_v6:
            gap = min(guard.arm_clearance(target,pose,loaded=False)[0], guard.chassis_clearance(pose)[0])
            clearance_weight = max(0.,min(1.,gap/.2))
            move_cost = 1.+abs(pan-servo[6])/500.
            score = score*clearance_weight/move_cost
        if finite_number(score) and score > 0:
            candidates.append({'pan': pan, 'observability_score': score})
    return sorted(candidates, key=lambda x: (-x['observability_score'], abs(x['pan'] - servo[6]), x['pan']))


class PairAlignRelook:
    """Adapter mixin; frozen M2 beam alignment itself is unchanged."""

    def _enter_budget_phase(self, now, phase):
        reset = getattr(self, 'reset_phase_budget', None)
        if reset is not None:
            reset(now, phase)
        self.align_look_count, self.align_look_total_s = 0, 0.
        self.pregrasp_look_started_at = None

    def _cp_open(self, now, arm_idle):
        # Stored regrasp calls _queue_grasp directly in the frozen controller;
        # it never enters set('align'). Reset before that call in all policies,
        # exactly once on checkpoint completion, never on its subsequent looks.
        if arm_idle and self.regrasp == 'stored':
            self._enter_budget_phase(now, 'stored_regrasp')
        return super()._cp_open(now, arm_idle)

    def set(self, state, now, **detail):
        if state in ('approach', 'reapproach', 'align'):
            # Final review P2-2: look/HIGH budgets are per phase entry (each
            # approach and each alignment attempt, incl. regrasp), identical
            # for v5h / b-only / a+b; a resumed align (relook return) does not
            # come through here and never refills them.
            self._enter_budget_phase(now, state)
        if state == 'align':
            self.align_started_at = now
            if getattr(getattr(self,'policy',None),'beam_relative',False):
                return super().set(state, now, **detail)
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
        self.relook_excluded = set()
        self.relook_cancelled = False
        self.aligned_streak = 0
        self.vo_pose = None
        report = self.port.own.last_report
        self.log(self.rid, 'align_relook_trigger', now, reason=reason,
                 count=self.align_look_count, fix_age_s=report.fix_age_s,
                 std_xy_m=report.std_xy_m, std_yaw_rad=report.std_yaw_rad)
        super().set('align_relook_stop', now)
        self.status[1].tick('aligning', now)

    def align_relook_expired(self, now):
        if self.state not in RELOOK_STATES:
            return False
        elapsed = now - self.align_look_started_at
        return elapsed >= MAX_LOOK_S - 1e-8 or self.align_look_total_s + elapsed >= MAX_TOTAL_LOOK_S - 1e-8

    def _align_fix_checks(self, now):
        from harness.zone_pair_grasp import FIX_STD_XY_M, FIX_STD_YAW_RAD

        own, start = self.port.own, self.align_look_started_at
        r = own.last_report
        fix = None if r is None else r.last_fix_t
        checks = {**accepted_fix_checks(r, now, start),
                'shared_localizer': self.driver.loc is own.pose.loc,
                'initialized': r is not None and r.initialized, 'gate_ok': own.gate.ok,
                'pose_finite': r is not None and all(finite_number(v) for v in (r.x_m, r.y_m, r.yaw_rad)),
                'std_xy': r is not None and 0 <= r.std_xy_m <= FIX_STD_XY_M,
                'std_yaw': r is not None and 0 <= r.std_yaw_rad <= FIX_STD_YAW_RAD,
                'fix_gap': finite_number(fix) and 0 <= now - fix < MAX_FIX_GAP_S - 1e-8,
                'sigma_reserve': r is not None and r.std_xy_m < RELOOK_XY_M and r.std_yaw_rad < RELOOK_YAW_RAD}
        if getattr(getattr(self,'policy',None),'posterior_relook',False):
            from harness.zone_pair_v6_policy import informative_fix
            checks['informative_fix'] = informative_fix(r)
        if getattr(getattr(self,'policy',None),'beam_relative',False):
            checks['global_anchor_verified'] = self.global_certificate(now)['clear']
        return checks

    def cancel_relook_pan(self, now):
        if self.state == 'align_relook_return':
            return self.fail('ALIGN_RETURN_VIEW_BLOCKED',now)
        self.relook_excluded = getattr(self,'relook_excluded',set())
        self.relook_excluded.add(getattr(self,'active_relook_pan',self.port.own.servo[6]))
        self.relook_cancelled = True
        self.log(self.rid,'relook_pan_cancelled',now,excluded=sorted(self.relook_excluded),
                 reason='blocked sweep; queue discarded; replan from issued PWM')

    def _begin_provider_look(self, now):
        if getattr(getattr(self,'policy',None),'posterior_relook',False):
            from harness.owncam_recovery_v6 import begin_observation
            quality = self.port.own.last_report.observation_quality or {}
            begin_observation(self.port.own.pose,now,self.port.own.servo,lost=quality.get('lost') is True)
        else:
            self.port.own.pose.begin_relocalization(now,self.port.own.servo)

    def _align_fix_ready(self, now):
        return all(self._align_fix_checks(now).values())

    def _log_align_fix_rejection(self, now, checks, **extra):
        r = self.port.own.last_report
        self.log(self.rid, 'align_relook_fix_rejected', now, checks=checks,
                 failed_checks=[k for k, v in checks.items() if not v],
                 last_fix_t=None if r is None else r.last_fix_t,
                 report_t=None if r is None else r.t_est, started_at_s=self.align_look_started_at, **extra)

    def _align_relook_stop(self, now, arm_idle):
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
        self._begin_provider_look(now)
        self.active_relook_pan = self.align_pans.pop(0)
        self.relook_directions_used = 1
        self.arm.queue({**LOOK_P20, 1: self.port.own.servo[1], 6: self.active_relook_pan},
                       now, duration=.8, settle=.6)
        super().set('align_relook', now)

    def _align_relook(self, now, arm_idle):
        from harness.owncam_pair_beam_v2 import pose_of

        if not arm_idle:
            return
        obs = self.look(now)
        checks = self._align_fix_checks(now)
        checks['frame_after_arm'] = obs['sim_time'] >= self.arm.until - 1e-8
        if all(checks.values()):
            self.log(self.rid, 'align_relook_fix', now, report_t=self.port.own.last_report.t_est,
                     frame_id=obs['frame_id'], sha256=obs['sha256'], source='shared own.pose/last_report')
            self.arm.queue(pose_of(self.align_resume_name), now, duration=.6, settle=.3)
            return super().set('align_relook_return', now)
        self._log_align_fix_rejection(now, checks, frame_id=obs['frame_id'])
        if getattr(getattr(self,'policy',None),'posterior_relook',False):
            if set(k for k,v in checks.items() if not v) <= {'gate_ok', 'global_anchor_verified'}:
                return  # dev14: let the unchanged dwell finish; no new pan
            self.relook_excluded = getattr(self,'relook_excluded',set())
            self.relook_excluded.add(getattr(self,'active_relook_pan',self.port.own.servo[6]))
            if getattr(self,'relook_directions_used',0)>=MAX_DIRECTIONS:
                return self.fail('ALIGN_RELOOK_NO_FIX',now)
            if getattr(self,'relook_cancelled',False):
                self.align_pans = [r['pan'] for r in self.align_look_choices()[:MAX_DIRECTIONS]]
                self.relook_cancelled = False
        if not self.align_pans:
            return self.fail('ALIGN_RELOOK_NO_FIX', now)
        self.active_relook_pan = self.align_pans.pop(0)
        self.relook_directions_used = getattr(self,'relook_directions_used',0)+1
        self.arm.queue({6: self.active_relook_pan}, now, duration=.4, settle=.6)

    def _align_relook_return(self, now, arm_idle):
        if not arm_idle:
            return
        checks = self._align_fix_checks(now)
        if not all(checks.values()):
            self._log_align_fix_rejection(now, checks)
            return self.fail('ALIGN_RELOOK_FIX_EXPIRED', now)
        self.align_look_total_s += now - self.align_look_started_at
        self.relative_views_tried = {}  # the relook interrupted any multiview window
        reset = getattr(self, 'reset_object_anchor', None)
        if reset is not None:
            reset()  # re-anchor from the refreshed global fix and the next ready view
        self.next_look = now
        super().set('align', now, resumed=True)
        # Keep the original align deadline; looks cannot refill it.
        self.state_t = self.align_started_at

    def tick(self, now):
        if self.state == 'align':
            reason = relook_reason(self.port.own.last_report, now)
            if getattr(getattr(self,'policy',None),'beam_relative',False):
                # A stale absolute fix does not redefine local alignment. Its
                # independently growing safety envelope decides when to stop.
                safety = self.global_certificate(now)
                reason = ('global_safety' if not safety['clear'] else
                          'global_safety_reserve' if safety.get('relook_reserve_low') else None)
                begin = getattr(self, 'begin_scheduled_reobserve', None)
                if reason == 'global_safety_reserve' and begin is not None and not begin(now):
                    return self.fail('PAIR_SCHEDULED_REOBSERVE_LIMIT', now)
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
