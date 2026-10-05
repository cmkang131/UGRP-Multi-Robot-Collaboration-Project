"""T07: six public role requests, four channels, fake clock/ports only."""
from __future__ import annotations

import copy
import hashlib
import itertools
import json
import math
import socket
import sys
from types import SimpleNamespace
from pathlib import Path

import pytest

from harness import zone_pair_role_integration as zi
from harness.zone_pair_role_executor import make_plan, m2_controller, role_door_schedule, PairStatusChannel, PairStatusEndpoint
from harness.zone_pair_role_host import RoleAwareHostMixin
from harness.zone_pair_roles import LEGACY_ROLES, PairRoles, requested_roles
from harness.zone_pair_status import FIELDS, STATES
from harness.zone_study_protocol import validate_action
from harness.zone_study_scenarios import bundle_for
from tests.test_zone_pair_executor import ORDER, SHEETS, active, ends, robot, PairFakeHost, FakeM2
from tests.test_zone_own_executor import MAP, CALIB
from scripts import run_m2_pair as m2

ASSIGNMENTS = tuple(PairRoles(*pair) for pair in itertools.permutations(zi.ROBOTS, 2))
SCENARIO = json.loads((Path(__file__).resolve().parents[1] /
                      'configs/zone_study_integration/i2_pair_long_beam.json').read_text())


class RoleFakeHost(RoleAwareHostMixin, PairFakeHost):
    pass


def setup(*, factory=FakeM2, limit=720):
    exs = {r: robot(r, limit=limit) for r in zi.ROBOTS}
    host = RoleFakeHost(exs, lambda *a: None)
    host.contact_record = {'profile': 'cargo_noslip_v1'}
    host.enable_pair_carry(SHEETS, CALIB['params'], controller_factory=factory)
    return host, exs


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setitem(sys.modules, 'mujoco', None)
    monkeypatch.setitem(sys.modules, 'torch', None)
    monkeypatch.setattr(socket.socket, 'connect', lambda *a: pytest.fail('network forbidden'))
    monkeypatch.setattr(socket.socket, 'connect_ex', lambda *a: pytest.fail('network forbidden'))


def submit(host, roles, actor, *, order='cargoX', zone='B', role=None):
    action = {'kind': 'claim', 'order_id': order, 'destination_zone': zone,
              'role': role or roles.role(actor)}
    plan = zi.executor_plan(action, None, actor=actor, orders=ORDER['orders'], role_assignment=roles.mapping())
    assert plan.rejected_reason is None
    return host.call(actor, plan.api, *plan.args)


def both(host, roles):
    for rid in roles.participants:
        assert submit(host, roles, rid)['accepted']
    return active(host)


def trial_for(host, condition, roles):
    from scripts.run_zone_study_integration import HostRobotLink
    for slot in host.robots.values():
        slot.port.capture = lambda camera='robot_cam', slot=slot: copy.deepcopy(slot.executor.last_obs)
    return zi.IntegratedTrial(SCENARIO, condition=condition, seed=700,
                              links={r: HostRobotLink(host, r) for r in zi.ROBOTS},
                              map_bundle=bundle_for(SCENARIO), horizon_s=30.,
                              pair_records=host.pairs.records, pair_role_assignment=roles.mapping())


def release_action(trial, actor, role, now=0.):
    """Only the model/clock are fake; production validation, dispatch and host run."""
    action = validate_action({'kind': 'claim', 'order_id': 'cargoX', 'destination_zone': 'B', 'role': role},
                             actor=actor, condition=trial.condition, order_ids=('cargoX',),
                             roles_by_order={'cargoX': ('end_neg', 'end_pos')})
    cid = f'call-{actor}-{len(trial.scheduler.calls)}'
    trial.scheduler.calls.append(SimpleNamespace(call_id=cid, actor=actor))
    trial.scheduler.call_causes[cid] = {'cause': 'test-release'}
    if not hasattr(trial, '_pending'):
        trial._pending = {}
    trial._pending[cid] = {'action_id': 'action-' + cid, 'request_id': 'request-' + cid}
    trial._on_action(actor, action, now)
    return trial.dispatch_log[-1]['ack']


@pytest.mark.parametrize('condition', zi.MAIN_CONDITIONS)
@pytest.mark.parametrize('roles', ASSIGNMENTS, ids=lambda p: '-'.join(p.participants))
def test_all_assignments_use_same_status_and_route_only_selected_ports(roles, condition):
    # The communication condition cannot choose a partner or change the lower controller.
    host, exs = setup()
    trial = trial_for(host, condition, roles)
    bus = trial.pair_status
    first, second = roles.participants
    assert release_action(trial, first, roles.role(first))['accepted']
    assert exs[second].job is None  # one request never creates the partner job
    assert not release_action(trial, first, roles.role(first))['accepted']
    assert release_action(trial, second, roles.role(second))['accepted']
    eps = active(host)
    for t in (0., .1, .2):
        host.world.data.time = t
        for rid in roles.participants:
            host._decide(rid, t)
    assert set(eps) == set(roles.participants)
    for rid in roles.participants:
        assert eps[rid].partner_id == roles.partner(rid)
        assert eps[rid].arguments['role'] == roles.role(rid)
        assert any(k == 'mecanum' for _, k, _ in host.robots[rid].port.log)
    outsider = next(r for r in zi.ROBOTS if r not in roles.participants)
    assert exs[outsider].job is None and exs[outsider]._pair is None
    assert not any(k in ('mecanum', 'arm') for _, k, _ in host.robots[outsider].port.log)
    records = bus.record()
    record = records['sessions'][0]
    assert record['role_to_robot'] == roles.mapping()
    assert record['role_assignment_sha256'] == roles.sha256()
    assert set(record['plan']['prestations']) == set(roles.participants)
    assert all(set(m) == FIELDS and m['state'] in STATES for m in record['status_messages'])
    assert {m['robot_id'] for m in record['status_messages']} == set(roles.participants)
    assert 'role_to_robot' not in str(record['status_messages'])


@pytest.mark.parametrize('roles', ASSIGNMENTS)
@pytest.mark.parametrize('first_index', (0, 1))
def test_actual_controller_uses_role_geometry_and_own_identity(roles, first_index):
    host, _ = setup(factory=m2_controller)
    order = roles.participants[first_index:] + roles.participants[:first_index]
    for rid in order:
        assert submit(host, roles, rid)['accepted']
    for rid, ep in active(host).items():
        ctl = ep.controller
        assert ctl.rid == ep.status.robot_id == ep.port.own.robot_id == rid
        ctl.grasp_estimate = (1., .06, 0. if roles.role(rid) == 'end_neg' else math.pi)
        ctl.seg = 0
        schedule = ctl.door_schedule(0.)
        assert schedule[-1][2]['forward'] * roles.sign(rid) > 0
        ctl.seg = next(i for i, (a, b) in enumerate(zip(ep.plan['route'], ep.plan['route'][1:]))
                       if abs(a[1] - b[1]) > 1e-6)
        schedule = ctl.door_schedule(0.)
        assert schedule[-1][2]['left'] * roles.sign(rid) < 0  # zone B is south
    assert m2.ROLES == {'r1': 'end_neg', 'r2': 'end_pos'}
    assert m2.DOOR_PLAN['headings_rad'] == {'r1': 0., 'r2': math.pi}


# Independent, numeric oracle for the authored [1.0, 0.0, 0] sheet:
# beam half-length .30, half-width .02, grid padding .06;
# grip offset .27 + base standoff .155 = .425; prestation backs off .30.
# Do not compute these expectations with make_plan/beam_keepout/prestation.
ROLE_GEOMETRY = {
    'end_neg': {'pre': [.275, 0., 0.], 'peer_station': [1.425, 0.], 'peer_pre': [1.725, 0.]},
    'end_pos': {'pre': [1.725, 0., -math.pi], 'peer_station': [.575, 0.], 'peer_pre': [.275, 0.]},
}


def assert_role_geometry(prestation, keepouts, role):
    expected = ROLE_GEOMETRY[role]
    assert prestation == pytest.approx(expected['pre'])
    assert [k['id'] for k in keepouts] == ['order_sheet_beam', 'partner_station', 'partner_prestation']
    assert keepouts[0]['center_m'] == pytest.approx([1., 0.])
    assert keepouts[0]['half_extents_m'] == pytest.approx([.36, .08])
    assert keepouts[0]['source'] == 'order-sheet beam footprint + sheet grid error pad (static), not a live pose'
    for keepout, center in zip(keepouts[1:], (expected['peer_station'], expected['peer_pre'])):
        assert keepout['center_m'] == pytest.approx(center)
        assert keepout['half_extents_m'] == pytest.approx([.17, .17])
        assert keepout['source'] == 'static order sheet'


@pytest.mark.parametrize('roles', ASSIGNMENTS)
def test_plan_keeps_fixed_beam_and_partner_exclusion_geometry(roles):
    assert SHEETS['cargoX']['beam_xyyaw'] == [1., 0., 0.]
    plan = make_plan(MAP, SHEETS['cargoX'], 'B', role_to_robot=roles.mapping())
    assert set(plan['keepouts']) == set(roles.participants)
    for rid in roles.participants:
        assert_role_geometry(plan['prestations'][rid], plan['keepouts'][rid], roles.role(rid))


@pytest.mark.parametrize('roles', ASSIGNMENTS)
def test_actual_approach_receives_fixed_role_exclusion_geometry(roles):
    from harness.zone_pair_guards import GuardedPairApproach
    host, _ = setup(factory=m2_controller)
    for rid, ep in both(host, roles).items():
        driver = ep.controller.driver
        assert isinstance(driver, GuardedPairApproach)
        assert_role_geometry([*driver.goal, driver.goal_yaw], driver.keepouts, roles.role(rid))


@pytest.mark.parametrize('name', ['zone_own_team_host', 'zone_own_executor', 'zone_pair_executor',
                                 'zone_pair_status', 'zone_study_integration'])
def test_role_adapter_preserves_each_registered_source(name):
    from tests.v6h_successor_pins import successor_blob, successor_pins
    root = Path(__file__).resolve().parents[1]
    path = f'harness/{name}.py'
    assert hashlib.sha256(successor_blob(path)).hexdigest() == successor_pins()[path]


def test_opt_in_host_and_study_leave_legacy_dispatch_available():
    from harness import zone_pair_executor as legacy_pair, zone_study_integration as legacy_study
    from tests.test_zone_pair_executor import setup as legacy_setup
    roles = PairRoles('r3', 'r1')
    role_host, _ = setup()
    both(role_host, roles)
    old_host, _ = legacy_setup()
    assert type(old_host.pairs) is legacy_pair.PairTeam
    assert not old_host.call('r3', 'pair_carry', 'cargoX', 'B', 'r1', 'end_neg')['accepted']
    for rid, partner in (('r1', 'r2'), ('r2', 'r1')):
        assert old_host.call(rid, 'pair_carry', 'cargoX', 'B', partner)['accepted']
    action = dict(kind='claim', order_id='cargoX', destination_zone='B', role='end_neg')
    assert legacy_study.executor_plan(action, None, actor='r1', orders=ORDER['orders']).args == ('cargoX', 'B', 'r2')
    assert legacy_study.executor_plan(action, None, actor='r3', orders=ORDER['orders']).api is None
    from harness.zone_pair_role_executor import controller_source_record
    record = controller_source_record()
    assert {'harness/zone_pair_role_executor.py', 'harness/zone_pair_role_host.py',
            'harness/zone_pair_role_integration.py', 'harness/zone_pair_roles.py'} <= set(record['controller_source_files'])
    assert 'role_to_robot' not in legacy_pair.make_plan(MAP, SHEETS['cargoX'], 'B')


@pytest.mark.parametrize('roles', ASSIGNMENTS)
def test_frozen_schedule_arithmetic_is_exact_under_role_relabeling(roles):
    for rid in roles.participants:
        alias = LEGACY_ROLES.mapping()[roles.role(rid)]
        fields = dict(grasp_estimate=(1., -.01, .03), seg=1, segments=[.55, .85])
        frozen = SimpleNamespace(**fields, rid=alias, door_plan=copy.deepcopy(m2.DOOR_PLAN), claims={})
        door = copy.deepcopy(m2.DOOR_PLAN)
        door['headings_rad'] = {r: (0. if roles.role(r) == 'end_neg' else math.pi) for r in roles.participants}
        live = SimpleNamespace(**fields, rid=rid, door_plan=door, claims={})
        assert role_door_schedule(live, .25, roles) == m2.M2DoorStudent.door_schedule(frozen, .25)
        assert live.claims == frozen.claims
        assert live.rid == rid and live.door_plan == door


@pytest.mark.parametrize('mapping', [None, {}, {'end_neg': 'r1'}, {'end_neg': 'r1', 'end_pos': 'r1'},
                                    {'end_neg': 'r0', 'end_pos': 'r2'}, {'end_neg': [], 'end_pos': 'r2'},
                                    {'end_neg': 'r1', 'end_pos': 'r2', 'peer_pose': [0, 0]}])
def test_bad_assignments_refused(mapping):
    with pytest.raises(ValueError):
        PairRoles.from_mapping(mapping)


@pytest.mark.parametrize('partner,role', [('r1', 'end_neg'), ('r0', 'end_neg'),
                                       ('r3', None), ('r3', 'west'), (['r3'], 'end_neg')])
def test_bad_self_or_unspecified_partner_never_starts_job(partner, role):
    h, exs = setup()
    ack = h.call('r1', 'pair_carry', 'cargoX', 'B', partner, role)
    assert not ack['accepted']
    assert all(ex.job is None for ex in exs.values()) and not h.pairs.sessions


@pytest.mark.parametrize('roles', ASSIGNMENTS)
@pytest.mark.parametrize('change', ('role', 'order', 'destination', 'static_map'))
def test_submission_mismatch_aborts_pending_and_never_starts_motion(roles, change):
    h, exs = setup()
    a, b = roles.participants
    assert submit(h, roles, a)['accepted']
    args = ['cargoX', 'B', a, roles.role(b)]
    if change == 'role': args[3] = roles.role(a)
    if change == 'order': args[0] = 'different_order'
    if change == 'destination': args[1] = 'A'
    if change == 'static_map': exs[b].map['regions']['zone_B']['center_m'][0] -= .1
    ack = h.call(b, 'pair_carry', *args)
    assert not ack['accepted']
    assert ack['rejected_reason'] == ('PAIR_STATIC_INPUT_MISMATCH' if change == 'static_map'
                                      else 'PAIR_SUBMISSION_MISMATCH')
    assert exs[a].job is None and exs[b].job is None
    assert not active(h)[a].controller.arm.events


@pytest.mark.parametrize('roles', ASSIGNMENTS)
def test_timeout_new_attempt_and_stale_status_do_not_cross_sessions(roles):
    h, exs = setup()
    a, b = roles.participants
    assert submit(h, roles, a)['accepted']
    old = active(h)[a]
    h.world.data.time = 5.
    h.pairs.poll(5.)
    assert old.terminal and exs[a].job is None and exs[b].job is None
    assert ends(exs[a])[-1]['detail']['reason'] == 'PAIR_RENDEZVOUS_TIMEOUT'
    # Refresh only the caller's fixture observations; no simulated state exists.
    for ex in exs.values():
        ex.last_obs['sim_time'] = 5.
        ex.last_report = type(ex.last_report)(t_est=5., initialized=True, x_m=0., y_m=0., yaw_rad=0.,
                                             std_xy_m=.01, std_yaw_rad=.01, source=ex.pose.source)
    fresh = both(h, roles)
    assert fresh[a].status.channel.task_id != old.status.channel.task_id
    assert not fresh[a].status.channel.publish(old.status.channel.log[0], 5.)
    assert set(fresh) == set(roles.participants) and not any(ep.terminal for ep in fresh.values())


@pytest.mark.parametrize('condition', zi.MAIN_CONDITIONS)
@pytest.mark.parametrize('roles', ASSIGNMENTS)
def test_peer_private_mutation_cannot_change_local_commands(roles, condition):
    def run(mutate):
        host, exs = setup()
        trial = trial_for(host, condition, roles)
        for rid in roles.participants:
            assert release_action(trial, rid, roles.role(rid))['accepted']
        eps = active(host)
        a, b = roles.participants
        eps[a].step(0.)
        if mutate:
            exs[b].last_report = None
            exs[b].job.phase = 'private'
            exs[b].map['regions']['zone_B']['center_m'] = [999., 999.]
            eps[b].controller.state = 'failed'
            eps[b].controller.failure = 'PRIVATE_CONTACT'
            eps[b].controller.claims['private_truth'] = [999., 999.]
            eps[b].controller.arm.events.clear()
            host.eval_only['future_events'] = {'r3_hold': [12., 52.]}
        decision = eps[a].step(.1)
        return decision, eps[a].controller.state, eps[a].plan
    assert run(False) == run(True)


@pytest.mark.parametrize('roles', ASSIGNMENTS)
def test_four_conditions_have_identical_controller_configuration(roles):
    configs = []
    for condition in zi.MAIN_CONDITIONS:
        host, _ = setup()
        trial = trial_for(host, condition, roles)
        configs.append(zi.condition_invariant_config(trial.study_config()))
    assert all(c == configs[0] for c in configs)


@pytest.mark.parametrize('roles', ASSIGNMENTS)
def test_one_sided_failure_clears_selected_queues_and_leaves_third_robot(roles):
    h, exs = setup()
    eps = both(h, roles)
    for rid in zi.ROBOTS:
        h.robots[rid].timeline = [(10., [{'kind': 'arm', 'servo_id': 1, 'pulse': 2000}])]
    a, b = roles.participants
    eps[b].status.tick('abort', .1)
    h.world.data.time = .1
    h._pair_safety(.1)
    for rid in roles.participants:
        assert eps[rid].terminal and not h.robots[rid].timeline
        assert not eps[rid].controller.arm.events and not eps[rid].port.commands
    third = next(r for r in zi.ROBOTS if r not in roles.participants)
    assert h.robots[third].timeline and not exs[third].events


def test_unaddressed_third_cannot_poison_waiting_pair():
    h, exs = setup()
    assert h.call('r3', 'pair_carry', 'cargoX', 'B', 'r2', 'end_neg')['accepted']
    first = active(h)['r3']
    assert h.call('r1', 'pair_carry', 'cargoX', 'B', 'r2', 'end_neg')['accepted']
    assert not first.terminal and exs['r2'].job is None
    assert h.call('r2', 'pair_carry', 'cargoX', 'B', 'r3', 'end_pos')['accepted']
    assert set(h.pairs.sessions[0]['endpoints']) == {'r2', 'r3'}
    assert len(h.pairs.sessions[1]['endpoints']) == 1


@pytest.mark.parametrize('participants', [('r3', 'r3'), ('r1',), ('r1', 'r2', 'r3'), ('r0', 'r2'), (['r1'], 'r2')])
def test_invalid_status_participant_set_refused(participants):
    with pytest.raises(ValueError):
        PairStatusChannel('bad', participants)


def test_legacy_default_plan_records_and_api_remain_fixed():
    assert requested_roles('r1', 'r2') == LEGACY_ROLES
    plan = make_plan(MAP, SHEETS['cargoX'], 'B')
    assert 'role_to_robot' not in plan
    action = dict(kind='claim', order_id='cargoX', destination_zone='B', role='end_neg')
    assert zi.executor_plan(action, None, actor='r1', orders=ORDER['orders']).args == ('cargoX', 'B', 'r2')
    h, _ = setup()
    assert h.call('r1', 'pair_carry', 'cargoX', 'B', 'r2')['accepted']
    assert 'role_to_robot' not in h.pairs.records()[0]
