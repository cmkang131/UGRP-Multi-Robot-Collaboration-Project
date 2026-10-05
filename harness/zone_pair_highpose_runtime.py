"""Instance-only pose adaptation of the existing v3 beam-relative student."""
import copy
from types import MethodType

import numpy as np

from harness import zone_final_pair_skill as previous
from harness import zone_pair_highpose as pose
from harness import zone_pair_highpose_blind_close as blind
from harness import zone_pair_highpose_final_veto as final_veto
from harness import zone_pair_highpose_frame_gate as frame_gate
from harness import zone_pair_highpose_grip as grip
from harness import zone_pair_highpose_guardlog as guardlog
from harness import zone_pair_highpose_lookaround as lookaround
from harness import zone_pair_highpose_relook as relook
from harness import zone_pair_highpose_start_relief as start_relief
from harness import zone_pair_highpose_guard_log_only as guard_log_only
from harness import zone_pair_highpose_own_load_occlusion as occlusion
from harness import zone_pair_highpose_contract as hp_contract
from harness import zone_pair_highpose_carry_align as carry_align
from harness import zone_pair_highpose_posture_defer as posture_defer
from harness import zone_pair_highpose_dr_checkpoint as dr_checkpoint
from harness import zone_pair_highpose_approach_looks as approach_looks
from harness import zone_pair_highpose_arrival_confirm as arrival_confirm
from harness import zone_pair_highpose_refix as refix
from harness import zone_pair_highpose_progress as progress
from harness.zone_final_pair_binding import bind
from harness.zone_final_pair_runtime import Runtime as PreviousRuntime
from harness.zone_final_pair_guards import CommandGuard as PreviousGuard
from harness.zone_own_executor import ZoneOwnExecutor
from harness.zone_pair_executor import PairExecution
from harness.zone_pair_grasp import PairGraspRelook
from harness.zone_pair_guards import PairCommandGuard
from harness.zone_pair_highpose_edge import HIGH_EDGE_INFORMATIVE, robust_edge_line as edge_line
from scripts import run_m2_pair as m2

# Grasp-time own grip view (close readiness + GRIP_NOT_SEEN): LOG-ONLY in v98 (registry grip_monitor).
GRASP_TIME_VIEW = grip.GRASP_TIME_VIEW


GRASP_RECEIPT_CARRIED_EVENT = 'beam_grasp_receipt_carried'


def carry_grasp_receipt(ctl, t):
    """Keep the own grasp receipt across an intermediate HIGH stop (v98 keeps the beam closed at HIGH).

    The parent's ``PairGraspRelook.beam_grasp_confirmed`` (zone_pair_grasp.py, frozen) is true only while the
    receipt's ``segment`` equals the current ``seg``; it was written for the inherited route, which lowered, opened
    and re-grasped at every checkpoint. v96/v98 stop at HIGH and only advance ``seg``, so from leg 1 on the
    controller read "not carrying" while holding the beam, and the pair guard computed its sweep certificates with
    ``loaded=False`` (beam not in the swept volume) on exactly the door legs. Recorded: align_to_carry@1236c63d,
    receipt segment 0, checkpoint stops seg 1 and 2 with the gripper closed (tests/fixtures/
    v98_grasp_receipt_segments_1236c63d.json).

    The receipt moves to the new segment only when it belonged to the previous segment; the parent already clears it
    on any issued open (``on_issued_command``, pulse >= 2000), and the property still requires the issued gripper
    pulse < 2000, so the carried receipt rests on the own issued-command history only (the v98 grip decision). The
    attached-object convention is the standard one (MoveIt attached collision objects stay attached across motions
    until an explicit detach; 미확인: not re-read for this change).
    """
    receipt = getattr(ctl, 'beam_grasp_receipt', None)
    if not receipt or receipt.get('segment') != ctl.seg-1:
        return False
    minted = receipt.get('minted_segment', receipt['segment'])
    ctl.beam_grasp_receipt = {**receipt, 'segment': ctl.seg, 'minted_segment': minted,
                              'carried_from_segment': ctl.seg-1, 'carried_at_s': t,
                              'carried_by': 'own issued commands: closed at HIGH through the stop, no open issued'}
    ctl.log(ctl.rid, GRASP_RECEIPT_CARRIED_EVENT, t, segment=ctl.seg, from_segment=ctl.seg-1, minted_segment=minted)
    return True


class HighController:
    """v96 HIGH carry. Grip monitor is LOG-ONLY (first-E2E scope, user 2026-10-03).

    Phase progress and barrier readiness come from this robot's own command
    history (gripper commanded closed in this grasp epoch, queued pose path
    reached) plus the existing fixed-enum partner status. Own-RGB grip values
    (low-lift co-motion IoU, transit relation()/stability, HIGH/floor anchor
    IoU, edge line) go to ``self.grip_monitor`` (write-only) and are exported
    only in the evaluation records. A dropped beam is not detected or
    signalled in-run in this version; success is judged only by evaluation.
    v98: the grasp-time grip view (pre-close readiness term and post-close
    GRIP_NOT_SEEN) is log-only as well; see ``_wait_close`` and
    ``GraspViewLogOnly``.
    """

    def _issued(self):
        # ArmSequence.commanded is the future queue endpoint, NOT issued PWM.
        return dict(self.port.own.servo)

    def _monitor(self, kind, now, **values):
        self.grip_monitor.record(self.rid, kind, now, epoch=getattr(self, 'grip_epoch', None),
                                 seg=getattr(self, 'seg', None), state=self.state, **values)

    def held_by_command(self):
        """Own command history only: closed in this epoch and still commanded closed."""
        return (getattr(self, 'grip_closed_epoch', None) == getattr(self, 'grip_epoch', None)
                and self._issued().get(1) == m2.study.CLOSED and self.state != 'failed')

    def _queue_open_descent(self, now):
        self.high_raising, self.high_ready = False, False
        self.grip_epoch = getattr(self, 'grip_epoch', 0)+1
        self.pose_anchors = {}
        self.transit = None
        self.floor_return_verified = False
        return super()._queue_open_descent(now)

    def _anchor(self, name, obs, now):
        # Monitor reference only (eval log); never a readiness input.
        key = grip.pose_key(self.pose_of(obs))
        self.pose_anchors[name] = grip.Anchor(self.grip_epoch, key,
            m2.hv3.hold_view_mask(obs['image']).copy(), obs['frame_id'], now)
        self._monitor('anchor', now, pose=name, frame_id=obs['frame_id'],
                      mask_px=int(self.pose_anchors[name].mask.sum()))

    def _wait_close(self, now, arm_idle):
        """``PairGraspRelook._wait_close`` with the open-grip view LOG-ONLY (v98).

        At the floor grasp pose the beam is outside the masterpi_v3 camera view (0 of 18 beam points in
        the field of view), so ``grip_view_m2`` cannot see it there. Under the user's log-only grip decision
        the view is recorded with ``applied=False`` and is not a readiness term. Every other term is the
        parent's: own fix checks, own servo commanded open at the grasp pose, valid own frame, stationary
        beam clearance, then the fixed-enum close barrier with its timeout. The valid-frame check is the v98
        gate (``zone_pair_highpose_frame_gate``, floor_light_v1 values); it still acts.
        """
        from harness.zone_pair_grasp import CLOSE_WAIT_S

        if not arm_idle:
            return
        obs = self.look(now)
        own = self.port.own
        track = getattr(self, 'blind_track', None)     # v98 blind final approach (zone_pair_highpose_blind_close)
        if track is not None:
            track.blind_code = None
        view = m2.grip_view_m2(obs['image'])
        self._monitor('close_grip_view', now, frame_id=obs['frame_id'], applied=False, **view)
        ready = (self.pregrasp_done and self._grasp_pose_ready(now)
                 and own.servo.get(1) == m2.study.OPEN
                 and all(own.servo.get(k) == v for k, v in self.grasp_pose.items() if k != 1)
                 and frame_gate.controller_gate(self)(obs, self.rid, now)
                 and self.preclose_check(now, obs))
        self.report('close', obs, now, ready=ready,
                    reason='own relook + issued open grip + stationary beam clearance (grip view log-only)')
        if not ready:
            checks = self._grasp_pose_checks(now)
            self.log(self.rid, 'pregrasp_fix_rejected', now, checks=checks,
                     failed_checks=[k for k, v in checks.items() if not v],
                     last_fix_t=own.last_report.last_fix_t, report_t=own.last_report.t_est)
            code = getattr(track, 'blind_code', None)
            if code is not None:
                self.log(self.rid, 'blind_final_approach_refused', now, code=code, window=track.window_record())
            return self.fail('PREGRASP_NOT_READY' if code is None else 'PREGRASP_'+code, now)
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
        # PairGraspRelook: GRIP_NOT_CONFIRMED (issued close + fresh valid own frame after it), unchanged
        # except that the valid-frame check is the v98 gate; its super()._grasp then reaches GraspViewLogOnly
        # (v98): the post-close own grip view is logged, not applied. Nothing between HighController and
        # PairGraspRelook defines _grasp (tests/test_highpose_frame_gate.py).
        _RELOOK_GRASP(self, now, arm_idle)
        if self.state == 'wait_lift':
            self.grip_closed_epoch = self.grip_epoch
            if 'floor' not in self.pose_anchors:
                self._anchor('floor', self.look(now), now)

    def report(self, key, obs, now, ready=True, reason=''):
        if key in ('lift', 'carry', 'lower', 'open') and str(reason).startswith('hold_ratio='):
            reason = 'grip by own command history (v96 grip monitor log-only)'
        return super().report(key, obs, now, ready=ready, reason=reason)

    def _partner_transit_ok(self, now, phase):
        if self.status is None:
            return False
        peers = self.status[0].partner_view(self.rid, now)
        allowed = {'lift'} if phase == 'raise' else {'put_down'}
        # One actor is stepped before the other on the same tick. Only the
        # first 100 ms can see the phase just before GO; no long grace period.
        if now-self.transit.started_at <= .1+1e-8:
            allowed.add('ready' if phase == 'raise' else 'carry')
        return bool(peers) and all(p['alive'] and p['state'] in allowed for p in peers.values())

    def _transit_abort(self, reason, now):
        self.arm.events.clear()
        self.arm.until = now
        self.arm.commanded = self._issued()
        self.high_ready = self.floor_return_verified = False
        self.anchor_full = None
        self.pose_anchors = {}
        self.port.hold(now)
        return self.fail(reason, now)

    def _start_transit(self, phase, path, now):
        servo = self._issued()
        pose.queue_path(self.arm, now, path)
        self.transit = grip.TransitMonitor(phase, now, servo, self.arm.events, self.arm.until,
                                           self.grip_epoch, sink=self.grip_monitor, rid=self.rid)
        self.next_transit_look = now
        return self._monitor_transit(now)

    def _monitor_transit(self, now):
        if now < self.next_transit_look-1e-8:
            return True
        self.next_transit_look = now+grip.SAMPLE_S
        obs, servo = self.look(now), self._issued()
        ok = self.transit.observe(now, obs, servo,
                    self._partner_transit_ok(now, self.transit.phase))
        self.log(self.rid, 'transit_progress', now, phase=self.transit.phase,
                 ok=ok, reason=self.transit.failure, epoch=self.grip_epoch,
                 decided_by='own_command_history+partner_status')
        if not ok:
            self._transit_abort(self.transit.failure, now)
        return ok

    def _low_lift(self, now, arm_idle):
        # Low lift (hover, closed) reached by own command; the legacy co-motion
        # check LOAD_NOT_HELD_AFTER_LIFT is logged, never applied.
        if not arm_idle:
            return
        if not self.held_by_command():
            return self.fail('LIFT_GRIP_NOT_COMMANDED_CLOSED', now)
        obs = self.look(now)
        from harness import owncam_pair_lift_v3 as lv3
        iou = (m2.study.ob.signature_iou(self.anchor, self._signature(obs['image']))
               if getattr(self, 'anchor', None) is not None else None)
        self._monitor('low_lift_view', now, frame_id=obs['frame_id'], frame_sha256=obs.get('sha256'),
                      co_motion_iou=iou, legacy_min_iou=lv3.HOLD_MIN_IOU,
                      legacy_check='LOAD_NOT_HELD_AFTER_LIFT',
                      legacy_would_fail=None if iou is None else bool(iou < lv3.HOLD_MIN_IOU))
        self.anchor, self.anchor_kind = m2.study.ob.held_signature(obs['image']), 'lime_v1'
        self.anchor_full = m2.hv3.hold_view_mask(obs['image'])
        self.claims.setdefault('lifts', []).append({'seg': self.seg, 'decided_by': 'own_command_history',
                                                    'sim_time': now})
        self.claims['lifted'] = {'decided_by': 'own_command_history', 'sim_time': now}
        self.high_raising, self.high_ready = True, False
        self.set('lift', now, subphase='raise_to_high', pose_id=pose.POSE_ID)
        self._start_transit('raise', pose.raise_path(), now)

    def _lift(self, now, arm_idle):
        if not getattr(self, 'high_raising', False):
            return self._low_lift(now, arm_idle)
        if not self._monitor_transit(now) or not arm_idle:
            return
        if not self.transit.complete(now):
            return self._transit_abort('HIGH_TRANSIT_EVIDENCE_INCOMPLETE', now)
        if not pose.at_high(self._issued()) or not self.held_by_command():
            return self._transit_abort('HIGH_POSE_NOT_COMMANDED', now)
        obs = self.look(now)
        rgb = m2.study.ob.decode(obs['image'])[..., ::-1]
        line = edge_line(np.ascontiguousarray(rgb))
        self._anchor('high', obs, now)
        self._monitor('high_view', now, frame_id=obs['frame_id'], frame_sha256=obs.get('sha256'),
                      edge_seen=line is not None, edge_columns=None if line is None else line[2],
                      edge_slope=None if line is None else line[0], edge_fit=getattr(line, 'fit', None),
                      edge_y320_px=None if line is None else line[1],
                      relation=grip.relation(obs['image'], self._issued()))
        self.anchor = m2.study.ob.held_signature(obs['image'])
        self.anchor_kind = 'lime_v1'
        self.anchor_full = self.pose_anchors['high'].mask.copy()
        self.high_ready = True
        self.log(self.rid, 'high_carry_pose', now, pose_id=pose.POSE_ID,
                 decided_by='own_command_history', physical_success=None)
        self.set('wait_carry', now)

    def hold_state(self, obs):
        """Readiness = own command history. Visual values are logged only."""
        servo = self.pose_of(obs)
        values = {'frame_id': obs['frame_id'], 'frame_sha256': obs.get('sha256')}
        try:
            if not getattr(self, 'high_raising', False):
                legacy = super().hold_state(obs)
                values.update(legacy_ok=legacy['ok'], v1_ratio=legacy['v1_ratio'],
                              v3_iou=legacy['v3_iou'], legacy_decided_by=legacy['decided_by'])
            else:
                name = 'high' if pose.at_high(servo) else 'floor'
                anchor = self.pose_anchors.get(name)
                values.update(anchor=name, anchor_iou=(m2.hv3.hold_iou(anchor.mask, obs['image'])
                                                       if anchor is not None else None))
                if name == 'high':
                    values['relation'] = grip.relation(obs['image'], servo)
        except Exception as exc:          # noqa: BLE001 - logged, never gates
            values['monitor_error'] = type(exc).__name__
        self._monitor('hold_view', now=float(obs['sim_time']), **values)
        return {'ok': self.held_by_command(), 'v1_ratio': 0., 'v3_iou': None,
                'decided_by': 'own_command_history_v96'}

    def _wait_carry(self, now, arm_idle):
        if not getattr(self, 'high_ready', False):
            return self.fail('HIGH_CARRY_VIEW_REQUIRED', now)
        if getattr(self, 'checkpoint_fix_after', None) is not None:
            from harness.zone_pair_highpose_timing import CHECKPOINT_REOBSERVE_S
            report = self.port.own.last_report
            # v98 (zone_pair_highpose_dr_checkpoint): no wall is visible at HIGH, so a fresh fix cannot come;
            # an own DR report inside the derived budget (67.4 mm / 2.89 deg, decision 5) is the receipt, over budget
            # aborts now (with the sigma re-fix mixin an over-budget report was already turned into a re-fix before the barrier).
            kind, detail = dr_checkpoint.decide(report, now, self.checkpoint_started, self.checkpoint_fix_after,
                                                CHECKPOINT_REOBSERVE_S)
            if kind == 'over':
                self.log(self.rid, dr_checkpoint.OVER_EVENT, now, seg=self.seg, high=True, **detail)
                if not light_soft(self, dr_checkpoint.OVER_REASON, now, 'wait_carry.dr_checkpoint'):
                    return self._transit_abort(dr_checkpoint.OVER_REASON, now)
                kind = 'dr'                         # DEV light: continue on the DR estimate (logged above)
            # Localization re-observe (navigation) keeps its bounded timeout.
            if now-self.checkpoint_started > 8.:
                if not light_soft(self, 'HIGH_CHECKPOINT_REOBSERVE_TIMEOUT', now, 'wait_carry.dr_checkpoint'):
                    return self._transit_abort('HIGH_CHECKPOINT_REOBSERVE_TIMEOUT', now)
                if kind == 'wait':
                    kind = 'dr'                     # DEV light: continue on the DR estimate
            if now >= self.next_look:
                self.next_look = now+m2.study.LOOK_EVERY_S
                obs = self.look(now)
                self.hold_state(obs)      # grip values logged only
                self.report('carry', obs, now, ready=False, reason='HIGH stop/reobserve pending')
            if kind == 'wait':
                return
            self.grasp_estimate = [float(report.x_m), float(report.y_m), float(report.yaw_rad)]
            if kind == 'fix':
                # detail carries fix_t (= report.last_fix_t) and the log-only own mean/cov (eval-only NEES scorer).
                self.log(self.rid, dr_checkpoint.FIX_EVENT, now, seg=self.seg,
                         high=True, opened=False, epoch=self.grip_epoch, **detail)
            else:
                self.log(self.rid, dr_checkpoint.DR_EVENT, now, seg=self.seg, high=True, opened=False,
                         epoch=self.grip_epoch, **detail)
            self.checkpoint_fix_after = None
        provider = self.port.own.pose.provider
        if (HIGH_EDGE_INFORMATIVE and not provider.beam_edge.available(now)
                and self.__dict__.get('dev_light_skip_edge_wait') != self.state_t):     # v98: no edge reference to wait for otherwise
            if now-self.state_t > m2.study.STATE_LIMIT_S['wait_carry']:
                if not light_soft(self, 'HIGH_CARRY_EDGE_REFERENCE_TIMEOUT', now, 'wait_carry.edge'):
                    return self.fail('HIGH_CARRY_EDGE_REFERENCE_TIMEOUT', now)
                self.dev_light_skip_edge_wait = self.state_t   # DEV light: this wait only, carry on without the edge
                return super()._wait_carry(now, arm_idle)
            if now >= self.next_look:
                self.next_look = now+m2.study.LOOK_EVERY_S
                self.report('carry', self.look(now), now, ready=False, reason='HIGH edge reference pending')
            return
        return super()._wait_carry(now, arm_idle)

    def door_schedule(self, t0):
        # v98 (zone_pair_highpose_carry_align) pair-neutral v2: the parent's schedule with the loaded door-axis align
        # command ALWAYS zero for BOTH robots (no lateral/yaw correction while loaded). The own significance test
        # (two-sided 95 %) and the command it would have issued are only logged (would_*); timing and pair_plan are
        # the parent's, unchanged. (v1, per-robot significance, is superseded: see the carry_align history note.)
        from harness.zone_pair_highpose_motion_v102 import shared_motor_command
        with shared_motor_command():     # v102 affine dead zone without editing the hash-pinned shared skill
            schedule = super().door_schedule(t0)
        return carry_align.gate_schedule(self, schedule, t0)

    def _wait_lower(self, now, arm_idle):
        # v98 (zone_pair_highpose_refix): a decided sigma re-fix takes the final set-down path at this stop.
        if self.seg+1 < len(self.segments) and not getattr(self, 'refix_active', False):
            # Same end-of-leg lower barrier is a STOP rendezvous only. It never
            # queues lower/open/raise. Change segment keys after both stop.
            def checkpoint(t):
                self.seg += 1
                carry_grasp_receipt(self, t)
                self.checkpoint_started = t
                self.checkpoint_fix_after = t
                self.grasp_estimate = None
                self.next_look = t
                self.port.own.pose.begin_relocalization(t, self._issued())
                self.log(self.rid, 'checkpoint_high_stop', t, seg=self.seg,
                         high=True, opened=False, epoch=self.grip_epoch)
            self._wait('lower', 'wait_carry', now, checkpoint)
            return
        def go(t):
            self.high_ready = False
            self.floor_return_verified = False
            self._start_transit('lower', pose.lower_path(), t)
        # Guard against the parent's unconditional set(nxt) after on_go when
        # the first lower observation already failed.
        self._wait('lower', 'lower', now, go)
        if self.transit is not None and self.transit.failure:
            self._transit_abort(self.transit.failure, now)

    def _lower(self, now, arm_idle):
        if not self._monitor_transit(now) or not arm_idle:
            return
        if not self.transit.complete(now):
            return self._transit_abort('LOWER_TRANSIT_EVIDENCE_INCOMPLETE', now)
        floor = self.pose_anchors.get('floor')
        at_floor = all(self._issued().get(k) == v for k, v in self.grasp_pose.items() if k != 1)
        if not at_floor or not self.held_by_command():
            return self._transit_abort('FLOOR_POSE_NOT_COMMANDED', now)
        obs = self.look(now)
        self._monitor('floor_return_view', now, frame_id=obs['frame_id'], frame_sha256=obs.get('sha256'),
                      anchor_iou=None if floor is None else m2.hv3.hold_iou(floor.mask, obs['image']),
                      anchor_mask_px=None if floor is None else int(floor.mask.sum()),
                      legacy_min_iou=m2.hv3.HOLD_MIN_IOU, legacy_check='FLOOR_RETURN_GRIP_CHANGED')
        self.floor_return_verified = True     # commanded floor pose reached, still closed
        return self.set('wait_open', now)

    def _wait_open(self, now, arm_idle):
        # An intermediate release only for a decided re-fix; the parent then opens to the v3 ``cp_open`` path.
        intermediate = self.seg+1 < len(self.segments)
        if (intermediate and not getattr(self, 'refix_active', False)) or not self.floor_return_verified:
            return self._transit_abort('FINAL_FLOOR_RELEASE_REQUIRED', now)
        return super()._wait_open(now, arm_idle)

# Frozen code objects run with the v98 frame gate (zone_pair_highpose_frame_gate.gated); none calls super().
_RELOOK_GRASP = frame_gate.gated(PairGraspRelook._grasp, _frame_gate=frame_gate.controller_gate)


class light_aborts:
    """DEV light (user 2026-10-05 "다 라이트 하게 줄여"): inside the block, ``ep.abort`` with a soft reason is recorded
    in ``soft`` instead of aborting. Hard reasons abort as before. No-op when DEV_LIGHT is off."""

    def __init__(self, ep, soft):
        self.ep, self.soft = ep, soft

    def __enter__(self):
        ep = self.ep
        self.shadowed, self.real = 'abort' in vars(ep), getattr(ep, 'abort', None)
        self.on = hp_contract.DEV_LIGHT and self.real is not None
        if self.on:
            real, soft = self.real, self.soft
            def abort(t, reason):
                if reason in hp_contract.DEV_LIGHT_SOFT_STOPS:
                    soft.append(reason)
                    return None
                return real(t, reason)
            ep.abort = abort
        return self

    def __exit__(self, *exc):
        if self.on:
            if self.shadowed:
                self.ep.abort = self.real
            else:
                del self.ep.abort
        return False


def _light_due(holder, key):
    counts = holder.__dict__.setdefault('dev_light_counts', {})
    counts[key] = counts.get(key, 0) + 1
    return counts[key], (counts[key] - 1) % hp_contract.DEV_LIGHT_LOG_EVERY == 0


def light_log(guard, now, soft, site, **detail):
    """One ``dev_light_would_stop`` event (deduplicated per site/reason). Never raises into the run."""
    ep = guard.ep
    count, due = _light_due(guard, (site, soft[0]))
    if not due:
        return
    try:
        report = guardlog._report(ep.own.last_report)
    except Exception as exc:
        report = {'error': repr(exc)}
    try:
        ep.log(ep.own.robot_id, hp_contract.DEV_LIGHT_EVENT, now, would_reason=soft[0], reasons=list(soft), site=site,
               occurrence=count, estimate=report, loaded=bool(getattr(guard, 'carrying_beam', False)),
               light_version=hp_contract.DEV_LIGHT_VERSION, **detail)
    except Exception as exc:
        ep.log(ep.own.robot_id, hp_contract.DEV_LIGHT_EVENT, now, would_reason=soft[0], log_error=repr(exc))


def light_soft(ctl, reason, now, site):
    """True (and one deduplicated ``dev_light_would_stop`` event) when DEV light turns this controller stop into a log."""
    if not (hp_contract.DEV_LIGHT and reason in hp_contract.DEV_LIGHT_SOFT_STOPS):
        return False
    count, due = _light_due(ctl, (site, reason))
    if due:
        ctl.log(ctl.rid, hp_contract.DEV_LIGHT_EVENT, now, would_reason=reason, site=site, state=ctl.state,
                seg=getattr(ctl, 'seg', None), occurrence=count, light_version=hp_contract.DEV_LIGHT_VERSION)
    return True


class LightFail:
    """Controller side of DEV light: ``fail``/``_transit_abort`` with a soft reason log and return (the state is
    retried next tick) instead of failing. Hard reasons are unchanged."""

    def _light_soft(self, reason, now, site):
        return light_soft(self, reason, now, site)

    def fail(self, reason, now):
        if self._light_soft(reason, now, 'controller.fail'):
            if reason == 'ALIGN_RELOOK_NO_FIX' and self.state == 'align_relook':
                # Retrying would stay in align_relook with no pans left: resume exactly like the accepted-fix branch
                # of zone_pair_align._align_relook (own estimate as it is; logged as dev_light_would_stop).
                from harness.owncam_pair_beam_v2 import pose_of
                self.arm.queue(pose_of(self.align_resume_name), now, duration=.6, settle=.3)
                from harness.zone_pair_align import PairAlignRelook
                setter = super(PairAlignRelook, self) if isinstance(self, PairAlignRelook) else super()
                return setter.set('align_relook_return', now)
            if reason == 'ALIGN_TIMEOUT' and self.state == 'align':
                # A time limit only: start a new align window from now (the alignment itself is unchanged).
                self.state_t = self.align_started_at = now
                return None
            if reason == 'ALIGN_RELOOK_FIX_EXPIRED' and self.state == 'align_relook_return':
                # The rest of the accepted branch of zone_pair_align._align_relook_return (own estimate as it is).
                from harness.zone_pair_align import PairAlignRelook
                setter = super(PairAlignRelook, self) if isinstance(self, PairAlignRelook) else super()
                self.align_look_total_s = getattr(self, 'align_look_total_s', 0.) + now - getattr(self, 'align_look_started_at', now)
                self.relative_views_tried = {}
                reset = getattr(self, 'reset_object_anchor', None)
                if reset is not None:
                    reset()
                self.next_look = now
                setter.set('align', now, resumed=True)
                self.state_t = getattr(self, 'align_started_at', now)
                return None
            return None
        return super().fail(reason, now)

    def _transit_abort(self, reason, now):
        if self._light_soft(reason, now, 'controller._transit_abort'):
            return None
        return super()._transit_abort(reason, now)


class CommandGuard(PreviousGuard):
    preclose_check = frame_gate.gated(PreviousGuard.preclose_check)
    observe_standoff = frame_gate.gated(PairCommandGuard.observe_standoff)

    veto_trace = None                    # v98 evidence log + start-state relief (guardlog, start_relief): set only in check()

    def __init__(self, execution, vision):
        super().__init__(execution, vision)
        progress.install(self)           # v98: loaded no-progress check, motion = REQUIRED_MOVEMENT_M commanded (B)

    def before_control(self, now):
        soft = []
        with light_aborts(self.ep, soft):
            out = super().before_control(now)
        if soft and out is False:
            light_log(self, now, soft, 'CommandGuard.before_control')
            return True
        return out

    def _stationary_reobserve(self, now, pose):
        soft = []
        with light_aborts(self.ep, soft):
            out = super()._stationary_reobserve(now, pose)
        if soft and out is False:
            light_log(self, now, soft, 'CommandGuard._stationary_reobserve')
            return True
        return out

    def sweep_guard(self):
        if hp_contract.COLLISION_GUARD_MODE == 'log_only':     # user 2026-10-05: PAIR_COLLISION_GUARD log only
            return guard_log_only.install(super().sweep_guard(), self.veto_trace)
        return start_relief.install(super().sweep_guard(), self.veto_trace)

    def check(self, now, commands):
        moving = any(c['kind'] == 'mecanum' and any(c.get(k, 0.) != 0.
                     for k in ('forward', 'left', 'turn')) for c in commands)
        if moving and self.carrying_beam and not pose.at_high(self.ep.own.servo):
            self.ep.abort(now, 'LOADED_BASE_MOTION_REQUIRES_HIGH')
            return [{'kind': 'hold'}]
        progress.leg_reset(self, now)    # v98: reset the loaded no-progress check at each carry leg start (A)
        before, issued = len(self.ep.own.events), copy.deepcopy(commands)
        self.veto_trace = trace = guardlog.Trace()
        soft = []
        try:
            with light_aborts(self.ep, soft):
                out = super().check(now, commands)
        finally:
            self.veto_trace = None
        if soft:
            light_log(self, now, soft, 'CommandGuard.check', commands=issued)
            out = commands
        start_relief.log_reliefs(self, now, trace)
        guardlog.log_veto(self, now, issued, before, trace)
        guard_log_only.log_would_veto(self, now, issued, trace)
        carry_align.log_gate_check(self, now, issued, out)     # observation only (sigma, yaw sigma, gate values)
        return out


class GraspViewLogOnly(m2.M2DoorStudent):
    """``M2DoorStudent._grasp`` (door v3) with GRIP_NOT_SEEN LOG-ONLY (v98, see HighController._wait_close).

    Placed by C3 right before ``M2DoorStudent`` (after ``PairGraspRelook``), so the parent's issued-close
    check still runs first and its receipt follows. The co-motion anchor stays a monitor reference only.
    """
    def _grasp(self, now, arm_idle):
        if self.version != 'v3':
            raise RuntimeError('v98 grasp adapter covers door v3 only')
        if not arm_idle:
            return
        obs = self.look(now)
        view = m2.ob2.grip_view(obs['image'])
        seen = m2.grip_view_m2(obs['image'])
        self.log(self.rid, 'grip_view', now, **view, m2=seen, applied=False)
        self._monitor('grasp_grip_view', now, frame_id=obs['frame_id'], applied=False, **seen)
        self.anchor = m2.lv3.co_motion_signature(obs['image'])
        self.anchor_kind = 'co_motion_v3'
        self.claims['gripped'] = {'grip_view': view, 'grip_view_m2': seen, 'sim_time': now,
                                  'decided_by': 'own command history (issued close) + partner status',
                                  'grip_view_applied': False}
        self.set('wait_lift', now)


def controller_class(base):
    # blind.HoverConfirm sits between HighController and V3Controller: hover check, then the blind descent (v98).
    # posture_defer.DeferRelook goes first: an align re-look never starts mid arm transition (v98).
    return type('HighPairController', (LightFail, posture_defer.DeferRelook, refix.SigmaRefix, HighController, blind.HoverConfirm, base,
                                       GraspViewLogOnly), {})


class Execution(previous.Execution):
    # Per-step own-image gate (INVALID_OWN_IMAGE) with the v98 values. The frozen code objects run twice bound:
    # with the v98 gate (``_*_gated``), and with a gate that accepts (``_*_accepted``), which is chosen only for a
    # tick whose frame ``OwnLoadOcclusion`` classified VALID or OCCLUDED_BY_OWN_LOAD inside a loaded window
    # (zone_pair_highpose_own_load_occlusion: no observation, not a fault).
    _step_gated = frame_gate.gated(PairExecution.step)
    _arm_step_gated = frame_gate.gated(PairExecution.arm_step)
    _step_accepted = frame_gate.gated_accepted(PairExecution.step)
    _arm_step_accepted = frame_gate.gated_accepted(PairExecution.arm_step)

    @property
    def own_load_occlusion(self):
        occ = self.__dict__.get('_own_load_occlusion')
        if occ is None:
            occ = self._own_load_occlusion = occlusion.OwnLoadOcclusion(self)
        return occ

    def step(self, now):
        run = self._step_accepted if self.own_load_occlusion.accepts(now) else self._step_gated
        return run(now)

    def arm_step(self, now):
        run = self._arm_step_accepted if self.own_load_occlusion.accepts(now) else self._arm_step_gated
        return run(now)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        ctl = self.controller
        ctl.__class__ = controller_class(type(ctl))
        ctl.driver.__class__ = approach_looks.adopt(type(ctl.driver))   # v98: no in-place no_fix re-look
        ctl.driver.__class__ = arrival_confirm.adopt(type(ctl.driver))  # v98: arrival needs the beam seen where the dock says
        arrival_confirm.configure(ctl.driver, self.plan, kwargs['calibration'])
        ctl.high_raising, ctl.high_ready = False, False
        ctl.grip_epoch, ctl.pose_anchors, ctl.transit = 0, {}, None
        ctl.floor_return_verified = False
        ctl.grip_monitor = grip.GripMonitorLog(tag=self.own_load_occlusion.tag_row)   # occluded frames are tagged
        ctl.grip_closed_epoch = None
        ctl.v98_measured_camera_keys = posture_defer.measured_keys(kwargs['calibration'])  # static calibration
        self.command_guard = CommandGuard(self, self.vision)
        blind.adopt(self.command_guard, ctl)
        # v98 sigma re-fix look (refix.SigmaRefix.align_look_choices): the same sweep guard the align re-look uses.
        ctl.refix_sweep_guard = self.command_guard.sweep_guard


class Team(previous.Team):
    def __init__(self, executors, calibration, static_task):
        super().__init__(executors, calibration, static_task)
        # v98 look recovery: the admitted partner waits for a bounded re-look of the other robot (relook module).
        self.rendezvous_timeout_s = relook.RENDEZVOUS_TIMEOUT_S
        def make_execution(own, status, arguments, plan, params, factory, *, policy):
            return Execution(own, status, arguments, plan, params, calibration=calibration)
        self.start = MethodType(bind(previous.pair.PairTeam.start,
            make_plan=previous.make_plan, PairExecution=make_execution), self)

    def records(self):
        rows = super().records()
        for row in rows:
            row.update(pair_policy='b-v6h1-v3-highpose-opencv', high_pose=pose.record(),
                       previous_acceptance_inherited=False)
        for row, session in zip(rows, self.sessions):
            # Evaluation/audit output only; the controller never reads it.
            row['grip_monitor'] = {'scope': grip.MONITOR_SCOPE, 'in_run_grip_loss_detection': False,
                                   'grasp_time_view': GRASP_TIME_VIEW,
                                   'rows': {r: ep.controller.grip_monitor.export()
                                            for r, ep in session['endpoints'].items()}}
            # Evaluation/audit output only (2026-10-05): own-image frames occluded by the own load (no observation).
            row['own_load_occlusion'] = {r: ep.own_load_occlusion.export() for r, ep in session['endpoints'].items()
                                         if hasattr(type(ep), 'own_load_occlusion')}
            # Log only (2026-10-05): the pair approach driver's own event log (looks, relocalizations, the
            # arrival view verdicts). Executor jobs already keep their driver_log; this driver's log was not saved,
            # so the dock_approach probe 1236c63d had no record of its arrival_view_* events.
            row['approach_driver_log'] = {r: [dict(e) for e in (getattr(getattr(ep.controller, 'driver', None),
                                                                        'log', None) or [])]
                                          for r, ep in session['endpoints'].items()}
        return rows


class OwnExecutor(ZoneOwnExecutor):
    """ZoneOwnExecutor whose pair admission (readiness_snapshot image_valid) uses the v98 frame gate."""
    _ack = frame_gate.gated(ZoneOwnExecutor._ack)
    pair_readiness = frame_gate.gated(ZoneOwnExecutor.pair_readiness)
    # v98 look-around: the guard gets the tick's covariance (guard half: lookaround.LookAroundGuard, installed in
    # adopt_v98_frame_gate) and a held look-around tick carries one hold, not [hold, hold]. The look_around job
    # (opening look and re-looks) pans over relook.DOCK_LOOK_PANS; other sweeps keep WIDE_LOOK_PANS.
    _tick_sweep, _sweep_steps = relook.dock_sweep(ZoneOwnExecutor._tick_sweep, ZoneOwnExecutor._sweep_steps)


def adopt_v98_frame_gate(runtime):
    """Give every actor the v98 admission gate; return the record. Every v98 runtime calls this after init."""
    for rid, actor in runtime.actors.items():
        if type(actor) is not ZoneOwnExecutor:
            raise TypeError(f'v98 frame gate expects ZoneOwnExecutor actors, {rid} is {type(actor).__name__}')
        lookaround.adopt_guard(rid, actor)
        actor.__class__ = OwnExecutor
    from harness.zone_pair_highpose_contract import own_image_gates
    gates = own_image_gates()
    return {'path': gates['path'], 'sha256': gates['sha256'], 'values': dict(gates['values']),
            'frame_gate': frame_gate.record(), 'look_around': lookaround.record(),
            'guard_veto_log': guardlog.record(), 'start_relief': start_relief.record(), 'dock_look': relook.record(),
            'carry_align': carry_align.record(), 'relook_posture_defer': posture_defer.record(),
            'dr_checkpoint': dr_checkpoint.record(), 'approach_looks': approach_looks.record(), 'arrival_confirm': arrival_confirm.record(),
            'own_load_occlusion': occlusion.record(),
            'high_edge_informative': HIGH_EDGE_INFORMATIVE,
            'sigma_refix': refix.record()}


def adopt_look_recovery(runtime):
    """v98 bounded look recovery on ``runtime.team.start``; every v98 runtime calls this after its team exists."""
    return relook.install(runtime, relook.LookRecovery(tuple(runtime.actors)))


class Runtime(PreviousRuntime):
    def __init__(self, static, calibration_path, calibration_sha, *, seed, provider_factory=None):
        from harness.vision_pose_source_highpose import build_provider
        if hp_contract.PARTIAL_FIX:      # DEV light: second-eigenvalue fix receipt (zone_pair_highpose_partial_fix)
            from harness.zone_pair_highpose_partial_fix import build_provider
        initialize = bind(PreviousRuntime.__init__, Team=Team)
        initialize(self, static, calibration_path, calibration_sha, seed=seed,
                   provider_factory=provider_factory or build_provider)
        # The parent hard-codes job_sim_limit_s=120 for every executor, which
        # would expire the pair job before the registered per-case cap (lower
        # bounds 184.6 s / 190-219 s). Align it with the bundle's case cap
        # before any job exists; recorded in execution_timing and record().
        from harness.zone_pair_highpose_contract import CASE_CAP_S
        self.job_sim_limit_s = CASE_CAP_S
        for actor in self.actors.values():
            actor.job_sim_limit_s = CASE_CAP_S
        self.own_image_gates = adopt_v98_frame_gate(self)
        self.look_recovery = adopt_look_recovery(self)

    def _vetoed(self, phase, now, call, propagate):
        """Run the parent's collection for one tick, then veto terminal endpoints' motion.

        The parent collects each actor's commands in sequence, so motion returned before a later actor
        aborted in the same tick is still in its list. All state is propagated first (``propagate``);
        only then are terminal endpoints reduced to a single hold. See ``zone_pair_highpose_final_veto``.
        """
        before = final_veto.terminal_robots(self.team, self.actors)
        issued = call(now)
        propagate(now)
        after = final_veto.terminal_robots(self.team, self.actors)
        return final_veto.final_veto(issued, now, phase, before, after, self.team, final_veto.log_of(self))

    def step(self, now):
        # One override for both v98 stages (they arrived as separate diffs that each defined ``step``; a
        # second ``def step`` would silently shadow the first). Order: look-recovery bookkeeping, the parent
        # collection (it already polls the team), the look-recovery pans-only filter, and the same-tick final
        # veto last, so nothing reaches the backend after a terminal endpoint.
        parent = super().step

        def collect(t):
            self.look_recovery.pre_step(self, t)
            return self.look_recovery.filter(self, t, parent(t))
        return self._vetoed('step', now, collect, lambda t: None)

    def arm_step(self, now):
        # The parent's arm_step never polls: a peer abort raised by a later actor was not even
        # propagated before the list went out. Propagate the same way step does.
        return self._vetoed('arm_step', now, super().arm_step, self.team.poll)

    def record(self):
        value = super().record()
        value['final_veto'] = final_veto.record(self)
        value['look_recovery'] = self.look_recovery.record()
        value['executor_job_sim_limit_s'] = self.job_sim_limit_s
        value['own_image_gates'] = copy.deepcopy(self.own_image_gates)
        value['blind_final_approach'] = blind.record()
        return value
