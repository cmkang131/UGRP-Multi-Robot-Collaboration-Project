"""T09b behavioral offline tests; fake pixels/actuators, not perception success."""
import copy
from dataclasses import replace
import hashlib
import json
from pathlib import Path

import pytest

from harness import zone_observed_door_reroute as rr
from harness.zone_pair_status import PairStatusChannel, PairStatusEndpoint, STATES
from harness.zone_study_protocol import Transport

ROOT = Path(__file__).resolve().parents[1]
CONDITIONS = ('no_comm', 'peer_ko', 'leader_ko', 'structured')
START, GOAL = (1., -1.2, 0.), (3.5, -1.2, 0.)
# Tiny PPM images encode scripted labels ONLY. No visual recognition claim.
PIXELS = {name: b'P6\n1 1\n255\n' + bytes(color) for name, color in {
    'clear': (128, 128, 128), 'narrow': (255, 0, 0),
    'both': (255, 0, 255), 'wide': (0, 0, 255), 'invalid': (0, 0, 0)}.items()}


class FakeObserver:
    version = 'test.scripted_rgb_labels.v1'

    def __init__(self):
        self.pose = START
        self.calls = []

    def observe(self, frame, static_map, own_commands):
        self.calls.append((frame, copy.deepcopy(static_map), own_commands))
        blocks = {PIXELS['clear']: (), PIXELS['narrow']: ('door_narrow',),
                  PIXELS['wide']: ('door_wide',), PIXELS['both']: ('door_narrow', 'door_wide')}
        return rr.OwnObservation(frame.sha256, self.pose, blocks.get(frame.rgb, ()),
                                 frame.rgb in blocks)


class FakeNavigation:
    version = 'test.bounded_navigation.v1'

    def __init__(self):
        self.calls, self.cancelled = [], 0
        self.result, self.stop_result = 'running', 'stopped'
        self.raise_tick = False

    def tick(self, route, frame, observation, own_commands):
        if self.raise_tick:
            raise RuntimeError('fake driver error')
        self.calls.append((route, frame, observation, own_commands))
        return rr.NavigationFeedback(self.result, (rr.IssuedCommand('drive', (.02, 0.)),))

    def stop(self):
        self.cancelled += 1
        return rr.NavigationFeedback(self.stop_result, (rr.IssuedCommand('stop'),))


def make(*, kind='cyan', robot='r1', channel=None, observer=None, navigation=None, static=None):
    static = static if static is not None else json.loads(
        (ROOT / 'maps/zones_final/zone_wide_two_doors_final_v1.json').read_text())
    roles = ('west', 'east') if kind == 'heavy_crate' else ('west',)
    pair = PairStatusEndpoint(channel, robot) if channel else None
    return rr.ObservedDoorReroute(robot_id=robot, static_map=static, goal_pose=GOAL,
                                  cargo_kind=kind, roles=roles, observer=observer or FakeObserver(),
                                  navigation=navigation or FakeNavigation(), pair_status=pair)


def tick(controller, sequence, pixels='clear', inbox=(), now=None):
    return controller.tick(rr.OwnFrame(controller.robot_id, sequence, PIXELS[pixels]),
                           now_s=sequence * .01 if now is None else now, delivered_messages=inbox)


def bus(condition):
    return Transport(condition, seed=1,
                     passages=('door_narrow', 'door_wide'), delivery_delay_sim_s=1.)


def report(transport, door='door_narrow', at=1.):
    transport.open_window('w', at_sim_s=at)
    kwargs = {'structured': {'act': 'inform', 'item': None, 'zone': None, 'role': None,
                             'passage': door, 'location_ref': None, 'state': 'blocked',
                             'confidence': 'high', 'observed_at_sim_s': at, 'reply_to': None}}
    if transport.condition != 'structured':
        kwargs = {'text': f'{door} 막힘 확인'}
    return transport.send('r2', recipients=['r1'], at_sim_s=at, **kwargs)


def test_observation_triggers_cancellation_then_wide_from_fresh_pose():
    c = make()
    initial = tick(c, 0)
    assert initial.route.passage_id == 'door_narrow'
    assert tick(c, 1).route == initial.route
    blocked = tick(c, 2, 'narrow')
    assert blocked.state == 'REPLAN_READY' and blocked.route.passage_id == 'door_wide'
    assert len(c.navigation.calls) == 2 and c.navigation.cancelled == 1
    assert c.belief['door_narrow'] == {'source': 'own_rgb', 'ref': hashlib.sha256(PIXELS['narrow']).hexdigest()}
    c.observer.pose = (1.05, -1.2, 0.)
    after = tick(c, 3)
    assert after.state == 'RUNNING' and after.route.passage_id == 'door_wide'
    assert after.route.poses_m_rad[0] == c.observer.pose
    assert c.navigation.calls[-1][3][-1].name == 'stop'
    assert c.observer.calls[-1][2] == c.navigation.calls[-1][3]


@pytest.mark.parametrize('condition', CONDITIONS)
def test_actual_inbox_delivery_only_and_no_comm_cannot_anticipate(condition):
    c, transport = make(), bus(condition)
    first = tick(c, 0)
    receipt = report(transport)
    assert receipt.accepted == (condition != 'no_comm')
    # The send has happened, but the delivered inbox is still empty.
    pending = transport.inbox('r1', now_sim_s=1.999)
    assert not pending
    before = tick(c, 1, inbox=pending, now=1.999)
    assert before.route == first.route and not c.belief
    received = transport.inbox('r1', now_sim_s=2.)
    after = tick(c, 2, inbox=received, now=2.)
    if condition == 'no_comm':
        assert after.route == first.route and after.state == 'RUNNING' and not c.belief
    else:
        assert after.route.passage_id == 'door_wide' and after.state == 'REPLAN_READY'
        assert c.belief['door_narrow']['source'] == 'message'
        assert c.belief['door_narrow']['ref'] == receipt.envelope.message_id


@pytest.mark.parametrize('condition', CONDITIONS)
def test_direct_observation_same_navigation_and_prior_in_every_condition(condition, record_property):
    c, baseline = make(), make()
    assert c.invariant == baseline.invariant
    assert rr.digest(c.invariant) == rr.digest(baseline.invariant)
    record_property('condition', condition)
    record_property('common_config_sha256', rr.digest(c.invariant))
    record_property('map_sha256', c.invariant['map_sha256'])
    record_property('prior_sha256', c.invariant['prior_sha256'])
    record_property('controller_sha256', hashlib.sha256(
        (ROOT / 'harness/zone_observed_door_reroute.py').read_bytes()).hexdigest())
    record_property('role_assignment_sha256', rr.digest({'west': 'r1'}))
    transport = bus(condition)
    assert tick(c, 0, inbox=transport.inbox('r1', now_sim_s=0.)) == tick(baseline, 0)
    assert tick(c, 1, 'narrow') == tick(baseline, 1, 'narrow')
    assert tick(c, 2) == tick(baseline, 2)
    assert c.navigation.calls == baseline.navigation.calls
    assert c.own_commands == baseline.own_commands


@pytest.mark.parametrize('condition', CONDITIONS)
def test_private_referee_event_pose_and_peer_truth_do_not_change_decisions(condition):
    # Actual source scenario retained as private data, never passed to controller.
    source = json.loads((ROOT / 'configs/zone_study_scenarios_v2/s2_unmapped_blockage_v2.json').read_text())
    mutated = copy.deepcopy(source)
    mutated['eval']['hidden_events'] = [{'at_sim_s': 0., 'target': {'center_m': [1., -1.2]}}]
    mutated['eval']['setup']['placements'] = [{'private_pose': [99., 99., 99.]}]
    mutated['eval']['referee'] = {'success': True, 'peer_pose': [2.2, .05, 0.], 'contact': True}
    class PrivateForbidden(dict):
        def __getitem__(self, key):
            raise AssertionError('private evaluator input accessed')
    mutated['eval'] = PrivateForbidden(mutated['eval'])
    controllers = []
    for private in (source, mutated):
        # Boundary follows the source's public map ID/order only. Own pose is
        # the RGB fixture, never a setup placement or P09 feasibility output.
        authored = json.loads((ROOT / 'maps/zones_final' / (private['map_id'] + '.json')).read_text())
        c, transport = make(static=authored, kind=private['orders'][0]['kind']), bus(condition)
        decisions = [tick(c, i, inbox=transport.inbox('r1', now_sim_s=t), now=t)
                     for i, t in enumerate((0., 44.999, 45., 46., 500.))]
        controllers.append((decisions, c.belief, c.invariant, c.navigation.calls))
    assert controllers[0] == controllers[1]
    assert {d.route.passage_id for d in controllers[0][0]} == {'door_narrow'}


@pytest.mark.parametrize('already_running', [False, True])
def test_both_blocked_refuses_and_cancels_old_route(already_running):
    c = make()
    if already_running:
        tick(c, 0)
    result = tick(c, 1, 'both')
    assert result.state == 'REFUSED' and result.reason == 'ALL_DOORS_BLOCKED'
    assert result.route is None and c.navigation.cancelled == 1
    count = len(c.navigation.calls)
    assert tick(c, 2) == result and len(c.navigation.calls) == count


def test_other_door_blockage_does_not_replace_route_and_belief_is_not_mutable():
    c = make()
    route = tick(c, 0).route
    assert tick(c, 1, 'wide').route == route
    assert c.navigation.cancelled == 0
    c.belief.clear()
    assert 'door_wide' in c.belief


@pytest.mark.parametrize('stop_result', ['running', 'failed', 'reached'])
def test_never_starts_new_path_before_queue_cancellation(stop_result):
    c = make()
    tick(c, 0)
    c.navigation.stop_result = stop_result
    result = tick(c, 1, 'narrow')
    assert result.state == ('STOPPING' if stop_result == 'running' else 'FAILED')
    assert len(c.navigation.calls) == 1
    if stop_result == 'running':
        assert tick(c, 2).state == 'STOPPING'
        c.navigation.stop_result = 'stopped'
        assert tick(c, 3).state == 'REPLAN_READY'
        assert len(c.navigation.calls) == 1


@pytest.mark.parametrize('fault', ['black', 'wrong_hash', 'pose_uncertain', 'nan', 'unknown_door', 'observer_error'])
def test_invalid_observation_fails_closed(fault):
    class Broken(FakeObserver):
        def observe(self, frame, static_map, own_commands):
            if fault == 'observer_error':
                raise RuntimeError('broken')
            good = super().observe(frame, static_map, own_commands)
            return replace(good, **{'black': {'image_valid': False},
                                   'wrong_hash': {'frame_sha256': '0' * 64},
                                   'pose_uncertain': {'pose_m_rad': None},
                                   'nan': {'pose_m_rad': (float('nan'), 0., 0.)},
                                   'unknown_door': {'blocked_doors': ('private_door',)}}[fault])
    c = make(observer=Broken())
    assert tick(c, 0).state == 'FAILED'
    assert c.navigation.cancelled == 1 and not c.navigation.calls and not c.belief


@pytest.mark.parametrize('fault', ['peer_frame', 'stale_frame', 'bad_time', 'empty_frame'])
def test_bad_frame_or_own_clock_stops(fault):
    c = make()
    tick(c, 1)
    frame, now = rr.OwnFrame('r1', 2, PIXELS['clear']), .02
    if fault == 'peer_frame':
        frame = replace(frame, robot_id='r2')
    if fault == 'stale_frame':
        frame = replace(frame, sequence=1)
    if fault == 'empty_frame':
        frame = replace(frame, rgb=b'')
    if fault == 'bad_time':
        now = .001
    assert c.tick(frame, now_s=now).state == 'FAILED'
    assert len(c.navigation.calls) == 1


@pytest.mark.parametrize('kind,pose', [('unknown', START), ('cyan', (1., -1.2, .2)),
                                      ('cyan', (2.2, .05, 0.))])
def test_unsupported_kind_rotation_or_in_door_replan_refuses(kind, pose):
    c = make(kind=kind)
    c.observer.pose = pose
    result = tick(c, 0)
    assert result.state == 'REFUSED' and result.reason.startswith('NO_SUPPORTED_ROUTE:')
    assert not c.navigation.calls


@pytest.mark.parametrize('fault', ['exception', 'failed', 'invented_state', 'false_reached'])
def test_lower_navigation_failure_and_false_completion_are_not_success(fault):
    c = make()
    c.navigation.raise_tick = fault == 'exception'
    c.navigation.result = {'failed': 'failed', 'invented_state': 'teleported',
                           'false_reached': 'reached'}.get(fault, 'running')
    result = tick(c, 0)
    assert result.state == 'FAILED'
    assert c.navigation.cancelled == 1


def test_own_estimate_route_end_is_separate_from_delivery_referee():
    c = make()
    tick(c, 0)
    c.observer.pose = GOAL
    c.navigation.result = 'reached'
    result = tick(c, 1)
    assert result.state == 'ROUTE_FINISHED' and result.reason == 'OWN_ESTIMATE_ONLY_NOT_DELIVERY'
    assert c.navigation.cancelled == 1


@pytest.mark.parametrize('condition', CONDITIONS)
def test_one_pair_side_failure_propagates_existing_abort_enum(condition):
    channel = PairStatusChannel('pair-job')
    a, b = [make(kind='heavy_crate', robot=rid, channel=channel) for rid in ('r1', 'r2')]
    for c in (a, b):
        c.pair_status.tick('carry', 0., force=True)
    assert tick(a, 0).state == tick(b, 0).state == 'RUNNING'
    a.navigation.result = 'failed'
    assert tick(a, 1).state == 'FAILED'
    assert tick(b, 1).reason == 'PAIR_NOT_SAFE'
    assert a.navigation.cancelled == b.navigation.cancelled == 1
    assert len(b.navigation.calls) == 1
    assert {m['state'] for m in channel.log} <= STATES
    assert all(m['state'] == 'abort' for m in channel.latest.values())


def test_pair_blockage_stops_job_and_never_unilaterally_drives_new_route():
    channel = PairStatusChannel('pair-job')
    a, b = [make(kind='heavy_crate', robot=rid, channel=channel) for rid in ('r1', 'r2')]
    for c in (a, b):
        c.pair_status.tick('carry', 0., force=True)
    for c in (a, b):
        assert tick(c, 0).state == 'RUNNING'
    result = tick(a, 1, 'narrow')
    assert result.state == 'PAIR_REPLAN_REQUIRED' and result.route.passage_id == 'door_wide'
    assert tick(b, 1).reason == 'PAIR_NOT_SAFE'
    assert tick(a, 2) == result
    assert len(a.navigation.calls) == len(b.navigation.calls) == 1


def test_pair_heartbeat_timeout_stops_before_motion():
    channel = PairStatusChannel('pair-job')
    a = make(kind='heavy_crate', channel=channel)
    PairStatusEndpoint(channel, 'r2').tick('carry', 0.)
    assert tick(a, 0, now=.149).state == 'RUNNING'
    assert tick(a, 1, now=.15).reason == 'PAIR_NOT_SAFE'
    assert len(a.navigation.calls) == 1


@pytest.mark.parametrize('change', ['negated', 'suspected', 'recipient', 'private_extra', 'unknown', 'clear'])
def test_unusable_message_is_not_blockage_evidence(change):
    t = bus('peer_ko')
    report(t)
    row = copy.deepcopy(t.inbox('r1', now_sim_s=2.)[0])
    if change in ('negated', 'suspected', 'unknown', 'clear'):
        row['body']['text'] = {'negated': 'door_narrow 막힘 확인 아님',
                               'suspected': 'door_narrow 막힘 의심',
                               'unknown': 'private_door 막힘 확인',
                               'clear': 'door_narrow 통과 가능'}[change]
    if change == 'recipient':
        row['recipients'] = ['r3']
    if change == 'private_extra':
        row['event_time'] = 45.
    c = make()
    first = tick(c, 0)
    after = tick(c, 1, inbox=(row,))
    assert after.route == first.route and not c.belief and c.navigation.cancelled == 0


def test_static_snapshot_is_frozen_and_private_container_is_rejected():
    static = json.loads((ROOT / 'maps/zones_final/zone_wide_two_doors_final_v1.json').read_text())
    c = make(static=static)
    identity = c.invariant
    static['obstacles'].append({'center_m': [1., -1.2], 'half_extents_m': [1., 1.]})
    assert c.invariant == identity and tick(c, 0).route.passage_id == 'door_narrow'
    with pytest.raises(ValueError, match='authored static map'):
        make(static={**static, 'hidden_events': []})


@pytest.mark.parametrize('change', ['missing', 'private_extra', 'suspected', 'low', 'wrong_act'])
def test_unusable_structured_message_cannot_close_a_door(change):
    transport = bus('structured')
    assert report(transport).accepted
    row = copy.deepcopy(transport.inbox('r1', now_sim_s=2.)[0])
    if change == 'missing':
        del row['body']['item']
    elif change == 'private_extra':
        row['body']['event_time'] = 45.
    elif change == 'suspected':
        row['body']['state'] = 'suspected'
    elif change == 'low':
        row['body']['confidence'] = 'low'
    else:
        row['body']['act'] = 'request'
    c = make()
    first = tick(c, 0)
    after = tick(c, 1, inbox=(row,))
    assert after.route == first.route and not c.belief and c.navigation.cancelled == 0


def test_pair_requires_own_endpoint():
    with pytest.raises(ValueError, match='endpoint'):
        make(kind='heavy_crate')


@pytest.mark.parametrize('participants', [('r1', 'r1'), ('r1', 'r4'), ('r2', 'r3')])
def test_invalid_pair_participants_are_rejected(participants):
    with pytest.raises(ValueError, match='endpoint'):
        make(kind='heavy_crate', channel=PairStatusChannel('pair-job', participants=participants))


def test_failed_stop_is_retried_without_new_motion():
    c = make()
    tick(c, 0)
    c.navigation.stop_result = 'failed'
    result = tick(c, 1, 'invalid')
    assert result.state == 'FAILED' and 'STOP_UNCONFIRMED' in result.reason
    cancelled = c.navigation.cancelled
    c.navigation.stop_result = 'stopped'
    assert tick(c, 2) == result
    assert c.navigation.cancelled == cancelled + 1 and len(c.navigation.calls) == 1


def test_pair_announces_abort_even_while_stop_is_pending():
    channel = PairStatusChannel('pair-job')
    a, b = [make(kind='heavy_crate', robot=rid, channel=channel) for rid in ('r1', 'r2')]
    for c in (a, b):
        c.pair_status.tick('carry', 0., force=True)
    assert tick(a, 0).state == tick(b, 0).state == 'RUNNING'
    a.navigation.stop_result = 'running'
    assert tick(a, 1, 'narrow').state == 'STOPPING'
    assert channel.latest['r1']['state'] == 'abort'
    assert tick(b, 1).reason == 'PAIR_NOT_SAFE'
    assert len(b.navigation.calls) == 1


def test_existing_ci_glob_collects_this_file():
    from scripts.run_ci_tests import TEST_PATTERNS
    assert any(Path(__file__).match(pattern) for pattern in TEST_PATTERNS)
