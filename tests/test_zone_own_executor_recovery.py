"""T13b fake-only decision tests; filename uses the existing CI executor glob.

No world construction, rendering, physics step, live provider or model call.
HiddenEventPhysics.apply is exercised with array/actuator fakes, not MuJoCo.
"""
import copy
import hashlib
import inspect
import json
import sys
from dataclasses import asdict, replace
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from harness import zone_item_recovery as recovery
from harness import zone_identity_jobs as ij
from harness import zone_recovery_eval as evaluation
from harness import zone_map_schematic as maps
from harness import zone_study_inputs as inputs
from harness import zone_study_contract as contract
from sim import zone_hidden_events as hidden

ROOT = Path(__file__).resolve().parents[1]
BOX = (.1, .1, .3, .3)
EMPTY_ROI = (.5, .5, .9, .9)


def order(kind='cyan', identity='kind_fungible'):
    return {'order_id': 'order-1', 'kind': kind, 'count': 1, 'identity': identity,
            'item_ids': ['cyan_1'] if identity == 'specific_item' else [],
            'destination_zone': 'A', 'initial_location': {'pickup_bay': 'P1', 'slot': 'P1-1'}}


class Backend:
    target_api = ij.TARGET_API

    def __init__(self):
        self.calls = []

    def submit_target(self, job):
        self.calls.append(('submit', asdict(job)))
        return True

    def refresh_target(self, job, frame, detection):
        self.calls.append(('refresh', job, frame.sequence, detection))

    def cancel_target(self, job, reason):
        self.calls.append(('cancel', job, reason))


class Fixture:
    def __init__(self, orders=None, robot='r1', backend=None):
        self.robot, self.seq, self.sha = robot, 0, None
        self.backend = backend or Backend()
        self.gate = recovery.RecoveryJobs(robot, orders or [order()], self.backend)

    def frame(self, *, holding='unknown', resting='unknown', zone=None, visible=True,
              previous=None, gap=1, kind='cyan'):
        self.seq += gap
        detections = (ij.Detection('d', kind, BOX,
                       previous if previous is not None else (('d',) if self.seq > 1 else ()),
                       zone, holding, resting),) if visible else ()
        sha = hashlib.sha256(f'fake:{self.robot}:{self.seq}'.encode()).hexdigest()
        frame = ij.OwnFrame(self.robot, self.seq, float(self.seq), sha, self.sha, detections)
        self.sha = sha
        return frame

    def view(self, *, pickup=None, **kw):
        frame = self.frame(**kw)
        view = recovery.PickupView('order-1', frame.sequence, frame.rgb_sha256,
                    'P1-1', EMPTY_ROI, *pickup) if pickup else None
        self.gate.observe(frame, pickup=view)
        return frame

    def submit(self, **kw):
        return self.gate.submit('order-1', 'd', now_sim_s=float(self.seq), **kw)

    def status(self):
        return self.gate.recovery_status('order-1')

    def carrying(self):
        self.view()
        job = self.submit()['job']['job_id']
        self.view(holding='yes')
        return job


def test_observed_drop_cancels_before_refresh_then_regrasp_needs_new_own_frame():
    f = Fixture()
    first = f.carrying()
    before = len(f.backend.calls)
    f.view(holding='no', resting='yes')
    assert f.backend.calls[before:] == [('cancel', first, 'OWN_RGB_DROP_OBSERVED')]
    assert f.status()['cargo'] == 'dropped' and f.status()['next_action'] == 'reobserve'
    assert f.submit()['reason'] == 'RECOVERY_REOBSERVE_REQUIRED'
    f.view(holding='no', resting='yes')
    second = f.submit()
    assert second['state'] == 'running' and second['job']['job_id'] != first
    assert second['job']['local_token'] == f.backend.calls[0][1]['local_token']
    assert f.status()['attempts'] == 1 and f.status()['cargo'] == 'dropped'
    assert f.gate.claim('order-1')['observed_count'] == 0  # command is not recovery
    f.view(holding='yes')
    f.gate.issued_open(second['job']['job_id'], command_id='own-open', issued_at_sim_s=f.seq)
    for _ in range(2):
        f.view(holding='no', resting='yes', zone='A')
    assert f.gate.claim('order-1')['observed_count'] == 1
    assert f.gate.job_status()['state'] == 'observed_delivered'


def test_intentional_release_and_backend_done_are_not_drop_or_delivery():
    f = Fixture()
    job = f.carrying()
    f.gate.terminal(job)
    assert f.gate.claim('order-1')['observed_count'] == 0
    before = f.status()
    f.gate.issued_open(job, command_id='open', issued_at_sim_s=f.seq)
    assert f.status() == before  # command alone changes no RGB belief
    f.view(holding='no', resting='yes', zone='A')
    assert f.status()['cargo'] != 'dropped'
    assert f.gate.claim('order-1')['observed_count'] == 0
    f.view(holding='no', resting='yes', zone='A')
    assert f.gate.claim('order-1')['observed_count'] == 1


@pytest.mark.parametrize('kw', [dict(holding='unknown'), dict(holding='no'),
    dict(visible=False), dict(holding='no', resting='yes', gap=2),
    dict(holding='no', resting='yes', previous=())])
def test_occlusion_uncertainty_and_track_loss_never_mean_absent_or_dropped(kw):
    f = Fixture()
    job = f.carrying()
    before = len(f.backend.calls)
    f.view(**kw)
    assert f.status()['cargo'] == 'unknown' and f.status()['pickup'] == 'unknown'
    assert f.backend.calls[before:][0][:2] == ('cancel', job)
    assert all(c[0] != 'refresh' for c in f.backend.calls[before:])
    assert f.gate.claim('order-1')['observed_count'] == 0


def test_lost_track_cannot_be_relabelled_for_recovery_and_relooks_are_bounded():
    f = Fixture()
    f.carrying()
    f.view(visible=False)
    for index in range(4):
        f.view(previous=() if index == 0 else ('d',))
        result = f.submit()
        assert result['state'] != 'running'
    assert result['reason'] == 'RECOVERY_LIMIT'
    assert len([c for c in f.backend.calls if c[0] == 'submit']) == 1


def test_repeated_drops_stop_at_recovery_budget():
    f = Fixture()
    f.carrying()
    for n in range(recovery.MAX_RECOVERIES + 1):
        f.view(holding='no', resting='yes')
        f.view(holding='no', resting='yes')
        result = f.submit()
        if n < recovery.MAX_RECOVERIES:
            assert result['state'] == 'running'
            f.view(holding='yes')
        else:
            assert result['state'] == 'failed' and result['reason'] == 'RECOVERY_LIMIT'


def test_absence_requires_two_contiguous_clear_region_observations():
    f = Fixture()
    f.view(visible=False)
    assert f.status()['pickup'] == 'unknown'
    f.view(visible=False, pickup=('clear', 'empty'))
    assert f.status()['pickup'] == 'unknown'
    f.view(visible=False, pickup=('clear', 'empty'))
    assert f.status()['pickup'] == 'absent'
    assert f.status()['cargo'] == 'unknown'
    assert len(f.status()['evidence']) == 2
    f.view(visible=False, pickup=('occluded', 'empty'))
    assert f.status()['pickup'] == 'unknown'
    f.view(visible=False, pickup=('clear', 'empty'))
    assert f.status()['pickup'] == 'unknown'
    f.view(visible=False, pickup=('clear', 'occupied'))
    assert f.status()['pickup'] == 'occupied'


def test_empty_initial_region_does_not_cancel_tracked_cargo_or_edit_order():
    orders = [order()]
    before = copy.deepcopy(orders)
    f = Fixture(orders)
    job = f.carrying()
    for _ in range(2):
        f.view(holding='yes', pickup=('clear', 'empty'))
    assert f.status()['pickup'] == 'absent' and f.status()['cargo'] == 'held'
    assert not [c for c in f.backend.calls if c[0] == 'cancel']
    assert f.gate.job_status()['job_id'] == job and orders == before


@pytest.mark.parametrize('kw', [dict(frame_sequence=True), dict(frame_sequence=999),
    dict(order_id=[]), dict(rgb_sha256=[]), dict(visibility=[]), dict(occupancy=[]),
    dict(rgb_sha256='0'*64), dict(location_ref='P1-3'), dict(roi=BOX),
    dict(roi=(0., 0., float('nan'), 1.)), dict(visibility='gt_clear'), dict(occupancy='absent')])
def test_bad_pickup_evidence_cancels_without_inventing_belief(kw):
    f = Fixture()
    job = f.carrying()
    frame = f.frame()
    view = recovery.PickupView('order-1', frame.sequence, frame.rgb_sha256,
                               'P1-1', EMPTY_ROI, 'clear', 'empty')
    before = f.status()
    with pytest.raises(contract.ContractViolation):
        f.gate.observe(frame, pickup=replace(view, **kw))
    assert f.status() == before
    assert f.backend.calls[-1] == ('cancel', job, 'INVALID_OWN_RECOVERY_FRAME')
    assert f.submit()['reason'] == 'INVALID_RECOVERY_EVIDENCE'
    assert len([c for c in f.backend.calls if c[0] == 'submit']) == 1


@pytest.mark.parametrize('kind,identity', [('red', 'kind_fungible'), ('can', 'kind_fungible'),
                                        ('cyan', 'specific_item')])
def test_recovery_cannot_bypass_t13a_unsupported_skill_or_specific_identity(kind, identity):
    f = Fixture([order(kind, identity)])
    f.view(visible=False, pickup=('clear', 'empty'))
    f.view(visible=False, pickup=('clear', 'empty'))
    for index in range(3):
        f.view(kind=kind, previous=() if index == 0 else ('d',))
        result = f.submit(item_id='cyan_1' if identity == 'specific_item' else None)
        assert result['state'] in ('unknown', 'failed', 'unsupported')
    assert not f.backend.calls


@pytest.mark.parametrize('failure', ['cancel', 'submit', 'refresh'])
def test_backend_errors_do_not_fabricate_recovery(failure):
    f = Fixture()
    f.carrying()
    def crash(*args):
        raise RuntimeError('fake failure')
    if failure == 'refresh':
        f.backend.refresh_target = crash
        with pytest.raises(RuntimeError):
            f.view(holding='yes')
    else:
        if failure == 'cancel':
            f.backend.cancel_target = crash
            with pytest.raises(RuntimeError):
                f.view(holding='no', resting='yes')
            # Cancel failed before the frame was accepted. Do not invent a new
            # accepted-frame chain or require one to expose the permanent fault.
            assert f.submit()['reason'] == 'TARGET_BACKEND_FAULT'
        else:
            f.view(holding='no', resting='yes')
            f.view(holding='no', resting='yes')
            f.backend.submit_target = crash
            with pytest.raises(RuntimeError):
                f.submit()
    assert f.gate.claim('order-1')['observed_count'] == 0


@pytest.mark.parametrize('kind,holders,effect', [
    ('item_moved', [], 'item_moved'), ('item_moved', ['r1'], 'none_item_held'),
    ('item_dropped', ['r1', 'r2'], 'gripper_fault_open'),
    ('item_dropped', [], 'none_item_not_held')])
def test_hidden_apply_four_branches_with_arrays_only(monkeypatch, kind, holders, effect):
    """Execute the production branch logic with fake MuJoCo names/forward only."""
    forward, opened = [], []
    monkeypatch.setitem(sys.modules, 'mujoco', SimpleNamespace(
        mjtObj=SimpleNamespace(mjOBJ_BODY=1), mjtJoint=SimpleNamespace(mjJNT_FREE=0),
        mj_name2id=lambda *a: 0, mj_forward=lambda *a: forward.append(True)))
    physics = hidden.HiddenEventPhysics.__new__(hidden.HiddenEventPhysics)
    physics.world = SimpleNamespace(
        model=SimpleNamespace(body_jntadr=[0], jnt_type=[0], jnt_qposadr=[0], jnt_dofadr=[0]),
        data=SimpleNamespace(qpos=np.array([.4, -2.45, .05, 1., 0., 0., 0.]), qvel=np.ones(6)))
    physics.objects = {'it': {'body_name': 'fake_body'}}
    physics.holders = lambda item: list(holders)
    physics.faults = SimpleNamespace(open_gripper=lambda *a: opened.append(a))
    now = 30. if kind == 'item_moved' else 62.5
    target = {'item_id': 'it'}
    if kind == 'item_moved':
        target['to_pose_m'] = [-.2, .75, 0.]
    event = {'event_id': kind, 'kind': kind, 'target': target, 'trigger': {'at_sim_s': now}}
    old = physics.world.data.qpos.copy()
    result = physics.apply(event, now)
    assert result['effect'] == effect and result['at_sim_s'] == now
    if effect == 'item_moved':
        assert physics.world.data.qpos[:3].tolist() == [-.2, .75, .05]
        assert not physics.world.data.qvel.any() and forward == [True] and opened == []
    else:
        assert np.array_equal(old, physics.world.data.qpos) and not forward
        assert np.array_equal(physics.world.data.qvel, np.ones(6))
        assert opened == ([(r, 63.5, kind) for r in holders] if effect == 'gripper_fault_open' else [])


@pytest.mark.parametrize('robot', contract.ROBOTS)
@pytest.mark.parametrize('identity', ['specific_item', 'kind_fungible'])
def test_private_event_time_effect_holder_and_pose_changes_cannot_change_robot_decisions(robot, identity):
    scenario = json.loads((ROOT/'configs/zone_study_scenarios_v2/s5_moved_dropped_item_v2.json').read_text())
    if identity == 'kind_fungible':
        # Explicit in-memory dev fixture for the executable fake target path.
        # This is NOT the original s5 specific-identity success criterion.
        scenario['orders'][0].update(identity=identity, item_ids=[])
    bundle = maps.map_bundle(scenario['map_id'], landmark_detail='none', schematic=False)
    before = copy.deepcopy(scenario['orders'])
    flows = []
    for condition in contract.MAIN_CONDITIONS:
        payloads = []
        for effect, holder, time in [('item_moved', [], 30.), ('none_item_held', ['r3'], 999.),
                    ('gripper_fault_open', ['r1'], 62.5), ('none_item_not_held', [], 0.)]:
            private = copy.deepcopy(scenario)
            private['eval']['hidden_events'][0]['trigger']['at_sim_s'] = time
            private['eval']['setup']['placements'][0]['pose_m'] = [8., 9., 0.]
            private['eval']['holders'] = holder
            private['eval']['event_effect'] = effect
            source = inputs.OrderSheetSource(private, bundle)
            payload = inputs.build_call_input(robot_id=robot, condition_name=condition,
                request_id='fake-request', sim_time_s=1., static_map=inputs.static_map_for_call(bundle),
                source=source, seed=641, own_rgb_refs=[inputs.own_rgb_ref(robot, 1, 1., 'a'*64)])
            payloads.append(payload)
            f = Fixture(payload['order_sheet']['orders'], robot=robot)
            if identity == 'specific_item':
                f.view(visible=False, pickup=('clear', 'empty'))
                f.view(visible=False, pickup=('clear', 'empty'))
                f.view(previous=())
                response = f.submit(item_id='cyan_1')
                assert f.status()['pickup'] == 'absent' and response['state'] != 'running'
            else:
                f.carrying()
                f.view(holding='no', resting='yes')
                assert f.status()['cargo'] == 'dropped'
                f.view(holding='no', resting='yes')
                response = f.submit()
                assert response['state'] == 'running'
            flows.append((f.status(), response, f.gate.claim('order-1'), f.backend.calls))
            assert payload['order_sheet']['orders'][0]['initial_location'] == before[0]['initial_location']
            assert payload.get('inbox', []) == [] and payload['own_command_history'] == []
            source.assert_unchanged()
        assert all(p == payloads[0] for p in payloads)
    assert all(flow == flows[0] for flow in flows) and scenario['orders'] == before


def test_controller_has_no_effect_or_partner_input_and_does_not_import_evaluator():
    for forbidden in ('world', 'effect', 'schedule', 'holders', 'partner', 'condition'):
        assert forbidden not in inspect.signature(recovery.RecoveryJobs).parameters
        with pytest.raises(TypeError):
            recovery.RecoveryJobs('r1', [order()], Backend(), **{forbidden: {}})
    source = inspect.getsource(recovery)
    assert 'from sim' not in source and 'zone_recovery_eval' not in source


def test_effective_recovery_denominators_keep_noops_caps_unexecuted_and_unknown():
    E = evaluation.EventTrial
    rows = [E('move', 'e', 'item_moved', 'completed', 'item_moved', True, True, True),
            E('move-noop', 'e', 'item_moved', 'completed', 'none_item_held', False),
            E('drop', 'e', 'item_dropped', 'cap', 'gripper_fault_open', True, True, False),
            E('drop-noop', 'e', 'item_dropped', 'completed', 'none_item_not_held', False),
            E('no-fall-proof', 'e', 'item_dropped', 'completed', 'gripper_fault_open'),
            E('unexecuted', 'e', 'item_dropped', 'unexecuted'),
            E('unknown', 'e', 'item_moved', 'host_error', 'item_moved', True)]
    summary = evaluation.summarize(rows)
    assert summary['assignments'] == 7 and len(summary['rows']) == 7
    move, drop = (summary['by_kind'][k] for k in ('item_moved', 'item_dropped'))
    assert (move['assigned'], move['noop'], move['physical_effective'], move['recovered_effective']) == (3, 1, 2, 1)
    assert move['recovery_rate_effective'] == .5 and move['recovery_unknown'] == 1
    assert not move['recovery_verdict_complete']
    assert (drop['assigned'], drop['noop'], drop['physical_effective'], drop['applied_without_verified_effect']) == (4, 1, 1, 1)
    assert drop['recovery_rate_effective'] == 0. and drop['terminal_counts']['cap'] == 1
    assert drop['terminal_counts']['unexecuted'] == 1


def test_only_noops_is_insufficient_event_establishment_not_zero_recovery():
    row = evaluation.EventTrial('r', 'e', 'item_dropped', 'completed', 'none_item_not_held', False)
    result = evaluation.summarize([row])['by_kind']['item_dropped']
    assert result['noop'] == result['assigned'] == 1
    assert result['event_establishment_insufficient'] and result['recovery_rate_effective'] is None


@pytest.mark.parametrize('change', [dict(kind='teleport'), dict(effect='success'), dict(physical_effect=1),
    dict(effect='none_item_not_held'), dict(terminal='unexecuted'), dict(physical_effect=None),
    dict(discovered=False), dict(terminal='cap')])
def test_evaluation_rejects_wrong_or_fabricated_verdicts(change):
    row = evaluation.EventTrial('r', 'e', 'item_dropped', 'completed', 'gripper_fault_open', True, True, True)
    with pytest.raises(contract.ContractViolation):
        evaluation.summarize([replace(row, **change)])


def test_noop_cannot_be_fabricated_failure_and_duplicate_assignment_is_rejected():
    row = evaluation.EventTrial('r', 'e', 'item_dropped', 'completed', 'none_item_not_held', False)
    with pytest.raises(contract.ContractViolation, match='no-op'):
        evaluation.summarize([replace(row, recovered=False)])
    with pytest.raises(contract.ContractViolation, match='duplicate'):
        evaluation.summarize([row, row])


@pytest.mark.parametrize('version', ['', '_v2'])
def test_original_s5_event_times_and_public_initial_location_are_preserved(version):
    path = ROOT/f'configs/zone_study_scenarios{version}/s5_moved_dropped_item{version}.json'
    scenario = json.loads(path.read_text())
    events = scenario['eval']['hidden_events']
    assert [(e['kind'], e['trigger']['at_sim_s']) for e in events] == [('item_moved', 30.), ('item_dropped', 62.5)]
    assert scenario['orders'][0]['initial_location'] == {'pickup_bay': 'P1', 'slot': 'P1-1'}
    assert events[0]['target'] == {'item_id': 'cyan_1', 'to_pose_m': [-.2, .75, 0.]}
