"""T12 on T07's real role-aware host API; fake controller/ports, no physics."""
from dataclasses import replace
import copy

import pytest

from harness.zone_pair_roles import PairRoles
from harness.zone_pair_rendezvous import OwnPairRecovery, PairRequest, RoleAwareOwnPairPort
from harness.zone_pair_status import EPS
from harness import zone_study_protocol as protocol
from tests.test_zone_pair_executor import active
from tests.test_zone_pair_role_exchange import setup
from tests.test_zone_pair_rendezvous import CONDITIONS, no_physics_or_models  # noqa: F401


def recovery(host, actor):
    own = host.robots[actor].executor
    port = RoleAwareOwnPairPort(actor, call=lambda api, *args: host.call(actor, api, *args),
                               status=own.status, endpoint=lambda: own._pair.status if own._pair else None)
    return OwnPairRecovery(actor, port, rendezvous_timeout_s=host.pairs.rendezvous_timeout_s)


def refresh(host, now, *actors):
    host.world.data.time = now
    for actor in actors:
        host._capture(actor, now)  # saved JPEG + explicit healthy own-pose fixture
        host.robots[actor].executor.gate.state = 'ok'


def request(roles, actor):
    return PairRequest('cargoX', 'B', roles.partner(actor), roles.role(actor))


@pytest.mark.parametrize('condition', CONDITIONS)
@pytest.mark.parametrize('role', ['end_neg', 'end_pos'])
@pytest.mark.parametrize('partner', ['r1', 'r2'])
def test_r3_host_reassigns_only_after_own_cancel_and_clears_old_jobs(condition, role, partner):
    protocol.Transport(condition, seed=2, order_ids=['cargoX'], roles=['end_neg', 'end_pos'])
    roles = PairRoles.from_request('r3', partner, role)
    host, exs = setup()
    controllers = {r: recovery(host, r) for r in ('r1', 'r2', 'r3')}
    first = controllers['r3'].submit(request(roles, 'r3'), now=0.)
    assert controllers[partner].submit(request(roles, partner), now=0.).state == 'waiting'
    old = dict(active(host))
    before = host.pairs.records()[0]
    assert before['role_assignment_sha256'] == controllers['r3'].record()['assignment']['role_assignment_sha256']
    for actor, ep in old.items():
        host.robots[actor].timeline = [(100., [{'kind': 'arm', 'servo_id': 1, 'pulse': 1500}])]
        ep.port.commands.append({'kind': 'mecanum', 'forward': .1, 'left': 0., 'turn': 0., 'duration_s': .1})
    new_partner = next(r for r in ('r1', 'r2') if r != partner)
    new_request = replace(request(roles, 'r3'), partner_id=new_partner)
    second = controllers['r3'].replace(first.job_id, new_request, now=0.)
    assert second.state == 'waiting' and second.job_id != first.job_id
    assert set(active(host)) == {'r3'}  # no host-created job for the chosen new peer
    assert exs[new_partner].job is None
    assert exs[partner].job is None and not host.robots[partner].timeline
    for ep in old.values():
        assert ep.terminal and not ep.port.commands and not ep.controller.arm.events and not ep.controller.schedule
        assert ep.arm_step(100.) == []
    assert controllers['r3'].cancel(first.job_id, now=0.).reason == 'STALE_JOB'
    assert exs['r3'].job.job_id == second.job_id
    assert controllers[partner].poll(now=0.).state == 'ended'
    new_roles = PairRoles.from_request('r3', new_partner, role)
    assert controllers[new_partner].submit(request(new_roles, new_partner), now=0.).state == 'waiting'
    assert controllers['r3'].poll(now=0.).state == 'active'
    after = host.pairs.records()[-1]
    assert before['role_assignment_sha256'] != after['role_assignment_sha256']
    assert before['controller_source_sha256'] == after['controller_source_sha256']


@pytest.mark.parametrize('role', ['end_neg', 'end_pos'])
@pytest.mark.parametrize('offset', [-1., -.01, -2 * EPS, -EPS, 0., .01])
def test_r3_host_submission_boundaries(role, offset):
    roles = PairRoles.from_request('r3', 'r1', role)
    host, exs = setup()
    r3, r1 = recovery(host, 'r3'), recovery(host, 'r1')
    assert r3.submit(request(roles, 'r3'), now=0.).state == 'waiting'
    old = active(host)['r3']
    now = 5. + offset
    old.status.tick('start_ready', now)
    refresh(host, now, 'r1')
    assert r1.submit(request(roles, 'r1'), now=now).state == 'waiting'
    joined = exs['r1']._pair.status.channel is old.status.channel
    assert joined == (offset < -EPS)
    if not joined:
        assert old.terminal and exs['r3'].job is None
        assert r3.poll(now=now).state == 'ended'


@pytest.mark.parametrize('condition', CONDITIONS)
@pytest.mark.parametrize('role', ['end_neg', 'end_pos'])
def test_r3_host_private_changes_cannot_select_new_partner(condition, role):
    outcomes = []
    for mutate in (False, True):
        protocol.Transport(condition, seed=2, order_ids=['cargoX'], roles=['end_neg', 'end_pos'])
        host, exs = setup()
        roles = PairRoles.from_request('r3', 'r1', role)
        ctl = recovery(host, 'r3')
        assert ctl.submit(request(roles, 'r3'), now=0.).state == 'waiting'
        if mutate:
            for r in ('r1', 'r2'):
                exs[r].last_report = replace(exs[r].last_report, x_m=123., y_m=456., std_xy_m=789.)
                exs[r]._holding_after = {'answer': 'yes', 'source': 'private fixture'}
                exs[r].orders['cargoX']['destination_zone'] = 'C'
            host.eval_only['event'] = {'r3_hold_late': [12., 52.], 'winner': 'r2'}
        peer_before = copy.deepcopy([(exs[r].events, exs[r].api_log, host.robots[r].commands) for r in ('r1', 'r2')])
        assert ctl.poll(now=4.9).state == 'waiting'
        host.world.data.time = 5.
        assert ctl.poll(now=5.).reason == 'PAIR_RENDEZVOUS_TIMEOUT'
        assert peer_before == [(exs[r].events, exs[r].api_log, host.robots[r].commands) for r in ('r1', 'r2')]
        outcomes.append((ctl.events, host.robots['r3'].commands))
    assert outcomes[0] == outcomes[1]


@pytest.mark.parametrize('condition', CONDITIONS)
@pytest.mark.parametrize('role', ['end_neg', 'end_pos'])
def test_r3_host_40_seconds_late_needs_a_new_request_and_new_partner_readiness(condition, role):
    protocol.Transport(condition, seed=2, order_ids=['cargoX'], roles=['end_neg', 'end_pos'])
    host, exs = setup()
    roles = PairRoles.from_request('r3', 'r1', role)
    r3, r1 = recovery(host, 'r3'), recovery(host, 'r1')
    # The partner requests while r3's own request has not arrived. The plant's
    # [12,52] hold is NOT installed or passed to either recovery instance.
    refresh(host, 12., 'r1')
    assert r1.submit(request(roles, 'r1'), now=12.).state == 'waiting'
    old = active(host)['r1']
    host.world.data.time = 17.
    assert r1.poll(now=17.).reason == 'PAIR_RENDEZVOUS_TIMEOUT'
    assert old.terminal and not old.controller.schedule and not host.robots['r1'].timeline
    refresh(host, 52., 'r1', 'r3')
    assert r1.poll(now=52.).state == r3.poll(now=52.).state == 'idle'
    # Only fresh own calls can rejoin; an old endpoint's readiness is useless.
    late = r3.submit(request(roles, 'r3'), now=52.)
    assert late.state == 'waiting'
    channel = active(host)['r3'].status.channel
    assert channel is not old.status.channel
    assert not channel.publish(old.status.channel.log[0], 52.)
    assert r3.poll(now=52.).state == 'waiting'
    assert r1.submit(request(roles, 'r1'), now=52.).state == 'waiting'
    assert r3.poll(now=52.).state == 'active'
    assert set(active(host)) == {'r1', 'r3'}
    assert exs['r2'].job is None and not exs['r2'].api_log


def test_r3_role_exchange_requires_independent_complementary_request():
    host, exs = setup()
    r3, r1 = recovery(host, 'r3'), recovery(host, 'r1')
    first = r3.submit(PairRequest('cargoX', 'B', 'r1', 'end_neg'), now=0.)
    bad = r1.submit(PairRequest('cargoX', 'B', 'r3', 'end_neg'), now=0.)
    assert bad.state == 'refused' and bad.reason == 'PAIR_SUBMISSION_MISMATCH'
    assert exs['r1'].job is None and exs['r3'].job is None
    assert r3.poll(now=0.).state == 'ended'
    assert r3.cancel(first.job_id, now=0.).reason == 'STALE_JOB'
