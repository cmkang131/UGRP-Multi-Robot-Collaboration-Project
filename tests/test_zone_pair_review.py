"""PR #235 adversarial regressions; fake clock/ports, no MuJoCo world."""
import base64
import copy
import hashlib
from pathlib import Path

import cv2
import numpy as np
import pytest

from tests.test_zone_pair_executor import (ROOT, FakeM2, PhasedM2, setup, active, ends,
                                          m2_controller, PoseReport)
from harness.zone_pair_status import PairStatusChannel, PairStatusEndpoint


def submit_both(host):
    first = host.call('r1', 'pair_carry', 'cargoX', 'B', 'r2')
    # Allows these regressions to exercise the old runtime before fixing P1-1.
    if host.robots['r2'].executor.job is None:
        assert host.call('r2', 'pair_carry', 'cargoX', 'B', 'r1')['accepted']
    return first


def set_image(ex, jpeg, now=0., fid=2):
    ex.last_obs = {**ex.last_obs, 'image': base64.b64encode(jpeg).decode(),
                   'sha256': hashlib.sha256(jpeg).hexdigest(), 'sim_time': now, 'frame_id': fid}


def valid_image():
    return (ROOT / 'tests/fixtures/m2_pair_door_v3/lift_824_r2_00759.jpg').read_bytes()


def image_fault(kind):
    if kind == 'corrupt':
        return b'not a jpeg'
    if kind == 'truncated':
        return valid_image()[:-200]
    a = cv2.imdecode(np.frombuffer(valid_image(), np.uint8), cv2.IMREAD_COLOR)
    if kind == 'black':
        a[:] = 0
    elif kind == 'covered':
        a[:, :480] = 0
    else:
        a[:] = 120
    return cv2.imencode('.jpg', a)[1].tobytes()


def test_p1_1_one_submission_never_selects_partners_job():
    h, exs = setup()
    ack = h.call('r1', 'pair_carry', 'cargoX', 'B', 'r2')
    assert ack['accepted']
    assert exs['r2'].job is None and exs['r2']._pair is None
    h._decide('r1', 0.)
    assert exs['r1'].job.phase == 'waiting_partner'
    assert not any(k in ('mecanum', 'arm') for _, k, _ in h.robots['r1'].port.log)
    assert h.call('r2', 'pair_carry', 'cargoX', 'B', 'r1')['accepted']
    assert all(exs[r].job.kind == 'pair_carry' for r in ('r1', 'r2'))


@pytest.mark.parametrize('change', [('cargoY', 'B', 'r1'), ('cargoX', 'A', 'r1'), ('cargoX', 'B', 'r3')])
def test_p1_1_mismatch_explicitly_ends_both_submissions(change):
    h, exs = setup()
    assert h.call('r1', 'pair_carry', 'cargoX', 'B', 'r2')['accepted']
    ack = h.call('r2', 'pair_carry', *change)
    assert not ack['accepted'] and ack['rejected_reason'] == 'PAIR_SUBMISSION_MISMATCH'
    assert all(exs[r].job is None for r in ('r1', 'r2'))
    for r in ('r1', 'r2'):
        assert any(e['detail'].get('reason') == 'PAIR_SUBMISSION_MISMATCH' for e in exs[r].events)


def test_p1_1_missing_submission_times_out_without_creating_peer_job():
    h, exs = setup()
    h.call('r1', 'pair_carry', 'cargoX', 'B', 'r2')
    h.pairs.poll(5.01)
    assert exs['r2'].job is None
    assert any(e['detail'].get('reason') == 'PAIR_RENDEZVOUS_TIMEOUT' for e in exs['r1'].events)
    assert not exs['r2'].events and not exs['r2'].drain_events()


def test_either_actor_can_submit_first_and_a_duplicate_cannot_select_peer():
    h, exs = setup()
    first = h.call('r2', 'pair_carry', 'cargoX', 'B', 'r1')
    assert first['accepted'] and first['arguments']['role'] == 'end_pos'
    assert exs['r1'].job is None
    assert not h.call('r2', 'pair_carry', 'cargoX', 'B', 'r1')['accepted']
    assert exs['r1'].job is None
    second = h.call('r1', 'pair_carry', 'cargoX', 'B', 'r2')
    assert second['accepted'] and second['arguments']['role'] == 'end_neg'


@pytest.mark.parametrize('cause', ['abort', 'episode_end'])
def test_pending_cancellation_sends_no_event_to_the_non_submitter(cause):
    h, exs = setup()
    assert h.call('r1', 'pair_carry', 'cargoX', 'B', 'r2')['accepted']
    assert exs['r2'].job is None
    if cause == 'abort':
        h.call('r1', 'abort')
    else:
        h.close_episode('TEST')
    assert exs['r2'].job is None
    assert not exs['r2'].events and not exs['r2'].drain_events()
    assert len(ends(exs['r1'])) == 1


@pytest.mark.parametrize('kind', ['black', 'covered', 'uniform', 'corrupt', 'truncated'])
def test_p1_2_bad_image_refused_before_readiness(kind):
    h, exs = setup(factory=m2_controller)
    set_image(exs['r1'], image_fault(kind))
    ack = h.call('r1', 'pair_carry', 'cargoX', 'B', 'r2')
    assert not ack['accepted'] and ack['rejected_reason'] == 'SELF_INVALID_IMAGE'
    assert exs['r2'].job is None


@pytest.mark.parametrize('kind', ['black', 'covered', 'corrupt', 'truncated'])
def test_p1_2_bad_image_during_real_carry_stops_before_any_motion(kind):
    h, exs = setup(factory=m2_controller)
    submit_both(h)
    eps = active(h)
    ctl = eps['r1'].controller
    from harness.owncam_pair_hold_v3 import hold_view_mask
    ctl.anchor_full = hold_view_mask(base64.b64encode(valid_image()).decode())
    ctl.state, ctl.next_look = 'carry', 0.
    ctl.schedule = [(0., 10., {'forward': .1, 'left': 0., 'turn': 0.})]
    set_image(exs['r1'], image_fault(kind))
    h._decide('r1', 0.)
    assert all(ep.terminal for ep in eps.values())
    assert not any(k == 'mecanum' for _, k, _ in h.robots['r1'].port.log)


def test_p1_3_late_go_cannot_start_real_lift_at_a_different_time():
    h, exs = setup(factory=m2_controller)
    submit_both(h)
    eps = active(h)
    for r, ep in eps.items():
        ctl = ep.controller
        ctl.state, ctl.hover = 'wait_lift', dict(exs[r].servo)
        ctl.next_look = 99.
        ep.status.sync_for('lift@0').report(r, ready=True, observed_at_s=0., received_at_s=0.,
                                          frame_id=f'{r}-2-0123456789ab')
    # Keep the wire heartbeat alive independently of readiness evidence.
    for ep in eps.values():
        ep.status.tick('ready', .1)
    set_image(exs['r1'], valid_image(), .2)
    eps['r1'].step(.2)
    for t in (.3, .4, .5, .6, .7, .8, .9, 1.):
        eps['r1'].status.tick('lift', t)
        eps['r2'].status.tick('ready', t)
    set_image(exs['r2'], valid_image(), 1.)
    result = eps['r2'].step(1.)
    assert not eps['r2'].controller.arm.events
    assert eps['r2'].controller.state != 'lift'
    assert result['commands'] == [{'kind': 'hold'}]


def test_p1_3_heartbeat_loss_holds_both_within_short_configured_limit():
    h, exs = setup()
    submit_both(h)
    eps = active(h)
    eps['r1'].status.channel.heartbeat_timeout_s = .15
    for ep in eps.values():
        ep.controller.state = 'carry'
    h._decide('r1', .16)
    assert all(ep.terminal for ep in eps.values())
    assert not any(k == 'mecanum' for _, k, _ in h.robots['r1'].port.log)


def test_p1_4_heartbeat_cannot_extend_frame_readiness_ttl():
    bus = PairStatusChannel('pair-000001')
    eps = {r: PairStatusEndpoint(bus, r) for r in ('r1', 'r2')}
    for r, ep in eps.items():
        ep.sync_for('lift@0').report(r, ready=True, observed_at_s=0., received_at_s=0.,
                                   frame_id=f'{r}-1-0123456789ab')
    for t in np.arange(.1, 3.21, .1):
        for ep in eps.values():
            ep.tick('ready', float(t))
    assert eps['r1'].sync_for('lift@0').authorize(3.2)['phase'] != 'GO'
    assert all(m.get('observed_at_s') in (None, 0.) for m in bus.log)
    assert all(m['ready_until_s'] == .6 and m['frame_id'].startswith(m['robot_id'] + '-1-')
               for m in bus.log if '_ready_' in m['state'])
    assert not eps['r1'].sync_for('lift@0').report('r1', ready=True, observed_at_s=3.2, received_at_s=3.2,
                                                 frame_id='r1-1-0123456789ab')


def test_p2_all_imported_m2_regressions_are_selected_by_ci():
    from scripts.run_ci_tests import TEST_PATTERNS
    selected = {p.name for pattern in TEST_PATTERNS for p in ROOT.glob(pattern)}
    assert {'test_m2_pair_door_v3.py', 'test_pair_owncam_approach.py', 'test_zone_tagged_cargo_scene.py'} <= selected


class ArmTiming(FakeM2):
    def __init__(self, *args):
        super().__init__(*args)
        from scripts.zone_teacher import ArmSequence
        self.arm = ArmSequence(self.ep.port, dict(self.ep.own.servo))
        self.schedule = []

    def tick(self, now):
        self.ep.status.tick('aligning', now)


def test_original_arm_command_emission_times_are_preserved_by_host():
    h, exs = setup(factory=ArmTiming)
    def layer(host, event, payload, now):
        if event != 'start':
            return
        for ex in exs.values():
            ex.last_report = PoseReport(t_est=now, initialized=True, std_xy_m=.01, std_yaw_rad=.01,
                                       x_m=0., y_m=0., yaw_rad=0., source=ex.pose.source)
            ex.gate.state = 'ok'
        submit_both(host)
        for ep in active(host).values():
            ep.controller.arm.queue({3: 1400}, now, duration=1.2, settle=.3)
    h.study_layer = layer
    h.run(2., done=lambda: h.world.data.time >= 1.75)
    for r in ('r1', 'r2'):
        actual = [(t, action) for t, k, action in h.robots[r].port.log if k == 'arm']
        from scripts.zone_teacher import ArmSequence
        from tests.test_zone_own_executor_host import FakePort
        reference = FakePort(r)
        arm = ArmSequence(reference, reference.servo)
        arm.queue({3: 1400}, .5, duration=1.2, settle=.3)
        t, next_arm = 0., 0.
        while t <= 1.75:
            if t >= next_arm:  # original outer loop on this fixture's rounded clock
                next_arm = t + .05
                arm.tick(t)
            t = round(t + .05, 6)
        assert actual == [(t, a) for t, k, a in reference.log if k == 'arm']


def test_real_condition_protocols_feed_only_independent_submissions_then_identical_status():
    """Real prompts -> reply validator -> condition transport -> own host API -> completion.

    Scripted model replies, not live LLM evidence. Communication must not mutate
    the executor; a leader's proposal is still not the follower's submission.
    """
    from harness import zone_study_protocol as zp
    from harness.zone_study_prompts_ko import system_prompt
    transcripts, prompts = [], []
    for condition, seed in [('no_comm', 0), ('peer_ko', 0), ('structured', 0),
                            ('leader_ko', 0), ('leader_ko', 1), ('leader_ko', 2)]:
        h, exs = setup(factory=PhasedM2)
        transport = zp.Transport(condition, seed=seed, order_ids=['cargoX'], roles=['end_neg', 'end_pos'])
        transport.open_window('pair-window', at_sim_s=0.)
        accepted_messages = []
        if condition == 'no_comm':
            assert transport.send('r1', recipients=['r2'], text='함께 운반하자', at_sim_s=0.).rejection == 'channel_closed'
        elif condition == 'leader_ko':
            followers = [r for r in zp.ROBOTS if r != transport.leader]
            assert not transport.send(followers[0], recipients=[followers[1]], text='함께 운반하자', at_sim_s=0.).accepted
            assert transport.leader == zp.ROBOTS[seed]
        elif condition == 'structured':
            assert not transport.send('r1', recipients=['r2'], text='자유문 금지', at_sim_s=0.).accepted

        def layer(host, event, payload, now):
            if event != 'start':
                return
            for ex in exs.values():
                ex.last_report = PoseReport(t_est=now, initialized=True, std_xy_m=.01, std_yaw_rad=.01,
                                           x_m=0., y_m=0., yaw_rad=0., source=ex.pose.source)
                ex.gate.state = 'ok'
            for rid, partner, role in [('r1', 'r2', 'end_neg'), ('r2', 'r1', 'end_pos')]:
                prompts.append(system_prompt(condition, rid, seed=seed))
                messages = []
                if condition != 'no_comm':
                    recipient = (transport.leader if condition == 'leader_ko' and rid != transport.leader else partner)
                    message = {'recipients': [recipient], 'reply_to': None}
                    if condition == 'structured':
                        message['message'] = {**dict.fromkeys(zp.STRUCT_FIELDS), 'act': 'propose',
                                              'item': 'cargoX', 'zone': 'B', 'role': role}
                    else:
                        message['text'] = '화물을 함께 B 구역으로 운반하자'
                    messages.append(message)
                raw = {'request_id': rid + '-request', 'decision_sources': ['order_sheet', 'own_rgb'],
                       'action': {'kind': 'claim', 'order_id': 'cargoX', 'role': role, 'destination_zone': 'B'},
                       'messages': messages}
                reply = zp.validate_reply(raw, request_id=raw['request_id'], condition=condition, actor=rid,
                                          order_ids=['cargoX'], roles_by_order={'cargoX': ['end_neg', 'end_pos']})
                accepted_messages.extend(zp.relay(transport, rid, reply, at_sim_s=now))
                # Delivery of dialogue does not choose the recipient's job.
                assert exs[rid].job is None
                if rid == 'r1':
                    assert exs['r2'].job is None
                action = reply['action']
                assert host.call(rid, 'pair_carry', action['order_id'], action['destination_zone'], partner)['accepted']
                if rid == 'r1':
                    assert exs['r2'].job is None
            for rid in zp.ROBOTS:
                inbox = transport.inbox(rid, now_sim_s=now + .1)
                if condition == 'no_comm':
                    assert not inbox

        h.study_layer = layer
        result = h.run(10., done=lambda: bool(h.pairs.sessions) and all(ep.terminal for ep in active(h).values()))
        assert result['outcome'] == 'STUDY_LAYER_DONE'
        assert all(ends(exs[r])[0]['event'] == 'job_done' for r in ('r1', 'r2'))
        assert all(receipt.accepted for receipt in accepted_messages)
        assert transport.sent_count() == (0 if condition == 'no_comm' else 2)
        # Opaque per-session UUIDs carry no host-wide attempt counter.
        transcripts.append([{**m, 'task_id': '<session>'} for m in active(h)['r1'].status.channel.log])
    assert all(log == transcripts[0] for log in transcripts)
    assert len(set(prompts)) >= 6


def test_peer_must_consume_same_go_before_first_real_arm_command():
    h, exs = setup(factory=m2_controller)
    submit_both(h)
    eps = active(h)
    for r, ep in eps.items():
        ep.controller.state, ep.controller.hover, ep.controller.next_look = 'wait_lift', dict(exs[r].servo), 99.
        ep.status.sync_for('lift@0').report(r, ready=True, observed_at_s=0., received_at_s=0.,
                                           frame_id=f'{r}-2-0123456789ab')
    for ep in eps.values():
        ep.status.tick('ready', .1)
    set_image(exs['r1'], valid_image(), .2)
    eps['r1'].step(.2)
    # Peer transport remains alive but its controller misses the common GO.
    eps['r2'].status.tick('ready', .2)
    set_image(exs['r1'], valid_image(), .25, fid=3)
    result = eps['r1'].step(.25)
    h.pairs.poll(.25)
    assert result['commands'] == [{'kind': 'hold'}]
    assert all(ep.terminal and not ep.controller.arm.events for ep in eps.values())
