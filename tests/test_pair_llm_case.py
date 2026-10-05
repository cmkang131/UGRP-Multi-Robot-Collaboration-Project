"""The pair LLM case loop on a fake physics owner: routing, gating, ledger, images, cost, evaluator, rule parity.
No physics, network or real model; every model reply comes from a stub behind the real proxy completer."""
import hashlib
import json
import re
from pathlib import Path

import pytest

from harness import pair_llm_contract as contract
from harness import pair_llm_inputs as pi
from harness import zone_final_pair_contract as c
from harness import zone_study_prompts_ko as pk
from harness.pair_llm_stub import StubModel, claim_action, scripted
from tests.pair_llm_fakes import (FakeBackend, FakeRuntime, ReadyRuntime, delivered_beam, offline_only,  # noqa: F401
                                  run_arm)


def rows(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def requests_of(out):
    return rows(Path(out) / 'llm' / 'requests.jsonl')


def user(row):
    return json.loads(row['user'])


@pytest.fixture(scope='module')
def peer_run(tmp_path_factory):
    """Real GatedHighRuntime + blind provider; enough SIM time for two v4-prompt reply rounds."""
    tmp = tmp_path_factory.mktemp('peer')
    result, out, model = run_arm(tmp, 'peer_nl', cap_s=14.)
    return result, out, model


# --------------------------------------------------------------------------- routing between r1 and r2

def test_messages_route_between_r1_and_r2_and_only_to_the_partner(peer_run):
    result, out, _ = peer_run
    assert result['status'] == 'COLLECTED_UNQUALIFIED' and result['failure'] is None
    sent = [r for r in rows(out / 'llm' / 'language.jsonl') if r['accepted']]
    assert sorted({r['sender'] for r in sent}) == ['r1', 'r2'] and len(sent) == 4
    by_robot = {'r1': [], 'r2': []}
    for row in requests_of(out):
        body = user(row)
        for envelope in body.get('inbox', ()):
            assert envelope['recipients'] == [body['robot_id']]
            assert envelope['sender'] == ('r2' if body['robot_id'] == 'r1' else 'r1')
            by_robot[body['robot_id']].append(envelope['message_id'])
        assert body['channel']['can_send_to'] == [('r2' if body['robot_id'] == 'r1' else 'r1')]
    assert by_robot['r1'] and by_robot['r2']
    channel = json.loads((out / 'llm' / 'channel.json').read_text())
    assert channel['sent'] == 4 and channel['accepted_messages'] == 4 and channel['rejected'] == 0
    assert channel['received'] == {'r1': 2, 'r2': 2}
    # delivery is not instant: a message is first seen by the partner AFTER the SIM cost of the sender's call
    first_seen = {}
    for row in requests_of(out):
        for envelope in user(row).get('inbox', ()):
            first_seen.setdefault(envelope['message_id'], row['sim_s'])
    created = {m['message_id']: m['created_at_sim_s'] for row in requests_of(out)
               for m in user(row).get('inbox', ())}
    assert all(first_seen[mid] > created[mid] for mid in created)


def test_the_language_report_is_recorded_for_every_message_and_is_not_a_gate(peer_run):
    result, out, _ = peer_run
    language = result['metrics']['language']
    assert language['messages'] == 4 and language['hangul_ratio_ge_0_9'] == 4 and language['share'] == 1.0
    assert language['gate'] is False and 'korean' not in result['metrics']
    assert all(r['hangul_ratio'] >= .9 and r['flags'] == [] for r in rows(out / 'llm' / 'language.jsonl'))
    assert result['metrics']['messages'] == {'sent': 4, 'accepted': 4, 'rejected': 0}


def test_an_english_message_is_delivered_but_flagged(tmp_path):
    english = {'recipients': ['r2'], 'reply_to': None, 'text': 'Starting the carry now, please follow me.'}
    model = StubModel(scripted({('r1', 0): (claim_action('r1', {'order_id': 'cargoX', 'destination_zone': 'B'}),
                                            [english])}))
    result, out, _ = run_arm(tmp_path, 'peer_nl', model, cap_s=12.)
    flagged = [r for r in rows(out / 'llm' / 'language.jsonl') if r['sender'] == 'r1']
    assert flagged[0]['accepted'] is True and flagged[0]['korean'] is False and flagged[0]['flags']
    assert flagged[0]['hangul_ratio'] < .9
    inbox = [m for row in requests_of(out) for m in user(row).get('inbox', ()) if m['sender'] == 'r1']
    assert inbox and inbox[0]['body']['text'] == english['text']
    language = result['metrics']['language']
    assert language['hangul_ratio_ge_0_9'] < language['messages'] and language['flagged'] >= 1
    assert language['gate'] is False
    # delivered, costed, never rejected for its language
    assert result['metrics']['messages']['rejected'] == 0 and flagged[0]['rejection'] is None


def test_no_comm_has_no_channel_and_a_message_is_refused_at_validation(tmp_path):
    talky = scripted({('r1', 0): (claim_action('r1', {'order_id': 'cargoX', 'destination_zone': 'B'}),
                                  [{'recipients': ['r2'], 'reply_to': None, 'text': '같이 시작합시다.'}])})
    result, out, model = run_arm(tmp_path, 'no_comm', StubModel(talky), cap_s=12.)
    assert all('inbox' not in user(row) and user(row)['channel']['can_send_to'] == [] for row in requests_of(out))
    statuses = {row['call_id']: row['status'] for row in requests_of(out)}
    assert statuses['call-0001-r1'] == 'invalid_json'          # a non-empty messages list is a protocol error
    assert result['metrics']['messages']['accepted'] == 0
    claims = json.loads((out / 'llm' / 'claim_gate.json').read_text())
    assert not [r for r in claims['log'] if r['robot_id'] == 'r1' and r['event'] == 'claim_released'
                and r['call_ref'] == 'call-0001-r1']
    clean, out2, _ = run_arm(tmp_path, 'no_comm', None, cap_s=12., name='no_comm_clean')
    assert clean['metrics']['messages'] == {'sent': 0, 'accepted': 0, 'rejected': 0}
    assert clean['metrics']['claims']['released'] == 2


# --------------------------------------------------------------------------- claims gate team.start

def test_a_released_claim_is_what_lets_team_start_run_and_the_blind_controller_stays_gated(peer_run):
    result, out, _ = peer_run
    claims = result['metrics']['claims']
    assert claims['released'] == 2 and claims['submitted'] == 0 and claims['accepted'] == 0
    assert claims['refusals']['r1'] and set(claims['refusals']['r1']) == {'SELF_UNCERTAIN'}
    record = json.loads((out / 'student_record.json').read_text())
    assert record['pair'] == [] and 'claim_gate' in record           # no pair session ever started


def test_with_an_available_pose_the_claim_starts_the_scripted_pair_skill(tmp_path):
    result, out, _ = run_arm(tmp_path, 'no_comm', cap_s=14., runtime_factory=ReadyRuntime)
    claims = result['metrics']['claims']
    assert claims['released'] == claims['submitted'] == claims['accepted'] == 2
    gate = json.loads((out / 'llm' / 'claim_gate.json').read_text())['log']
    released = {r['robot_id']: r for r in gate if r['event'] == 'claim_released'}
    submitted = {r['robot_id']: r for r in gate if r['event'] == 'claim_submitted'}
    assert set(released) == set(submitted) == {'r1', 'r2'}
    for rid in released:
        assert submitted[rid]['sim_s'] >= released[rid]['sim_s'] and submitted[rid]['call_ref'] == released[rid]['call_ref']
    events = json.loads((out / 'student_record.json').read_text())['robots']
    for rid, robot in events.items():
        started = [e for e in robot['events'] if e['event'] == 'job_started' and e['job_kind'] == 'pair_carry']
        assert started and started[0]['sim_s'] - 1. >= released[rid]['sim_s']     # backend reset is 1 s of SIM time
    assert len(json.loads((out / 'student_record.json').read_text())['pair']) == 1


def test_a_model_that_never_claims_keeps_the_scripted_start_closed(tmp_path):
    never = StubModel(scripted({}, default=lambda rid, i, body, sys_text: ({'kind': 'continue'}, [])))
    result, out, _ = run_arm(tmp_path, 'no_comm', never, cap_s=14., runtime_factory=ReadyRuntime)
    assert result['metrics']['claims']['released'] == 0 and result['metrics']['claims']['submitted'] == 0
    gate = json.loads((out / 'llm' / 'claim_gate.json').read_text())
    assert gate['refused_without_permit']['r1'] > 0 and gate['refused_without_permit']['r2'] > 0
    assert json.loads((out / 'student_record.json').read_text())['pair'] == []
    # the C-rule arm with the same readiness submits on the first idle tick: plain Runtime, no gate
    from harness.zone_final_pair_runtime import Runtime

    class ReadyPlain(Runtime):
        def on_frames(self, now, frames):
            super().on_frames(now, frames)
            from harness.owncam_pose_source import PoseReport
            for own in self.actors.values():
                if own.job is None:
                    own.last_report = PoseReport(now, True, x_m=0., y_m=0., yaw_rad=0., std_xy_m=.01,
                                                 std_yaw_rad=.01, source=own.pose.source)
                    own.gate.state = 'ok'

    rule, rout, _ = run_arm(tmp_path, 'rule', cap_s=14., runtime_factory=ReadyPlain)
    assert len(json.loads((rout / 'student_record.json').read_text())['pair']) == 1
    assert 'claim_gate' not in json.loads((rout / 'student_record.json').read_text())


def test_rule_arm_uses_the_unmodified_runtime_and_the_llm_arms_the_gated_one(tmp_path, monkeypatch):
    from harness import zone_pair_highpose_runtime as runtime_module
    created = []
    original = runtime_module.Runtime

    class Recording(original):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            created.append(type(self))

    monkeypatch.setattr(runtime_module, 'Runtime', Recording)
    result, out, _ = run_arm(tmp_path, 'rule', cap_s=3.)
    assert created == [Recording] and result['metrics']['model_calls'] == 0
    assert result['model_kind'] == 'none' and not (out / 'llm').exists()
    assert 'claim_gate' not in json.loads((out / 'student_record.json').read_text())


# --------------------------------------------------------------------------- rule arm = the existing runtime path

def test_rule_arm_issues_exactly_the_commands_of_the_v88_runner(tmp_path):
    from harness.pair_llm_case import run_pair_case
    from scripts import run_final_pair_v3 as v88
    cal = {'path': 'unused', 'sha256': '0' * 64}
    case = c.cases('carry')[0]
    assert case['sim_cap_s'] == 120.
    old_backends, new_backends = [], []

    def old_factory(*a, **kw):
        old_backends.append(FakeBackend(*a, **kw))
        return old_backends[-1]

    def new_factory(*a, **kw):
        new_backends.append(FakeBackend(*a, **kw))
        return new_backends[-1]

    old_runtime = []
    original = FakeRuntime.__init__

    def tracking(self, *a, **kw):
        original(self, *a, **kw)
        old_runtime.append(self)

    FakeRuntime.__init__ = tracking
    try:
        b88 = {**c.bundle(case['map_id'], 'carry'), 'case': case}
        v88.run_case(b88, tmp_path / 'v88', seed=911, backend_factory=old_factory, runtime_factory=FakeRuntime,
                     calibration=cal['path'], calibration_sha=cal['sha256'])
        bundle = contract.bundle('rule', source_sha='0' * 40)
        result = run_pair_case(bundle, tmp_path / 'pair', condition='rule', seed=911, backend_factory=new_factory,
                               calibration=cal['path'], calibration_sha=cal['sha256'], cap_s=120.,
                               runtime_factory=FakeRuntime)
    finally:
        FakeRuntime.__init__ = original
    old, new = old_backends[0], new_backends[0]
    assert result['status'] == 'COLLECTED_UNQUALIFIED' and old.actions and old.actions == new.actions
    assert old.samples == new.samples and old.captures == new.captures == 2401
    assert old_runtime[0].commands == old_runtime[1].commands
    assert new.now == new.deadline == old.now == old.deadline == 121.


def test_every_arm_has_the_same_case_cap_and_a_larger_one_is_refused(tmp_path):
    from harness.pair_llm_case import run_pair_case
    caps = {}
    for condition in contract.CONDITIONS:
        result, _, _ = run_arm(tmp_path, condition, cap_s=3., name=f'cap-{condition}')
        caps[condition] = (result['case_sim_cap_s'], result['registered_case_cap_s'], result['reset_sim_cap_s'],
                           result['case_sim_s'])
    assert set(caps.values()) == {(3., 900., 5., 3.)}
    bundle = contract.bundle('rule', source_sha='0' * 40)
    with pytest.raises(ValueError):
        run_pair_case(bundle, tmp_path / 'toolong', condition='rule', seed=1, backend_factory=FakeBackend,
                      calibration='x', calibration_sha='0' * 64, cap_s=901.)
    with pytest.raises(ValueError):
        run_pair_case(bundle, tmp_path / 'wrongarm', condition='no_comm', seed=1, backend_factory=FakeBackend,
                      calibration='x', calibration_sha='0' * 64, cap_s=3.)


# --------------------------------------------------------------------------- ledger, wire images, archive

def test_the_ledger_preserves_every_request_and_response_byte_for_byte(peer_run):
    result, out, _ = peer_run
    ledger = out / 'llm' / 'ledger'
    requests = sorted(ledger.glob('*-request.json'))
    responses = sorted(ledger.glob('*-response.json'))
    wire = rows(out / 'llm' / 'wire_wall.jsonl')
    assert len(requests) == len(responses) == len(wire) == result['metrics']['http_attempts'] > 3
    for path, row in zip(requests, wire):
        assert hashlib.sha256(path.read_bytes()).hexdigest() == row['request_sha256']
        assert row['request_bytes'] == path.stat().st_size and row['error'] is None
    book = json.loads((out / 'llm' / 'send_ledger.json').read_text())
    assert len(book['entries']) == len(requests)
    assert all(json.loads(p.read_text()).get('choices') for p in responses)
    # every archived request re-hashes from disk, and the exact system/user text is the one that was sent
    archive = requests_of(out)
    assert len(archive) == len(requests) and result['llm_artifacts']['archived_request_problems'] == []
    assert all(pk.verify_archived_request(row) == [] for row in archive)
    for path, row in zip(requests, archive):
        body = json.loads(path.read_text())
        assert body['messages'][0]['content'] == row['system']
        user_text = next(p['text'] for p in body['messages'][1]['content'] if p['type'] == 'text')
        assert user_text == row['user']


def test_audit_c_the_wire_carries_exactly_two_images_own_frame_and_map_figure(peer_run):
    result, out, _ = peer_run
    registered = json.loads((out / 'bundle.json').read_text())
    frames = {p.stem for p in (out / 'llm' / 'request_images').glob('*.jpg')}
    map_sha = hashlib.sha256((out / 'llm' / 'map_figure.png').read_bytes()).hexdigest()
    seen_requests = 0
    for path, row in zip(sorted((out / 'llm' / 'ledger').glob('*-request.json')), requests_of(out)):
        images = pi.wire_images(path.read_bytes())
        assert [(i['label'], i['mime']) for i in images] == [('CURRENT OWN WRIST RGB', 'image/jpeg'),
                                                             ('STATIC MAP FIGURE', 'image/png')]
        assert images[0]['sha256'] in frames and images[1]['sha256'] == map_sha
        own = user(row)['own_rgb_refs'][-1]
        assert own['sha256'] == images[0]['sha256'] and own['ref'].startswith(f'own-{user(row)["robot_id"]}-')
        assert [r['sha256'] for r in row['image_refs']] == [i['sha256'] for i in images]
        seen_requests += 1
    assert seen_requests == result['metrics']['http_attempts']
    assert map_sha == user(requests_of(out)[0])['static_map']['schematic_ref']['png_sha256']
    assert registered['condition'] == 'peer_nl'


def test_each_request_image_is_the_senders_own_camera(peer_run):
    result, out, _ = peer_run
    for row in requests_of(out):
        body = user(row)
        rid = body['robot_id']
        ref = body['own_rgb_refs'][-1]
        assert ref['kind'] == 'own_wrist_rgb' and f'own-{rid}-' in ref['ref']
        assert all(f'own-{rid}-' in r['ref'] for r in body['own_rgb_refs'])


# --------------------------------------------------------------------------- cost and metrics

def test_sim_cost_is_charged_and_wall_time_is_recorded_apart(peer_run):
    result, out, _ = peer_run
    metrics = result['metrics']
    calls = rows(out / 'llm' / 'inputs.jsonl')
    assert metrics['model_cost_sim_s'] > 0 and metrics['input_tokens'] > 0 and metrics['output_tokens'] > 0
    assert metrics['response_wall_s']['requests'] == metrics['http_attempts']
    study = json.loads((out / 'llm' / 'study_config.json').read_text())
    assert study['cost_params']['version'] == 'zone_sim_cost.v1' and study['cost_params']['provisional'] is True
    assert study['model_settings']['model'] == 'stub-pair-llm-v1' and study['model_settings']['temperature'] == 0.
    assert study['prompt_version'] == 'ugrp.pair_llm_prompts_ko.v4' and study['robots'] == ['r1', 'r2']
    # the thinking charge moves the SIM clock; wall latency never does (the stub's wall latency is ~0 but nonzero)
    scheduler = rows(out / 'llm' / 'scheduler_events.jsonl')
    starts = [e for e in scheduler if e.get('kind') == 'call_start']
    assert len(starts) == len(calls) and result['trial']['calls'] == len(calls) == metrics['model_calls']
    assert metrics['command_count_total'] == sum(metrics['command_count'].values()) > 0
    assert set(metrics) >= {'success', 'end_sim_s', 'command_count', 'model_calls', 'response_wall_s', 'input_tokens',
                            'output_tokens', 'language', 'messages', 'self_sabotage', 'claims', 'model_cost_sim_s'}


def test_rule_arm_pays_no_model_cost_and_records_the_same_metric_keys(tmp_path):
    rule, _, _ = run_arm(tmp_path, 'rule', cap_s=3.)
    llm, _, _ = run_arm(tmp_path, 'no_comm', cap_s=3., name='nc3')
    assert rule['metrics']['model_calls'] == 0 and rule['metrics']['model_cost_sim_s'] == 0.
    assert set(rule['metrics']) <= set(llm['metrics'])


# --------------------------------------------------------------------------- evaluator is separate

def test_success_comes_only_from_the_separate_evaluator(tmp_path):
    delivered = lambda b, o, seed: FakeBackend(b, o, seed=seed, beam=delivered_beam)    # noqa: E731
    results = {}
    for condition in contract.CONDITIONS:
        win, wout, _ = run_arm(tmp_path, condition, cap_s=12., name=f'win-{condition}', backend=delivered)
        lose, lout, _ = run_arm(tmp_path, condition, cap_s=12., name=f'lose-{condition}')
        results[condition] = (win['metrics']['success'], lose['metrics']['success'])
        verdict = json.loads((wout / 'eval_only' / 'verdict.json').read_text())
        assert verdict['success_provisional'] is True and verdict['judge_status'].startswith('PROVISIONAL')
        assert win['metrics']['success_source'] == 'pair_llm_eval.judge'
    assert set(results.values()) == {(True, False)}
    # no model request ever contained a verdict, a success flag or a beam position
    for condition in ('no_comm', 'peer_nl'):
        text = ''.join(row['user'] + row['system'] for row in requests_of(tmp_path / f'win-{condition}'))
        assert not re.search(r'success|verdict|beam_xyz|trajectory|physical', text)


def test_a_host_error_keeps_partial_records_and_classifies_enospc(tmp_path):
    import errno

    class FullDisk(FakeBackend):
        def capture(self):
            if self.captures >= 3:
                raise OSError(errno.ENOSPC, 'No space left on device')
            return super().capture()

    result, out, _ = run_arm(tmp_path, 'no_comm', cap_s=12., backend=FullDisk)
    assert result['status'] == 'HOST_ERROR' and result['failure']['class'] == 'ENOSPC'
    assert result['protocol_complete'] is False and (out / 'result.json').is_file()
    assert (out / 'bundle.json').is_file() and (out / 'llm' / 'requests.jsonl').is_file()
    assert result['metrics']['success'] is False


# --------------------------------------------------------------------------- CLI and registration

def test_cli_plans_without_running_and_refuses_missing_calibration_and_unfrozen_source(capsys):
    from scripts import run_pair_llm as cli
    args = ['--condition', 'peer_nl', '--expected-source-sha', 'a' * 40, '--output',
            '/Users/changmin/projects/ugrp/outputs/never-created', '--synthetic-plumbing-calibration']
    assert cli.main(args) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan['execution_started'] is False and plan['model_kind'] == 'stub' and plan['research_result'] is False
    assert plan['execution_bundle_id'] == 'zone-pair-llm-v100' and plan['workflow_version'] == '3.12.0'
    assert not Path('/Users/changmin/projects/ugrp/outputs/never-created').exists()
    assert cli.main(args + ['--live', '--cap-s', '60']) == 0       # a live PLAN touches no network and no proxy
    assert json.loads(capsys.readouterr().out)['model_kind'] == 'live'
    with pytest.raises(ValueError):
        cli.main(['--condition', 'rule', '--expected-source-sha', 'a' * 40, '--output', '/x'])
    with pytest.raises(ValueError):
        cli.main(args[:-1] + ['--cap-s', '901', '--synthetic-plumbing-calibration'])
    with pytest.raises(ValueError, match='expected source SHA'):      # nothing runs on an unfrozen source
        cli.main(args + ['--execute'])


def test_workflow_is_registered_in_the_managed_catalog():
    from sim import workflow_manager as wm
    row, _ = wm._row(contract.ROOT, contract.WORKFLOW_ID)
    assert row['version'] == '3.12.0' and row['entry'] == 'scripts/run_pair_llm.py'
    plan = wm.plan(contract.ROOT, contract.WORKFLOW_ID, ['--condition', 'no_comm', '--expected-source-sha', 'a' * 40])
    assert not plan['execution_started'] and plan['command'][1:3] == ['-m', 'scripts.run_pair_llm']
    assert contract.WORKFLOW == 'configs/simulation_workflows.d/pair_llm_v100.json'
    assert 'stub' in json.dumps(json.loads((contract.ROOT / contract.WORKFLOW).read_text()))
