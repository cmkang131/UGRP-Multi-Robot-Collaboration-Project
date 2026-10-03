"""Instance-only pose adaptation of the existing v3 beam-relative student."""
from types import MethodType

import numpy as np

from harness import zone_final_pair_skill as previous
from harness import zone_pair_highpose as pose
from harness import zone_pair_highpose_grip as grip
from harness.zone_final_pair_binding import bind
from harness.zone_final_pair_runtime import Runtime as PreviousRuntime
from harness.zone_final_pair_guards import CommandGuard as PreviousGuard
from harness.own_beam_edge import edge_line
from scripts import run_m2_pair as m2


class HighController:
    """v96 HIGH carry. Grip monitor is LOG-ONLY (first-E2E scope, user 2026-10-03).

    Phase progress and barrier readiness come from this robot's own command
    history (gripper commanded closed in this grasp epoch, queued pose path
    reached) plus the existing fixed-enum partner status. Own-RGB grip values
    (low-lift co-motion IoU, transit relation()/stability, HIGH/floor anchor
    IoU, edge line) go to ``self.grip_monitor`` (write-only) and are exported
    only in the evaluation records. A dropped beam is not detected or
    signalled in-run in this version; success is judged only by evaluation.
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

    def _grasp(self, now, arm_idle):
        # Unchanged grasp-time checks (issued close + own grip view, v88/v92).
        super()._grasp(now, arm_idle)
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
                      edge_slope=None if line is None else line[0], relation=grip.relation(obs['image'], self._issued()))
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
            from harness.zone_own_contract import pose_report_fresh
            from harness.zone_pair_highpose_timing import CHECKPOINT_REOBSERVE_S
            report = self.port.own.last_report
            fresh = (report is not None and pose_report_fresh(report, now)
                     and report.initialized and report.last_fix_t is not None
                     and report.last_fix_t > self.checkpoint_fix_after
                     and report.std_xy_m <= .05 and report.std_yaw_rad <= np.deg2rad(3.))
            # Localization re-observe (navigation) keeps its bounded timeout.
            if now-self.checkpoint_started > 8.:
                return self._transit_abort('HIGH_CHECKPOINT_REOBSERVE_TIMEOUT', now)
            if now >= self.next_look:
                self.next_look = now+m2.study.LOOK_EVERY_S
                obs = self.look(now)
                self.hold_state(obs)      # grip values logged only
                self.report('carry', obs, now, ready=False, reason='HIGH stop/reobserve pending')
            if not fresh or now-self.checkpoint_started < CHECKPOINT_REOBSERVE_S:
                return
            self.grasp_estimate = [float(report.x_m), float(report.y_m), float(report.yaw_rad)]
            self.log(self.rid, 'checkpoint_high_reobserved', now, seg=self.seg,
                     fix_t=report.last_fix_t, high=True, opened=False, epoch=self.grip_epoch)
            self.checkpoint_fix_after = None
        provider = self.port.own.pose.provider
        if not provider.beam_edge.available(now):
            if now-self.state_t > m2.study.STATE_LIMIT_S['wait_carry']:
                return self.fail('HIGH_CARRY_EDGE_REFERENCE_TIMEOUT', now)
            if now >= self.next_look:
                self.next_look = now+m2.study.LOOK_EVERY_S
                self.report('carry', self.look(now), now, ready=False, reason='HIGH edge reference pending')
            return
        return super()._wait_carry(now, arm_idle)

    def _wait_lower(self, now, arm_idle):
        if self.seg+1 < len(self.segments):
            # Same end-of-leg lower barrier is a STOP rendezvous only. It never
            # queues lower/open/raise. Change segment keys after both stop.
            def checkpoint(t):
                self.seg += 1
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
        if self.seg+1 < len(self.segments) or not self.floor_return_verified:
            return self._transit_abort('FINAL_FLOOR_RELEASE_REQUIRED', now)
        return super()._wait_open(now, arm_idle)

class CommandGuard(PreviousGuard):
    def check(self, now, commands):
        moving = any(c['kind'] == 'mecanum' and any(c.get(k, 0.) != 0.
                     for k in ('forward', 'left', 'turn')) for c in commands)
        if moving and self.carrying_beam and not pose.at_high(self.ep.own.servo):
            self.ep.abort(now, 'LOADED_BASE_MOTION_REQUIRES_HIGH')
            return [{'kind': 'hold'}]
        return super().check(now, commands)


class Execution(previous.Execution):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        ctl = self.controller
        ctl.__class__ = type('HighPairController', (HighController, type(ctl)), {})
        ctl.high_raising, ctl.high_ready = False, False
        ctl.grip_epoch, ctl.pose_anchors, ctl.transit = 0, {}, None
        ctl.floor_return_verified = False
        ctl.grip_monitor, ctl.grip_closed_epoch = grip.GripMonitorLog(), None
        self.command_guard = CommandGuard(self, self.vision)


class Team(previous.Team):
    def __init__(self, executors, calibration, static_task):
        super().__init__(executors, calibration, static_task)
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
                                   'rows': {r: ep.controller.grip_monitor.export()
                                            for r, ep in session['endpoints'].items()}}
        return rows


class Runtime(PreviousRuntime):
    def __init__(self, static, calibration_path, calibration_sha, *, seed, provider_factory=None):
        from harness.vision_pose_source_highpose import build_provider
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

    def record(self):
        value = super().record()
        value['executor_job_sim_limit_s'] = self.job_sim_limit_s
        return value
