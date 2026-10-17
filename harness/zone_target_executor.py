"""Target-aware adapter around the unchanged ZoneOwnExecutor.

The wrapper owns no host/world/peer. Its cancel callback is a command-only
capability: cancel queued OWN macros and hold, never query physics. Original
executors, delivery controllers, registrations and v9 sources are unchanged.
"""
from __future__ import annotations

import copy
from dataclasses import asdict

from harness.zone_identity_jobs import TARGET_API, TargetJob, MAX_FRAME_AGE_S
from harness.zone_study_contract import ContractViolation
from harness.zone_target_identity import TargetRecoveryJobs
from harness.zone_target_rgb import OwnRGBRecognizer, TargetView
from harness.zone_own_deliver import _DeliverController
from harness.zone_own_contract import zone_slot
from harness.wrist_zone_skill_v9 import WristZoneDeliveryV9

SUPPORTED_ROBOT_MODELS = ('masterpi_v2',)


class TargetSkill(WristZoneDeliveryV9):
    def __init__(self, order, *, target, **kwargs):
        if not isinstance(target, TargetJob):
            raise ContractViolation('skill requires an explicit target job')
        self.target, self.target_view = target, None
        super().__init__(order, **kwargs)

    def bind(self, view):
        if (not isinstance(view, TargetView) or view.job_id != self.target.job_id
                or view.local_token != self.target.local_token):
            raise ContractViolation('skill view belongs to another target')
        self.target_view = view

    def decide(self, observation, estimate):
        if (self.target_view is None or observation != self.target_view.observation):
            raise ContractViolation('skill needs the refreshed target-only observation')
        return super().decide(observation, estimate)


class TargetDelivery(_DeliverController):
    def __init__(self, executor, job, target, view, target_xy):
        if executor.map.get('robot_model', 'masterpi_v2') not in SUPPORTED_ROBOT_MODELS:
            raise ContractViolation('FINAL_V3_TARGET_MANIPULATION_ADAPTER_REQUIRED')
        self.target = target
        self.target_view = view

        def make(order):
            # The spatial v9 skill consumes a cyan attention channel; the raw
            # semantic kind/identity remains target.kind/requested_item_id.
            from harness.wrist_zone_skill_v6 import StaticKeepout
            keepouts = tuple(StaticKeepout(d['id'], tuple(d['center_m']), d['radius_m'], d['source'])
                             for d in executor.static_keepouts)
            from harness.map_goto import UNLOADED_ENVELOPE, plan_path
            from harness.owncam_drive import LOADED_ENVELOPE

            def planner(start, goal, carrying):
                path = plan_path(executor.map, start, goal,
                                 LOADED_ENVELOPE if carrying else UNLOADED_ENVELOPE,
                                 obstacles=self._keepouts(), escape_start_m=.25)
                return None if path is None else [tuple(p) for p in path['waypoints_m'][1:]]

            skill = TargetSkill(order, target=target, robot_id=executor.robot_id, mode='m1',
                                planner=planner, static_keepouts=keepouts,
                                static_bounds_m=list(executor.map['bounds_m']))
            skill.bind(self.target_view)
            return skill

        slot = executor.slots[job.args['pickup_slot']]
        super().__init__(executor.map, executor.params, box_kind='cyan', slot_id=job.args['slot_id'],
                         slot_xy=job.args['slot_xy'], skill_factory=make,
                         pose_estimate_cls=executor.pose_estimate_cls,
                         search_rows_y=executor.search_rows_y, robot_id=executor.robot_id,
                         seed=executor.seed, order_kind='own_rgb_bay', shared_pose=executor.pose,
                         servo=executor.servo, slot_rect=(tuple(slot['x_range_m']), tuple(slot['y_range_m'])),
                         all_rows_y=executor.search_rows_y, gate=executor.gate, guard=executor.guard,
                         static_keepouts=executor.static_keepouts)
        self.target_xy = tuple(target_xy)
        self.pickup_source = 'own_rgb_search'
        self.last_obs = view.observation
        self.last_frame_id = view.observation['frame_id']
        goal = self._approach_goal(self.target_xy)
        if goal is None:
            raise ContractViolation('target approach blocked')
        self.phase = 'approach_leg'
        self._start_leg(goal, loaded=False)

    def bind(self, view):
        if view.job_id != self.target.job_id or view.local_token != self.target.local_token:
            raise ContractViolation('delivery target mismatch')
        self.target_view, self.last_obs = view, view.observation
        if self.skill is not None:
            self.skill.bind(view)

    def on_frame(self, now, obs, rgb):
        # Pose consumes the original full RGB exactly once. refresh_target,
        # after RecoveryJobs checks this frame, binds the skill attention view.
        report = super().on_frame(now, obs, rgb)
        self.last_obs = None
        return report

    def _search_detect(self, obs, report):
        raise ContractViolation('target delivery cannot revert to unbound colour search')

    def summary(self):
        return {**super().summary(), 'target': asdict(self.target),
                'input_transform': 'target_cube_attention_v1'}


class TargetOwnExecutor:
    """Explicit deliver(order, destination, *, target) plus RecoveryJobs backend."""
    target_api = TARGET_API

    def __init__(self, executor, *, visual_catalogue, cancel_scheduled,
                 recognizer=None, delivery_factory=TargetDelivery):
        if executor.map.get('robot_model', 'masterpi_v2') not in SUPPORTED_ROBOT_MODELS:
            raise ContractViolation('FINAL_V3_TARGET_RGB_AND_MANIPULATION_ADAPTER_REQUIRED')
        self.inner = executor
        self.recognizer = recognizer or OwnRGBRecognizer(executor.robot_id, executor.map)
        self.cancel_scheduled = cancel_scheduled
        self.delivery_factory = delivery_factory
        self.target = None
        self.target_log = []
        self.cancel_generation = 0
        self.jobs = TargetRecoveryJobs(executor.robot_id, list(executor.orders.values()), self,
                                       visual_catalogue=visual_catalogue)
        self.inner.judgments = False  # target-specific judgments come from this recognizer

    def __getattr__(self, name):
        return getattr(self.inner, name)

    @property
    def now(self):
        return self.inner.now

    @now.setter
    def now(self, value):
        self.inner.now = value

    def on_frame(self, now, obs, rgb):
        try:
            report = self.inner.on_frame(now, obs, rgb)
            frame = self.recognizer.observe(now, obs, report)
            self.jobs.observe(frame)
            return report
        except Exception:
            self.jobs._stop('INVALID_TARGET_FRAME')
            raise

    def on_command(self, row):
        old_grip = self.inner.servo.get(1, 2000)
        self.inner.on_command(row)
        if (self.target is not None and row['kind'] == 'arm' and int(row['servo_id']) == 1
                and old_grip < 1900 <= int(row['pulse']) and self.jobs._active is not None):
            self.jobs.issued_open(self.target.job_id, command_id=f'{self.target.job_id}-open-{len(self.target_log)}',
                                  issued_at_sim_s=float(row['t']))
            self.target_log.append({'operation': 'issued_open', 'job_id': self.target.job_id, 'command': dict(row)})

    def submit_target(self, target):
        return self.deliver(target.order_id, target.destination_zone, target=target)['accepted']

    def deliver(self, item_ref, zone_slot_id, *, target):
        if not isinstance(target, TargetJob) or target.schema != TARGET_API:
            raise ContractViolation('deliver requires a target job')
        order = self.inner.orders.get(item_ref)
        f = self.recognizer.frame
        if (order is None or target.order_id != item_ref or target.robot_id != self.robot_id
                or order['kind'] != target.kind or order['destination_zone'] != target.destination_zone
                or zone_slot_id != target.destination_zone or self.inner.job is not None
                or self.inner.stopped is not None or f is None
                or target.frame_sequence != f.sequence or target.rgb_sha256 != f.rgb_sha256
                or not 0 <= self.now-f.captured_at_sim_s <= MAX_FRAME_AGE_S):
            return {'accepted': False, 'reason': 'TARGET_JOB_MISMATCH_OR_BUSY'}
        chosen = self.jobs.select(item_ref, target.detection_id, item_id=target.requested_item_id, now_sim_s=self.now)
        if chosen['state'] != 'ready' or chosen['local_token'] != target.local_token:
            return {'accepted': False, 'reason': 'TARGET_IDENTITY_NOT_READY'}
        point = self.recognizer.candidates[target.detection_id]['map_xy']
        if point is None or not self.inner.last_report.initialized:
            return {'accepted': False, 'reason': 'TARGET_OWN_POSE_UNKNOWN'}
        view = self.recognizer.target_view(target, f, target.detection_id)
        slots = self.inner.map['zone_slots'][zone_slot_id]
        count = self.jobs.claim(item_ref)['observed_count']
        if count >= len(slots):
            return {'accepted': False, 'reason': 'DESTINATION_SLOTS_EXHAUSTED'}
        slot = zone_slot(self.inner.map, slots[count]['slot_id'])
        arguments = {'order_id': item_ref, 'target_ref': zone_slot_id, 'target': asdict(target)}
        ack = self.inner._start('deliver', 'deliver', arguments, slot_id=slot['slot_id'],
                                slot_xy=list(slot['center_m']), pickup_slot=order['initial_location']['slot'])
        if ack['accepted']:
            self.target = target
            try:
                self.inner.job.ctl = self.delivery_factory(self.inner, self.inner.job, target, view, point)
                self.inner.job.phase = 'm1_delivery'
            except Exception:
                self.cancel_target(target.job_id, 'TARGET_DELIVERY_BUILD_ERROR')
                raise
            self.target_log.append({'operation': 'submit', 'target': asdict(target), 'lower_job_id': ack['job_id']})
        return ack

    def refresh_target(self, job_id, frame, detection_id):
        if self.target is None or self.target.job_id != job_id:
            raise ContractViolation('refresh belongs to another target')
        view = self.recognizer.target_view(self.target, frame, detection_id)
        if self.inner.job is not None and self.inner.job.ctl is not None:
            self.inner.job.ctl.bind(view)
        self.target_log.append({'operation': 'refresh', 'job_id': job_id, 'frame_sequence': frame.sequence,
                                'detection_id': detection_id, 'raw_sha256': view.raw_sha256,
                                'skill_sha256': view.observation['sha256']})

    def cancel_target(self, job_id, reason):
        # IdentityJobs also cancels a refused submission. It has no lower job
        # to cancel and must not poison all future submissions as a backend fault.
        if self.target is None:
            return
        if self.target.job_id != job_id:
            raise ContractViolation('cancel belongs to another target')
        self.target_log.append({'operation': 'cancel', 'job_id': job_id, 'reason': reason, 'sim_s': self.now})
        self.target = None
        self.cancel_generation += 1
        # Drop pending macros immediately, including during a frame callback
        # between two entries in a multi-step arm motion.
        try:
            self.inner.cancel(self.now, reason)
        finally:
            self.cancel_scheduled(self.now, reason)

    def cancel(self, now, reason):
        self.now = now
        if self.target is not None:
            self.jobs._stop(reason)
            return True
        return self.inner.cancel(now, reason)

    def stop(self, now, reason):
        self.cancel(now, reason)
        self.inner.stop(now, reason)

    def expire_if_due(self, now):
        expired = self.inner.expire_if_due(now)
        if expired and self.target is not None:
            self.jobs.terminal(self.target.job_id, failed=True)
        return expired

    def step(self, now):
        self.now = now
        if self.target is not None:
            f = self.recognizer.frame
            if f is None or not 0 <= now-f.captured_at_sim_s <= .25:
                self.jobs._stop('TARGET_FRAME_EXPIRED')
                return {'mode': 'tick', 'commands': [{'kind': 'hold'}]}
        decision = self.inner.step(now)
        if (decision['mode'] == 'capture' and self.recognizer.frame is not None
                and now <= self.recognizer.frame.captured_at_sim_s):
            return {'mode': 'tick', 'commands': [{'kind': 'hold'}]}
        if self.target is not None and self.inner.job is None:
            # A low-level success does not manufacture an identity/count claim.
            failed = bool(self.inner.jobs_done and self.inner.jobs_done[-1].get('confirmation') == 'failed')
            self.jobs.terminal(self.target.job_id, failed=failed)
        return decision

    def drain_events(self):
        rows = copy.deepcopy(self.inner.drain_events())
        for row in rows:
            if row['job_kind'] == 'deliver' and row['event'] == 'job_done':
                row['detail']['confirmation'] = 'unconfirmed'
                row['detail']['identity_claim'] = 'consult_target_jobs_own_rgb_belief'
        return rows
