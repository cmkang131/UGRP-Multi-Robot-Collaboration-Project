"""Real scheduler/client/budget, prerecorded replies, stub links; no physics/network."""
import copy
import email.message
import hashlib
import io
import json
import socket
import sys
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError

import pytest
from PIL import Image

from harness import pair_llm_contract as contract
from harness import pair_llm_live as live
from harness import s4_llm_host as s4
from harness import s4_llm_inputs as si
from harness import zone_map_schematic as maps
from harness import zone_study_llm_driver as llm
from harness import zone_study_prompts_ko as pk
from harness.pair_llm_stop_adapter import unknown_belief
from harness.zone_main_budget import MainStudyBudget
from harness.zone_send_ledger import completion_body
from harness.zone_study_contract import ContractViolation
from harness.zone_study_inputs import belief_skeleton
from harness.zone_study_integration import ModelAdapter, OwnFrame

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = json.loads((ROOT / 'tests/fixtures/s4_llm_replies.json').read_text())


@pytest.fixture(autouse=True)
def no_external_work(monkeypatch):
    for name in ('mujoco', 'torch', 'torchvision', 'sim.multi_masterpi_production'):
        monkeypatch.setitem(sys.modules, name, None)
    monkeypatch.setattr(socket.socket, 'connect', lambda *a: pytest.fail('network forbidden'))
    monkeypatch.setattr(socket.socket, 'connect_ex', lambda *a: pytest.fail('network forbidden'))
    monkeypatch.setattr(llm, 'live_proxy', lambda *a, **kw: pytest.fail('live proxy forbidden'))
    from harness.vision_loc_client import VisionWorkerClient
    monkeypatch.setattr(VisionWorkerClient, '__init__', lambda *a, **kw: pytest.fail('worker forbidden'))


@pytest.fixture(scope='module')
def setup_data():
    scenario = json.loads((ROOT / 'configs/zone_study_dev/dev_s1lite.json').read_text())
    return scenario, maps.map_bundle(scenario['map_id'], landmark_detail='none')


class StubController:
    def __init__(self):
        self.refix_hook_events, self.decisions = [], []

    def own_belief(self, now):
        return unknown_belief()

    def carry_decision(self, choice, now):
        self.decisions.append(('carry_decision', choice, now))
        return {'accepted': True}

    def post_look_decision(self, choice, now):
        self.decisions.append(('post_look_decision', choice, now))
        return {'accepted': True}


class StubLink:
    def __init__(self, rid):
        self.robot_id, self.now, self.active = rid, 0., None
        self.calls, self.call_ref = [], None
        buf = io.BytesIO()
        Image.new('RGB', (8, 8), {'r1': 'red', 'r2': 'green', 'r3': 'blue'}[rid]).save(buf, 'JPEG')
        self.jpeg = buf.getvalue()
        self.sha = hashlib.sha256(self.jpeg).hexdigest()

    def clock(self):
        return self.now

    def frame_at(self, t):
        return OwnFrame(int(t * 10), t, self.jpeg, self.sha)

    def belief(self):
        return belief_skeleton()

    def job(self):
        return self.active

    def call(self, api, *args):
        self.calls.append((api, args))
        if api in ('deliver', 'pair_carry'):
            self.active = {'kind': api, 'order_id': args[0], 'job_id': self.robot_id + '-job'}
        elif api == 'abort':
            self.active = None
        arguments = {'order_id': args[0], 'target_ref': args[1]} if api in ('deliver', 'pair_carry') else {}
        return {'robot_id': self.robot_id, 'api': api, 'sim_s': self.now, 'action_id': self.robot_id + '-act',
                'arguments': arguments, 'accepted': True, 'rejected_reason': None,
                'job_id': self.active['job_id'] if self.active else None, 'local_state': 'command_issued'}


class RecordedWire:
    def __init__(self, *, scripts=None, fault_at=None, finish_reason='stop'):
        self.scripts = copy.deepcopy(scripts or {r: ['claim_' + r] for r in s4.routing.ROBOTS})
        self.requests, self.responses = [], []
        self.fault_at, self.finish_reason = fault_at, finish_reason

    def __call__(self, request, *, timeout=None):
        self.requests.append(bytes(request.data))
        if len(self.requests) == self.fault_at:
            headers = email.message.Message()
            headers['Retry-After'] = '30'
            raise HTTPError(request.full_url, 429, 'rate limit', headers, io.BytesIO(b'{"error":"quota"}'))
        body = json.loads(request.data)
        user = next(part['text'] for part in body['messages'][-1]['content'] if part['type'] == 'text')
        payload = json.loads(user)
        queue = self.scripts.setdefault(payload['robot_id'], [])
        reply = copy.deepcopy(FIXTURE['responses'][queue.pop(0) if queue else 'continue'])
        reply['request_id'] = payload['request_id']
        raw = completion_body(json.dumps(reply), usage=FIXTURE['usage'], model='fixture-model')
        parsed = json.loads(raw)
        parsed['choices'][0]['finish_reason'] = self.finish_reason
        raw = json.dumps(parsed).encode()
        self.responses.append(raw)
        return io.BytesIO(raw)


class StubS3Link(StubLink):
    """Published #394 OwnLink contract at e4b72aaf, with no runtime/provider."""
    def __init__(self, rid):
        super().__init__(rid)
        self.s3_calls = []

    def belief(self):
        return {'x_m': 1., 'y_m': 2., 'yaw_rad': 0., 'std_xy_m': .1} if self.robot_id == 'r3' else super().belief()

    def call(self, api, *args):
        self.s3_calls.append((api, args))
        if self.robot_id == 'r3':
            assert api == 'deliver' and args == ('order-1', 'A')
            super().call(api, *args)
            return {'accepted': True, 'robot_id': 'r3', 'api': api, 'local_state': 'command_issued',
                    'rejected_reason': None, 'order_id': 'order-1'}
        partner = 'r2' if self.robot_id == 'r1' else 'r1'
        role = 'end_neg' if self.robot_id == 'r1' else 'end_pos'
        assert api == 'pair_carry' and args == ('order-5', 'B', partner, role)
        ack = super().call(api, *args[:3])
        ack['arguments']['order_id'] = 'cargoX'
        return dict(ack, public_order_id='order-5', executor_order_alias='cargoX')


def make_host(tmp_path, setup_data, *, arm='no_comm', wire=None, s3_links=False, origin_s=0.):
    scenario, bundle = setup_data
    inner = {r: (StubS3Link if s3_links else StubLink)(r) for r in s4.routing.ROBOTS}
    for link in inner.values():
        link.now = origin_s
    controllers = {r: StubController() for r in si.PAIR}
    own = {r: SimpleNamespace(robot_id=r, _pair=SimpleNamespace(controller=c)) for r, c in controllers.items()}
    links = {r: (s4.S3Link if s3_links else s4.Link)(inner[r], condition=arm, executor=own.get(r),
                                                   origin_s=origin_s) for r in inner}
    budget = adapter = None
    if arm != 'rule':
        budget = MainStudyBudget.create(tmp_path / 'budget.sqlite')
        budget.register_cohort('s4-fixture', token_cap=1100000, unknown_usage_charge_tokens=12000,
                               prereg_sha256='f' * 64, source={'test_only': True})
        budget.start_run('s4-fixture-run', cohort_id='s4-fixture', bundle_id=s4.VERSION,
                         bundle_sha256='e' * 64, record={'test_only': True})
        profile = contract.driver_profile()
        ledger = live.PairLiveLedger(store_dir=tmp_path / 'wire', budget=budget, run_key='s4-fixture-run',
                                     profile=profile, wire=wire or RecordedWire(), pacer=SimpleNamespace(wait=lambda: None))
        adapter = ModelAdapter(llm.client_factory(profile), ledger)
    host = s4.Host(scenario, condition=arm, links=links, seed=601, map_bundle=bundle, model_adapter=adapter,
                   horizon_s=120., code_sha='a' * 40)
    return host, inner, controllers, budget


def advance(host, inner, start, end):
    # Logical scheduler clock ONLY. Stub links do not move, render or simulate.
    for tick in range(round(start * 10) + 1, round(end * 10) + 1):
        for rid, link in inner.items():
            link.now = tick / 10 + (host.links[rid].origin_s if isinstance(host.links[rid], s4.S3Link) else 0.)
        host.step_to(tick / 10)


@pytest.mark.parametrize('arm', s4.CONDITIONS)
@pytest.mark.parametrize('s3_links', [False, True])
def test_three_own_claims_route_on_one_host(tmp_path, setup_data, arm, s3_links):
    host, inner, controllers, _ = make_host(tmp_path, setup_data, arm=arm, s3_links=s3_links,
                                           origin_s=1.3 if s3_links else 0.)
    host.begin()
    advance(host, inner, 0, 20)
    assert inner['r1'].calls == [('pair_carry', ('order-5', 'B', 'r2'))]
    assert inner['r2'].calls == [('pair_carry', ('order-5', 'B', 'r1'))]
    assert inner['r3'].calls == [('deliver', ('order-1', 'A'))]
    assert all(c.refix_llm_attached is (arm != 'rule') for c in controllers.values())
    if arm == 'rule':
        assert host.trial is None
    else:
        assert host.trial.actors == ('r1', 'r2', 'r3')
        assert host.trial.send_ledger._owner is host.trial.scheduler
        assert len(host.trial.send_ledger.entries) == 3
        if s3_links:
            assert all(row['reset_offset_s'] == 1.3 for row in host.trial.dispatch_log)
            solo_request = next(row for row in host.trial.requests if row['robot'] == 'r3')
            assert json.loads(solo_request['user'])['self_belief'] == belief_skeleton()
            assert 'cargoX' not in json.dumps(host.trial._history)
    if s3_links:
        assert inner['r1'].s3_calls == [('pair_carry', ('order-5', 'B', 'r2', 'end_neg'))]
        assert inner['r2'].s3_calls == [('pair_carry', ('order-5', 'B', 'r1', 'end_pos'))]
        assert inner['r3'].s3_calls == [('deliver', ('order-1', 'A'))]


def test_s3_stop_clock_and_unpublished_apis(tmp_path, setup_data):
    host, inner, controllers, _ = make_host(tmp_path, setup_data, s3_links=True, origin_s=1.3)
    link = host.links['r1']
    adapter = link.stop_adapter
    adapter.controller()
    adapter.window.on_event(dict(event='pair_progress', sim_s=1.3,
        detail={'kind': 'carry_stop_reached', 'decide_at_s': 11.3, 'latch_until_s': 10.3}), origin_s=1.3)
    inner['r1'].now = 2.3
    assert link.call('carry_decision', 'set_down', window_ref=adapter.window.reference(1.))['accepted']
    assert controllers['r1'].decisions == [('carry_decision', 'set_down', 2.3)]
    assert not inner['r1'].s3_calls
    for rid, api in [('r1', 'abort'), ('r2', 'look_around'), ('r3', 'abort')]:
        ack = host.links[rid].call(api, 'release_requested') if api == 'abort' else host.links[rid].call(api)
        assert not ack['accepted'] and ack['rejected_reason'] == 'S3_API_UNAVAILABLE'
        assert not inner[rid].s3_calls


def test_text_image_hashes_usage_latency_and_durable_budget(tmp_path, setup_data):
    wire = RecordedWire()
    host, inner, _, budget = make_host(tmp_path, setup_data, wire=wire)
    host.begin()
    advance(host, inner, 0, 20)
    host.finish(20)
    result = host.save(tmp_path / 'evidence')
    assert result['status'] == 'FINISHED' and result['physical_verified'] is False
    assert result['live'] is False and result['model_usage']['requests'] == 3
    assert result['model_usage']['tokens_prompt'] == 3 * 3100
    assert result['model_usage']['tokens_completion'] == 3 * 70
    assert result['model_usage']['tokens_complete'] is True
    assert len(result['response_wall_s']) == 3
    assert all(t >= 0 for t in result['response_wall_s'])
    rows = live.live_records(host.trial.send_ledger)['rows']
    for row, request, response in zip(rows, wire.requests, wire.responses):
        assert (tmp_path / 'wire' / row['request_path']).read_bytes() == request
        assert (tmp_path / 'wire' / row['response_path']).read_bytes() == response
        assert hashlib.sha256(request).hexdigest() == row['body_sha256']
        assert hashlib.sha256(response).hexdigest() == row['response_sha256']
        assert len(row['images']) == 2 and row['latency_ms'] >= 0
    for row in host.trial.requests:
        assert pk.verify_archived_request(row) == []
        assert s4.pair.billing.billing_problems(row) == []
        payload = json.loads(row['user'])
        assert payload['order_sheet']['team_size'] == 3
        assert payload['own_rgb_refs'][0]['sha256'] == inner[row['robot']].sha
        assert 'inbox' not in payload
        assert 'eval' not in payload and 'robot_spawns' not in str(payload)
        assert 'pose_m' not in str(payload) and 'physical_success' not in str(payload)
    requests = budget.requests('s4-fixture-run')
    assert len(requests) == 3 and all(r['total_tokens'] == 3170 for r in requests)
    images = json.loads((tmp_path / 'evidence/image_sha256.json').read_text())
    assert len(images) == 3 and all(len(r['images']) == 2 for r in images)
    # JSON arrays preserve tuple contents, but decode as lists.
    assert json.loads((tmp_path / 'evidence/scheduler_ledger.json').read_text()) == json.loads(
        json.dumps(host.trial.scheduler.ledger))
    assert json.loads((tmp_path / 'evidence/unsent_calls.json').read_text()) == []
    assert json.loads((tmp_path / 'evidence/transport_errors.json').read_text()) == []
    manifest = json.loads((tmp_path / 'evidence/artifacts.sha256.json').read_text())
    for name, sha in manifest.items():
        assert hashlib.sha256((tmp_path / 'evidence' / name).read_bytes()).hexdigest() == sha
    with pytest.raises(FileExistsError):
        host.save(tmp_path / 'evidence')


def test_peer_nl_reaches_third_robot_channel_but_no_comm_rejects_messages(tmp_path, setup_data):
    scripts = {'r1': ['claim_r1'], 'r2': ['claim_r2'], 'r3': ['peer_r3']}
    host, inner, _, _ = make_host(tmp_path / 'peer', setup_data, arm='peer_nl', wire=RecordedWire(scripts=scripts))
    host.begin()
    advance(host, inner, 0, 25)
    assert len(host.trial.channel.inbox('r1', now_sim_s=25)) == 1
    assert not host.trial.channel.inbox('r2', now_sim_s=25)
    assert 'r3' in host.trial.channel.inbox('r1', now_sim_s=25)[0]['sender']
    closed, closed_inner, _, _ = make_host(tmp_path / 'closed', setup_data, wire=RecordedWire(scripts=scripts))
    closed.begin()
    advance(closed, closed_inner, 0, 25)
    assert closed_inner['r3'].calls == []
    assert closed.trial.requests[-1]['status'] == 'invalid_json'
    assert not closed.trial.channel.inbox('r1', now_sim_s=25)


@pytest.mark.parametrize('fault_at', [1, 2, 3])
def test_429_latches_rate_limit_without_later_posts_or_actions(tmp_path, setup_data, fault_at):
    wire = RecordedWire(fault_at=fault_at)
    host, inner, _, budget = make_host(tmp_path, setup_data, wire=wire)
    with pytest.raises(live.RateLimited):
        host.begin()
        advance(host, inner, 0, 25)
    assert len(wire.requests) == fault_at
    assert not any(link.calls for link in inner.values())
    with pytest.raises(live.RateLimited):
        host.step_to(30)
    with pytest.raises(live.RateLimited):
        host.finish(30)
    result = host.save(tmp_path / 'failed')
    assert result['failure_label'] == 'RATE_LIMIT' and result['failure_class'] == 'infra:API'
    assert result['status'] == 'FAILED' and result['model_usage']['requests'] == fault_at
    assert len(wire.requests) == fault_at and len(budget.requests('s4-fixture-run')) == fault_at
    row = live.live_records(host.trial.send_ledger)['rows'][-1]
    assert row['http_status'] == 429 and row['error_response']['retry_after'] == '30'
    assert (tmp_path / 'wire' / row['error_response']['path']).read_bytes() == b'{"error":"quota"}'
    assert len(row['images']) == 2
    for name in ('scheduler_ledger', 'unsent_calls', 'transport_errors'):
        state = host.trial.scheduler.ledger if name == 'scheduler_ledger' else getattr(host.trial.scheduler, name)
        assert json.loads((tmp_path / 'failed' / f'{name}.json').read_text()) == json.loads(json.dumps(state))


def test_non_normal_completion_keeps_usage_but_executes_nothing(tmp_path, setup_data):
    host, inner, _, budget = make_host(tmp_path, setup_data, wire=RecordedWire(finish_reason='length'))
    with pytest.raises(Exception, match='no successful model response'):
        host.begin()
        advance(host, inner, 0, 20)
    assert not any(link.calls for link in inner.values())
    assert budget.usage('s4-fixture')['known_tokens'] > 0


@pytest.mark.parametrize('kind,choice', [('carry_decision', 'set_down'), ('post_look_decision', 'regrasp')])
def test_stop_decisions_bind_to_original_window(tmp_path, setup_data, kind, choice):
    host, inner, controllers, _ = make_host(tmp_path, setup_data)
    link = host.links['r1']
    adapter = link.stop_adapter
    adapter.controller()
    detail = ({'kind': 'carry_stop_reached', 'decide_at_s': 10., 'latch_until_s': 9.}
              if kind == 'carry_decision' else {'kind': 'relook_result', 'window_until_s': 10.})
    event = dict(robot_id='r1', event='pair_progress', sim_s=0., detail=detail)
    adapter.window.on_event(event, origin_s=0.)
    ref = adapter.window.reference(0.)
    inner['r1'].now = 1.
    assert link.call(kind, choice, window_ref=ref)['accepted']
    assert controllers['r1'].decisions == [(kind, choice, 1.)]
    adapter.window.on_event(event, origin_s=0.)
    assert link.call(kind, choice, window_ref=ref)['rejected_reason'] == 'DEADLINE_PASSED'
    inner['r1'].now = 11.
    assert link.call(kind, choice, window_ref=adapter.window.serial)['accepted'] is False
    assert len(controllers['r1'].decisions) == 1


def test_pair_hook_reply_uses_same_trial_and_ledger(tmp_path, setup_data):
    wire = RecordedWire(scripts={'r1': ['carry'], 'r2': ['post_look'], 'r3': ['claim_r3']})
    host, inner, controllers, _ = make_host(tmp_path, setup_data, wire=wire)
    for rid in si.PAIR:
        inner[rid].active = {'kind': 'pair_carry', 'order_id': 'order-5', 'job_id': rid + '-job'}
        adapter = host.links[rid].stop_adapter
        adapter.controller()
        kind = 'carry_stop_reached' if rid == 'r1' else 'relook_result'
        detail = dict(kind=kind, decide_at_s=10., latch_until_s=9.) if rid == 'r1' else dict(kind=kind, window_until_s=10.)
        adapter.window.on_event(dict(event='pair_progress', sim_s=0., detail=detail), origin_s=0.)
    host.begin()
    advance(host, inner, 0, 20)
    assert len(host.trial.send_ledger.entries) == 3
    assert {r['api'] for r in host.trial.dispatch_log} == {'carry_decision', 'post_look_decision', 'deliver'}
    for row in host.trial.dispatch_log:
        if row['actor'] in si.PAIR:
            assert row['ack']['accepted'], row
            assert controllers[row['actor']].decisions


def test_rejects_foreign_executor_and_rule_model_adapter(tmp_path, setup_data):
    with pytest.raises(ContractViolation, match='own executor'):
        s4.Link(StubLink('r1'), condition='no_comm', executor=SimpleNamespace(robot_id='r2'))
    with pytest.raises(ContractViolation, match='r3'):
        s4.Link(StubLink('r3'), condition='no_comm', executor=SimpleNamespace(robot_id='r1'))
    host, _, _, _ = make_host(tmp_path, setup_data, arm='rule')
    scenario, bundle = setup_data
    with pytest.raises(ContractViolation, match='rule has no model adapter'):
        s4.Host(scenario, condition='rule', links=host.links, seed=601, map_bundle=bundle,
                model_adapter=object())


@pytest.mark.parametrize('corrupt', ['peer_frame', 'truth_belief', 'pair_truth'])
def test_bad_own_input_is_rejected_before_that_robots_post(tmp_path, setup_data, corrupt):
    wire = RecordedWire()
    host, inner, controllers, _ = make_host(tmp_path, setup_data, wire=wire)
    if corrupt == 'peer_frame':
        inner['r1'].sha = inner['r2'].sha
    elif corrupt == 'truth_belief':
        inner['r1'].belief = lambda: {'ground_truth_pose': [1, 2, 3]}
    else:
        controllers['r1'].own_belief = lambda now: dict(unknown_belief(), partner_pose=[1, 2])
    host.begin()
    advance(host, inner, 0, 20)
    # The established scheduler refunds an unsent invalid input, records its
    # error, and lets independent robots continue. It does not rethrow it.
    assert inner['r1'].calls == []
    assert {r['actor'] for r in host.trial.send_ledger.entries} == {'r2', 'r3'}
    scheduler = host.trial.scheduler
    rejected = {cid: row for cid, row in scheduler.ledger.items() if row['actor'] == 'r1'}
    assert rejected
    unsent = {row['call_id']: row for row in scheduler.unsent_calls if row['actor'] == 'r1'}
    errors = {row['call_id']: row for row in scheduler.transport_errors if row['actor'] == 'r1'}
    assert rejected.keys() == unsent.keys() == errors.keys()
    for cid, row in rejected.items():
        assert row['status'] == 'not_sent' and row['attempts'] == 0
        assert row['ledger_sends'] == host.trial.send_ledger.sends(cid) == 0
        assert unsent[cid]['error'] and unsent[cid]['error'] == errors[cid]['error']
    assert controllers['r1'].decisions == []
    host.finish(20)
    sends = len(wire.requests)
    host.save(tmp_path / 'rejected')
    for name in ('scheduler_ledger', 'unsent_calls', 'transport_errors'):
        state = scheduler.ledger if name == 'scheduler_ledger' else getattr(scheduler, name)
        assert json.loads((tmp_path / 'rejected' / f'{name}.json').read_text()) == json.loads(json.dumps(state))
    assert len(wire.requests) == sends
    assert inner['r1'].calls == controllers['r1'].decisions == []


def test_s3_own_hook_event_opens_only_that_robots_window(tmp_path, setup_data):
    host, inner, _, _ = make_host(tmp_path, setup_data)
    for link in host.links.values():
        if link.stop_adapter:
            link.stop_adapter.controller()
    event = dict(robot_id='r1', event='pair_progress', sim_s=2., job_kind='pair_carry',
                 job_id='r1-job', scheduler_trigger=None,
                 detail={'kind': 'carry_stop_reached', 'decide_at_s': 12., 'latch_until_s': 11.})
    host.on_executor_event(event, at_s=2.)
    assert host.links['r1'].stop_adapter.window.is_open(2.)
    assert not host.links['r2'].stop_adapter.window.is_open(2.)
    assert host.links['r3'].stop_adapter is None


def test_stale_window_reply_through_scheduler_cannot_reach_new_stop(tmp_path, setup_data):
    wire = RecordedWire(scripts={'r1': ['carry'], 'r2': ['claim_r2'], 'r3': ['claim_r3']})
    host, inner, controllers, _ = make_host(tmp_path, setup_data, wire=wire)
    inner['r1'].active = {'kind': 'pair_carry', 'order_id': 'order-5', 'job_id': 'r1-job'}
    adapter = host.links['r1'].stop_adapter
    adapter.controller()
    event = dict(event='pair_progress', sim_s=0.,
                 detail={'kind': 'carry_stop_reached', 'decide_at_s': 10., 'latch_until_s': 9.})
    adapter.window.on_event(event, origin_s=0.)
    host.begin()
    assert len(wire.requests) == 3
    adapter.window.on_event(event, origin_s=0.)  # another stop, after the request snapshot
    advance(host, inner, 0, 20)
    row = next(row for row in host.trial.dispatch_log if row['actor'] == 'r1')
    assert row['ack']['rejected_reason'] == 'DEADLINE_PASSED'
    assert controllers['r1'].decisions == []
