"""Second PR #235 review: real host/STATUS/condition paths, no physics engine."""
import copy

import pytest

from harness import zone_study_protocol as protocol
from harness.zone_study_prompts_ko import system_prompt
from tests.test_zone_pair_executor import (PairFakeHost, PhasedM2, SHEETS, active, ends,
                                          m2_controller, robot, setup)
from tests.test_zone_pair_review import ArmTiming, submit_both, set_image, valid_image
from tests.test_zone_own_executor import CALIB
from tests.test_zone_own_executor_host import FakePort


@pytest.mark.parametrize('condition', ['no_comm', 'peer_ko', 'leader_ko', 'structured'])
@pytest.mark.parametrize('ending', ['abort', 'timeout'])
def test_p1_no_host_channel_to_a_non_submitter(condition, ending):
    """Exercise each real prompt/validator/relay; actor explicitly chooses silence."""
    h, exs = setup()
    transport = protocol.Transport(condition, seed=0, order_ids=['cargoX'], roles=['end_neg', 'end_pos'])
    transport.open_window('isolation', at_sim_s=0.)
    assert system_prompt(condition, 'r1', seed=0)
    # Run the actual condition-specific transport rejection path as well.
    sender, recipient = ('r2', 'r3') if condition == 'leader_ko' else ('r1', 'r2')
    if condition == 'peer_ko':
        recipient = sender  # free mesh still forbids self-delivery
    receipt = transport.send(sender, recipients=[recipient], text='우회 전달 검사', at_sim_s=0.)
    assert receipt.rejection == {'no_comm': 'channel_closed', 'peer_ko': 'self_recipient',
                                 'leader_ko': 'no_follower_to_follower',
                                 'structured': 'free_text_not_allowed'}[condition]
    reply = protocol.validate_reply(
        {'request_id': 'private-claim', 'decision_sources': ['order_sheet', 'own_rgb'],
         'action': {'kind': 'claim', 'order_id': 'cargoX', 'role': 'end_neg', 'destination_zone': 'B'},
         'messages': []}, request_id='private-claim', condition=condition, actor='r1',
        order_ids=['cargoX'], roles_by_order={'cargoX': ['end_neg', 'end_pos']})
    assert not protocol.relay(transport, 'r1', reply, at_sim_s=0.)
    before = copy.deepcopy((exs['r2'].status(), exs['r2'].events, exs['r2'].api_log,
                            h.robots['r2'].commands, exs['r2'].drain_events()))
    action = reply['action']
    assert h.call('r1', 'pair_carry', action['order_id'], action['destination_zone'], 'r2')['accepted']
    if ending == 'abort':
        assert h.call('r1', 'abort', 'cargoX -> B; r2 please join')['accepted']
    else:
        h.world.data.time = 5.01
        h.pairs.poll(5.01)
    after = (exs['r2'].status(), exs['r2'].events, exs['r2'].api_log,
             h.robots['r2'].commands, exs['r2'].drain_events())
    assert after == before  # zero peer events, commands, status changes or implicit API calls
    assert transport.sent_count() == 0 and not transport.inbox('r2', now_sim_s=5.1)
    assert ends(exs['r1'])[-1]['detail']['reason'] == ('ABORTED' if ending == 'abort' else 'PAIR_RENDEZVOUS_TIMEOUT')


def test_p1_busy_refusal_cannot_probe_or_change_partner_submission():
    observed = []
    for target in ('B', 'A'):
        h, exs = setup()
        assert h.call('r2', 'hold', 10.)['accepted']
        assert h.call('r1', 'pair_carry', 'cargoX', 'B', 'r2')['accepted']
        before = copy.deepcopy((exs['r1'].events, active(h)['r1'].status.channel.log))
        ack = h.call('r2', 'pair_carry', 'cargoX', target, 'r1')
        observed.append(ack['rejected_reason'])
        assert (exs['r1'].events, active(h)['r1'].status.channel.log) == before
    assert observed == ['SELF_BUSY', 'SELF_BUSY']


def test_p1_expired_peer_attempt_does_not_reject_a_new_own_submission():
    h, exs = setup()
    h.call('r1', 'pair_carry', 'cargoX', 'B', 'r2')
    h.world.data.time = 5.01
    h.pairs.poll(5.01)
    h._capture('r2', 5.01)
    # A current own pose, not a hint about the other actor's past attempt.
    from dataclasses import replace
    exs['r2'].last_report = replace(exs['r1'].last_report, t_est=5.01)
    exs['r2'].gate.state = 'ok'
    assert h.call('r2', 'pair_carry', 'cargoX', 'B', 'r1')['accepted']
    assert active(h)['r2'].rendezvous_deadline == 10.01


@pytest.mark.parametrize('factory', [PhasedM2, m2_controller])
def test_p1_submission_at_point03_wakes_on_the_common_go_grid(factory):
    h, exs = setup(factory=factory)
    h.world.data.time = .03
    submit_both(h)
    eps = active(h)
    if factory is m2_controller:
        for r, ep in eps.items():
            ep.controller.state, ep.controller.hover, ep.controller.next_look = 'wait_lift', dict(exs[r].servo), 99.
            ep.status.sync_for('lift@0').report(r, ready=True, observed_at_s=.03, received_at_s=.03,
                                              frame_id=f'{r}-2-0123456789ab')
    now = .03
    while now <= .51:
        h.world.data.time = now
        for r in ('r1', 'r2'):
            set_image(exs[r], valid_image(), now, fid=3 + round(now * 1000))
            if now + 1e-9 >= h.robots[r].next_decide:
                h._decide(r, now)
        now = min(s.next_decide for r, s in h.robots.items() if r in ('r1', 'r2'))
    assert not any(ep.terminal for ep in eps.values())
    go = []
    for r, ep in eps.items():
        consumed = {}
        for m in ep.status.channel.log:
            if m['robot_id'] == r and '_go_' in m['state']:
                consumed.setdefault(m['state'], m['sent_at_s'])  # subsequent packets are heartbeats
        go.append(list(consumed.values()))
    assert go[0] == go[1] and go[0]
    assert all(abs(t * 10 - round(t * 10)) < 1e-8 for t in go[0])


def test_p2_abort_at_readiness_expiry_emits_abort_and_holds_both_immediately():
    h, exs = setup()
    submit_both(h)
    eps = active(h)
    for r, ep in eps.items():
        ep.controller.state = 'carry'
        ep.status.sync_for('lift@0').report(r, ready=True, observed_at_s=0., received_at_s=0.,
                                           frame_id=f'{r}-2-0123456789ab')
        for t in (.1, .2, .3, .4, .5):
            ep.status.tick('ready', t)
    h.world.data.time = .6
    assert h.call('r2', 'abort')['accepted']
    assert eps['r2'].status.channel.latest['r2']['state'] == 'abort'
    assert all(ep.terminal and not ep.controller.arm.events and not ep.controller.schedule for ep in eps.values())
    h._decide('r1', .6)
    assert not any(k == 'mecanum' for _, k, _ in h.robots['r1'].port.log)
    assert all(h.robots[r].port.log[-1][1] == 'hold' for r in ('r1', 'r2'))


class PrecisePort(FakePort):
    def apply(self, action, now):
        super().apply(action, now)
        self.log[-1] = (now, action['kind'], dict(action))  # no rounding masks floating point drift


class TwoMsHost(PairFakeHost):
    def _physics_until(self, t_end):
        d = self.world.data
        while d.time < t_end - 1e-9:
            # Same pre-physics seam as the native host; absent on the baseline.
            if hasattr(self, '_pair_arm_tick'):
                self._pair_arm_tick(d.time)
            d.time += .002
            while self.hooks and d.time >= self.hooks[0][0]:
                self.hooks.pop(0)[1](self)
            for rid, slot in self.robots.items():
                if not slot.dead and d.time >= slot.next_frame:
                    self._capture(rid, d.time)


def test_p2_arm_issue_times_match_original_cli_bit_for_bit_on_accumulated_2ms_clock():
    exs = {r: robot(r) for r in ('r1', 'r2', 'r3')}
    h = TwoMsHost(exs, lambda *a: None)
    h.world.model.opt.timestep = .002
    for r, slot in h.robots.items():
        slot.port = PrecisePort(r)
    h.contact_record = {'profile': 'cargo_noslip_v1'}
    h.enable_pair_carry(SHEETS, CALIB['params'], controller_factory=ArmTiming)
    def layer(host, event, payload, now):
        if event == 'start':
            from dataclasses import replace
            for ex in exs.values():
                ex.last_report = replace(robot(ex.robot_id).last_report, t_est=now)
                ex.gate.state = 'ok'
            submit_both(host)
    h.study_layer = layer
    h.hooks = [(3., lambda host: [ep.controller.arm.queue({3: 1400}, 3., duration=1.2, settle=.3)
                                 for ep in active(host).values()])]
    h.run(4.5, done=lambda: h.world.data.time >= 4.4)

    from scripts.zone_teacher import ArmSequence
    reference = PrecisePort('r1')
    arm = ArmSequence(reference, reference.servo)
    arm.queue({3: 1400}, 3., duration=1.2, settle=.3)
    now, next_arm = 0., 0.
    while now < 4.4:
        # Literal original run_m2_pair.main loop: intentionally NO epsilon.
        if now >= next_arm:
            next_arm = now + .05
            arm.tick(now)
        now += .002
    expected = [(t.hex(), a) for t, kind, a in reference.log if kind == 'arm']
    assert len(expected) == 24
    for r in ('r1', 'r2'):
        actual = [(t.hex(), a) for t, kind, a in h.robots[r].port.log if kind == 'arm']
        assert actual == expected
