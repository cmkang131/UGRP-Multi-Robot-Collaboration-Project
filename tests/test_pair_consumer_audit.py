"""Tests for the owned consumer-side apply-call ledger.

Scope (2026-11-05, UGRP-Pair, branch ugrp/pair-consumer-audit-20261105T2046Z)
---------------------------------------------------------------------------
What is verified here (CPU only, no model, no simulator, no head worker, no
physics, no network):

* the owned consumer runner really wires the consumer ledger into its S3
  apply hook (the hook function of the owned runner file is EXECUTED with a
  fake apply callable and fake ports, not merely declared);
* the wrapped call happens EXACTLY ONCE per robot and the arguments are the
  pinned ones: ``(port, command, now, previous)``;
* the ledger copies the command and the prior BEFORE the call, so the legacy
  quirk (the runner overwrites ``previous[rid]`` with the command right after
  the apply) cannot hide the real prior in the ledger -- while the original
  metric is left untouched;
* the return value and an exception are recorded as two separate facts, and
  neither is dressed up as environment application, an acknowledgement or
  motion;
* the robot's next own observation is linked to the apply that preceded it,
  through the producer's observation row and its ``linked_issue_seq``;
* an apply that no observation answers is recorded explicitly at close;
* the producer file is consumed READ ONLY and is verified before it is
  trusted: a foreign run id, a foreign robot, a missing issue, a duplicated
  row, an edited row and a reused issue are all refused;
* a repeated identical command at the same time is still distinguishable;
* the consumer output is created exclusively and an existing file is refused;
* an aliased apply callable is refused;
* consumer audit OFF is the default, creates no ledger and behaves exactly
  like the PR642 runner;
* the real CLI in ``--prepare-only`` mode plans the ledger but does NOT create
  it.

Only files created by the test itself are modified.  The pinned trees, the
PR642 runner and the producer module are read-only inputs.
"""
from __future__ import annotations

import argparse
import ast
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest


def test_source_pin_is_checked_before_module_code_executes(runner, tmp_path):
    marker = tmp_path / 'executed'
    source = tmp_path / 'changed_helper.py'
    source.write_text('from pathlib import Path\nPath(%r).write_text("executed")\n'
                      % str(marker))
    with pytest.raises(RuntimeError, match='hash drift before import'):
        runner.load_module(source, 'changed_helper_test', expected_sha='0' * 64)
    assert not marker.exists()


@pytest.mark.parametrize('case', ['duplicate_issue', 'wrong_first_number',
                                  'wrong_command_digest', 'duplicate_observation'])
def test_refresh_checks_the_whole_new_batch(consumer, producer_mod, tmp_path, case):
    path = tmp_path / 'producer.jsonl'
    writer = ProducerWriter(producer_mod, path)
    writer.issue(consumer, ROBOT, make_command(),
                 issue_number=2 if case == 'wrong_first_number' else 1)
    if case == 'duplicate_issue':
        writer.issue(consumer, ROBOT, make_command(2.0), issue_number=1)
    if case == 'duplicate_observation':
        obs = make_observation('same')
        writer.observation(consumer, ROBOT, obs)
        writer.observation(consumer, ROBOT, obs)
    writer.close()
    if case == 'wrong_command_digest':
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        rows[0]['command']['wheels'][0] = 0.35
        rows[0]['record_digest'] = consumer.digest(
            {k: v for k, v in rows[0].items() if k != 'record_digest'})
        path.write_text('\n'.join(json.dumps(row) for row in rows) + '\n')
    with pytest.raises(consumer.ConsumerAuditError):
        consumer.ProducerIndex(path, run_id=RUN_ID)


def test_failed_new_batch_commits_no_reader_state(consumer, producer_mod, tmp_path):
    path = tmp_path / 'producer.jsonl'
    reader = consumer.ProducerIndex(path, run_id=RUN_ID)
    writer = ProducerWriter(producer_mod, path)
    writer.issue(consumer, ROBOT, make_command(), issue_number=1)
    writer.issue(consumer, ROBOT, make_command(2), issue_number=1)
    writer.close()
    with pytest.raises(consumer.ConsumerAuditError):
        reader.refresh()
    assert reader.rows == 0
    assert reader.issues == {}
    assert reader.observations == {}
    assert reader._seen_seq == -1
    assert reader.invalid

REPO_ROOT = Path(__file__).resolve().parents[1]
CONSUMER_HELPER = REPO_ROOT / 'harness' / 'pair_consumer_audit.py'
PRODUCER_AUDIT = REPO_ROOT / 'harness' / 'pair_worker_audit.py'
OWNED_RUNNER = (REPO_ROOT / 'experiments' / '2026-11-05-pair-consumer-audit' /
                'run_cpu_joint_e2e_consumer_audit.py')
PR642_RUNNER = (REPO_ROOT / 'experiments' / '2026-11-05-pair-runner-wire' /
                'run_cpu_joint_e2e_audit_wire.py')

RUN_ID = 'consumertest01'
EPISODE_ID = 'ep-consumer-01'
ROBOT = 'r1'


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, str(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope='module')
def consumer():
    return load_module(CONSUMER_HELPER, 'ugrp_test_pair_consumer_audit')


@pytest.fixture(scope='module')
def producer_mod():
    return load_module(PRODUCER_AUDIT, 'ugrp_test_pair_producer_audit')


@pytest.fixture(scope='module')
def runner():
    return load_module(OWNED_RUNNER, 'ugrp_test_pair_consumer_runner')


# ------------------------------------------------------------------ fixtures
def make_command(t=1.0):
    return {'t': float(t), 'wheels': [0.0, 0.0, 0.0, 0.0],
            'duration_s': [0.0, 0.0, 0.0, 0.0],
            'pwm': {'1': 1500, '3': 1500, '4': 1500, '5': 1500, '6': 1500}}


def make_observation(sample_id, t=1.0):
    return {'schema': 'ugrp.grasp_act.student.v6', 'robot_id': ROBOT,
            'sample_id': sample_id, 't': float(t), 'skill': 'grasp',
            'object_kind': 'long_beam', 'role': 'blue', 'destination_zone': 'none',
            'rgb': [], 'issued': [make_command(t)]}


class FakePort:
    """A fake actuator port: it records the calls, it actuates nothing."""

    def __init__(self):
        self.calls = []

    def _actuator_state(self):
        return {'applied_calls': len(self.calls)}

    def apply(self, command, now):
        self.calls.append((command, now))


def fake_apply(port, cmd, now, previous):
    """The fake apply callable: it returns, it does not actuate anything."""
    port.apply(cmd, now)
    return {'accepted': True, 'echo': cmd}


def failing_apply(port, cmd, now, previous):
    raise RuntimeError('fake apply refused the command')


class ProducerWriter:
    """Writes a producer-shaped audit file with the real producer sink."""

    def __init__(self, producer_module, path, run_id=RUN_ID):
        self.module = producer_module
        self.path = Path(path)
        self.run_id = run_id
        self.sink = producer_module.AuditSink(run_id=run_id,
                                              output_root=str(self.path.parent),
                                              filename=self.path.name)
        self.seqs = {}

    def issue(self, consumer, robot_id, command, issue_number=1, origin='unknown'):
        normalized = consumer.normalize_command(command)
        row = {'kind': 'issue_command', 'robot_id': robot_id, 't': command['t'],
               'command_digest': consumer.digest(normalized),
               'command': normalized, 'origin': origin,
               'origin_source': ('declared by the caller' if origin != 'unknown'
                                 else 'unknown; values never imply an origin'),
               'supersedes_observation_seq': None, 'issue_number': issue_number}
        seq = self.sink.write(row)
        self.seqs['issue:%s:%s' % (robot_id, issue_number)] = seq
        return seq

    def observation(self, consumer, robot_id, observation, linked_issue_seq=None):
        row = {'kind': 'observation', 'robot_id': robot_id,
               'sample_id': observation['sample_id'], 't': observation['t'],
               'observation_digest': consumer.digest(observation),
               'window_digest': consumer.digest(observation.get('issued', [])),
               'issued_count': len(observation.get('issued', [])),
               'linked_issue_seq': linked_issue_seq}
        seq = self.sink.write(row)
        self.seqs['obs:%s' % observation['sample_id']] = seq
        return seq

    def close(self):
        self.sink.close()


def make_ledger(consumer, tmp_path, producer_path, *, robots=(ROBOT,), run_id=RUN_ID,
                episode_id=EPISODE_ID):
    ledger = consumer.ConsumerLedger(run_id=run_id, episode_id=episode_id,
                                     output_root=str(tmp_path / 'consumer'),
                                     producer_audit_path=producer_path,
                                     robots=list(robots))
    ledger.attach_apply(fake_apply)
    return ledger


def read_rows(ledger):
    rows = []
    for line in ledger.sink.path.read_text(encoding='utf-8').splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def kinds(ledger, kind):
    return [row for row in read_rows(ledger) if row.get('kind') == kind]


# ------------------------------------------------------------------ the hook
def test_owned_runner_wires_the_hook_into_s3():
    """The S3 block of the owned runner really calls the hook (AST check)."""
    tree = ast.parse(OWNED_RUNNER.read_text(encoding='utf-8'))
    main = next(node for node in tree.body
                if isinstance(node, ast.FunctionDef) and node.name == 'main')
    calls = [node for node in ast.walk(main)
             if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Name)
             and node.func.id == 'apply_issued_commands']
    assert calls, 'the S3 block does not call apply_issued_commands'
    # the original teacher_apply call must not survive as a direct call
    direct = [node for node in ast.walk(main)
              if isinstance(node, ast.Call)
              and isinstance(node.func, ast.Name)
              and node.func.id == 'teacher_apply']
    assert not direct, 'teacher_apply is still called directly in main()'


def test_hook_calls_apply_exactly_once_with_the_pinned_arguments(runner, consumer,
                                                                 tmp_path, producer_mod):
    producer_path = tmp_path / 'audit' / ('pair-audit-%s.jsonl' % RUN_ID)
    writer = ProducerWriter(producer_mod, producer_path)
    command = make_command(1.0)
    issue_seq = writer.issue(consumer, ROBOT, command)
    writer.close()

    ledger = make_ledger(consumer, tmp_path, producer_path)
    port = FakePort()
    prior = make_command(0.5)
    previous = {ROBOT: prior}
    issued = {ROBOT: {'command': command}}

    applied = runner.apply_issued_commands(
        apply_callable=fake_apply, roles=(ROBOT,), issued=issued,
        ports={ROBOT: port}, now=1.0, previous=previous, ledger=ledger, tick=3)

    # exactly one call, with the pinned argument shape
    assert len(port.calls) == 1
    assert port.calls[0][0] is command
    # the ledger copied the command and the prior BEFORE the call
    call_rows = kinds(ledger, 'apply_call')
    assert len(call_rows) == 1
    row = call_rows[0]
    assert row['command'] == command
    assert row['prior_command'] == prior
    assert row['prior_is_a_copy'] is True
    assert row['producer_issue']['seq'] == issue_seq
    assert row['producer_issue']['issue_number'] == 1
    # the outcome is the function return, and nothing more
    result_rows = kinds(ledger, 'apply_result')
    assert len(result_rows) == 1
    assert result_rows[0]['outcome'] == 'returned'
    assert result_rows[0]['returned'] == {'accepted': True, 'echo': command}
    assert result_rows[0]['apply_returned_is_only_the_function_return'] is True
    assert result_rows[0]['environment_applied'] == 'unknown'
    assert result_rows[0]['transmission_acknowledged'] == 'unknown'
    assert result_rows[0]['motion_observed'] == 'unknown'
    assert 'port_state' in result_rows[0]
    # the original metric is untouched: previous is still overwritten
    assert previous[ROBOT] is command
    assert applied[ROBOT]['command'] is command
    assert applied[ROBOT]['actuator_state'] == {'applied_calls': 1}


def test_hook_records_an_exception_separately(runner, consumer, tmp_path, producer_mod):
    producer_path = tmp_path / 'audit' / ('pair-audit-%s.jsonl' % RUN_ID)
    writer = ProducerWriter(producer_mod, producer_path)
    command = make_command(1.0)
    writer.issue(consumer, ROBOT, command)
    writer.close()

    ledger = make_ledger(consumer, tmp_path, producer_path)
    port = FakePort()
    with pytest.raises(RuntimeError):
        runner.apply_issued_commands(
            apply_callable=failing_apply, roles=(ROBOT,),
            issued={ROBOT: {'command': command}}, ports={ROBOT: port},
            now=1.0, previous={ROBOT: make_command(0.5)}, ledger=ledger, tick=0)
    assert port.calls == []
    results = kinds(ledger, 'apply_result')
    assert len(results) == 1
    assert results[0]['outcome'] == 'exception'
    assert results[0]['exception_type'] == 'RuntimeError'
    assert 'refused' in results[0]['exception']
    assert results[0]['environment_applied'] == 'unknown'
    assert 'returned' not in results[0]


def test_off_mode_creates_no_ledger_and_behaves_like_the_original(runner, tmp_path):
    """Without a ledger the hook is the original code path."""
    port = FakePort()
    command = make_command(2.0)
    previous = {ROBOT: make_command(1.0)}
    applied = runner.apply_issued_commands(
        apply_callable=fake_apply, roles=(ROBOT,),
        issued={ROBOT: {'command': command}}, ports={ROBOT: port},
        now=2.0, previous=previous, ledger=None, tick=1)
    assert len(port.calls) == 1
    assert previous[ROBOT] is command
    assert applied[ROBOT]['actuator_state'] == {'applied_calls': 1}
    assert list(tmp_path.iterdir()) == []


def test_consumer_audit_is_off_by_default(runner):
    source = OWNED_RUNNER.read_text(encoding='utf-8')
    assert '"--consumer-audit", choices=("off", "on"), default="off"' in source
    tree = ast.parse(source)
    args = [node for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == 'add_argument']
    consumer_args = [node for node in args
                     if any(isinstance(a, ast.Constant) and a.value == '--consumer-audit'
                            for a in node.args)]
    assert len(consumer_args) == 1


# ------------------------------------------------------------------ linking
def test_next_observation_is_linked_to_the_previous_apply(runner, consumer, tmp_path, producer_mod):
    producer_path = tmp_path / 'audit' / ('pair-audit-%s.jsonl' % RUN_ID)
    writer = ProducerWriter(producer_mod, producer_path)
    command = make_command(1.0)
    observation = make_observation('ep:0:%s' % ROBOT, 1.0)
    writer.observation(consumer, ROBOT, observation, linked_issue_seq=None)
    issue_seq = writer.issue(consumer, ROBOT, command)
    next_observation = make_observation('ep:1:%s' % ROBOT, 1.1)
    writer.observation(consumer, ROBOT, next_observation, linked_issue_seq=issue_seq)
    writer.close()

    ledger = make_ledger(consumer, tmp_path, producer_path)
    port = FakePort()
    # the runner order: the own observation of a tick is recorded BEFORE the
    # apply of that tick, so the first observation answers nothing.
    first = ledger.record_observation(ROBOT, observation=observation,
                                      rgb_sha256='a' * 64, tick=0)
    assert first is not None
    rows = kinds(ledger, 'observation_link')
    assert rows[0]['unanswered'] is True
    assert rows[0]['answers_apply_seq'] is None
    runner.apply_issued_commands(
        apply_callable=fake_apply, roles=(ROBOT,), issued={ROBOT: {'command': command}},
        ports={ROBOT: port}, now=1.0, previous={ROBOT: make_command(0.5)},
        ledger=ledger, tick=0)
    # the next own observation answers the apply
    ledger.record_observation(ROBOT, observation=next_observation,
                              rgb_sha256='b' * 64, tick=1)
    rows = kinds(ledger, 'observation_link')
    linked = rows[1]
    assert linked['unanswered'] is False
    assert linked['answers_apply_seq'] == kinds(ledger, 'apply_call')[0]['seq']
    assert linked['producer_observation']['linked_issue_seq'] == issue_seq
    assert linked['observation_digest_matches_producer'] is True
    assert linked['rgb_sha256'] == 'b' * 64


def test_observation_that_links_a_different_issue_is_refused(consumer, tmp_path, producer_mod):
    producer_path = tmp_path / 'audit' / ('pair-audit-%s.jsonl' % RUN_ID)
    writer = ProducerWriter(producer_mod, producer_path)
    command = make_command(1.0)
    issue_seq = writer.issue(consumer, ROBOT, command)
    other = writer.issue(consumer, ROBOT, make_command(2.0), issue_number=2)
    observation = make_observation('ep:1:%s' % ROBOT, 1.1)
    writer.observation(consumer, ROBOT, observation, linked_issue_seq=other)
    writer.close()

    ledger = make_ledger(consumer, tmp_path, producer_path)
    ledger.begin_apply(ROBOT, cmd=command, prior=make_command(0.5), now=1.0, tick=0)
    with pytest.raises(consumer.ConsumerAuditError):
        ledger.record_observation(ROBOT, observation=observation, tick=1)


def test_unanswered_apply_is_recorded_at_close(runner, consumer, tmp_path, producer_mod):
    producer_path = tmp_path / 'audit' / ('pair-audit-%s.jsonl' % RUN_ID)
    writer = ProducerWriter(producer_mod, producer_path)
    command = make_command(1.0)
    writer.issue(consumer, ROBOT, command)
    writer.close()

    ledger = make_ledger(consumer, tmp_path, producer_path)
    port = FakePort()
    runner.apply_issued_commands(
        apply_callable=fake_apply, roles=(ROBOT,), issued={ROBOT: {'command': command}},
        ports={ROBOT: port}, now=1.0, previous={ROBOT: make_command(0.5)},
        ledger=ledger, tick=0)
    ledger.close()
    unanswered = kinds(ledger, 'unanswered_apply')
    assert len(unanswered) == 1
    assert unanswered[0]['unanswered'] is True
    summary = kinds(ledger, 'run_summary')[0]
    assert summary['apply_calls'] == 1
    assert summary['apply_returned'] == 1
    assert summary['apply_exceptions'] == 0
    assert summary['observations_linked_to_an_apply'] == 0
    assert summary['environment_applied'].startswith('unknown')
    assert summary['port_state'] == 'not captured by this ledger'
    assert 'NOT a carry-success claim' in summary['scope']


# ------------------------------------------------------------------ refusals
def test_foreign_run_id_is_refused(consumer, tmp_path, producer_mod):
    producer_path = tmp_path / 'audit' / 'pair-audit-other-run.jsonl'
    writer = ProducerWriter(producer_mod, producer_path, run_id='someoneelsesrun')
    writer.issue(consumer, ROBOT, make_command(1.0))
    writer.close()
    # the refusal happens as soon as the producer file is read (fail closed)
    with pytest.raises(consumer.ConsumerAuditError):
        ledger = make_ledger(consumer, tmp_path, producer_path)
        ledger.begin_apply(ROBOT, cmd=make_command(1.0), prior=make_command(0.5),
                           now=1.0, tick=0)


def test_foreign_robot_is_refused(consumer, tmp_path, producer_mod):
    producer_path = tmp_path / 'audit' / ('pair-audit-%s.jsonl' % RUN_ID)
    writer = ProducerWriter(producer_mod, producer_path)
    writer.issue(consumer, ROBOT, make_command(1.0))
    writer.close()
    ledger = make_ledger(consumer, tmp_path, producer_path, robots=('r1', 'r2'))
    with pytest.raises(consumer.ConsumerAuditError):
        ledger.begin_apply('r2', cmd=make_command(1.0), prior=make_command(0.5),
                           now=1.0, tick=0)


def test_missing_producer_issue_is_refused(consumer, tmp_path, producer_mod):
    producer_path = tmp_path / 'audit' / ('pair-audit-%s.jsonl' % RUN_ID)
    writer = ProducerWriter(producer_mod, producer_path)
    writer.issue(consumer, ROBOT, make_command(5.0))
    writer.close()
    ledger = make_ledger(consumer, tmp_path, producer_path)
    with pytest.raises(consumer.ConsumerAuditError):
        ledger.begin_apply(ROBOT, cmd=make_command(1.0), prior=make_command(0.5),
                           now=1.0, tick=0)


def test_duplicated_producer_row_is_refused(consumer, tmp_path, producer_mod):
    producer_path = tmp_path / 'audit' / ('pair-audit-%s.jsonl' % RUN_ID)
    writer = ProducerWriter(producer_mod, producer_path)
    writer.issue(consumer, ROBOT, make_command(1.0))
    writer.close()
    lines = producer_path.read_text(encoding='utf-8').splitlines()
    producer_path.write_text('\n'.join(lines + [lines[-1]]) + '\n', encoding='utf-8')
    with pytest.raises(consumer.ConsumerAuditError):
        ledger = make_ledger(consumer, tmp_path, producer_path)
        ledger.begin_apply(ROBOT, cmd=make_command(1.0), prior=make_command(0.5),
                           now=1.0, tick=0)


def test_edited_producer_row_is_refused(consumer, tmp_path, producer_mod):
    producer_path = tmp_path / 'audit' / ('pair-audit-%s.jsonl' % RUN_ID)
    writer = ProducerWriter(producer_mod, producer_path)
    writer.issue(consumer, ROBOT, make_command(1.0))
    writer.close()
    rows = [json.loads(line) for line in
            producer_path.read_text(encoding='utf-8').splitlines() if line.strip()]
    rows[0]['command']['wheels'] = [0.4, 0.0, 0.0, 0.0]
    producer_path.write_text(
        '\n'.join(json.dumps(r, sort_keys=True, separators=(',', ':')) for r in rows) + '\n',
        encoding='utf-8')
    with pytest.raises(consumer.ConsumerAuditError):
        ledger = make_ledger(consumer, tmp_path, producer_path)
        ledger.begin_apply(ROBOT, cmd=make_command(1.0), prior=make_command(0.5),
                           now=1.0, tick=0)


def test_a_producer_issue_cannot_be_bound_twice(consumer, tmp_path, producer_mod):
    producer_path = tmp_path / 'audit' / ('pair-audit-%s.jsonl' % RUN_ID)
    writer = ProducerWriter(producer_mod, producer_path)
    writer.issue(consumer, ROBOT, make_command(1.0))
    writer.close()
    ledger = make_ledger(consumer, tmp_path, producer_path)
    ledger.begin_apply(ROBOT, cmd=make_command(1.0), prior=make_command(0.5),
                       now=1.0, tick=0)
    ledger.end_apply(ROBOT, outcome='returned', result=None)
    with pytest.raises(consumer.ConsumerAuditError):
        ledger.begin_apply(ROBOT, cmd=make_command(1.0), prior=make_command(0.5),
                           now=1.0, tick=1)


def test_repeated_identical_command_is_distinguished(consumer, tmp_path, producer_mod):
    """The same command at the same time keeps its order (issue 1, then 2)."""
    producer_path = tmp_path / 'audit' / ('pair-audit-%s.jsonl' % RUN_ID)
    writer = ProducerWriter(producer_mod, producer_path)
    command = make_command(1.0)
    first = writer.issue(consumer, ROBOT, command, issue_number=1)
    second = writer.issue(consumer, ROBOT, command, issue_number=2)
    first_observation = make_observation('ep:0:%s' % ROBOT, 1.0)
    writer.observation(consumer, ROBOT, first_observation, linked_issue_seq=None)
    second_observation = make_observation('ep:1:%s' % ROBOT, 1.0)
    writer.observation(consumer, ROBOT, second_observation, linked_issue_seq=first)
    writer.close()
    ledger = make_ledger(consumer, tmp_path, producer_path)
    ledger.record_observation(ROBOT, observation=first_observation, tick=0)
    seq_a = ledger.begin_apply(ROBOT, cmd=command, prior=make_command(0.5),
                                now=1.0, tick=0)
    ledger.end_apply(ROBOT, outcome='returned', result=None)
    ledger.record_observation(ROBOT, observation=second_observation, tick=1)
    seq_b = ledger.begin_apply(ROBOT, cmd=command, prior=make_command(0.5),
                                now=1.0, tick=1)
    ledger.end_apply(ROBOT, outcome='returned', result=None)
    rows = kinds(ledger, 'apply_call')
    assert rows[0]['producer_issue']['seq'] == first
    assert rows[1]['producer_issue']['seq'] == second
    assert rows[0]['producer_issue']['issue_number'] == 1
    assert rows[1]['producer_issue']['issue_number'] == 2
    assert seq_a != seq_b
    assert ledger.observations_linked == 1


def test_consumer_output_is_created_exclusively(consumer, tmp_path, producer_mod):
    producer_path = tmp_path / 'audit' / ('pair-audit-%s.jsonl' % RUN_ID)
    writer = ProducerWriter(producer_mod, producer_path)
    writer.issue(consumer, ROBOT, make_command(1.0))
    writer.close()
    ledger = make_ledger(consumer, tmp_path, producer_path)
    path = ledger.sink.path
    ledger.close()
    with pytest.raises(consumer.ConsumerAuditError):
        consumer.ConsumerSink(run_id=RUN_ID, episode_id=EPISODE_ID,
                              output_root=str(tmp_path / 'consumer'))


def test_an_aliased_apply_callable_is_refused(consumer, tmp_path, producer_mod):
    producer_path = tmp_path / 'audit' / ('pair-audit-%s.jsonl' % RUN_ID)
    writer = ProducerWriter(producer_mod, producer_path)
    writer.issue(consumer, ROBOT, make_command(1.0))
    writer.close()
    ledger = make_ledger(consumer, tmp_path, producer_path)
    with pytest.raises(consumer.ConsumerAuditError):
        ledger.attach_apply(failing_apply)


def test_a_partial_producer_tail_is_ignored(consumer, tmp_path, producer_mod):
    producer_path = tmp_path / 'audit' / ('pair-audit-%s.jsonl' % RUN_ID)
    writer = ProducerWriter(producer_mod, producer_path)
    command = make_command(1.0)
    writer.issue(consumer, ROBOT, command)
    writer.close()
    with open(producer_path, 'a', encoding='utf-8') as stream:
        stream.write('{"kind": "issue_command", "robot_id": "r1"')   # not flushed yet
    ledger = make_ledger(consumer, tmp_path, producer_path)
    seq = ledger.begin_apply(ROBOT, cmd=command, prior=make_command(0.5),
                              now=1.0, tick=0)
    assert seq is not None
    assert ledger.producer.rows == 1


def test_missing_producer_file_is_refused_at_binding_time(consumer, tmp_path):
    producer_path = tmp_path / 'audit' / ('pair-audit-%s.jsonl' % RUN_ID)
    ledger = make_ledger(consumer, tmp_path, producer_path)
    # the ledger itself is created before the producer writes anything
    assert ledger.sink.path.is_file()
    with pytest.raises(consumer.ConsumerAuditError):
        ledger.begin_apply(ROBOT, cmd=make_command(1.0), prior=make_command(0.5),
                           now=1.0, tick=0)


# ------------------------------------------------------------------ the plan
def test_plan_refuses_a_consumer_ledger_without_the_audited_worker(runner, tmp_path):
    args = argparse.Namespace(consumer_audit='on', consumer_output_root=None,
                              consumer_episode_id=None)
    selection = {'mode': 'off', 'audit_run_id': None, 'audit_output_root': None}
    with pytest.raises(SystemExit):
        runner.plan_consumer_ledger(args=args, out=tmp_path, worker_selection=selection)


def test_plan_off_creates_nothing(runner, tmp_path):
    args = argparse.Namespace(consumer_audit='off', consumer_output_root=None,
                              consumer_episode_id=None)
    selection = {'mode': 'on', 'audit_run_id': RUN_ID, 'audit_output_root': str(tmp_path)}
    plan = runner.plan_consumer_ledger(args=args, out=tmp_path, worker_selection=selection)
    assert plan['mode'] == 'off'
    assert plan['plan']['ledger_created'] is False
    assert list(tmp_path.iterdir()) == []


def test_plan_on_points_at_the_producer_audit_file(runner, tmp_path):
    args = argparse.Namespace(consumer_audit='on', consumer_output_root=None,
                              consumer_episode_id=None)
    selection = {'mode': 'on', 'audit_run_id': RUN_ID,
                 'audit_output_root': str(tmp_path / 'audit')}
    plan = runner.plan_consumer_ledger(args=args, out=tmp_path, worker_selection=selection)
    assert plan['mode'] == 'on'
    assert plan['plan']['producer_audit_path'] == str(
        tmp_path / 'audit' / ('pair-audit-%s.jsonl' % RUN_ID))
    assert plan['plan']['ledger_created'] is False


def test_the_real_cli_prepare_only_plans_but_does_not_create_the_ledger(tmp_path, runner):
    # This integration case uses the exact local research assets. Pure ledger
    # tests above remain runnable on CI without those external files.
    required = [Path(runner.CKPT) / 'model.safetensors', Path(runner.CONFIG),
                Path(runner.WORKER), Path(runner.HEADWORKER), Path(runner.HEAD_POLICY),
                Path(runner.ASTRA), Path(runner.TREE) / 'harness/pairact_r1_student.py']
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        pytest.skip('local pinned research assets unavailable: ' + ', '.join(missing))
    run_dir = tmp_path / 'run'
    argv = [sys.executable, str(OWNED_RUNNER), '--run-dir', str(run_dir),
            '--audit-worker', 'on', '--audit-run-id', 'cli-prepare-01',
            '--consumer-audit', 'on', '--prepare-only']
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=600)
    assert proc.returncode == 0, proc.stderr[-2000:]
    payload = json.loads(proc.stdout)
    assert payload['prepared'] is True
    assert payload['consumer_audit'] == 'on'
    assert payload['consumer_ledger_created'] is False
    plan = json.loads((run_dir / 'consumer-audit-plan.json').read_text(encoding='utf-8'))
    assert plan['ledger_created'] is False
    assert plan['run_id'] == 'cli-prepare-01'
    # no ledger file was created anywhere in the run directory
    assert not list(run_dir.rglob('pair-consumer-audit-*.jsonl'))
    prepare = json.loads((run_dir / 'prepare.json').read_text(encoding='utf-8'))
    assert prepare['executed'] is False
    assert prepare['model_forwards'] == 0
    assert prepare['worker_started'] is False
    assert prepare['mujoco_imported'] is False


def test_the_owned_copy_does_not_touch_the_pr642_runner():
    """The PR642 runner and the original stay read-only inputs."""
    assert PR642_RUNNER.is_file()
    source = PR642_RUNNER.read_text(encoding='utf-8')
    assert '--consumer-audit' not in source
    assert 'apply_issued_commands' not in source


# ================================================================== the fixes
# The seven counterexamples that the coordinator reproduced directly.  Every
# one of them must be refused now, and a refusal must not destroy evidence.
def test_counterexample_1_wrong_robot_observation_is_refused(consumer, tmp_path, producer_mod):
    """An observation of another robot must not answer this robot's apply."""
    producer_path = tmp_path / 'audit' / ('pair-audit-%s.jsonl' % RUN_ID)
    writer = ProducerWriter(producer_mod, producer_path)
    command = make_command(1.0)
    issue = writer.issue(consumer, ROBOT, command)
    observation = make_observation('sample-1', 2.0)
    observation['robot_id'] = 'r2'
    writer.observation(consumer, 'r2', observation, linked_issue_seq=issue)
    writer.close()

    ledger = make_ledger(consumer, tmp_path, producer_path)
    ledger.begin_apply(ROBOT, cmd=command, prior=make_command(0.5), now=1.0, tick=0)
    ledger.end_apply(ROBOT, outcome='returned', result=None)
    with pytest.raises(consumer.ConsumerAuditError):
        ledger.record_observation(ROBOT, observation=observation, tick=1)
    # the refusal did not count as a link and did not release the pending apply
    assert ledger.observations_linked == 0
    assert ledger.observations == 0
    ledger.close()
    assert len(kinds(ledger, 'unanswered_apply')) == 1


def test_counterexample_2_changed_observation_is_refused(consumer, tmp_path, producer_mod):
    """A body that differs from the producer row is not a link."""
    producer_path = tmp_path / 'audit' / ('pair-audit-%s.jsonl' % RUN_ID)
    writer = ProducerWriter(producer_mod, producer_path)
    command = make_command(1.0)
    issue = writer.issue(consumer, ROBOT, command)
    observation = make_observation('sample-1', 2.0)
    writer.observation(consumer, ROBOT, observation, linked_issue_seq=issue)
    writer.close()

    ledger = make_ledger(consumer, tmp_path, producer_path)
    ledger.begin_apply(ROBOT, cmd=command, prior=make_command(0.5), now=1.0, tick=0)
    ledger.end_apply(ROBOT, outcome='returned', result=None)
    changed = dict(observation)
    changed['skill'] = 'changed'
    with pytest.raises(consumer.ConsumerAuditError):
        ledger.record_observation(ROBOT, observation=changed, tick=1)
    assert ledger.observations_linked == 0
    assert ledger.observations == 0
    ledger.close()
    assert len(kinds(ledger, 'unanswered_apply')) == 1


def test_counterexample_3_out_of_order_issue_is_refused(consumer, tmp_path, producer_mod):
    """Issue 2 may not be bound while issue 1 is still unconsumed."""
    producer_path = tmp_path / 'audit' / ('pair-audit-%s.jsonl' % RUN_ID)
    writer = ProducerWriter(producer_mod, producer_path)
    first = make_command(1.0)
    second = make_command(2.0)
    writer.issue(consumer, ROBOT, first, issue_number=1)
    writer.issue(consumer, ROBOT, second, issue_number=2)
    writer.close()

    ledger = make_ledger(consumer, tmp_path, producer_path)
    # the second command must not be bound first
    with pytest.raises(consumer.ConsumerAuditError):
        ledger.begin_apply(ROBOT, cmd=second, prior=make_command(0.5), now=2.0, tick=0)
    assert ledger.apply_calls == 0
    # the first one binds exactly issue number 1
    ledger.begin_apply(ROBOT, cmd=first, prior=make_command(0.5), now=1.0, tick=0)
    ledger.end_apply(ROBOT, outcome='returned', result=None)
    assert kinds(ledger, 'apply_call')[0]['producer_issue']['issue_number'] == 1


def test_counterexample_4_an_edited_producer_prefix_is_refused(consumer, tmp_path, producer_mod):
    """A producer file that changed after it was read is not trusted again."""
    producer_path = tmp_path / 'audit' / ('pair-audit-%s.jsonl' % RUN_ID)
    writer = ProducerWriter(producer_mod, producer_path)
    command = make_command(1.0)
    writer.issue(consumer, ROBOT, command)
    writer.close()

    ledger = make_ledger(consumer, tmp_path, producer_path)
    assert ledger.producer.rows == 1
    # the same length, different bytes
    producer_path.write_text(
        producer_path.read_text(encoding='utf-8').replace('unknown', 'changed'),
        encoding='utf-8')
    with pytest.raises(consumer.ConsumerAuditError):
        ledger.begin_apply(ROBOT, cmd=command, prior=make_command(0.5), now=1.0, tick=0)
    assert ledger.apply_calls == 0
    # the reader is terminally invalid: it is not trusted again
    assert ledger.producer.invalid is True
    with pytest.raises(consumer.ConsumerAuditError):
        ledger.begin_apply(ROBOT, cmd=command, prior=make_command(0.5), now=1.0, tick=0)


def test_a_shrunken_producer_file_is_refused(consumer, tmp_path, producer_mod):
    producer_path = tmp_path / 'audit' / ('pair-audit-%s.jsonl' % RUN_ID)
    writer = ProducerWriter(producer_mod, producer_path)
    writer.issue(consumer, ROBOT, make_command(1.0))
    writer.close()
    ledger = make_ledger(consumer, tmp_path, producer_path)
    text = producer_path.read_text(encoding='utf-8')
    producer_path.write_text(text[:len(text) // 2], encoding='utf-8')
    with pytest.raises(consumer.ConsumerAuditError):
        ledger.begin_apply(ROBOT, cmd=make_command(1.0), prior=make_command(0.5),
                           now=1.0, tick=0)
    assert ledger.producer.invalid is True


def test_counterexample_5_duplicate_result_is_refused(consumer, tmp_path, producer_mod):
    """The outcome of an apply call is recorded exactly once."""
    producer_path = tmp_path / 'audit' / ('pair-audit-%s.jsonl' % RUN_ID)
    writer = ProducerWriter(producer_mod, producer_path)
    command = make_command(1.0)
    writer.issue(consumer, ROBOT, command)
    writer.close()
    ledger = make_ledger(consumer, tmp_path, producer_path)
    ledger.begin_apply(ROBOT, cmd=command, prior=make_command(0.5), now=1.0, tick=0)
    ledger.end_apply(ROBOT, outcome='returned', result=None)
    with pytest.raises(consumer.ConsumerAuditError):
        ledger.end_apply(ROBOT, outcome='returned', result=None)
    assert ledger.apply_calls == 1
    assert ledger.apply_returned == 1
    assert len(kinds(ledger, 'apply_result')) == 1


def test_counterexample_6_a_failed_observation_keeps_the_pending_apply(consumer, tmp_path,
                                                                       producer_mod):
    """A refused observation must not delete the unanswered-apply evidence."""
    producer_path = tmp_path / 'audit' / ('pair-audit-%s.jsonl' % RUN_ID)
    writer = ProducerWriter(producer_mod, producer_path)
    command = make_command(1.0)
    issue = writer.issue(consumer, ROBOT, command)
    observation = make_observation('sample-1', 2.0)
    writer.observation(consumer, ROBOT, observation, linked_issue_seq=99)
    writer.close()
    ledger = make_ledger(consumer, tmp_path, producer_path)
    ledger.begin_apply(ROBOT, cmd=command, prior=make_command(0.5), now=1.0, tick=0)
    ledger.end_apply(ROBOT, outcome='returned', result=None)
    with pytest.raises(consumer.ConsumerAuditError):
        ledger.record_observation(ROBOT, observation=observation, tick=1)
    ledger.close()
    unanswered = kinds(ledger, 'unanswered_apply')
    assert len(unanswered) == 1
    assert unanswered[0]['unanswered'] is True
    assert unanswered[0]['applies_to_seq'] == kinds(ledger, 'apply_call')[0]['seq']


def test_counterexample_7_an_absolute_filename_is_refused(consumer, tmp_path):
    with pytest.raises(consumer.ConsumerAuditError):
        consumer.ConsumerSink(run_id='x', episode_id='y',
                              output_root=str(tmp_path / 'intended'),
                              filename=str(tmp_path / 'escaped.jsonl'))
    assert not (tmp_path / 'escaped.jsonl').exists()


def test_a_filename_that_escapes_the_output_root_is_refused(consumer, tmp_path):
    with pytest.raises(consumer.ConsumerAuditError):
        consumer.ConsumerSink(run_id='x', episode_id='y',
                              output_root=str(tmp_path / 'intended'),
                              filename='../escaped.jsonl')
    assert not (tmp_path / 'escaped.jsonl').exists()


def test_the_sink_refuses_reserved_envelope_fields(consumer, tmp_path):
    sink = consumer.ConsumerSink(run_id='x', episode_id='y',
                                 output_root=str(tmp_path / 'consumer'))
    for field in ('schema', 'run_id', 'seq', 'claim', 'row_digest'):
        with pytest.raises(consumer.ConsumerAuditError):
            sink.write({'kind': 'x', field: 'hijacked'})
    sink.close()


def test_a_closed_ledger_refuses_every_call(consumer, tmp_path, producer_mod):
    producer_path = tmp_path / 'audit' / ('pair-audit-%s.jsonl' % RUN_ID)
    writer = ProducerWriter(producer_mod, producer_path)
    command = make_command(1.0)
    writer.issue(consumer, ROBOT, command)
    writer.close()
    ledger = make_ledger(consumer, tmp_path, producer_path)
    ledger.close()
    with pytest.raises(consumer.ConsumerAuditError):
        ledger.attach_apply(fake_apply)
    with pytest.raises(consumer.ConsumerAuditError):
        ledger.begin_apply(ROBOT, cmd=command, prior=make_command(0.5), now=1.0, tick=0)
    with pytest.raises(consumer.ConsumerAuditError):
        ledger.end_apply(ROBOT, outcome='returned', result=None)
    with pytest.raises(consumer.ConsumerAuditError):
        ledger.record_observation(ROBOT, observation=make_observation('s', 1.0))


def test_an_open_apply_cannot_be_overwritten(consumer, tmp_path, producer_mod):
    producer_path = tmp_path / 'audit' / ('pair-audit-%s.jsonl' % RUN_ID)
    writer = ProducerWriter(producer_mod, producer_path)
    command = make_command(1.0)
    writer.issue(consumer, ROBOT, command)
    writer.issue(consumer, ROBOT, make_command(2.0), issue_number=2)
    writer.close()
    ledger = make_ledger(consumer, tmp_path, producer_path)
    ledger.begin_apply(ROBOT, cmd=command, prior=make_command(0.5), now=1.0, tick=0)
    with pytest.raises(consumer.ConsumerAuditError):
        ledger.begin_apply(ROBOT, cmd=make_command(2.0), prior=make_command(0.5),
                           now=2.0, tick=1)
    assert ledger.apply_calls == 1
    ledger.end_apply(ROBOT, outcome='returned', result=None)


def test_an_unanswered_apply_blocks_the_next_apply(consumer, tmp_path, producer_mod):
    producer_path = tmp_path / 'audit' / ('pair-audit-%s.jsonl' % RUN_ID)
    writer = ProducerWriter(producer_mod, producer_path)
    writer.issue(consumer, ROBOT, make_command(1.0))
    writer.issue(consumer, ROBOT, make_command(2.0), issue_number=2)
    writer.close()
    ledger = make_ledger(consumer, tmp_path, producer_path)
    ledger.begin_apply(ROBOT, cmd=make_command(1.0), prior=make_command(0.5), now=1.0, tick=0)
    ledger.end_apply(ROBOT, outcome='returned', result=None)
    with pytest.raises(consumer.ConsumerAuditError):
        ledger.begin_apply(ROBOT, cmd=make_command(2.0), prior=make_command(0.5),
                           now=2.0, tick=1)
    assert ledger.apply_calls == 1


def test_a_non_finite_or_backwards_time_is_refused(consumer, tmp_path, producer_mod):
    producer_path = tmp_path / 'audit' / ('pair-audit-%s.jsonl' % RUN_ID)
    writer = ProducerWriter(producer_mod, producer_path)
    writer.issue(consumer, ROBOT, make_command(1.0))
    writer.close()
    ledger = make_ledger(consumer, tmp_path, producer_path)
    for bad in (float('nan'), float('inf'), '1.0', True, None):
        with pytest.raises(consumer.ConsumerAuditError):
            ledger.begin_apply(ROBOT, cmd=make_command(1.0), prior=make_command(0.5),
                               now=bad, tick=0)
    assert ledger.apply_calls == 0
    ledger.begin_apply(ROBOT, cmd=make_command(1.0), prior=make_command(0.5), now=2.0, tick=0)
    with pytest.raises(consumer.ConsumerAuditError):
        ledger.begin_apply(ROBOT, cmd=make_command(1.0), prior=make_command(0.5),
                           now=1.0, tick=1)


def test_a_producer_row_with_a_string_sequence_is_refused(consumer, tmp_path, producer_mod):
    producer_path = tmp_path / 'audit' / ('pair-audit-%s.jsonl' % RUN_ID)
    writer = ProducerWriter(producer_mod, producer_path)
    writer.issue(consumer, ROBOT, make_command(1.0))
    writer.close()
    rows = [json.loads(line) for line in
            producer_path.read_text(encoding='utf-8').splitlines() if line.strip()]
    rows[0]['seq'] = str(rows[0]['seq'])
    body = {k: v for k, v in rows[0].items() if k != 'record_digest'}
    rows[0]['record_digest'] = consumer.digest(body)
    producer_path.write_text(
        '\n'.join(json.dumps(r, sort_keys=True, separators=(',', ':')) for r in rows) + '\n',
        encoding='utf-8')
    with pytest.raises(consumer.ConsumerAuditError):
        make_ledger(consumer, tmp_path, producer_path)


def test_a_producer_row_with_a_boolean_sequence_is_refused(consumer, tmp_path, producer_mod):
    producer_path = tmp_path / 'audit' / ('pair-audit-%s.jsonl' % RUN_ID)
    writer = ProducerWriter(producer_mod, producer_path)
    writer.issue(consumer, ROBOT, make_command(1.0))
    writer.close()
    rows = [json.loads(line) for line in
            producer_path.read_text(encoding='utf-8').splitlines() if line.strip()]
    rows[0]['seq'] = True
    body = {k: v for k, v in rows[0].items() if k != 'record_digest'}
    rows[0]['record_digest'] = consumer.digest(body)
    producer_path.write_text(
        '\n'.join(json.dumps(r, sort_keys=True, separators=(',', ':')) for r in rows) + '\n',
        encoding='utf-8')
    with pytest.raises(consumer.ConsumerAuditError):
        make_ledger(consumer, tmp_path, producer_path)


def test_a_failed_call_leaves_the_ledger_untouched(consumer, tmp_path, producer_mod):
    """A refused call changes no counter, no pending state and no binding."""
    producer_path = tmp_path / 'audit' / ('pair-audit-%s.jsonl' % RUN_ID)
    writer = ProducerWriter(producer_mod, producer_path)
    command = make_command(1.0)
    writer.issue(consumer, ROBOT, command)
    writer.close()
    ledger = make_ledger(consumer, tmp_path, producer_path)
    before_rows = len(read_rows(ledger))
    with pytest.raises(consumer.ConsumerAuditError):
        ledger.begin_apply(ROBOT, cmd=make_command(9.0), prior=make_command(0.5),
                           now=1.0, tick=0)
    assert ledger.apply_calls == 0
    assert ledger.apply_returned == 0
    assert ledger.observations == 0
    assert ledger.observations_linked == 0
    assert ledger._pending == {}
    assert ledger._consumed == set()
    assert len(read_rows(ledger)) == before_rows
    # the very same issue can still be bound afterwards
    ledger.begin_apply(ROBOT, cmd=command, prior=make_command(0.5), now=1.0, tick=0)
    assert ledger.apply_calls == 1


# ================================================================== lifecycle
class FakeClient:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class FakeLedger:
    def __init__(self, fail=False):
        self.closed = False
        self.fail = fail

    def close(self):
        if self.fail:
            raise RuntimeError('fake ledger close failed')
        self.closed = True


@pytest.mark.parametrize('fail', [False, True])
def test_scope_cleans_up_exactly_once_on_success_or_failure(runner, fail):
    calls = []

    class Client:
        def close(self):
            calls.append('client')
            raise ValueError('cleanup failed')

    class Ledger:
        def close(self):
            calls.append('ledger')

    res = {'errors': []}

    def run():
        with runner.owned_worker_scope(res=res, ledger=Ledger()) as owned:
            owned['client'] = Client()
            if fail:
                raise RuntimeError('original body failure')

    if fail:
        with pytest.raises(RuntimeError, match='original body failure'):
            run()
    else:
        run()
    assert calls == ['client', 'ledger']
    assert 'worker client close failed' in res['errors'][0]
    tree = ast.parse(OWNED_RUNNER.read_text())
    main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'main')
    assert not any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                   and n.func.attr == 'close' for n in ast.walk(main))


def test_apply_error_is_preserved_when_error_recording_fails(runner):
    class Ledger:
        def begin_apply(self, *args, **kwargs):
            pass

        def end_apply(self, *args, **kwargs):
            raise ValueError('ledger failed')

    with pytest.raises(RuntimeError, match='fake apply refused') as exc:
        runner.apply_issued_commands(apply_callable=failing_apply, roles=(ROBOT,),
            issued={ROBOT: {'command': make_command()}}, ports={ROBOT: FakePort()},
            now=1.0, previous={ROBOT: make_command(0)}, ledger=Ledger())
    assert 'consumer exception recording failed' in exc.value.__notes__[0]


def test_the_scope_closes_the_child_and_the_ledger_and_keeps_the_exception(runner):
    res = {'errors': []}
    client = FakeClient()
    ledger = FakeLedger()
    with pytest.raises(RuntimeError):
        with runner.owned_worker_scope(res=res, ledger=ledger) as owned:
            owned['client'] = client
            raise RuntimeError('fake boot failed')
    assert client.closed is True
    assert ledger.closed is True
    assert res['errors'] == []


def test_a_failing_ledger_close_is_recorded_and_the_exception_survives(runner):
    res = {'errors': []}
    ledger = FakeLedger(fail=True)
    with pytest.raises(RuntimeError):
        with runner.owned_worker_scope(res=res, ledger=ledger) as owned:
            raise RuntimeError('fake boot failed')
    assert any('ledger close failed' in text for text in res['errors'])


def test_the_ledger_is_created_after_the_world_build_and_before_the_worker():
    source = OWNED_RUNNER.read_text(encoding='utf-8')
    build = source.index('world = build_world(')
    create = source.index('ledger = consumer.ConsumerLedger(')
    boot = source.index('client = boot_worker(')
    assert build < create < boot, (build, create, boot)
    assert 'with owned_worker_scope(res=res, ledger=ledger) as owned:' in source
