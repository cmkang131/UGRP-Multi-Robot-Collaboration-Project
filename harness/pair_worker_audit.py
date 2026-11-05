"""Opt-in provenance audit for the pinned pair-worker path.

Scope (2026-11-05, UGRP-Pair, branch ugrp/pair-worker-audit-20261105T1952Z)
---------------------------------------------------------------------------
* This module is an ADD-ON WRAPPER.  It never replaces the pinned
  ``OwnInputs`` with the main-branch ``OwnHistory``, never edits a pinned
  source, never changes the four-operation protocol (``reset``/``propose``/
  ``issue``/``summary``) and never adds a field to a model observation or to a
  protocol response.  It wraps the pinned objects and returns their values
  unchanged.
* The audit material goes to ONE new JSONL file per run, created with the
  exclusive ``'x'`` mode.  An existing file is never overwritten and a run id
  is never reused.
* FAIL CLOSED.  A harness tree mismatch, a pinned source hash mismatch, an
  unwritable audit file or a malformed audited value raises ``AuditError``
  instead of silently continuing.
* WHAT AN AUDIT RECORD IS NOT: an issue record states that a command was
  ISSUED AT THE PRODUCER.  It is not evidence that the command was applied to
  the environment, acknowledged, or that the robot moved.

Origin policy
-------------
The origin of an issued command is recorded as ``unknown`` unless the caller
explicitly declares ``policy`` or ``protocol_hold`` at the moment of the call.
A zero-wheel command, ``permit=False`` or an identical command value are NOT
used to infer an origin: the pinned path cannot tell them apart, so it stays
``unknown``.

Provenance of the record
------------------------
* ``reset_padding`` - the replicated initial window of the pinned ``OwnInputs``.
* ``observation``   - one produced observation: sample id, observation digest
  and issued-window digest.  It links to the issue that preceded it
  (``linked_issue_seq``).
* ``issue_command`` - one issued command with its values and digest.  It names
  the observation it supersedes (``supersedes_observation_seq``).
* ``propose_op``    - the protocol view of one propose call (per robot: sample
  id, digests, ready flag, stage).
* ``issue_op``      - the protocol view of one issue call (per robot: command
  digest, permit, blocked, done, stage, segment, proposal link).
* ``summary_op``    - the digest of one summary response.
* ``pending_observation`` - an issue command that no observation followed.

A proposal is written and verified BEFORE the issue that supersedes it, and an
issue command is written immediately.  When no observation follows an issue,
the record is marked ``unpaired``; no sample is ever invented.

Owned geometry-worker entry
----------------------------
``owned_worker_main`` is the owned copy of the pinned ``geometry_pair_worker``
four-operation loop.  The pinned script is READ (never modified) and its
operation allowlist is reused verbatim.  The audit is OFF unless
``--audit-run-id`` and ``--audit-output-root`` are both given; with them the
controller is wrapped at ``reset`` and the four responses are unchanged.
"""
from __future__ import annotations

import argparse
import base64
from collections.abc import Mapping
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

SCHEMA = 'ugrp.pair_worker_audit.v1'
ORIGINS = ('policy', 'protocol_hold', 'unknown')
RESERVED_FIELDS = {'schema', 'run_id', 'seq', 'claim', 'record_digest'}
CLAIM = ('issued at the producer only; not environment application, '
         'acknowledgement, or motion success')
SAFE_CHARS = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-')

# The four-operation allowlist of the pinned geometry worker.  It is compared
# against the pinned script at start-up; a mismatch stops the run.
GEOMETRY_WORKER_OPS = {
    'reset': {'op', 'roles', 'episode_id', 'initial'},
    'propose': {'op', 't', 'robots'},
    'issue': {'op', 't', 'permits'},
    'summary': {'op'},
}
GEOMETRY_WORKER_MODE = 'pairact_r1_student_eval_v1'
AUDIT_DEFAULTS = {'done_recovery': 'off', 'place_sync': 'off',
                  'issued_clock_deadband': 2}


class AuditError(RuntimeError):
    """Raised when the audit cannot be trusted; the run must stop."""


def _nonempty(value, name):
    if type(value) is not str or not value.strip():
        raise AuditError('%s must be a nonempty string' % name)
    return value


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    """SHA256 over the canonical JSON form of a value."""
    return hashlib.sha256(_canonical(value).encode('utf-8')).hexdigest()


def file_digest(path):
    hasher = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            hasher.update(chunk)
    return hasher.hexdigest()


def harness_dir(path):
    """The harness package directory of a module file, or None."""
    parent = Path(path).resolve().parent
    return parent if parent.name == 'harness' else None


def check_same_tree(audit_file, audited_file):
    """Refuse to audit code that lives in another harness tree."""
    mine = harness_dir(audit_file)
    theirs = harness_dir(audited_file)
    if mine is None or theirs is None:
        raise AuditError('audit module and audited code must live in a harness package')
    if mine != theirs:
        raise AuditError('harness tree mixing refused: %s vs %s' % (mine, theirs))
    return True


def verify_sources(sources):
    """Check every pinned source against its expected sha256 (read only)."""
    verified = {}
    for path, expected in sorted(sources.items()):
        if not Path(path).is_file():
            raise AuditError('pinned source is missing: %s' % path)
        actual = file_digest(path)
        if actual != expected:
            raise AuditError('pinned source hash mismatch: %s' % path)
        verified[path] = actual
    return verified


def load_source_manifest(path):
    """Read a JSON manifest of ``{absolute path: {sha256, bytes}}``."""
    raw = json.loads(Path(path).read_text(encoding='utf-8'))
    sources = {}
    for name, entry in raw.items():
        if isinstance(entry, Mapping):
            sources[name] = entry['sha256']
        else:
            sources[name] = entry
    return sources


class AuditSink:
    """One JSONL audit file per run, created exclusively and never reused."""

    def __init__(self, *, run_id, output_root, filename=None):
        self.run_id = _nonempty(run_id, 'run_id')
        if filename is None:
            if set(self.run_id) - SAFE_CHARS:
                raise AuditError('run_id must use letters, digits, dot, dash or underscore')
            filename = 'pair-audit-%s.jsonl' % self.run_id
        if Path(filename).name != filename or filename in ('.', '..'):
            raise AuditError('audit filename must be a basename inside output_root')
        root = Path(output_root)
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / filename
        try:
            self._stream = self.path.open('x', encoding='utf-8')
        except FileExistsError:
            raise AuditError('audit output already exists: %s' % self.path)
        self._seq = 0
        self.closed = False

    def write(self, record):
        if self.closed:
            raise AuditError('audit sink is closed')
        if not isinstance(record, Mapping):
            raise AuditError('audit record must be a mapping')
        if set(record) & RESERVED_FIELDS:
            raise AuditError('audit record attempts to override reserved envelope fields')
        payload = {'schema': SCHEMA, 'run_id': self.run_id, 'seq': self._seq,
                   'claim': CLAIM, **dict(record)}
        payload['record_digest'] = digest(payload)
        self._stream.write(_canonical(payload) + '\n')
        self._stream.flush()
        self._seq += 1
        return payload['seq']

    def close(self):
        if not self.closed:
            self.closed = True
            self._stream.close()


class PairWorkerAudit:
    """Audit state for one run of the pinned pair worker path."""

    def __init__(self, *, run_id, output_root=None, sources=None, filename=None,
                 sink=None):
        self.run_id = _nonempty(run_id, 'run_id')
        self.sources = dict(sources or {})
        if sink is None:
            if output_root is None:
                raise AuditError('an audit output root or an audit sink is required')
            sink = AuditSink(run_id=run_id, output_root=output_root,
                             filename=filename)
        self.sink = sink
        self.contract = None
        self._robots = {}
        self._attached = False
        self._closed = False

    # -- attachment -----------------------------------------------------
    def attach(self, controller):
        """Wrap a pinned controller and return the transparent proxy."""
        if self._attached:
            raise AuditError('audit is already attached to a controller')
        module = sys.modules.get(type(controller).__module__)
        audited_file = getattr(module, '__file__', None)
        if not audited_file:
            raise AuditError('audited controller has no source file')
        check_same_tree(__file__, audited_file)
        contract = self._resolve_contract(audited_file)
        verified = verify_sources(self.sources)
        inputs = getattr(controller, 'inputs', None)
        if not isinstance(inputs, Mapping) or not inputs:
            raise AuditError('audited controller exposes no per-robot inputs')
        self.contract = contract
        self.sink.write({'kind': 'inventory',
                         'audit_module': str(Path(__file__).resolve()),
                         'audit_module_sha256': file_digest(__file__),
                         'audited_controller': str(Path(audited_file).resolve()),
                         'audited_controller_sha256': file_digest(audited_file),
                         'contract': str(Path(contract.__file__).resolve()),
                         'contract_sha256': file_digest(contract.__file__),
                         'tree_root': str(harness_dir(audited_file)),
                         'pinned_sources': verified,
                         'candidate_is_the_pinned_worker': False,
                         'origin_policy': 'declared only; values never imply an origin'})
        for robot_id, owner in list(inputs.items()):
            inputs[robot_id] = AuditedInputs(owner, audit=self, robot_id=robot_id)
            self._state(robot_id)
        self._attached = True
        return AuditedController(controller, audit=self)

    def _resolve_contract(self, audited_file):
        """The contract module the audited code uses, in the same tree."""
        name = 'harness.grasp_act_contract'
        contract = sys.modules.get(name)
        if contract is None:
            raise AuditError('audited contract module is not loaded: %s' % name)
        contract_file = getattr(contract, '__file__', None)
        if not contract_file:
            raise AuditError('contract module has no source file')
        if harness_dir(contract_file) != harness_dir(audited_file):
            raise AuditError('contract from another harness tree: %s' % contract_file)
        return contract

    # -- recording ------------------------------------------------------
    def _state(self, robot_id):
        return self._robots.setdefault(robot_id, {'observation_seq': None,
                                                  'propose_seq': None,
                                                  'pending_issue_seq': None,
                                                  'issue_count': 0})

    def record_reset_padding(self, robot_id, issued_window, contract):
        rows = list(issued_window)
        if not rows:
            raise AuditError('issued window is empty')
        identical = all(digest(row) == digest(rows[0]) for row in rows)
        self.sink.write({'kind': 'reset_padding', 'robot_id': robot_id,
                         'count': len(rows), 'identical_rows': identical,
                         'row_digest': digest(rows[0]),
                         'contract_history': int(getattr(contract, 'HISTORY', 0))})

    def record_observation(self, robot_id, observation, *, contract):
        sample_id = observation.get('sample_id')
        issued = observation.get('issued')
        if not isinstance(sample_id, str) or not isinstance(issued, list):
            raise AuditError('audited observation has no sample id or issued window')
        if len(issued) != int(getattr(contract, 'HISTORY', len(issued))):
            raise AuditError('audited observation window has an unexpected length')
        state = self._state(robot_id)
        linked = state['pending_issue_seq']
        seq = self.sink.write({'kind': 'observation', 'robot_id': robot_id,
                               'sample_id': sample_id, 't': observation.get('t'),
                               'observation_digest': digest(observation),
                               'window_digest': digest(issued),
                               'issued_count': len(issued),
                               'linked_issue_seq': linked})
        state['pending_issue_seq'] = None
        state['observation_seq'] = seq
        return seq

    def record_issue_command(self, robot_id, command, *, origin='unknown'):
        if type(origin) is not str or origin not in ORIGINS:
            raise AuditError('unknown origin label: %r' % (origin,))
        state = self._state(robot_id)
        issue_count = state['issue_count'] + 1
        supersedes = state['observation_seq']
        seq = self.sink.write({'kind': 'issue_command', 'robot_id': robot_id,
                               't': command.get('t'),
                               'command_digest': digest(command),
                               'command': json.loads(_canonical(command)),
                               'origin': origin,
                               'origin_source': 'declared by the caller' if origin != 'unknown'
                               else 'unknown; values never imply an origin',
                               'supersedes_observation_seq': supersedes,
                               'issue_number': issue_count})
        state['issue_count'] = issue_count
        state['observation_seq'] = None
        state['pending_issue_seq'] = seq
        return seq

    def record_propose(self, now, result):
        robots = {}
        for robot_id, value in result.items():
            observation = value.get('observation')
            if not isinstance(observation, Mapping):
                raise AuditError('propose result carries no observation')
            robots[robot_id] = {'sample_id': observation.get('sample_id'),
                                'observation_digest': digest(observation),
                                'window_digest': digest(observation.get('issued')),
                                'ready': value.get('ready'), 'stage': value.get('stage'),
                                'rgb_path': value.get('rgb_path')}
        seq = self.sink.write({'kind': 'propose_op', 't': now, 'robots': robots})
        for robot_id in robots:
            self._state(robot_id)['propose_seq'] = seq
        return seq

    def record_issue_op(self, now, permits, result):
        robots = {}
        for robot_id, value in result.items():
            command = value.get('command')
            if not isinstance(command, Mapping):
                raise AuditError('issue result carries no command')
            robots[robot_id] = {'command_digest': digest(command),
                                'permit': value.get('permit'),
                                'blocked': value.get('blocked'),
                                'done': value.get('done'),
                                'stage': value.get('stage'),
                                'segment': value.get('segment'),
                                'propose_seq': self._state(robot_id)['propose_seq']}
        seq = self.sink.write({'kind': 'issue_op', 't': now,
                               'permits': dict(permits), 'robots': robots})
        return seq

    def record_summary(self, summary):
        return self.sink.write({'kind': 'summary_op', 'summary_digest': digest(summary)})

    def close(self):
        """Mark unpaired issues and close the sink."""
        if self._closed:
            return
        for robot_id, state in self._robots.items():
            pending = state['pending_issue_seq']
            if pending is not None:
                self.sink.write({'kind': 'pending_observation', 'robot_id': robot_id,
                                 'issue_seq': pending, 'unpaired': True})
                state['pending_issue_seq'] = None
        self._closed = True
        self.sink.close()


class AuditedInputs:
    """Transparent proxy around the pinned OwnInputs of one robot."""

    def __init__(self, owner, *, audit, robot_id):
        self._owner = owner
        self._audit = audit
        self.robot_id = robot_id
        audit.record_reset_padding(robot_id, owner.issued, audit.contract)

    def __getattr__(self, name):
        return getattr(self._owner, name)

    def observe(self, now, jpeg, **kwargs):
        observation, pixels, path = self._owner.observe(now, jpeg, **kwargs)
        self._audit.record_observation(self.robot_id, observation,
                                       contract=self._audit.contract)
        return observation, pixels, path

    def issue(self, value, *, origin='unknown'):
        if type(origin) is not str or origin not in ORIGINS:
            raise AuditError('unknown origin label: %r' % (origin,))
        # Check all caller-controlled input before the pinned producer mutates.
        self._audit.contract.command(value)
        _canonical(value)
        self._owner.issue(value)
        self._audit.record_issue_command(self.robot_id, self._owner.issued[-1], origin=origin)


class AuditedController:
    """Transparent proxy around the pinned controller (four operations)."""

    def __init__(self, controller, *, audit):
        self._controller = controller
        self._audit = audit

    def __getattr__(self, name):
        return getattr(self._controller, name)

    def propose(self, now, robots):
        result = self._controller.propose(now, robots)
        self._audit.record_propose(now, result)
        return result

    def issue(self, now, permits):
        result = self._controller.issue(now, permits)
        self._audit.record_issue_op(now, permits, result)
        return result

    def summary(self):
        result = self._controller.summary()
        self._audit.record_summary(result)
        return result

    def close(self):
        self._audit.close()


# ------------------------------------------------------------------ owned entry

def load_pinned_geometry_worker(path):
    """Read the pinned geometry worker script and reuse its contract.

    The file is imported read-only; ``main`` is not executed and no head
    process is started by this call.
    """
    target = Path(path).resolve()
    if not target.is_file():
        raise AuditError('pinned geometry worker is missing: %s' % target)
    spec = importlib.util.spec_from_file_location('ugrp_pinned_geometry_pair_worker',
                                                  str(target))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    ops = getattr(module, 'OPS', None)
    if ops != GEOMETRY_WORKER_OPS:
        raise AuditError('pinned geometry worker operation allowlist changed')
    if getattr(module, 'MODE', None) != GEOMETRY_WORKER_MODE:
        raise AuditError('pinned geometry worker mode changed')
    return module


def _owned_parser():
    parser = argparse.ArgumentParser(description='Owned pair worker entry with an '
                                                 'opt-in provenance audit.')
    parser.add_argument('--student-root', type=Path, required=True)
    parser.add_argument('--geometry-worker', type=Path, required=True)
    parser.add_argument('--config', type=Path, default=None)
    parser.add_argument('--model', default=None)
    parser.add_argument('--device', default='cpu')
    parser.add_argument('--threads', type=int, default=1)
    parser.add_argument('--headworker', type=Path, default=None)
    parser.add_argument('--head-source-root', type=Path, default=None)
    parser.add_argument('--geometry-trace-dir', type=Path, default=None)
    parser.add_argument('--audit-run-id', default=None)
    parser.add_argument('--audit-output-root', type=Path, default=None)
    parser.add_argument('--audit-sources', type=Path, default=None)
    return parser


def owned_worker_main(argv=None, *, predict=None, stdin=None, stdout=None):
    """The owned four-operation loop of the pinned geometry worker.

    The audit is OFF unless ``--audit-run-id`` and ``--audit-output-root`` are
    both given.  With the audit ON the pinned controller is wrapped at
    ``reset``; the four protocol responses are byte-for-byte the pinned ones
    and carry no audit metadata.
    """
    args = _owned_parser().parse_args(argv)
    if bool(args.audit_run_id) != bool(args.audit_output_root):
        raise AuditError('audit run id and audit output root must be given together')
    startup_sources = (load_source_manifest(args.audit_sources)
                       if args.audit_sources is not None else {})
    verify_sources(startup_sources)  # fail before importing or starting a head
    pinned = load_pinned_geometry_worker(args.geometry_worker)
    student_root = str(Path(args.student_root).resolve())
    if student_root not in sys.path:
        sys.path.insert(0, student_root)

    from harness.pairact_r1_student import PairStudentController

    settings = dict(AUDIT_DEFAULTS)
    if args.config is not None:
        from harness.pairact_r1 import load_config
        settings.update(load_config(args.config))

    head = None
    if predict is None:
        if args.headworker is None or args.geometry_trace_dir is None:
            raise AuditError('a head worker is required unless a predictor is injected')
        head = pinned.GeometryHeadClient(
            model=args.model, device=args.device, threads=args.threads,
            headworker=args.headworker, head_source_root=args.head_source_root,
            student_root=Path(student_root), trace_dir=args.geometry_trace_dir,
        )
        predict = head.predict

    audit = None
    if bool(args.audit_run_id) != bool(args.audit_output_root):
        raise AuditError('audit run id and audit output root must be given together')
    if args.audit_run_id:
        sources = (load_source_manifest(args.audit_sources) if args.audit_sources
                   else {})
        audit = PairWorkerAudit(run_id=args.audit_run_id,
                                output_root=args.audit_output_root,
                                sources=sources)

    stream_in = stdin if stdin is not None else sys.stdin
    stream_out = stdout if stdout is not None else sys.stdout
    controller = None
    try:
        print(json.dumps({'ready': True, 'mode': pinned.MODE}), flush=True, file=stream_out)
        for line in stream_in:
            request = json.loads(line)
            op = request.get('op')
            if op not in pinned.OPS or set(request) != pinned.OPS[op]:
                raise ValueError('worker allowlist mismatch')
            if op == 'reset':
                controller = PairStudentController(
                    predict, request['roles'], request['episode_id'], request['initial'],
                    done_recovery=settings['done_recovery'],
                    place_sync=settings['place_sync'],
                    deadband=settings['issued_clock_deadband'],
                )
                if audit is not None:
                    controller = audit.attach(controller)
                result = {'ok': True}
            elif op == 'propose':
                if controller is None:
                    raise RuntimeError('propose before reset')
                if not isinstance(request['robots'], dict) or any(
                        not isinstance(value, dict) or set(value) != {'jpeg', 'issued'}
                        for value in request['robots'].values()):
                    raise ValueError('own camera + own issued command only')
                robots = {rid: {'jpeg': base64.b64decode(value['jpeg'], validate=True),
                                'issued': value['issued']}
                          for rid, value in request['robots'].items()}
                result = {'robots': controller.propose(float(request['t']), robots)}
            elif op == 'issue':
                if controller is None:
                    raise RuntimeError('issue before reset')
                result = {'robots': controller.issue(float(request['t']), request['permits']),
                          'finished': controller.finished}
            else:
                if controller is None:
                    raise RuntimeError('summary before reset')
                result = controller.summary()
            print(json.dumps(result, allow_nan=False), flush=True, file=stream_out)
    finally:
        if audit is not None:
            audit.close()
        if head is not None:
            head.close()
    return 0
