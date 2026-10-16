"""T10b synthetic observer/command-port tests; no physics, images or LLM claims.

The filename is included by the EXISTING test_zone_own_executor*.py CI glob.
Scripted own labels are fake camera outputs, not P09/evaluator runtime inputs.
"""
import copy
from dataclasses import asdict, replace
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys

import pytest

from harness.zone_corridor_contract import UnsupportedCorridor
from harness.zone_corridor_control import CorridorController, OwnFrame, OwnView
from harness.zone_corridor_control_plan import ControlConfig, CorridorPlan
from harness.zone_pair_status import FIELDS, PROFILE as STATUS_PROFILE

ROOT = Path(__file__).resolve().parents[1]
MODES = ('no_comm', 'peer_ko', 'leader_ko', 'structured')


@pytest.fixture
def static():
    return {'robot_model': 'masterpi_v3', 'bounds_m': [-4., 5., -3., 3.], 'obstacles': [],
            'passages': [{'id': 'corridor_1', 'kind': 'corridor', 'axis': 'x',
                          'center_m': [0., 0.], 'half_extents_m': [1., .25], 'width_m': .5},
                         {'id': 'bay_1', 'kind': 'passing_bay', 'axis': 'y', 'opens_to': 'corridor_1',
                          'center_m': [0., -1.], 'half_extents_m': [.8, .5]}]}


def plan(static, *, pair=False, reverse=False, refuge=True, roles=None):
    path = [(-2., 0., 0.), (0., 0., 0.), (2., 0., 0.)]
    return CorridorPlan(static, kind='long_beam' if pair else 'cyan',
                        roles=roles or ({'end_neg': 'r1', 'end_pos': 'r2'} if pair else {'west': 'r3'}),
                        path=path[::-1] if reverse else path,
                        direction='east_to_west' if reverse else 'west_to_east',
                        refuge_path=[(0., 0., 0.), (0., -1., 0.)] if refuge else None)


class FakeOwnObserver:
    def __init__(self):
        self.labels, self.calls = {}, []

    def __call__(self, frame, geometry, issued_history):
        self.calls.append((frame, geometry, issued_history))
        return self.labels[frame.rgb]


class Trace:
    def __init__(self, p, robot='r3', config=ControlConfig(), issue=None):
        self.observer, self.issued = FakeOwnObserver(), []
        self.controller = CorridorController(robot, p, task_id='fake-episode-01',
                                            observe=self.observer, issue=issue or self.issued.append,
                                            config=config)
        self.p, self.robot, self.seq, self.now = p, robot, 0, -.05

    def tick(self, pose=None, *, now=None, travel='clear', refuge='clear', holding='yes',
             delivered=(), **view_changes):
        self.seq += 1
        self.now = round(self.now + .05, 9) if now is None else now
        pose = self.p.path[0] if pose is None else tuple(pose)
        data = f'FAKE_OWN_RGB:{self.robot}:{self.seq}'.encode()
        label = OwnView(pose, pose[2] + self.p.stations[self.robot][2], .001, .001,
                        holding, travel, refuge, self.seq, self.now, hashlib.sha256(data).hexdigest())
        self.observer.labels[data] = replace(label, **view_changes)
        return self.controller.tick(OwnFrame(self.robot, self.seq, self.now, data),
                                    now_s=self.now, delivered=delivered)


def solo_to_junction(t):
    assert t.tick().command.moving
    d = t.tick(t.p.path[1])
    assert not d.command.moving and not d.passage_observed
    assert t.controller.station == 1


def finish_solo(t):
    assert t.tick(t.p.path[1]).command.moving
    result = [t.tick(t.p.path[2]) for _ in range(4)]
    assert all(not x.passage_observed for x in result[:3])
    assert result[-1].state == 'PASSED'
    assert all(not x.delivery_complete for x in result)
    return result


@pytest.mark.parametrize('reverse', [False, True])
def test_solo_entry_translation_full_exit_not_waypoint_or_delivery(static, reverse):
    t = Trace(plan(static, reverse=reverse))
    first = t.tick()
    assert first.command.forward_m_s * (-1 if reverse else 1) > 0
    d = t.tick(t.p.path[1])
    assert not d.passage_observed and t.controller.station == 1
    finish_solo(t)
    assert all(x.robot_id == 'r3' and x.duration_s <= .05 for x in t.issued)


def test_issued_commands_are_history_not_observed_motion(static):
    t = Trace(plan(static), config=replace(ControlConfig(), progress_timeout_s=.2))
    for _ in range(5):
        d = t.tick()
    assert d.state == 'ABORTED' and d.reason == 'OWN_RGB_NO_PROGRESS'
    assert t.controller.station == 0 and not d.command.moving
    histories = [row[2] for row in t.observer.calls]
    assert histories[0] == () and tuple(t.issued[:-1]) == histories[-1]
    assert all(not c.passage_observed for c in [d])


def test_capable_solo_decides_to_yield_then_reenters_on_own_clear_frames(static):
    t = Trace(plan(static))
    solo_to_junction(t)
    d = t.tick((.25, 0., 0.), travel='blocked')
    assert (d.state, d.reason) == ('RETREAT', 'self_feasible_refuge')
    assert not d.command.moving
    reverse = t.tick((.25, 0., 0.), travel='blocked')
    assert reverse.command.forward_m_s < 0  # observed prefix back to bay junction
    t.tick((0., 0., 0.), travel='blocked')
    lateral = t.tick((0., 0., 0.), travel='blocked')
    assert lateral.command.left_m_s < 0
    assert t.tick((0., -1., 0.), travel='blocked').state == 'WAIT_BAY'
    assert t.tick((0., -1., 0.), travel='blocked').state == 'WAIT_BAY'
    for _ in range(7):
        d = t.tick((0., -1., 0.))
    assert d.state == 'REENTER'
    assert t.tick((0., -1., 0.)).command.left_m_s > 0
    assert t.tick((0., 0., 0.)).state == 'FOLLOW'
    finish_solo(t)


def test_clear_notice_or_timeout_cannot_replace_own_rgb_clearance(static):
    t = Trace(plan(static), config=replace(ControlConfig(), wait_timeout_s=.2))
    first = t.tick(travel='blocked')
    assert first.state == 'WAIT_LANE'
    d = t.tick(now=.2, travel='unknown')
    assert d.state == 'ABORTED' and d.reason == 'WAIT_TIMEOUT'
    assert not any(c.moving for c in t.issued)


@pytest.mark.parametrize('offset, expected', [(.199, 'WAIT_LANE'), (.2, 'ABORTED'), (.201, 'ABORTED')])
def test_wait_timeout_boundary(static, offset, expected):
    t = Trace(plan(static), config=replace(ControlConfig(), wait_timeout_s=.2))
    t.tick(travel='blocked')
    assert t.tick(now=offset, travel='blocked').state == expected


def test_repeated_standoff_count_survives_clear_and_reentry(static):
    t = Trace(plan(static, refuge=False), config=replace(ControlConfig(), clear_frames=1, clear_hold_s=.05))
    for attempt in range(3):
        d = t.tick(travel='blocked')
        if attempt < 2:
            assert d.state == 'WAIT_LANE'
            t.tick()
            assert t.tick().state == 'FOLLOW'
        else:
            assert d.reason == 'REPEATED_STANDOFF'
    assert d.state == 'ABORTED' and not d.command.moving


@pytest.mark.parametrize('clearance', ['blocked', 'unknown'])
def test_refuge_conflict_refused_without_host_selecting_another_yielder(static, clearance):
    t = Trace(plan(static))
    solo_to_junction(t)
    d = t.tick((0., 0., 0.), travel='blocked', refuge=clearance)
    assert d.reason == 'REFUGE_UNOBSERVED_OR_BLOCKED' and not d.command.moving


def test_reentry_conflict_stops_instead_of_driving_into_traffic(static):
    t = Trace(plan(static), config=replace(ControlConfig(), clear_frames=1, clear_hold_s=.05))
    solo_to_junction(t)
    t.tick((0., 0., 0.), travel='blocked')
    t.tick((0., -1., 0.), travel='blocked')
    t.tick((0., -1., 0.))
    assert t.tick((0., -1., 0.)).state == 'REENTER'
    d = t.tick((0., -1., 0.), travel='blocked')
    assert d.state == 'ABORTED' and d.reason == 'REFUGE_TRAFFIC_CONFLICT'


def test_bay_waypoint_tolerance_does_not_override_whole_formation_containment(static):
    t = Trace(plan(static))
    solo_to_junction(t)
    t.tick((0., 0., 0.), travel='blocked')
    # If a stale/forged bay certificate were trusted, this would enter WAIT_BAY.
    t.controller.plan.contract.bay_stop = lambda *a: {'static_ok': False}
    d = t.tick((0., -1., 0.), travel='blocked')
    assert d.reason == 'BAY_NOT_OCCUPIED_BY_SELF'


def run_pair(p, *, modes=MODES, fault=None):
    records = []
    for mode in modes:
        # The speech transport is the ONLY mode selection. The status channel,
        # observer, controller, timing and configuration are byte-identical.
        actors = [Trace(p, rid) for rid in p.formation.robots]
        mail = [(), ()]
        decisions = []
        poses = [p.path[0], p.path[0]]
        for tick in range(60):
            next_mail, row = [(), ()], []
            now = round(tick * .05, 9)
            for i, actor in enumerate(actors):
                if fault == 'heartbeat' and tick >= 8 and i == 0:
                    mail[i] = ()
                if fault == 'bad_phase' and tick == 7 and i == 0:
                    mail[i] = tuple({**m, 'state': 'available'} for m in mail[i])
                holding = 'no' if fault == 'own_grip' and tick == 8 and i == 1 else 'yes'
                # Tick 7 follows the first GO lease; tick 8 is already a
                # stopped station and may correctly wait/restart instead.
                travel = 'blocked' if fault == 'traffic' and tick == 7 and i == 1 else 'clear'
                d = actor.tick(poses[i], now=now, delivered=mail[i], holding=holding, travel=travel)
                row.append(d)
                next_mail[1 - i] = d.status_messages
            decisions.append(row)
            mail = next_mail
            if all(d.command.moving for d in row):
                for i, actor in enumerate(actors):
                    if fault == 'one_side_motion' and i == 0:
                        continue
                    poses[i] = p.path[min(actor.controller.station + 1, len(p.path) - 1)]
            if all(d.state in ('PASSED', 'ABORTED') for d in row):
                break
        records.append((mode, actors, decisions))
    return records


@pytest.mark.parametrize('reverse', [False, True])
def test_pair_barriers_and_role_relative_commands_in_four_conditions(static, reverse):
    p = plan(static, pair=True, reverse=reverse)
    records = run_pair(p)
    traces = []
    for mode, actors, decisions in records:
        assert [d.state for d in decisions[-1]] == ['PASSED', 'PASSED'], (mode, decisions[-1])
        first_moving = next(row for row in decisions if all(d.command.moving for d in row))
        assert first_moving[0].command.forward_m_s == pytest.approx(-first_moving[1].command.forward_m_s)
        for actor in actors:
            assert actor.controller.record()['status_profile'] == STATUS_PROFILE
            assert actor.controller.deliveries
            assert all(row['received_at_s'] >= row['message']['sent_at_s']
                       for row in actor.controller.deliveries)
        for row in decisions:
            for d in row:
                assert not d.delivery_complete
                assert all(set(m) == FIELDS for m in d.status_messages)
        traces.append([[asdict(d) for d in row] for row in decisions])
    assert traces[0] == traces[1] == traces[2] == traces[3]


@pytest.mark.parametrize('roles', [
    {'end_neg': 'r1', 'end_pos': 'r2'}, {'end_neg': 'r2', 'end_pos': 'r1'},
    {'end_neg': 'r1', 'end_pos': 'r3'}, {'end_neg': 'r3', 'end_pos': 'r1'},
    {'end_neg': 'r2', 'end_pos': 'r3'}, {'end_neg': 'r3', 'end_pos': 'r2'},
])
def test_controller_never_reroutes_an_assigned_actor_command(static, roles):
    p = plan(static, pair=True, roles=roles)
    _, actors, decisions = run_pair(p, modes=('no_comm',))[0]
    assert all(d.state == 'PASSED' for d in decisions[-1])
    assert all(c.robot_id == actor.robot for actor in actors for c in actor.issued)
    assert {actor.robot for actor in actors} == set(roles.values())


@pytest.mark.parametrize('fault', ['own_grip', 'heartbeat', 'traffic', 'bad_phase', 'one_side_motion'])
def test_pair_one_side_failure_or_heartbeat_loss_is_terminal(static, fault):
    _, actors, decisions = run_pair(plan(static, pair=True), modes=('no_comm',), fault=fault)[0]
    assert all(d.state == 'ABORTED' for d in decisions[-1]), decisions[-1]
    assert all(not d.command.moving for d in decisions[-1])
    assert any('PAIR_' in d.reason or 'HEARTBEAT' in d.reason or 'OWN_GRIP' in d.reason
               for row in decisions for d in row)


def wire(t, state='carry', seq=1, at=0., **extra):
    peer = next(r for r in t.p.formation.robots if r != t.robot)
    return dict(robot_id=peer, task_id=t.controller.task_id, seq=seq, state=state,
                sent_at_s=at, observed_at_s=None, frame_id=None, ready_until_s=None, **extra)


@pytest.mark.parametrize('at, expected', [(.149, 'FOLLOW'), (.15, 'ABORTED'), (.151, 'ABORTED')])
def test_heartbeat_boundary_uses_actual_delivery_not_private_partner_state(static, at, expected):
    t = Trace(plan(static, pair=True), 'r1')
    t.tick(delivered=(wire(t),))
    d = t.tick(now=at)
    assert d.state == expected
    if expected == 'ABORTED':
        assert d.reason == 'HEARTBEAT_EXPIRED' and not d.command.moving


def test_missing_initial_partner_never_moves_and_terminates(static):
    t = Trace(plan(static, pair=True), 'r1', config=replace(ControlConfig(), pair_start_timeout_s=.2))
    assert not t.tick().command.moving
    d = t.tick(now=.2)
    assert d.reason == 'HEARTBEAT_MISSING' and not any(c.moving for c in t.issued)


def test_live_but_never_ready_partner_has_a_bounded_wait(static):
    t = Trace(plan(static, pair=True), 'r1', config=replace(ControlConfig(), wait_timeout_s=.2))
    for seq, at in enumerate((0., .1, .2), 1):
        d = t.tick(now=at, delivered=(wire(t, seq=seq, at=at),))
    assert d.reason == 'PAIR_WAIT_TIMEOUT' and not any(c.moving for c in t.issued)


@pytest.mark.parametrize('fault', ['extra_pose', 'wrong_job', 'self', 'replay', 'future', 'unknown_state'])
def test_invalid_delivered_status_cannot_grant_motion(static, fault):
    t = Trace(plan(static, pair=True), 'r1')
    raw = wire(t)
    if fault == 'extra_pose': raw['partner_pose'] = [0., 0., 0.]
    if fault == 'wrong_job': raw['task_id'] = 'other-task'
    if fault == 'self': raw['robot_id'] = 'r1'
    if fault == 'future': raw['sent_at_s'] = 1.
    if fault == 'unknown_state': raw['state'] = 'please_go_now'
    if fault == 'replay':
        t.tick(delivered=(raw,))
    d = t.tick(delivered=(raw,))
    assert d.reason == 'INVALID_DELIVERY' and not d.command.moving


def test_pair_cannot_assume_it_fits_final_bay_and_solo_self_selects(static):
    final = json.loads((ROOT / 'maps/zones_final/zone_wide_corridor_final_v1.json').read_text())
    kwargs = dict(path=[(1.5, 1.175, 0.), (3.2, 1.175, 0.), (4.6, 1.175, 0.)],
                  direction='west_to_east', refuge_path=[(3.2, 1.175, 0.), (3.2, .625, 0.)])
    pair = CorridorPlan(final, kind='long_beam', roles={'end_neg': 'r1', 'end_pos': 'r2'}, **kwargs)
    solo = CorridorPlan(final, kind='cyan', roles={'west': 'r3'}, **kwargs)
    assert pair.refuge_path is None and pair.refuge_reason == 'REFUGE_STATICALLY_BLOCKED'
    assert solo.refuge_path is not None
    t = Trace(pair, 'r1')
    d = t.tick(travel='blocked', delivered=(wire(t),))
    assert d.state == 'WAIT_LANE' and not d.command.moving
    # No four-robot pair-vs-pair fixture is created: r1/r2 + r3 = three robots.
    assert set(pair.formation.robots) | set(solo.formation.robots) == {'r1', 'r2', 'r3'}


@pytest.mark.parametrize('kind', ['can', 'heavy_crate', 'red', 'unknown'])
def test_unsupported_load_is_explicit(static, kind):
    with pytest.raises(UnsupportedCorridor, match='LOAD_CONTROLLER_UNSUPPORTED'):
        CorridorPlan(static, kind=kind, roles={'west': 'r1'},
                     path=[(-2., 0., 0.), (2., 0., 0.)], direction='west_to_east')


def test_impossible_and_disconnected_routes_refused(static):
    static['obstacles'] = [{'center_m': [.3, 0.], 'half_extents_m': [.01, .5]}]
    with pytest.raises(UnsupportedCorridor, match='PASSAGE_REFUSED'):
        plan(static)
    static['obstacles'] = []
    with pytest.raises(ValueError, match='interior route station'):
        CorridorPlan(static, kind='cyan', roles={'west': 'r1'},
                     path=[(-2., 0., 0.), (2., 0., 0.)], direction='west_to_east',
                     refuge_path=[(0., 0., 0.), (0., -1., 0.)])
    with pytest.raises(ValueError, match='distinct'):
        plan(static, pair=True, roles={'end_neg': 'r1', 'end_pos': 'r1'})


def test_unsupported_pair_turn_not_silently_replaced_by_translation(static):
    with pytest.raises(UnsupportedCorridor, match='PAIR_PIVOT'):
        CorridorPlan(static, kind='long_beam', roles={'end_neg': 'r1', 'end_pos': 'r2'},
                     path=[(-2., 0., 0.), (2., 0., 0.), (3., 0., math.pi / 2)], direction='west_to_east')


def test_solo_yaw_motion_is_swept_and_command_is_bounded(static):
    p = CorridorPlan(static, kind='cyan', roles={'west': 'r3'},
                     path=[(-2., 0., math.pi / 2), (-2., 0., 0.), (2., 0., 0.)], direction='west_to_east')
    t = Trace(p)
    d = t.tick()
    assert d.command.yaw_rad_s < 0
    assert math.hypot(d.command.forward_m_s, d.command.left_m_s) <= t.controller.config.base_speed_m_s
    assert abs(d.command.yaw_rad_s) <= .1 and d.command.duration_s <= .05


@pytest.mark.parametrize('changes', [dict(position_error_m=.1), dict(yaw_error_rad=.1),
                                    dict(reference_pose=(math.nan, 0., 0.)), dict(travel='yes'),
                                    dict(travel=[]), dict(refuge={}),
                                    dict(base_yaw_rad=math.pi), dict(position_error_m=-.1)])
def test_bad_or_uncertain_own_view_cannot_drive(static, changes):
    t = Trace(plan(static))
    d = t.tick(**changes)
    assert d.reason == 'OWN_VIEW_INVALID_OR_UNCERTAIN' and not d.command.moving


@pytest.mark.parametrize('changes', [dict(source_frame_sequence=0), dict(source_captured_at_s=-1.),
                                    dict(source_rgb_sha256='0' * 64)])
def test_observer_result_must_belong_to_this_actual_own_frame(static, changes):
    t = Trace(plan(static))
    d = t.tick(**changes)
    assert d.reason == 'OWN_VIEW_INVALID_OR_UNCERTAIN' and not d.command.moving


@pytest.mark.parametrize('holding', ['no', 'unknown'])
def test_own_grip_loss_does_not_wait_for_host_referee(static, holding):
    t = Trace(plan(static))
    assert t.tick(holding=holding).reason == 'OWN_GRIP_NOT_CONFIRMED'


@pytest.mark.parametrize('fault', ['actor', 'sequence', 'stale', 'future', 'empty', 'clock'])
def test_invalid_or_replayed_frame_is_terminal(static, fault):
    t = Trace(plan(static))
    t.tick()
    frame = OwnFrame('r3', 2, .05, b'never passed to observer')
    now = .05
    if fault == 'actor': frame = replace(frame, robot_id='r1')
    if fault == 'sequence': frame = replace(frame, sequence=1)
    if fault == 'stale': frame, now = replace(frame, captured_at_s=0.), .15
    if fault == 'future': frame = replace(frame, captured_at_s=1.)
    if fault == 'empty': frame = replace(frame, rgb=b'')
    if fault == 'clock': now = math.nan
    d = t.controller.tick(frame, now_s=now)
    assert d.state == 'ABORTED' and not d.command.moving
    assert len(t.observer.calls) == 1
    assert t.tick().state == 'ABORTED'  # no resurrection with a valid image


def test_new_sequence_cannot_refresh_an_old_capture_or_exit_evidence(static):
    t = Trace(plan(static))
    t.tick()
    frame = OwnFrame('r3', 2, 0., b'new ID, old capture')
    d = t.controller.tick(frame, now_s=.05)
    assert d.reason == 'OWN_IMAGE_INVALID' and len(t.observer.calls) == 1


def test_arriving_at_refuge_junction_with_new_blockage_can_yield(static):
    t = Trace(plan(static))
    t.tick()
    # First blockage and arrival share a frame; there was no prior clear
    # waypoint event to advance the remembered prefix.
    assert not t.tick((0., 0., 0.), travel='blocked').command.moving
    d = t.tick((0., 0., 0.), travel='blocked')
    assert d.state == 'RETREAT'


def test_drift_out_of_bay_cannot_continue_wait_and_reentry(static):
    t = Trace(plan(static))
    solo_to_junction(t)
    t.tick((0., 0., 0.), travel='blocked')
    assert t.tick((0., -1., 0.), travel='blocked').state == 'WAIT_BAY'
    d = t.tick((1., -1., 0.), travel='blocked')
    assert d.reason == 'BAY_NOT_OCCUPIED_BY_SELF'


def test_waypoint_proximity_cannot_override_full_exit(static):
    p = plan(static)
    t = Trace(p)
    solo_to_junction(t)
    t.tick(p.path[1])
    t.tick(p.path[2])
    t.controller._full_exit = lambda pose: False
    d = t.tick(p.path[2])
    assert d.reason == 'EXIT_NOT_CONFIRMED' and not d.passage_observed


def test_clock_cap_includes_waiting_and_does_not_reset_on_clearance(static):
    t = Trace(plan(static), config=replace(ControlConfig(), passage_timeout_s=.2))
    t.tick(travel='blocked')
    d = t.tick(now=.2)
    assert d.reason == 'PASSAGE_TIMEOUT' and not d.command.moving


def test_observer_or_actuator_error_is_terminal_and_failed_stop_is_exposed(static):
    t = Trace(plan(static))
    t.controller.observe = lambda *a: (_ for _ in ()).throw(RuntimeError('fake provider error'))
    assert t.tick().reason == 'OWN_VIEW_INVALID_OR_UNCERTAIN'
    fail = lambda command: (_ for _ in ()).throw(RuntimeError('fake transport error'))
    t = Trace(plan(static), issue=fail)
    d = t.tick()
    assert d.reason == 'ACTUATOR_ISSUE_FAILED' and not d.issued and not d.command.moving
    assert not t.controller.history


def test_private_mutation_and_input_mutation_cannot_change_controller_trace(static):
    baseline = None
    for mode in MODES:
        private = copy.deepcopy(static)
        private.update(communication_mode=mode, eval={'contact': True, 'success': False},
                       setup={'placements': [{'robot': 'r2', 'pose': [999, -999, 3.]}]},
                       inventory={'secret': 'ignored'}, events=[{'at_sim_s': 1e9}],
                       partner_realtime={'pose': [-999, 999, 2.]})
        p = plan(private)
        t = Trace(p)
        # Caller mutations after construction also cannot steer this actor.
        p.path = ((999., 999., 0.),) * 3
        private['obstacles'].append({'center_m': [0., 0.], 'half_extents_m': [1., 1.]})
        d = t.tick((-2., 0., 0.))
        observed = t.observer.calls[0]
        assert not hasattr(observed[1], 'setup') and not hasattr(observed[1], 'inventory')
        snapshot = (asdict(d), t.controller.record(), asdict(observed[1]))
        if baseline is None:
            baseline = snapshot
        assert snapshot == baseline


def test_role_hash_separate_from_controller_geometry_and_config(static):
    first = plan(static, pair=True)
    second = plan(static, pair=True, roles={'end_neg': 'r3', 'end_pos': 'r1'})
    assert first.route_sha256 == second.route_sha256
    assert first.assignment_sha256 != second.assignment_sha256
    a, b = Trace(first, 'r1').controller.record(), Trace(second, 'r1').controller.record()
    assert a['config_sha256'] == b['config_sha256']
    assert a['task_id'] != b['task_id']


@pytest.mark.parametrize('changes', [dict(tick_s=.2), dict(clear_frames=True), dict(speed_m_s=.1),
                                    dict(wait_timeout_s=math.inf), dict(max_standoffs=0)])
def test_unvalidated_or_malformed_config_refused(changes):
    with pytest.raises(ValueError):
        replace(ControlConfig(), **changes)


def test_import_does_not_load_simulator_or_private_feasibility():
    code = '''
import importlib.abc, sys
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in ('mujoco', 'torch', 'openai') or fullname in (
            'harness.zone_scenario_feasibility', 'harness.zone_own_team_host',
            'scripts.run_zone_study_integration'):
            raise AssertionError(fullname)
sys.meta_path.insert(0, Block())
from harness.zone_corridor_control import CorridorController
from harness.zone_corridor_control_plan import CorridorPlan
'''
    completed = subprocess.run([sys.executable, '-c', code], cwd=ROOT, text=True, capture_output=True)
    assert completed.returncode == 0, completed.stderr
