"""Synthetic detection/action contracts only: no renderer, physics, model or GT lookup."""
import copy
import hashlib
import inspect
import json
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from harness import zone_identity_jobs as ij
from harness import zone_map_schematic as maps
from harness import zone_study_inputs as inputs
from harness import zone_study_contract as contract

ROOT = Path(__file__).resolve().parents[1]
LEFT = (.1, .1, .3, .3)
RIGHT = (.6, .1, .8, .3)


def order(oid='order-1', count=2, *, identity='kind_fungible', item_ids=None, kind='cyan', zone='A'):
    return {'order_id': oid, 'kind': kind, 'count': count, 'identity': identity,
            'item_ids': item_ids or [], 'destination_zone': zone,
            'initial_location': {'pickup_bay': 'P1', 'slot': 'P1-1'}}


def detection(name='a', *, previous=(), box=LEFT, kind='cyan', **kw):
    return ij.Detection(name, kind, box, previous, **kw)


class FakeTargetExecutor:
    target_api = ij.TARGET_API

    def __init__(self, *, accepted=True):
        self.submitted, self.refreshed, self.cancelled = [], [], []
        self.accepted = accepted

    def submit_target(self, job):
        self.submitted.append(asdict(job))
        return self.accepted

    def refresh_target(self, job_id, frame, detection_id):
        self.refreshed.append((job_id, frame.sequence, detection_id))

    def cancel_target(self, job_id, reason):
        self.cancelled.append((job_id, reason))


class Fixture:
    def __init__(self, orders=None, backend=None, robot='r1'):
        self.backend = backend if backend is not None else FakeTargetExecutor()
        self.gate = ij.IdentityJobs(robot, orders if orders is not None else [order()], self.backend)
        self.robot, self.seq, self.time, self.sha = robot, 0, 0., None

    def view(self, *detections, step=1., seq_step=1):
        self.seq += seq_step
        self.time += step
        sha = hashlib.sha256(f'fake-own-image-{self.robot}-{self.seq}'.encode()).hexdigest()
        frame = ij.OwnFrame(self.robot, self.seq, self.time, sha, self.sha, tuple(detections))
        self.gate.observe(frame)
        self.sha = sha
        return frame

    def submit(self, name='a', oid='order-1', **kw):
        return self.gate.submit(oid, name, now_sim_s=self.time, **kw)

    def open(self, job):
        self.gate.issued_open(job, command_id=f'open-{self.seq}', issued_at_sim_s=self.time)


def test_two_same_colour_objects_count_once_each_and_reach_lower_job():
    f = Fixture()
    f.view(detection(), detection('b', box=RIGHT))
    first = f.submit()
    job1 = first['job']
    assert first['state'] == 'running'
    assert job1['order_id'] == 'order-1' and job1['requested_item_id'] is None
    assert job1['local_token'] != 'a' and job1['rgb_sha256'] == f.sha
    assert f.backend.submitted == [job1]
    assert f.submit('b')['reason'] == 'OWN_JOB_BUSY'
    f.view(detection(previous=('a',), holding='yes'), detection('b', previous=('b',), box=RIGHT))
    f.open(job1['job_id'])
    for _ in range(2):
        f.view(detection(previous=('a',), holding='no', resting='yes', zone='A'),
               detection('b', previous=('b',), box=RIGHT))
    assert f.gate.claim('order-1')['observed_count'] == 1
    assert f.gate.claim('order-1')['state'] == 'unknown'
    assert f.submit()['reason'] == 'TARGET_ALREADY_COUNTED_OR_ASSIGNED'
    second = f.submit('b')
    assert second['job']['local_token'] != job1['local_token']
    f.view(detection(previous=('a',), holding='no', resting='yes', zone='A'),
           detection('b', previous=('b',), box=RIGHT, holding='yes'))
    f.open(second['job']['job_id'])
    for _ in range(2):
        f.view(detection(previous=('a',), holding='no', resting='yes', zone='A'),
               detection('b', previous=('b',), box=RIGHT, holding='no', resting='yes', zone='A'))
    claim = f.gate.claim('order-1')
    assert claim['state'] == 'observed_delivered' and claim['observed_count'] == 2
    assert claim['basis'] == 'own_rgb_belief_only'
    assert {r['job_id'] for r in claim['receipts']} == {job1['job_id'], second['job']['job_id']}
    assert all(len(r['evidence']) == 2 for r in claim['receipts'])


def test_specific_name_and_unique_colour_are_not_visual_identity():
    f = Fixture([order(count=1, identity='specific_item', item_ids=['cyan_1'])])
    for i in range(3):
        f.view(detection('cyan_1', previous=('cyan_1',) if i else ()))
        result = f.submit('cyan_1', item_id='cyan_1')
        assert result['resolved_item_id'] is None
        assert f.gate.claim('order-1')['observed_count'] == 0
        assert result['state'] == ('unknown' if i < 2 else 'failed')
    assert result['reason'] == 'IDENTITY_RELOOK_LIMIT'
    assert f.backend.submitted == []


def test_specific_two_same_colour_items_and_swapped_labels_remain_unknown():
    f = Fixture([order(count=1, identity='specific_item', item_ids=['cyan_1'])])
    f.view(detection('cyan_1'), detection('cyan_2', box=RIGHT))
    assert f.submit('cyan_1', item_id='cyan_1')['reason'] == 'SPECIFIC_IDENTITY_UNGROUNDED'
    f.view(detection('cyan_2', previous=('cyan_1',)),
           detection('cyan_1', previous=('cyan_2',), box=RIGHT))
    assert f.submit('cyan_1', item_id='cyan_1')['state'] == 'unknown'
    assert f.backend.submitted == []


def test_item_and_order_ids_are_not_interchangeable():
    f = Fixture([order('order-5', 1, identity='specific_item', item_ids=['cyan_1'])])
    f.view(detection('cyan_1'))
    with pytest.raises(contract.ContractViolation, match='unknown order_id'):
        f.submit('cyan_1', 'cyan_1', item_id='cyan_1')
    with pytest.raises(contract.ContractViolation, match='specific item_id'):
        f.submit('cyan_1', 'order-5', item_id='order-5')
    result = f.submit('cyan_1', 'order-5', item_id='cyan_1')
    assert result['order_id'] == 'order-5' and result['requested_item_id'] == 'cyan_1'


@pytest.mark.parametrize('replacement', ['same_label', 'new_label', 'sequence_gap', 'split', 'merge'])
def test_loss_or_ambiguous_association_cancels_and_cannot_make_new_count(replacement):
    f = Fixture()
    f.view(detection(), detection('b', box=RIGHT))
    job = f.submit()['job']
    if replacement in ('same_label', 'new_label'):
        f.view()
        f.view(detection('a' if replacement == 'same_label' else 'fresh'))
    elif replacement == 'sequence_gap':
        f.view(detection(previous=('a',)), seq_step=2)
    elif replacement == 'split':
        f.view(detection(previous=('a',)), detection('fresh', previous=('a',), box=RIGHT))
    else:
        f.view(detection(previous=('a', 'b')))
    assert f.backend.cancelled == [(job['job_id'], 'TRACK_LOST_OR_AMBIGUOUS')]
    assert f.gate.claim('order-1')['observed_count'] == 0
    assert f.submit('fresh' if replacement == 'new_label' else 'a')['state'] == 'unknown'
    assert len(f.backend.submitted) == 1


def test_renamed_detection_with_unique_continuous_association_keeps_target():
    f = Fixture()
    f.view(detection())
    job = f.submit()['job']
    f.view(detection('renamed', previous=('a',)))
    assert f.backend.refreshed == [(job['job_id'], 2, 'renamed')]
    assert f.backend.cancelled == []


def test_overlapping_boxes_cannot_inflate_two_distinct_targets():
    f = Fixture()
    f.view(detection(), detection('duplicate', box=LEFT))
    assert f.submit()['state'] == f.submit('duplicate')['state'] == 'unknown'
    assert f.backend.submitted == []


def test_new_birth_requires_covisibility_with_all_historical_same_kind_tokens():
    f = Fixture()
    f.view(detection())
    f.view(detection(previous=('a',)), detection('b', box=RIGHT))
    assert f.gate.select('order-1', 'b', now_sim_s=f.time)['state'] == 'ready'
    f.view(detection('b', previous=('b',), box=RIGHT))
    f.view(detection('new', box=LEFT), detection('b', previous=('b',), box=RIGHT))
    assert f.gate.select('order-1', 'new', now_sim_s=f.time)['state'] == 'unknown'


@pytest.mark.parametrize('case', ['backend_done', 'no_grasp', 'wrong_zone', 'holding_unknown',
                                  'not_resting', 'only_one_frame', 'no_open', 'dropped_before_open'])
def test_false_completion_is_not_counted(case):
    f = Fixture([order(count=1)])
    f.view(detection())
    job = f.submit()['job']['job_id']
    if case == 'backend_done':
        f.gate.terminal(job)
    else:
        if case != 'no_grasp':
            f.view(detection(previous=('a',), holding='yes'))
        if case == 'dropped_before_open':
            f.view(detection(previous=('a',), holding='no'))
        if case != 'no_open':
            f.open(job)
        for _ in range(1 if case == 'only_one_frame' else 2):
            f.view(detection(previous=('a',), holding='unknown' if case == 'holding_unknown' else 'no',
                             resting='no' if case == 'not_resting' else 'yes',
                             zone='B' if case == 'wrong_zone' else 'A'))
    assert f.gate.claim('order-1')['state'] == 'unknown'
    assert f.gate.claim('order-1')['observed_count'] == 0
    if case == 'wrong_zone':
        assert f.backend.cancelled == [(job, 'MISDELIVERY_OBSERVED')]
        with pytest.raises(contract.ContractViolation):
            f.gate.terminal(job)  # delayed bogus success after misdelivery


def test_settle_cadence_and_unknown_break_the_receipt_streak():
    f = Fixture([order(count=1)])
    f.view(detection())
    job = f.submit()['job']['job_id']
    f.view(detection(previous=('a',), holding='yes'))
    f.open(job)
    landed = detection(previous=('a',), holding='no', resting='yes', zone='A')
    f.view(landed)
    f.view(landed, step=.1)
    assert f.gate.claim('order-1')['observed_count'] == 0
    f.view(detection(previous=('a',)))
    f.view(landed)
    assert f.gate.claim('order-1')['observed_count'] == 0
    f.view(landed)
    assert f.gate.claim('order-1')['observed_count'] == 1
    f.view(detection(previous=('a',), holding='no', resting='yes', zone='B'))
    assert f.gate.claim('order-1')['observed_count'] == 0


def test_release_requires_fresh_holding_and_new_post_command_frames():
    for delay in (.8, 1.01):
        f = Fixture([order(count=1)])
        f.view(detection())
        job = f.submit()['job']['job_id']
        f.view(detection(previous=('a',), holding='yes'))
        f.gate.issued_open(job, command_id='open-1', issued_at_sim_s=f.time + delay)
        landed = detection(previous=('a',), holding='no', resting='yes', zone='A')
        f.view(landed, step=.5)  # observation precedes the open command
        f.view(landed)
        assert f.gate.claim('order-1')['observed_count'] == 0
        f.view(landed)
        assert f.gate.claim('order-1')['observed_count'] == (1 if delay < 1 else 0)


def test_foreign_job_and_replayed_open_command_are_rejected():
    f = Fixture()
    f.view(detection())
    job = f.submit()['job']['job_id']
    with pytest.raises(contract.ContractViolation):
        f.open('foreign-job')
    f.view(detection(previous=('a',), holding='yes'))
    f.open(job)
    with pytest.raises(contract.ContractViolation, match='duplicate'):
        f.open(job)


def test_receipt_is_not_reused_for_another_order_or_duplicate_target():
    f = Fixture([order('first', 1), order('second', 1)])
    f.view(detection(), detection('b', box=RIGHT))
    job = f.submit(oid='first')['job']['job_id']
    f.view(detection(previous=('a',), holding='yes'), detection('b', previous=('b',), box=RIGHT))
    f.open(job)
    for _ in range(2):
        f.view(detection(previous=('a',), holding='no', resting='yes', zone='A'),
               detection('b', previous=('b',), box=RIGHT))
    assert f.submit(oid='second')['reason'] == 'TARGET_ALREADY_COUNTED_OR_ASSIGNED'
    assert f.submit('b', oid='first')['reason'] == 'ORDER_COUNT_ALREADY_MET'
    assert f.gate.claim('second')['observed_count'] == 0


@pytest.mark.parametrize('age,state', [(0., 'ready'), (1., 'ready'), (1.00001, 'unknown'), (-.01, 'unknown')])
def test_frame_freshness_boundary(age, state):
    f = Fixture()
    f.view(detection())
    assert f.gate.select('order-1', 'a', now_sim_s=f.time + age)['state'] == state


def test_unknown_relooks_count_distinct_observations_not_repeat_api_calls():
    f = Fixture([order(count=1, identity='specific_item', item_ids=['cyan_1'])])
    f.view(detection())
    for _ in range(10):
        assert f.submit(item_id='cyan_1')['state'] == 'unknown'


@pytest.mark.parametrize('backend', [object(), FakeTargetExecutor(accepted=False), FakeTargetExecutor(accepted=1)])
def test_legacy_or_refusing_backend_cannot_silently_run_colour_only_deliver(backend):
    f = Fixture(backend=backend)
    f.view(detection())
    assert f.submit()['state'] in ('unsupported', 'failed')
    assert f.gate.claim('order-1')['observed_count'] == 0


@pytest.mark.parametrize('method', ['submit_target', 'refresh_target'])
def test_backend_exception_cancels_without_receipt(method):
    f = Fixture()
    f.view(detection())
    def crash(*args):
        raise RuntimeError('fake backend fault')
    if method == 'submit_target':
        f.backend.submit_target = crash
        with pytest.raises(RuntimeError):
            f.submit()
    else:
        f.submit()
        f.backend.refresh_target = crash
        with pytest.raises(RuntimeError):
            f.view(detection(previous=('a',)))
    assert f.backend.cancelled[-1][1].endswith('_ERROR')
    assert f.gate.claim('order-1')['observed_count'] == 0


def test_cancel_failure_latches_backend_fault_instead_of_starting_another_job():
    f = Fixture()
    f.view(detection(), detection('b', box=RIGHT))
    job = f.submit()['job']['job_id']
    def crash(*args):
        raise RuntimeError('fake cancel fault')
    f.backend.cancel_target = crash
    with pytest.raises(RuntimeError):
        f.gate.terminal(job, failed=True)
    assert f.submit('b')['reason'] == 'TARGET_BACKEND_FAULT'
    assert f.gate.job_status()['state'] == 'failed'
    assert len(f.backend.submitted) == 1


@pytest.mark.parametrize('change', [dict(robot_id='r2'), dict(sequence=True), dict(sequence=1),
                                  dict(captured_at_sim_s=float('nan')), dict(rgb_sha256='GT'),
                                  dict(previous_rgb_sha256='0' * 64), dict(detections=[])])
def test_invalid_frame_is_rejected_without_credit_and_cancels_running_job(change):
    f = Fixture()
    first = f.view(detection())
    job = f.submit()['job']
    valid = replace(first, sequence=2, captured_at_sim_s=2., rgb_sha256='a' * 64,
                    previous_rgb_sha256=first.rgb_sha256, detections=(detection(previous=('a',)),))
    before = f.gate.claim('order-1')
    with pytest.raises(contract.ContractViolation):
        f.gate.observe(replace(valid, **change))
    assert f.gate.claim('order-1') == before
    assert f.backend.refreshed == [] and f.backend.submitted == [job]
    assert f.backend.cancelled == [(job['job_id'], 'INVALID_OWN_FRAME')]


@pytest.mark.parametrize('dets', [
    (detection(), detection()), (detection(box=(.2, .1, .1, .3)),),
    (detection(box=(float('nan'), .1, .3, .3)),), (detection(previous=('missing',)),),
    (detection(holding='gt_held'),), (detection(zone='door_1'),),
    (detection(kind=''),), (detection(previous=('a', 'a')),),
])
def test_invalid_detection(dets):
    f = Fixture()
    with pytest.raises(contract.ContractViolation):
        f.view(*dets)


@pytest.mark.parametrize('orders', [
    [],
    [order(count=True)], [order(count=0)], [order(count=-1)], [order(identity='guessed')],
    [order(identity='specific_item')], [order(), order()],
    [order(count=1, identity='specific_item', item_ids=['x']),
     order('other', 1, identity='specific_item', item_ids=['x'])],
    [{**order(), 'gt_pose': [0, 0, 0]}], [{**order(), 'placements': []}],
])
def test_invalid_public_orders(orders):
    with pytest.raises(contract.ContractViolation):
        Fixture(orders)


@pytest.mark.parametrize('kind', ['red', 'green', 'can', 'tile', 'heavy_crate', 'long_beam'])
def test_no_skill_support_is_inferred_from_a_fungible_count_contract(kind):
    f = Fixture([order(kind=kind)])
    f.view(detection(kind=kind))
    assert f.submit()['state'] == 'unsupported'
    assert f.backend.submitted == []


@pytest.mark.parametrize('robot', contract.ROBOTS)
def test_private_setup_events_and_peer_truth_never_change_fixed_actions_or_claims(robot):
    """Use the real public-input projection in all 4 conditions, no models."""
    path = ROOT / 'configs/zone_study_scenarios_v2/s1_normal_mixed_v2.json'
    scenario = json.loads(path.read_text())
    bundle = maps.map_bundle(scenario['map_id'], landmark_detail='none', schematic=False)
    moved, event, peer = (copy.deepcopy(scenario) for _ in range(3))
    moved['eval']['setup']['placements'][0]['pose_m'] = [10., 10., 0.]
    event['eval']['hidden_events'] = [{'at_sim_s': 999., 'kind': 'item_moved', 'target': {'item_id': 'cyan_1'}}]
    peer['eval']['peer_actual_deliveries'] = ['cyan_1', 'cyan_2']
    runs = []
    for condition in contract.MAIN_CONDITIONS:
        for config in (scenario, moved, event, peer):
            source = inputs.OrderSheetSource(config, bundle)
            payload = inputs.build_call_input(
                robot_id=robot, condition_name=condition, request_id='fake-request-1', sim_time_s=1.,
                static_map=inputs.static_map_for_call(bundle), source=source, seed=601,
                own_rgb_refs=[inputs.own_rgb_ref(robot, 1, 1., 'a' * 64)])
            # Fixed action, not P09 inventory or an oracle-driven target selector.
            f = Fixture(payload['order_sheet']['orders'], robot=robot)
            f.view(detection(), detection('b', box=RIGHT))
            decision = f.submit()
            f.gate.terminal(decision['job']['job_id'])
            before_observation = f.gate.claim('order-1')
            assert before_observation['observed_count'] == 0
            f.view(detection(previous=('a',), holding='yes'), detection('b', previous=('b',), box=RIGHT))
            f.open(decision['job']['job_id'])
            for _ in range(2):
                f.view(detection(previous=('a',), holding='no', resting='yes', zone='A'),
                       detection('b', previous=('b',), box=RIGHT))
            assert f.gate.claim('order-1')['observed_count'] == 1
            runs.append((decision, before_observation, f.gate.claim('order-1'), f.backend.submitted))
            assert 'peer_actual_deliveries' not in json.dumps(payload)
            assert payload.get('inbox', []) == []
            assert payload['own_command_history'] == []
    assert len(runs) == 16 and all(run == runs[0] for run in runs)


def test_observation_and_job_schemas_reject_private_identity_fields():
    with pytest.raises(TypeError):
        ij.Detection('a', 'cyan', LEFT, item_id='cyan_1')
    with pytest.raises(TypeError):
        ij.IdentityJobs('r1', [order()], FakeTargetExecutor(), inventory={})
    with pytest.raises(TypeError):
        ij.IdentityJobs('r1', [order()], FakeTargetExecutor(), peer_deliveries=[])
    signature = inspect.signature(ij.IdentityJobs)
    assert 'condition' not in signature.parameters
    assert 'world' not in signature.parameters


def test_inputs_and_returned_claims_do_not_share_mutable_state():
    orders = [order()]
    f = Fixture(orders)
    orders[0]['count'] = 1
    f.view(detection())
    result = f.gate.claim('order-1')
    result['item_ids'].append('forged')
    assert f.gate.claim('order-1')['required_count'] == 2
    assert f.gate.claim('order-1')['item_ids'] == []
