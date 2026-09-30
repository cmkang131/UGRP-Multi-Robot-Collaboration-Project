"""T06 decision tests: no physics, native adapter, trained model or render.

Included by the existing test_zone_own_executor*.py CI glob; CI config unchanged.
The fake perception adapter decodes fixture bytes, not a physical observation.
"""
from dataclasses import asdict, replace
import copy
import json
import socket
import sys
from types import SimpleNamespace

import pytest

from harness import zone_crate_skill as crate
from harness.zone_pair_status import FIELDS, STATES, PairStatusChannel, PairStatusEndpoint
from harness.zone_crate_dispatch import PairTeam, executor_plan

ORDER = {'order_id': 'order-crate', 'kind': 'heavy_crate', 'count': 1,
         'required_robots': 2, 'destination_zone': 'B'}
STATIC_MAP = {'regions': {'zone_B': {'center_m': [4.6, -2.1], 'half_extents_m': [.3, .7]}}}
CONDITIONS = ('no_comm', 'peer_ko', 'leader_ko', 'structured')


@pytest.fixture(autouse=True)
def no_physics_network(monkeypatch):
    monkeypatch.setitem(sys.modules, 'mujoco', None)
    monkeypatch.setattr(socket.socket, 'connect', lambda *a: pytest.fail('network forbidden'))


def fake_perception(frame, history, goal):
    assert frame.robot_id in crate.ROLES
    assert all(row['robot_id'] == frame.robot_id for row in history)
    assert goal['target']['part'] == 'lug_' + crate.ROLES[frame.robot_id]
    return crate.CrateEvidence(**json.loads(frame.jpeg))


def fixture_frame(skill, now, *, overrides=None, fid=None):
    # All yes values are controlled mock observations. They prove no vision or
    # physical capability and are never written as robot success metrics.
    ev = crate.CrateEvidence(target_part='lug_' + skill.role, aligned='yes', grasped='yes',
                             holding='yes', at_destination='yes', supported='yes', released='yes')
    if skill.phase == 'carry' and now - skill.phase_at < .4:
        ev = replace(ev, at_destination='no')
    if overrides:
        ev = replace(ev, **overrides)
    return crate.OwnRGB(skill.robot_id, int(round(now * 1000)) if fid is None else fid,
                        now, json.dumps(asdict(ev)).encode())


class Rig:
    def __init__(self, *, timeout=3., horizon=10., order=None, static_map=None):
        order, static_map = order or ORDER, static_map or STATIC_MAP
        self.bus = PairStatusChannel(crate.task_id(order, static_map))
        self.skills = {rid: crate.CrateLugSkill(order, static_map, rid, role,
                       'r2' if rid == 'r1' else 'r1', PairStatusEndpoint(self.bus, rid),
                       fake_perception, phase_timeout_s=timeout, horizon_s=horizon)
                       for rid, role in crate.ROLES.items()}
        self.trace, self.t = [], -.05

    def tick(self, changes=None, *, omit=(), reverse=False):
        self.t = round(self.t + .05, 8)
        for rid in (('r2', 'r1') if reverse else ('r1', 'r2')):
            if rid in omit:
                continue
            skill = self.skills[rid]
            overrides = (changes or {}).get(rid, {})
            if callable(overrides):
                overrides = overrides(skill)
            frame = fixture_frame(skill, self.t, overrides=overrides)
            intent = skill.step(self.t, frame)
            self.trace.append(copy.deepcopy(intent))
            # This is issued-command history only, never a completion receipt.
            if intent['kind'] not in ('hold', 'sequence_complete_unconfirmed'):
                skill.on_command({'robot_id': rid, 't': self.t, 'kind': intent['kind']})

    def until(self, predicate, *, limit=150, changes=None, reverse=False):
        for _ in range(limit):
            self.tick(changes, reverse=reverse)
            if predicate():
                return
        pytest.fail(f'condition unmet: {[(s.phase, s.failure) for s in self.skills.values()]}')


@pytest.mark.parametrize('condition', CONDITIONS)
@pytest.mark.parametrize('rid,role,partner', [('r1', 'west', 'r2'), ('r2', 'east', 'r1')])
def test_crate_kind_dispatch_uses_lug_roles(condition, rid, role, partner):
    # Condition controls communication allowance elsewhere, never this dispatch.
    action = dict(kind='claim', order_id=ORDER['order_id'], destination_zone='B', role=role)
    plan = executor_plan(action, None, actor=rid, orders=[ORDER])
    assert (plan.api, plan.args, plan.rejected_reason) == ('pair_carry', ('order-crate', 'B', partner), None)
    assert condition in CONDITIONS


@pytest.mark.parametrize('rid,role', [('r1', 'end_neg'), ('r2', 'end_pos'), ('r1', 'east'), ('r3', 'west')])
def test_crate_dispatch_rejects_beam_or_wrong_actor_roles(rid, role):
    plan = executor_plan(dict(kind='claim', order_id=ORDER['order_id'], destination_zone='B', role=role),
                         None, actor=rid, orders=[ORDER])
    assert plan.api is None and plan.rejected_reason.startswith('UNSUPPORTED_CRATE_')


@pytest.mark.parametrize('change', [{'count': 2}, {'count': True}, {'required_robots': 1},
                                  {'kind': 'long_beam'}, {'kind': 'tri_frame'}])
def test_crate_contract_rejects_unsupported_order(change):
    with pytest.raises(ValueError, match='UNSUPPORTED_CRATE_ORDER'):
        crate.validate_request({**ORDER, **change}, 'r1', 'west', 'r2', 'B')


def test_duplicate_robot_and_bad_status_contract_rejected():
    with pytest.raises(ValueError, match='UNSUPPORTED_CRATE_PAIR'):
        crate.validate_request(ORDER, 'r1', 'west', 'r1', 'B')
    for participants in (('r1', 'r1'), ('r1', 'r3')):
        bus = PairStatusChannel(crate.task_id(ORDER, STATIC_MAP), participants=participants)
        with pytest.raises(ValueError, match='CRATE_STATUS_CONTRACT_MISMATCH'):
            crate.CrateLugSkill(ORDER, STATIC_MAP, 'r1', 'west', 'r2', PairStatusEndpoint(bus, 'r1'), fake_perception)
    bus = PairStatusChannel('wrong-public-task')
    with pytest.raises(ValueError, match='CRATE_STATUS_CONTRACT_MISMATCH'):
        crate.CrateLugSkill(ORDER, STATIC_MAP, 'r1', 'west', 'r2', PairStatusEndpoint(bus, 'r1'), fake_perception)


@pytest.mark.parametrize('reverse', [False, True])
def test_complete_decision_sequence_has_simultaneous_lift_but_no_physical_success(reverse):
    rig = Rig()
    rig.until(lambda: all(s.terminal for s in rig.skills.values()), reverse=reverse)
    assert {s.phase for s in rig.skills.values()} == {'sequence_complete_unconfirmed'}
    for rid in ('r1', 'r2'):
        actions = [a for a in rig.trace if a['robot_id'] == rid]
        kinds = [a['kind'] for a in actions if a['kind'] != 'hold']
        assert kinds[:2] == ['close_lug', 'lift_lug']
        assert 'carry_to_zone' in kinds
        assert kinds[-3:] == ['lower_lugs', 'open_lugs', 'sequence_complete_unconfirmed']
        assert all(a['target']['part'] == 'lug_' + crate.ROLES[rid] for a in actions)
        assert all(a['target']['mass_kg'] == .9 for a in actions)
        assert all(a['physical_supported'] is False and a['max_duration_s'] <= .1 for a in actions)
    for kind in ('close_lug', 'lift_lug', 'lower_lugs', 'open_lugs'):
        rows = [a for a in rig.trace if a['kind'] == kind]
        assert len(rows) == 2 and rows[0]['at_s'] == rows[1]['at_s']
    assert all(set(m) == FIELDS and m['state'] in STATES for m in rig.bus.log)
    assert not any('order-crate' in str(m) or 'lug_' in str(m) for m in rig.bus.log)
    assert crate.capability()['physical_supported'] is False


def test_actual_approach_targets_black_lug_instead_of_crate_body():
    rig = Rig()
    rig.tick({'r1': {'aligned': 'no'}, 'r2': {'aligned': 'no'}})
    rig.tick({'r1': {'aligned': 'no'}, 'r2': {'aligned': 'no'}})
    approaches = [a for a in rig.trace if a['kind'] == 'approach_lug']
    assert {a['target']['part'] for a in approaches} == {'lug_west', 'lug_east'}
    assert {a['target']['grip_xyz_m'] for a in approaches} == {(-.1, 0., .024), (.1, 0., .024)}
    assert all(a['target']['grip_width_m'] == .04 and a['target']['lug_height_m'] == .046 for a in approaches)


def test_lug_contract_matches_static_catalogue_without_copying_beam():
    from sim.zone_cargo import CATALOGUE
    spec = CATALOGUE['heavy_crate']
    assert spec.mass_kg == crate.MASS_KG == .9
    for grasp in spec.grasps:
        target = crate.lug_target(grasp.role)
        assert target['part'] == grasp.geom
        assert target['grip_xyz_m'] == grasp.grip_xyz
    assert {crate.lug_target(r)['part'] for r in ('west', 'east')} == {'lug_west', 'lug_east'}


@pytest.mark.parametrize('change', [{'aligned': 'unknown'}, {'target_part': 'box'}, {'target_part': 'lug_west'}])
def test_one_side_not_ready_or_wrong_lug_never_closes(change):
    rig = Rig(timeout=.8)
    rig.until(lambda: all(s.terminal for s in rig.skills.values()), changes={'r2': change})
    assert not any(a['kind'] in ('close_lug', 'lift_lug', 'carry_to_zone') for a in rig.trace)
    assert {s.phase for s in rig.skills.values()} == {'failed'}


@pytest.mark.parametrize('field,forbidden', [('grasped', 'lift_lug'), ('holding', 'carry_to_zone')])
def test_missing_one_side_grasp_or_holding_blocks_next_phase(field, forbidden):
    rig = Rig(timeout=.8)
    rig.until(lambda: all(s.terminal for s in rig.skills.values()), changes={'r2': {field: 'unknown'}})
    assert not any(a['kind'] == forbidden for a in rig.trace)
    assert any(a['kind'] == 'close_lug' for a in rig.trace)


def test_one_side_grasp_failure_is_propagated_as_abort_enum():
    rig = Rig()
    rig.until(lambda: all(s.terminal for s in rig.skills.values()), changes={'r2': {'grasped': 'no'}})
    assert rig.skills['r2'].failure == 'OWN_GRASP_FAILED'
    assert rig.skills['r1'].failure == 'PARTNER_ABORT'
    assert not any(a['kind'] == 'lift_lug' for a in rig.trace)
    assert [m['state'] for m in rig.bus.log[-2:]] == ['abort', 'abort']


def test_holding_loss_stops_carry_and_peer_before_any_further_motion():
    rig = Rig()
    rig.until(lambda: all(s.phase == 'carry' for s in rig.skills.values()))
    before = len(rig.trace)
    rig.tick({'r2': {'holding': 'unknown'}}, reverse=True)
    assert {s.phase for s in rig.skills.values()} == {'failed'}
    assert [a['kind'] for a in rig.trace[before:]] == ['hold', 'hold']
    assert rig.skills['r2'].failure == 'OWN_HOLDING_LOST'
    assert rig.skills['r1'].failure == 'PARTNER_ABORT'


@pytest.mark.parametrize('phase', ['approach', 'grasp', 'lift', 'carry', 'lower', 'release'])
def test_heartbeat_break_at_every_phase_terminates(phase):
    rig = Rig()
    if phase != 'approach':
        rig.until(lambda: all(s.phase == phase for s in rig.skills.values()))
    else:
        rig.tick({'r1': {'aligned': 'unknown'}, 'r2': {'aligned': 'unknown'}})
    for _ in range(5):
        rig.tick(omit=('r2',))
    assert rig.skills['r1'].terminal
    assert rig.skills['r1'].failure in ('PARTNER_SILENT', 'PARTNER_MISSED_GO')
    assert rig.trace[-1]['kind'] == 'hold'


def test_destination_or_release_evidence_is_required_commands_do_not_complete_job():
    for field, forbidden in [('at_destination', 'lower_lugs'), ('supported', 'open_lugs'),
                             ('released', 'sequence_complete_unconfirmed')]:
        rig = Rig(timeout=.8)
        rig.until(lambda: all(s.terminal for s in rig.skills.values()), changes={'r2': {field: 'unknown'}})
        assert not any(a['kind'] == forbidden for a in rig.trace)
        assert {s.phase for s in rig.skills.values()} == {'failed'}


def test_stale_same_frame_does_not_renew_holding_evidence():
    rig = Rig()
    rig.until(lambda: all(s.phase == 'carry' for s in rig.skills.values()))
    right = rig.skills['r2']
    stale = fixture_frame(right, rig.t, overrides={'at_destination': 'no'})
    # Fresh heartbeat records do not make a retained own RGB frame fresh.
    for _ in range(8):
        rig.t = round(rig.t + .05, 8)
        right.step(rig.t, stale)
        left = rig.skills['r1']
        left.step(rig.t, fixture_frame(left, rig.t, overrides={'at_destination': 'no'}))
    assert right.terminal and left.terminal
    assert right.failure == 'INVALID_OWN_RGB_OR_EVIDENCE'


@pytest.mark.parametrize('mode', ['foreign', 'top', 'future', 'replay', 'mutate', 'empty'])
def test_own_rgb_boundary_rejects_bad_frame(mode):
    rig = Rig()
    rig.tick()
    s = rig.skills['r1']
    frame = fixture_frame(s, .05)
    if mode == 'foreign': frame = replace(frame, robot_id='r2')
    if mode == 'top': frame = replace(frame, camera='cctv_top')
    if mode == 'future': frame = replace(frame, observed_at_s=.1)
    if mode == 'replay': frame = replace(frame, frame_id=-1)
    if mode == 'mutate': frame = replace(frame, frame_id=0)
    if mode == 'empty': frame = replace(frame, jpeg=b'')
    assert s.step(.05, frame)['kind'] == 'hold'
    assert s.failure == 'INVALID_OWN_RGB_OR_EVIDENCE'


def test_old_pre_command_positive_frame_does_not_authorize_lift():
    rig = Rig()
    rig.until(lambda: all(s.phase == 'grasp' for s in rig.skills.values()))
    s = rig.skills['r1']
    frame = s.last_frame
    rig.skills['r2'].status.tick('ready', rig.t + .05)
    s.step(rig.t + .05, frame)
    assert s.phase == 'grasp'
    assert s.status.state == 'not_ready'


def test_no_peer_ready_times_out_and_late_go_cannot_catch_up():
    rig = Rig(timeout=.3)
    for _ in range(8): rig.tick(omit=('r2',))
    assert rig.skills['r1'].failure == 'CRATE_TIMEOUT'
    assert all(a['kind'] == 'hold' for a in rig.trace)
    rig = Rig()
    for _ in range(4): rig.tick()
    # Ready at 0/.05 grants .3 on the shared control grid. Skip that epoch.
    rig.t = .3
    rig.tick()
    assert all(s.terminal for s in rig.skills.values())
    assert not any(a['kind'] == 'close_lug' for a in rig.trace)


def test_private_state_changes_and_condition_names_do_not_change_decisions():
    traces = []
    for condition in CONDITIONS:
        rig = Rig()
        # Poisoned host data is deliberately inaccessible through the provider
        # seam. The static task excludes setup identity/eval/hidden-event keys.
        for s in rig.skills.values():
            s.private_host = SimpleNamespace(gt_pose=object(), contact=object(),
                                             peer_live_state=object(), condition=condition)
        rig.until(lambda: all(s.terminal for s in rig.skills.values()))
        traces.append((rig.trace, rig.bus.log))
    assert all(trace == traces[0] for trace in traces)
    assert crate.task_id({**ORDER, 'setup_item_id': 'secret-changed', 'hidden_event_s': 12}, STATIC_MAP) == crate.task_id(ORDER, STATIC_MAP)


def test_native_pairteam_refuses_crate_even_with_fake_positive_factory(monkeypatch):
    from tests.test_zone_pair_executor import CALIB, FakeM2, SHEETS, setup
    host, exs = setup()
    host.pairs = PairTeam(exs, SHEETS, CALIB['params'], cancel_scheduled=host.pairs.cancel_scheduled,
                          contact_profile='cargo_noslip_v1', controller_factory=FakeM2)
    for ex in exs.values(): ex.orders['order-crate'] = dict(ORDER)
    called = []
    monkeypatch.setattr(host.pairs, 'factory', lambda *a: called.append(a))
    for rid, partner in [('r1', 'r2'), ('r2', 'r1')]:
        ack = host.pairs.start(rid, 'order-crate', 'B', partner, now=0.)
        assert not ack['accepted']
        assert ack['rejected_reason'] == 'CRATE_PHYSICAL_ADAPTER_UNAVAILABLE'
        assert ack['arguments']['role'] == crate.ROLES[rid]
    assert not called and not host.pairs.sessions
    assert all(ex.job is None for ex in exs.values())


def test_beam_and_unsupported_team_dispatch_remain_separate():
    beam = {**ORDER, 'kind': 'long_beam'}
    action = dict(kind='claim', order_id=ORDER['order_id'], destination_zone='B', role='end_neg')
    assert executor_plan(action, None, actor='r1', orders=[beam]).api == 'pair_carry'
    other = {**ORDER, 'kind': 'tri_frame', 'required_robots': 3}
    assert executor_plan(action, None, actor='r1', orders=[other]).rejected_reason == 'UNSUPPORTED_TEAM_ORDER'


def test_wrong_destination_foreign_history_and_malformed_provider_fail_closed():
    with pytest.raises(ValueError, match='WRONG_CRATE_DESTINATION'):
        crate.validate_request(ORDER, 'r1', 'west', 'r2', 'A')
    rig = Rig()
    s = rig.skills['r1']
    with pytest.raises(ValueError, match='NOT_OWN_COMMAND'):
        s.on_command({'robot_id': 'r2', 'kind': 'lift_lug'})
    with pytest.raises(ValueError, match='NOT_OWN_COMMAND'):
        s.on_command({'robot_id': 'r1', 'kind': 'arm', 't': 0., 'measured_joint': .3})
    with pytest.raises(ValueError, match='NOT_OWN_COMMAND'):
        s.on_command({'robot_id': 'r1', 'kind': 'mecanum', 't': 0., 'partner_pose': [0, 0]})
    s.perceive = lambda *a: {'holding': True}
    assert s.step(0., fixture_frame(s, 0.))['kind'] == 'hold'
    assert s.failure == 'INVALID_OWN_RGB_OR_EVIDENCE'


def test_missing_or_body_only_view_requests_lug_observation_without_closing():
    rig = Rig()
    for _ in range(4):
        rig.tick({'r1': {'target_part': 'box'}, 'r2': {'target_part': None}})
    assert {a['kind'] for a in rig.trace} == {'hold', 'observe_lug'}


def test_perception_adapter_error_becomes_abort_not_an_uncaught_motion_loop():
    rig = Rig()
    def broken(*args):
        raise RuntimeError('camera decoder failure')
    rig.skills['r2'].perceive = broken
    rig.tick()
    rig.tick()
    assert {s.phase for s in rig.skills.values()} == {'failed'}
    assert rig.skills['r1'].failure == 'PARTNER_ABORT'


def test_crate_dependency_is_pinned_and_collected_without_ci_configuration_changes():
    from pathlib import Path
    from harness.python_source_closure import source_closure
    from scripts.run_ci_tests import TEST_PATTERNS
    root = Path(__file__).resolve().parents[1]
    paths = source_closure(root, ['harness/zone_crate_dispatch.py'])
    assert 'harness/zone_crate_skill.py' in paths
    assert any(Path(__file__) in root.glob(pattern) for pattern in TEST_PATTERNS)


def test_sealed_beam_entry_points_remain_byte_identical_and_do_not_enable_crates():
    from pathlib import Path
    import hashlib
    from harness.zone_study_integration import executor_plan as sealed_plan
    root = Path(__file__).resolve().parents[1]
    pinned = json.loads((root / 'experiments/2026-09-29-pair-v6e-carry/prereg_v6e.json').read_text())
    for name in ('harness/zone_pair_executor.py', 'harness/zone_study_integration.py'):
        assert hashlib.sha256((root / name).read_bytes()).hexdigest() == pinned['v6_contract']['source_sha256'][name]
    action = dict(kind='claim', order_id=ORDER['order_id'], destination_zone='B', role='west')
    assert sealed_plan(action, None, actor='r1', orders=[ORDER]).rejected_reason == 'UNSUPPORTED_TEAM_ORDER'


def test_opt_in_pairteam_preserves_actual_beam_dispatch():
    from tests.test_zone_pair_executor import CALIB, FakeM2, SHEETS, setup
    host, exs = setup()
    pair = PairTeam(exs, SHEETS, CALIB['params'], cancel_scheduled=host.pairs.cancel_scheduled,
                    contact_profile='cargo_noslip_v1', controller_factory=FakeM2)
    assert pair.start('r1', 'cargoX', 'B', 'r2', now=0.)['accepted']
    assert pair.start('r2', 'cargoX', 'B', 'r1', now=0.)['accepted']
    assert len(pair.sessions) == 1
    assert set(pair.sessions[0]['endpoints']) == {'r1', 'r2'}
