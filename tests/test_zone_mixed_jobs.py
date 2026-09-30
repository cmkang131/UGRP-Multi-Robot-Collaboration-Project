"""P02: static inventory + production robot APIs/scheduler on fake ports only."""
from __future__ import annotations

import copy
import hashlib
import json
import socket
import sys
from pathlib import Path
from types import MethodType, SimpleNamespace

import pytest

from harness import zone_mixed_jobs as mixed
from harness import zone_mixed_integration as mixed_zi
from harness import zone_study_integration as zi
from harness.zone_mixed_host import MixedOwnCamTeamHost
from harness.zone_own_team_host import OwnCamTeamHost
from harness.zone_own_executor import ZoneOwnExecutor
from harness.owncam_pose_source import OwnCamPoseSource, PoseReport
from harness.zone_study_inputs import OrderSheetSource
from harness.zone_study_scenarios import bundle_for
from scripts import run_zone_study_integration as legacy_runner
from scripts import zone_mixed_study_adapter as runner
from sim.zone_geometry_scene import GeometryCargoZoneScene
from sim.zone_mixed_inventory import MixedGeometryCargoZoneScene, check_scene_inventory, prepare_inventory
from tests.test_zone_pair_executor import FakeM2, PairFakeHost, pair_obs
from tests.test_zone_own_executor import CALIB, ROWS_Y, SEARCH_POSE, rgb_of
from tests.test_zone_study_integration import Scripted, reply

ROOT = Path(__file__).resolve().parents[1]
DEV = json.loads((ROOT / 'configs/zone_study_integration/mixed_jobs_dev_spec.json').read_text())
SCENARIO = json.loads((ROOT / DEV['episode']['scenario']).read_text())
BUNDLE = bundle_for(SCENARIO)
STATIC = json.loads((ROOT / BUNDLE['map_file']).read_text())
PROTOTYPE = {'box_00': {'kind': 'cyan', 'body_name': 'cargo_box_00', 'joint_name': 'cargo_box_00_free',
                         'position_m': [.4, -.85, .016], 'half_extents_m': [.02, .02, .016]}}


@pytest.mark.parametrize('path', [
    'harness/zone_own_team_host.py',
    'harness/zone_study_integration.py',
    'scripts/run_zone_study_integration.py',
])
def test_b1_mixed_adapter_keeps_registered_source_bytes(path):
    """B1: opt-in additions must not rewrite the current v6e source pins."""
    prereg = json.loads((ROOT / 'experiments/2026-09-29-pair-v6e-carry/prereg_v6e.json').read_text())
    assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == prereg['v6_contract']['source_sha256'][path]


@pytest.fixture(autouse=True)
def forbid_execution(monkeypatch):
    monkeypatch.setitem(sys.modules, 'mujoco', None)
    monkeypatch.setitem(sys.modules, 'sim.multi_masterpi_production', None)
    monkeypatch.setitem(sys.modules, 'scripts.zone_teacher', None)
    monkeypatch.setattr(socket.socket, 'connect', lambda *a: pytest.fail('network forbidden'))
    monkeypatch.setattr(socket.socket, 'connect_ex', lambda *a: pytest.fail('network forbidden'))
    # A fake controller is the only permissible M2 factory in this file.
    monkeypatch.setattr('harness.zone_pair_executor.m2_controller', lambda *a: pytest.fail('real controller forbidden'))
    monkeypatch.setattr(zi, 'build_pose_provider', lambda *a, **k: pytest.fail('provider/model forbidden'))


def spec(scenario=None, episode=None):
    return runner.host_spec(scenario or SCENARIO, episode or DEV['episode'], BUNDLE)


class DoneM2(FakeM2):
    def tick(self, now):
        self.state = 'done'  # synthetic API completion, never evaluated arrival


class SoloExecutor(ZoneOwnExecutor):
    def _step_deliver(self, now, job):
        if now - job.started_at >= 4.:
            self._finish(now, 'unconfirmed', 'FAKE_SOLO_SEQUENCE_DONE')
        return {'mode': 'tick', 'commands': [{'kind': 'hold'}]}


class FakePose(OwnCamPoseSource):
    """Own API timing fixture; no PF, landmarks, worker or model is constructed."""
    source = 'owncam_pf_v2:p02_fake'
    def __init__(self):
        self.loc, self.servo = self, {}
    def on_command(self, row): pass
    def set_motion_profile(self, *args): pass
    def report(self, t):
        return PoseReport(t, True, x_m=0., y_m=0., yaw_rad=0., std_xy_m=.01, std_yaw_rad=.01,
                          since_tag_s=0., fix_age_s=0., last_fix_t=t, source=self.source)
    def on_frame(self, t, rgb): return self.report(t)


class MixedPairFakeHost(PairFakeHost, MixedOwnCamTeamHost):
    """Fake world/ports with the production mixed API admission in the MRO."""


def fake_host(factory=DoneM2):
    host_spec = spec()
    exs = {r: SoloExecutor(r, STATIC, CALIB['params'], host_spec['order_sheet'],
                          skill_factory=lambda *a, **k: pytest.fail('real skill forbidden'),
                          pose_estimate_cls=tuple, search_rows_y=ROWS_Y, judgments=False,
                          seed=host_spec['seed'], pose_source=FakePose()) for r in zi.ROBOTS}
    host = MixedPairFakeHost(exs, lambda *a: None)
    host.spec = host_spec
    host.contact_record = {'profile': 'cargo_noslip_v1'}
    host.enable_pair_carry(host_spec['pair_order_sheets'], CALIB['params'], controller_factory=factory)
    for r, ex in exs.items():
        ex.on_command({'t': 0., 'kind': 'initial_servo_command', 'pulses': SEARCH_POSE})
        slot = host.robots[r]
        def capture(camera='robot_cam', r=r, slot=slot):
            slot.port.fid += 1
            return pair_obs(r, slot.port.fid, host.world.data.time, slot.port.servo)
        slot.port.capture = capture
    host.links = {r: runner.HostRobotLink(host, r) for r in zi.ROBOTS}
    # All frames pass through the production own-port tap. A bypass would leave
    # frame_at empty and can never count as a successful fake decision test.
    def capture_raw(host, rid, now):
        slot = host.robots[rid]
        frame = slot.port.capture()
        slot.executor.on_frame(now, frame, rgb_of(frame))
        slot.frames.append({'robot_id': rid, 'camera': frame['camera'], 'sha256': frame['sha256'], 't': now})
        slot.next_frame = now + host.FRAME_S
    host._capture_raw = MethodType(capture_raw, host)
    for r, ex in exs.items():
        host._capture(r, 0.)
        ex.gate.state = 'ok'  # explicit own-readiness fixture; no localisation claim
        assert not host.robots[r].dead
    return host, exs


def claim(actor, oid, zone, role):
    return mixed_zi.executor_plan({'kind': 'claim', 'order_id': oid, 'destination_zone': zone, 'role': role},
                            None, actor=actor, orders=SCENARIO['orders'])


def test_static_bindings_and_public_sheet_have_distinct_ids_and_no_setup_pose():
    from harness.zone_study_scenarios import validate
    report = validate(SCENARIO)
    assert report.ok, report.checks
    host_spec = spec()
    record = host_spec['mixed_jobs']
    assert record['bindings']['beam-order']['item_ids'] == ['beam_dev']
    assert record['bindings']['cyan-order']['item_ids'] == ['cyan_dev']
    assert record['constraints'] == mixed.CONSTRAINTS
    sheet = host_spec['order_sheet']
    public = {k: v for k, v in SCENARIO.items() if k != 'eval'}
    assert sheet == OrderSheetSource(public, BUNDLE).sheet()
    serialized = json.dumps(sheet)
    assert all(key not in serialized for key in ('pose_m', 'beam_xyyaw', 'setup', 'mixed_jobs', 'bindings'))
    assert [o['initial_location']['slot'] for o in sheet['orders']] == ['P2-3', 'P1-1']
    mixed.validate_host_spec(host_spec)
    assert DEV['source_sha'] is DEV['execution_bundle_id'] is DEV['bundle_sha256'] is None


def test_b1_legacy_admission_and_source_closure_are_not_rebound():
    from harness.python_source_closure import source_closure
    with pytest.raises(zi.ContractViolation, match='pair-only'):
        legacy_runner.host_spec(SCENARIO, DEV['episode'], BUNDLE)
    legacy = set(source_closure(ROOT, ['scripts/run_zone_study_integration.py']))
    added = set(source_closure(ROOT, ['scripts/zone_mixed_study_adapter.py']))
    for name in ('harness/zone_mixed_host.py', 'harness/zone_mixed_integration.py',
                 'harness/zone_mixed_jobs.py', 'sim/zone_mixed_inventory.py'):
        assert name in added and name not in legacy
    assert legacy_runner.StudyTeamHost is not runner.StudyTeamHost
    assert zi.IntegratedTrial is not runner.IntegratedTrial
    assert legacy_runner.zi.executor_plan is zi.executor_plan


def test_mixed_study_constructor_uses_static_scene_then_attaches_order_keyed_pair(monkeypatch, tmp_path):
    """Exercise the real cooperative constructors with only the World owner faked."""
    from sim.zone_own_scene_provider import own_scene
    host_spec = spec()
    original = copy.deepcopy(host_spec)
    calls = []
    def init_base(host, base_spec, student, **kw):
        calls.append(('base', copy.deepcopy(base_spec)))
        assert base_spec['pair_order_sheets'] == {}
        scene = own_scene(base_spec, base_spec['contact_profile'], kw['scene'])
        assert isinstance(scene, MixedGeometryCargoZoneScene)
        check_scene_inventory(scene.config['setup_only']['objects'],
                              scene.config['cargo_set']['items'], original['mixed_jobs'])
        host.spec = base_spec
        host.static, host.eval_only = scene.config['static_map'], {}
        host.world = SimpleNamespace(close=lambda: None)
        host.robots = {r: SimpleNamespace(port=SimpleNamespace(capture=lambda *a: None)) for r in zi.ROBOTS}
    def attach(host, sheets, params, **kw):
        assert host.spec == original
        calls.append(('pair', copy.deepcopy(sheets), kw))
    monkeypatch.setattr(OwnCamTeamHost, '__init__', init_base)
    monkeypatch.setattr(OwnCamTeamHost, 'enable_pair_carry', attach)
    monkeypatch.setattr(legacy_runner.zone_eval_top, 'apply_to_world', lambda *a: {'fake': True})
    host = runner.StudyTeamHost(host_spec, {}, root=ROOT, provider_spec={'uses_landmark_tags': False},
                               frames_dir=tmp_path)
    assert host_spec == original and host.spec == original
    assert [row[0] for row in calls] == ['base', 'pair']
    assert calls[1][1] == original['pair_order_sheets']
    assert calls[1][2] == {'policy': 'v5h'}
    assert set(host.links) == set(zi.ROBOTS)


@pytest.mark.parametrize('damage', ['frames_missing', 'inventory_missing', 'contract_changed'])
def test_mixed_constructor_refuses_before_world_owner(monkeypatch, tmp_path, damage):
    host_spec = spec()
    scene = MixedGeometryCargoZoneScene.from_spec(host_spec, 'local_contact_fine')
    frames = tmp_path
    if damage == 'frames_missing':
        frames = None
    elif damage == 'inventory_missing':
        scene.config['setup_only']['objects'].clear()
    else:
        host_spec['pair_order_sheets']['beam-order']['beam_xyyaw'][0] = 10.
    monkeypatch.setattr(OwnCamTeamHost, '__init__', lambda *a, **k: pytest.fail('World owner reached'))
    with pytest.raises((ValueError, zi.ContractViolation)):
        MixedOwnCamTeamHost(host_spec, {}, root=ROOT, study_layer=None, frames_dir=frames, scene=scene)


@pytest.mark.parametrize('closed,dead,reason', [
    (True, False, 'EPISODE_ENDED'), (False, True, 'ROBOT_STOPPED'),
])
def test_mixed_refusals_keep_shutdown_precedence(closed, dead, reason):
    host, _ = fake_host()
    host.closed, host.robots['r3'].dead = closed, dead
    ack = host.links['r3'].call('pair_carry', 'beam-order', 'B', 'r1')
    assert not ack['accepted'] and ack['rejected_reason'] == reason
    assert host.api_calls[-1] is ack


def test_one_to_many_static_binding_for_fungible_order():
    s = copy.deepcopy(SCENARIO)
    solo = s['orders'][1]
    solo.update(count=2, identity='kind_fungible', item_ids=[])
    p = copy.deepcopy(s['eval']['setup']['placements'][1]); p['item_id'] = 'cyan_other'
    s['eval']['setup']['placements'].append(p)
    assert mixed.order_bindings(s['orders'], s['eval']['setup']['placements'])['cyan-order']['item_ids'] == [
        'cyan_dev', 'cyan_other']
    with pytest.raises(zi.ContractViolation, match='COUNT'):
        spec(s)


@pytest.mark.parametrize('mutation', [
    lambda s: s['eval']['setup']['placements'].pop(),
    lambda s: s['eval']['setup']['placements'].append(copy.deepcopy(s['eval']['setup']['placements'][0])),
    lambda s: s['eval']['setup']['placements'][1].update(kind='red'),
    lambda s: s['eval']['setup']['placements'][1].update(item_id='beam_dev'),
    lambda s: s['eval']['setup']['placements'][1].update(order_id='missing-order'),
    lambda s: s['eval']['setup']['placements'][1].update(slot='P2-3'),
    lambda s: s['eval']['setup']['placements'][1].update(pose_m=[float('nan'), 0., 0.]),
])
def test_invalid_order_physical_join_is_refused(mutation):
    s = copy.deepcopy(SCENARIO); mutation(s)
    with pytest.raises(zi.ContractViolation):
        spec(s)


def test_fake_scene_resolver_preserves_both_items_and_leaves_legacy_pair_only(monkeypatch):
    from sim.zone_cargo_scene import CargoZoneScene
    host_spec = spec()
    class CaptureScene(MixedGeometryCargoZoneScene):
        def __init__(self, selected, root): self.selected = selected
    selected = CaptureScene.from_spec(host_spec, 'local_contact_fine').selected
    def parent_resolve(scene):
        scene.config = {'variant': 'zone_wide_door',
                        'static_map': json.loads((ROOT / 'maps/zones/zone_wide_door.json').read_text()),
                        'setup_only': {'objects': copy.deepcopy(PROTOTYPE)},
                        'cargo_set': {'items': host_spec['team_cargo']}}
        scene.inventory = list(PROTOTYPE)
        scene.cargo = [object()]
    monkeypatch.setattr(CargoZoneScene, '_resolve', parent_resolve)
    scene = MixedGeometryCargoZoneScene.__new__(MixedGeometryCargoZoneScene)
    scene.selection, scene.scene = selected['layout'], selected
    scene._read = lambda *a: None
    scene._verify_camera = lambda: None
    scene._resolve()
    assert scene.inventory == ['cyan_dev']
    assert scene.config['setup_only']['objects']['cyan_dev']['position_m'] == [-.2, -2.45, .016]
    assert scene.config['cargo_set']['items'][0]['item_id'] == 'beam_dev'
    fake = SimpleNamespace(spec=host_spec, objects=scene.config['setup_only']['objects'])
    runner.placements_match(SCENARIO, fake)
    check_scene_inventory(fake.objects, host_spec['team_cargo'], host_spec['mixed_jobs'])
    with pytest.raises(zi.ContractViolation, match='missing'):
        check_scene_inventory({}, host_spec['team_cargo'], host_spec['mixed_jobs'])
    GeometryCargoZoneScene._resolve(scene)
    assert scene.inventory == [] and scene.config['setup_only']['objects'] == {}


@pytest.mark.parametrize('mutation', [
    lambda rows: rows.pop(),
    lambda rows: rows.append(copy.deepcopy(rows[0])),
    lambda rows: rows[0].update(kind='heavy_crate'),
    lambda rows: rows[0].update(item_id='unknown'),
    lambda rows: rows[0].update(pose=[1., .05, 0.]),
    lambda rows: rows[0].update(mass_kg=.001),
])
def test_fake_inventory_refuses_missing_duplicate_kind_identity_or_pose(mutation):
    host_spec = spec(); rows = copy.deepcopy(host_spec['team_cargo']); mutation(rows)
    with pytest.raises(zi.ContractViolation):
        prepare_inventory(PROTOTYPE, rows, host_spec['mixed_jobs'])


@pytest.mark.parametrize('kind', ['red', 'heavy_crate'])
def test_unsupported_kind_and_new_route_are_refused(kind):
    s = copy.deepcopy(SCENARIO); s['orders'][0]['kind'] = kind
    with pytest.raises(zi.ContractViolation): spec(s)
    e = copy.deepcopy(DEV['episode']); e['map'] = 'zone_wide_corridor_geometry_v2'
    with pytest.raises(zi.ContractViolation, match='ROUTE'): spec(episode=e)
    e = copy.deepcopy(DEV['episode']); e.pop('mixed_jobs_profile')
    with pytest.raises(zi.ContractViolation, match='pair-only'): spec(episode=e)
    s = copy.deepcopy(SCENARIO); s['orders'][0]['destination_zone'] = 'C'
    with pytest.raises(zi.ContractViolation, match='ROUTE'): spec(s)
    e = copy.deepcopy(DEV['episode']); e['pair_policy'] = 'b-v6g'
    with pytest.raises(zi.ContractViolation, match='POLICY'): spec(episode=e)


def test_rehashed_contract_cannot_enable_r3_pair_or_mutate_inventory_and_sheet():
    host_spec = spec()
    for change in (lambda r: r['jobs']['beam-order']['actors'].update(r3='end_pos'),
                   lambda r: r['bindings']['beam-order'].update(kind='heavy_crate')):
        record = copy.deepcopy(host_spec['mixed_jobs']); change(record)
        record['sha256'] = zi.digest({k: v for k, v in record.items() if k != 'sha256'})
        with pytest.raises(zi.ContractViolation): mixed.validate_contract(record)
    host_spec['pair_order_sheets']['beam-order']['beam_xyyaw'][0] = 1.
    with pytest.raises(zi.ContractViolation, match='sheet'):
        mixed.validate_host_spec(host_spec)


def test_wrong_api_kind_and_destination_fail_closed():
    assert claim('r3', 'missing', 'A', 'west').rejected_reason == 'UNKNOWN_ORDER'
    assert claim('r3', 'cyan-order', 'B', 'west').rejected_reason == 'WRONG_ORDER_DESTINATION'
    orders = [{**SCENARIO['orders'][1], 'kind': 'red'}]
    action = {'kind': 'claim', 'order_id': 'cyan-order', 'destination_zone': 'A', 'role': 'west'}
    assert mixed_zi.executor_plan(action, None, actor='r3', orders=orders).rejected_reason == 'UNSUPPORTED_SOLO_ORDER'


def test_independent_claims_no_auto_peer_and_pair_failure_does_not_stop_r3():
    host, exs = fake_host(FakeM2)
    for r, oid, z, role in [('r1', 'beam-order', 'B', 'end_neg'), ('r3', 'cyan-order', 'A', 'west')]:
        p = claim(r, oid, z, role)
        ack = host.links[r].call(p.api, *p.args)
        assert ack['accepted'], ack
    assert host.links['r2'].job() is None
    assert set(host.pairs.sessions[0]['endpoints']) == {'r1'}
    solo_job = exs['r3'].job
    p = claim('r2', 'beam-order', 'B', 'end_pos')
    assert host.links['r2'].call(p.api, *p.args)['accepted']
    assert host.links['r1'].call('abort', 'fake_pair_failure')['accepted']
    host.pairs.poll(.1)
    assert exs['r1'].job is exs['r2'].job is None
    assert exs['r3'].job is solo_job and not host.robots['r3'].cancellations
    exs['r3']._finish(4., 'unconfirmed', 'FAKE_SOLO_SEQUENCE_DONE')
    assert [e['event'] for e in exs['r3'].events if e['event'].startswith('job_')] == ['job_started', 'job_done']
    assert not [a for a in host.api_calls if a['robot_id'] == 'r3' and a['api'] != 'deliver']


def test_solo_failure_does_not_abort_pair_and_direct_api_rejects_unsupported_roles():
    host, exs = fake_host()
    assert host.links['r3'].call('deliver', 'cyan-order', 'A')['accepted']
    exs['r3']._fail(1., 'FAKE_SOLO_FAILURE')
    for r, partner in [('r1', 'r2'), ('r2', 'r1')]:
        ack = host.links[r].call('pair_carry', 'beam-order', 'B', partner)
        assert ack['accepted'], ack
    assert exs['r1'].job is not None and exs['r2'].job is not None
    assert not host.links['r3'].call('pair_carry', 'beam-order', 'B', 'r1')['accepted']
    assert not host.links['r1'].call('deliver', 'cyan-order', 'A')['accepted']
    assert not host.links['r3'].call('deliver', 'beam_dev', 'B')['accepted']
    assert not host.links['r3'].call('goto', 'A')['accepted']
    assert not host.links['r3'].call('deliver', {'order_id': 'cyan-order'}, 'A')['accepted']
    assert claim('r3', 'beam-order', 'B', 'end_neg').rejected_reason == 'UNSUPPORTED_PAIR_ROLE'


def decision(payload):
    rid = payload['robot_id']
    oid = 'cyan-order' if rid == 'r3' else 'beam-order'
    order = next(o for o in payload['order_sheet']['orders'] if o['order_id'] == oid)
    role = {'r1': 'end_neg', 'r2': 'end_pos', 'r3': 'west'}[rid]
    claimed = any(h['arguments'].get('order_id') == oid for h in payload['own_command_history'])
    action = {'kind': 'continue'} if claimed else {'kind': 'claim', 'order_id': oid, 'role': role,
                                                 'destination_zone': order['destination_zone']}
    return reply(payload, action)


def run_fake(condition, *, mutate_eval=False):
    host, exs = fake_host()
    scenario = copy.deepcopy(SCENARIO)
    if mutate_eval:
        scenario['eval']['setup']['placements'][0]['pose_m'] = [99., 99., 99.]
        scenario['eval']['gt'] = {'robots': {'r3': [-99., 99.]}}
        scenario['eval']['top_rgb'] = 'different evaluation-only frame'
        host.eval_only.update(gt={'r1': 'different'}, top_rgb='different')
    trial = runner.IntegratedTrial(scenario, condition=condition, seed=700, links=host.links, horizon_s=25.,
                               map_bundle=BUNDLE, pair_records=host.pairs.records)
    trial.fixtures = {r: Scripted(decision) for r in zi.ROBOTS}
    trial.begin(0.)
    for i in range(1, 251):
        t = round(i * zi.QUANTUM_S, 6)
        for event in runner.StudyTeamHost.advance_to(host, t):
            trial.on_executor_event(event, at_s=t)
        trial.step_to(t)
    result = trial.finish(25.)
    return host, exs, trial, result


@pytest.mark.parametrize('condition', zi.MAIN_CONDITIONS)
def test_four_condition_identity_ledger_dispatch_terminal_eval_join_and_gt_top_invariance(condition):
    host, exs, trial, result = run_fake(condition)
    assert zi.digest(host.spec) == zi.digest(spec())
    changed = run_fake(condition, mutate_eval=True)[2]
    assert [r['request_sha256'] for r in trial.requests] == [r['request_sha256'] for r in changed.requests]
    assert trial.actions == changed.actions
    assert trial.send_ledger.sends() == len(trial.requests) > 3
    assert all(c['provenance']['order_sheet_sha256'] == trial.source.sha256 for c in result.calls)
    dispatch = [d for d in trial.dispatch_log if d['api'] in ('deliver', 'pair_carry') and d['ack']['accepted']]
    assert [(d['actor'], d['args'][0]) for d in dispatch] == [('r1', 'beam-order'), ('r2', 'beam-order'), ('r3', 'cyan-order')]
    for d in dispatch:
        assert d['call_id'] in trial.scheduler.ledger
    terminal = [e for ex in exs.values() for e in ex.events if e['event'] in ('job_done', 'job_failed')]
    assert len(terminal) == 3 and all(e['event'] == 'job_done' for e in terminal)
    assert all(e['detail']['confirmation'] == 'unconfirmed' for e in terminal)
    # Evaluation is a separate synthetic referee stream, never an executor receipt.
    from harness.zone_study_referee import Referee, SETTLE_S
    ref = Referee(SCENARIO['orders'], STATIC)
    truth = {}
    for oid, b in host.spec['mixed_jobs']['bindings'].items():
        x, y = STATIC['regions']['zone_' + b['destination_zone']]['center_m']
        truth[b['item_ids'][0]] = {'kind': b['kind'], 'x': x, 'y': y, 'yaw': 0., 'z': .016, 'held': False, 'speed': 0.}
    for t in (20., 20. + SETTLE_S + .1): ref.observe(t, truth)
    assert ref.orders_complete()
    deliveries = ref.record()['deliveries']
    joined = mixed.evidence_join(host.spec['mixed_jobs'], dispatch, terminal, deliveries)
    assert len(joined) == 3
    assert {row['order_id']: row['item_ids'] for row in joined} == {'beam-order': ['beam_dev'], 'cyan-order': ['cyan_dev']}
    assert all(row['terminal_event'] == 'job_done' and len(row['deliveries']) == 1 for row in joined)
    assert ref.per_order()['beam-order']['item_delivered_sim_s'].keys() == {'beam_dev'}
    assert ref.per_order()['cyan-order']['item_delivered_sim_s'].keys() == {'cyan_dev'}
    for row in trial.requests:
        payload = json.loads(row['user'])
        assert len(payload['own_rgb_refs']) == 1
        assert payload['own_rgb_refs'][0]['ref'].startswith('own-' + row['robot'] + '-')
        assert 'GT' not in row['user'] and 'top_rgb' not in row['user'] and 'pose_m' not in row['user']
    with pytest.raises(zi.ContractViolation, match='terminal'):
        mixed.evidence_join(host.spec['mixed_jobs'], dispatch, [*terminal, terminal[0]], deliveries)
    with pytest.raises(zi.ContractViolation, match='evaluation'):
        mixed.evidence_join(host.spec['mixed_jobs'], dispatch, terminal, [{**deliveries[0], 'item_id': 'wrong'}])
    bad = copy.deepcopy(dispatch); bad[0]['ack']['arguments']['order_id'] = 'cyan-order'
    with pytest.raises(zi.ContractViolation, match='ack identity'):
        mixed.evidence_join(host.spec['mixed_jobs'], bad, terminal, deliveries)
