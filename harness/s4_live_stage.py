"""Command-only S4 departure permit; no simulator or truth inputs."""
import copy
from collections import deque
from harness import s4_llm_host as s4
from harness.zone_study_inputs import command_entry

CONDITIONS = ('no_comm', 'peer_ko', 'leader_ko', 'structured')


class Link(s4.S3Link):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.departure_opened = None
        self.departure_accepted = False
        self.departure_decisions = []
        self.claim_call = None
        self.frames = deque(maxlen=64)

    def capture_frame(self):
        frame = super().frame_at(self.clock())
        if frame is not None: self.frames.append(frame)

    def frame_at(self, t):
        return next((f for f in reversed(self.frames) if f.t <= t+1e-9), None)

    def call(self, api, *args, **kwargs):
        if api == 'pair_carry':
            expected = (self.inner.order['order_id'], self.inner.order['destination_zone'],
                        'r2' if self.robot_id == 'r1' else 'r1')
            accepted = args == expected and self.claim_call is None
            if accepted: self.claim_call = self.call_ref
            return dict(robot_id=self.robot_id, api=api, accepted=accepted,
                rejected_reason=None if accepted else 'PAIR_CLAIM_REJECTED', sim_s=self.inner.clock(),
                arguments={'order_id': args[0], 'target_ref': args[1]},
                action_id=f'{self.robot_id}-s4-claim', job_id=f'{self.robot_id}-claim-only',
                local_state='command_issued' if accepted else 'command_rejected',
                scope='claim_only_no_pair_motion', physical_started=False)
        if api == 'deliver' and self.inner.active:
            return dict(robot_id=self.robot_id, api=api, accepted=False,
                rejected_reason='ALREADY_CLAIMED', sim_s=self.inner.clock(),
                arguments={'order_id': args[0], 'target_ref': args[1]},
                action_id='s4-duplicate-claim', job_id=None, local_state='command_rejected')
        ack = super().call(api, *args, **kwargs)
        if api in ('deliver', 'pair_carry') and ack['accepted']:
            self.claim_call = self.call_ref
        return ack

    def job(self):
        if self.robot_id != 'r3' and self.claim_call is not None:
            return {'kind': 'pair_carry', 'order_id': self.inner.order['order_id']}
        if self.robot_id == 'r3' and self.departure_opened is not None and not self.departure_accepted:
            return None  # own command phase is awaiting a decision; no world feedback
        return self.inner.job()

    def decide_departure(self, *, requested_at, now, call_id):
        opened = self.departure_opened
        accepted = (opened is not None and not self.departure_accepted
                    and opened <= requested_at <= now < opened+10.)
        row = dict(call_id=call_id, requested_at=requested_at, at=now, opened=opened,
                   accepted=accepted, reason=None if accepted else 'STALE_OR_CLOSED_DEPARTURE')
        self.departure_decisions.append(row)
        self.departure_accepted |= accepted
        return row


class Trial(s4.Trial):
    def _on_action(self, actor, action, sim_s):
        super()._on_action(actor, action, sim_s)
        link = self.links[actor]
        if actor == 'r3' and action['kind'] == 'continue' and link.departure_opened is not None:
            call = self.scheduler.calls[-1]
            self.dispatch_log[-1]['departure_gate'] = link.decide_departure(
                requested_at=call.started_sim_s, now=sim_s, call_id=call.call_id)

    def open_departure(self, at):
        link = self.links['r3']
        if link.departure_opened is not None: return
        link.departure_opened = at
        self._history['r3'].append(command_entry('s4_departure_pending', at, 'noop',
            {'reason_code': 'S4_DEPARTURE_PENDING'}, local_state='queue_empty'))
        self.scheduler.trigger('r3', 'idle', at=at)


class Host(s4.Host):
    def __init__(self, *args, **kwargs):
        from harness.zone_final_pair_binding import bind
        bind(s4.Host.__init__, Trial=Trial)(self, *args, **kwargs)


def use_public_destination(runtime, order, static):
    """The S3 constructor is B-only; retarget before any frames/commands, from public task."""
    from harness.zone_solo_cyan_v106 import passage_route
    own = runtime.localizers['r3']
    own.destination = order['destination_zone']
    own.route = passage_route(static, 'door_1', own.destination)
    runtime.links['r3'].order = copy.deepcopy(order)
    return own
