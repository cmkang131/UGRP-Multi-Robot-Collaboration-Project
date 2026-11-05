"""Consumer-side apply-call ledger for the pinned pair path.

Scope (2026-11-05, UGRP-Pair, branch ugrp/pair-consumer-audit-20261105T2046Z)
---------------------------------------------------------------------------
This module is a **runtime forensic logger** of the consumer side of the pair
path.  It records that the apply callable was called, what it was called with
and what it returned, and it binds that call to the producer's issue record
and to the robot's next own observation.

What it is NOT
--------------
* It is **not** a security audit, it does not attest any origin and it is
  **not** an authentication of the apply callable.  The callable identity is a
  label (module, qualname, source hash) that is compared with the expected
  one; it proves nothing about who called it.
* ``apply_returned`` is only the **return value of the called function**.  It
  is NOT evidence that the command reached the environment, that anything was
  transmitted or acknowledged, or that the robot moved.
* An exception is recorded as an exception; a missing port state stays
  missing.  No acknowledgement, no "applied" flag and no motion result is
  ever synthesised.
* The origin of an issued command is never inferred here.  Values, zero
  wheels, a ``permit`` flag or a repeated command are not used to attribute
  anything.

Phases
------
The ledger is a small state machine.  Every phase validates EVERYTHING
before it changes ANYTHING, so a refused call leaves the ledger exactly as it
was (pending applies, consumed rows, issue counters and counters included):

  1. ``attach_apply``  -- bind one identified apply callable (an alias is
     refused).
  2. ``begin_apply``   -- the apply call is about to happen: the command and
     the prior are copied and the call is bound to the producer's NEXT issue
     of that robot.
  3. ``end_apply``     -- the call returned or raised: exactly one result row
     is written and the apply becomes *pending* (it awaits an observation).
  4. ``record_observation`` -- the robot's next own observation: it is checked
     against the body, the producer row and the pending apply; only then the
     pending apply is released and the counters move.
  5. ``close``         -- the applies that no observation answered are written
     explicitly, followed by the summary.

Binding to the producer
-----------------------
The producer's audit file (``harness/pair_worker_audit.py``) holds
``issue_command`` rows (``run_id``, ``seq``, ``robot_id``, ``t``,
``issue_number``, ``command_digest``, ``command``) and ``observation`` rows
(``robot_id``, ``sample_id``, ``linked_issue_seq``).  This module reads that
file **read-only** and verifies before it trusts it:

* the producer schema and the run id must match this ledger's run id;
* the producer rows must have contiguous ``seq`` values of type ``int``
  (a string or a boolean sequence is refused);
* every row's ``record_digest`` must recompute correctly;
* every row that was already read is re-checked: the file must not have
  shrunk and the already accepted prefix must hash exactly as it did.  An
  edited, truncated or replaced prefix is refused, and the reader becomes
  terminally invalid -- it is not trusted again.

Only rows the producer actually flushed are read: a trailing partial line is
ignored.  A command is bound to the producer issue with the NEXT
``issue_number`` of that robot (the producer numbers them densely per robot),
so the order is preserved, a skipped issue is refused, a duplicated issue is
refused and one issue can never be bound twice.  A repeated identical command
at the same time therefore stays distinguishable.

Command digests
---------------
The producer digests the command **after** the pinned contract normalised it
(``harness/grasp_act_contract.py``: ``float()`` on the numeric fields, the
four-field whitelist).  The consumer holds the raw command of the issue
response.  The two digests can therefore differ when the raw command carries
an integer where the normalised one carries a float.  The binding accepts the
raw digest **or** the contract-normalised digest and records both, so a
mismatch is never silently papered over.

The ledger writes its own new JSONL file with the exclusive ``'x'`` mode, one
file per ``(run_id, episode_id)``; every row carries a contiguous ``seq`` and
a ``row_digest``.  The producer's raw records and responses are never
modified, and no metadata is added to them.

Standard library only.  The outer runner loads this module **by path** so it
can never shadow the pinned ``harness`` package of the physics closure.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path
import sys

SCHEMA = 'ugrp.pair_consumer_audit.v1'
PRODUCER_SCHEMA = 'ugrp.pair_worker_audit.v1'
CLAIM = ('the apply callable was called and returned; NOT environment '
         'application, NOT transmission acknowledgement, NOT motion success')
SAFE_CHARS = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-')
COMMAND_FIELDS = {'t', 'wheels', 'duration_s', 'pwm'}
RESERVED_FIELDS = {'schema', 'run_id', 'seq', 'claim', 'row_digest'}
ORIGINS = ('policy', 'protocol_hold', 'unknown')


class ConsumerAuditError(RuntimeError):
    """Raised when the ledger cannot be trusted; the run must stop."""


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    """SHA256 over the canonical JSON form of a value (producer compatible)."""
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


def file_digest(path):
    hasher = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            hasher.update(chunk)
    return hasher.hexdigest()


def deep_copy(value):
    """A JSON-safe deep copy of a value (no shared mutable state)."""
    return json.loads(canonical(value))


def is_finite_number(value):
    """True for a real finite number (a bool is not a number here)."""
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value))


def normalize_command(command):
    """The pinned contract's normalisation of one issued command, or None.

    ``harness/grasp_act_contract.command`` returns a fresh four-field mapping
    with ``float()`` on ``t``/``wheels``/``duration_s`` and an integer ``pwm``.
    Only the type normalisation is reproduced here; the range checks belong to
    the pinned contract and are not duplicated.
    """
    if not isinstance(command, dict) or set(command) != COMMAND_FIELDS:
        return None
    try:
        wheels = [float(v) for v in command['wheels']]
        duration = [float(v) for v in command['duration_s']]
        pwm = {str(k): int(v) for k, v in command['pwm'].items()}
        return {'t': float(command['t']), 'wheels': wheels,
                'duration_s': duration, 'pwm': pwm}
    except (TypeError, ValueError):
        return None


def identity_of(callable_):
    """Identify a callable so that an alias cannot impersonate it.

    This is a LABEL, not an authentication: it says which module, function
    and source file the callable comes from.
    """
    module = getattr(callable_, '__module__', None)
    qualname = getattr(callable_, '__qualname__', None) or getattr(callable_, '__name__', None)
    if not module or not qualname:
        raise ConsumerAuditError('the apply callable is not identifiable')
    source_path = None
    source_sha256 = None
    module_object = sys.modules.get(module)
    source_file = getattr(module_object, '__file__', None)
    if source_file and Path(source_file).is_file():
        source_path = str(Path(source_file).resolve())
        source_sha256 = file_digest(source_path)
    return {'module': module, 'qualname': qualname, 'source_path': source_path,
            'source_sha256': source_sha256,
            'identity': '%s:%s:%s' % (module, qualname, source_sha256)}


class ConsumerSink:
    """One JSONL ledger file per (run_id, episode_id), created exclusively."""

    def __init__(self, *, run_id, episode_id, output_root, filename=None):
        self.run_id = run_id
        self.episode_id = episode_id
        if not isinstance(run_id, str) or not run_id.strip():
            raise ConsumerAuditError('run_id must be a nonempty string')
        if not isinstance(episode_id, str) or not episode_id.strip():
            raise ConsumerAuditError('episode_id must be a nonempty string')
        if filename is None:
            if set(self.run_id) - SAFE_CHARS or set(self.episode_id) - SAFE_CHARS:
                raise ConsumerAuditError('run and episode ids must use letters, digits, '
                                         'dot, dash or underscore')
            filename = 'pair-consumer-audit-%s-%s.jsonl' % (self.run_id, self.episode_id)
        else:
            if not isinstance(filename, str) or not filename.strip():
                raise ConsumerAuditError('the consumer audit filename must be a nonempty string')
            if filename in ('.', '..') or '/' in filename or '\\' in filename:
                raise ConsumerAuditError('the consumer audit filename must be a plain basename: %r'
                                         % (filename,))
            if Path(filename).is_absolute() or Path(filename).name != filename:
                raise ConsumerAuditError('the consumer audit filename must not be a path: %r'
                                         % (filename,))
        root = Path(output_root).resolve()
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / filename
        if self.path.resolve().parent != root:
            raise ConsumerAuditError('the consumer audit file must stay inside the output root')
        try:
            self._stream = self.path.open('x', encoding='utf-8')
        except FileExistsError:
            raise ConsumerAuditError('consumer audit output already exists: %s' % self.path)
        self._seq = 0
        self.closed = False

    def write(self, record):
        if self.closed:
            raise ConsumerAuditError('consumer audit sink is closed')
        if not isinstance(record, dict):
            raise ConsumerAuditError('consumer audit record must be a mapping')
        if set(record) & RESERVED_FIELDS:
            raise ConsumerAuditError('consumer audit record attempts to override the reserved '
                                     'envelope fields: %s' % sorted(set(record) & RESERVED_FIELDS))
        payload = {'schema': SCHEMA, 'run_id': self.run_id, 'seq': self._seq,
                   'claim': CLAIM, **dict(record)}
        payload['row_digest'] = digest(payload)
        self._stream.write(canonical(payload) + '\n')
        self._stream.flush()
        self._seq += 1
        return payload['seq']

    def close(self):
        if not self.closed:
            self.closed = True
            self._stream.close()


class ProducerIndex:
    """Verified reader of the producer's audit JSONL.

    The file is re-read completely on every refresh, but only the part that
    was not accepted before is parsed; the already accepted prefix is
    re-verified by its hash, so an edited, truncated or replaced prefix is
    refused.  A refresh that fails is atomic (no partial state) and makes the
    reader terminally invalid: it is not trusted again.
    """

    def __init__(self, path, *, run_id):
        self.path = Path(path)
        self.run_id = run_id
        self.rows = 0
        self.issues = {}           # robot_id -> {issue_number: row}
        self.issue_order = {}      # robot_id -> [row, ...] in file order
        self.observations = {}     # (robot_id, sample_id) -> row
        self.invalid = False
        self.invalid_reason = None
        self._prefix_len = 0
        self._prefix_sha = hashlib.sha256(b'').hexdigest()
        self._seen_seq = -1
        # The ledger is created before the producer worker starts, so a missing
        # producer file is normal at construction time.  Binding (below) is
        # fail-closed: the file must exist and verify then.
        self.refresh(required=False)

    # -- failure ---------------------------------------------------------
    def _fail(self, message):
        self.invalid = True
        self.invalid_reason = message
        raise ConsumerAuditError(message)

    # -- reading ---------------------------------------------------------
    def refresh(self, *, required=True):
        """Read the rows the producer has flushed since the last call."""
        if self.invalid:
            raise ConsumerAuditError('the producer audit reader is invalid and is not '
                                     'trusted again: %s' % self.invalid_reason)
        if not self.path.is_file():
            if not required:
                return self.rows
            self._fail('producer audit file is missing: %s' % self.path)
        data = self.path.read_bytes()
        if len(data) < self._prefix_len:
            self._fail('producer audit file shrank: %s' % self.path)
        if hashlib.sha256(data[:self._prefix_len]).hexdigest() != self._prefix_sha:
            self._fail('the accepted producer audit prefix changed: %s' % self.path)
        rest = data[self._prefix_len:]
        parts = rest.split(b'\n')
        tail = parts.pop()                       # an unfinished line: not flushed yet
        # Validate sequentially against a private prospective index. New rows
        # in one read must see preceding rows in that same read, while a
        # rejected batch must not modify the accepted index.
        staged = copy.copy(self)
        staged.issues = {robot: dict(rows) for robot, rows in self.issues.items()}
        staged.issue_order = {robot: list(rows) for robot, rows in self.issue_order.items()}
        staged.observations = dict(self.observations)
        seen = self._seen_seq
        try:
            for part in parts:
                if not part.strip():
                    continue
                try:
                    line = part.decode('utf-8')
                except UnicodeDecodeError:
                    staged._fail('producer audit row is not valid UTF-8')
                row, seen = staged._parse(line, seen)
                staged._commit(row)
        except (ConsumerAuditError, ValueError, TypeError, OverflowError) as exc:
            self._fail(str(exc))
        self.issues = staged.issues
        self.issue_order = staged.issue_order
        self.observations = staged.observations
        self.rows = staged.rows
        self._seen_seq = seen
        consumed = len(rest) - len(tail)
        self._prefix_len += consumed
        self._prefix_sha = hashlib.sha256(data[:self._prefix_len]).hexdigest()
        return self.rows

    def _parse(self, line, seen):
        try:
            row = json.loads(line)
        except ValueError as exc:
            self._fail('producer audit row is not valid JSON: %s' % exc)
        if not isinstance(row, dict):
            self._fail('producer audit row is not an object')
        if row.get('schema') != PRODUCER_SCHEMA:
            self._fail('producer audit schema mismatch')
        if row.get('run_id') != self.run_id:
            self._fail('producer audit run id mismatch')
        seq = row.get('seq')
        if type(seq) is not int:
            self._fail('producer audit sequence is not an integer: %r' % (seq,))
        if seq != seen + 1:
            self._fail('producer audit sequence gap at %r' % (seq,))
        recorded = row.get('record_digest')
        body = {k: v for k, v in row.items() if k != 'record_digest'}
        if not isinstance(recorded, str) or digest(body) != recorded:
            self._fail('producer audit row digest mismatch at seq %s' % seq)
        kind = row.get('kind')
        if kind == 'issue_command':
            self._check_issue(row)
        elif kind == 'observation':
            self._check_observation(row)
        return row, seq

    def _check_issue(self, row):
        robot = row.get('robot_id')
        if not isinstance(robot, str) or not robot.strip():
            self._fail('producer issue row has no robot id')
        number = row.get('issue_number')
        if type(number) is not int or number < 1:
            self._fail('producer issue row has a malformed issue number: %r' % (number,))
        if not isinstance(row.get('command_digest'), str):
            self._fail('producer issue row has no command digest')
        if not is_finite_number(row.get('t')):
            self._fail('producer issue row has a malformed time: %r' % (row.get('t'),))
        if row.get('origin') not in ORIGINS:
            self._fail('producer issue row has an unknown origin label: %r'
                       % (row.get('origin'),))
        known = self.issues.get(robot, {})
        if number != len(known) + 1:
            self._fail('producer issue numbers must be dense and ordered for robot %r: %r'
                       % (robot, number))
        command = row.get('command')
        if not isinstance(command, dict) or normalize_command(command) is None:
            self._fail('producer issue command is malformed')
        if digest(command) != row['command_digest']:
            self._fail('producer issue command digest does not match its command')
        if command.get('t') != row['t']:
            self._fail('producer issue time does not match its command')
        if known and row['t'] < known[number - 1]['t']:
            self._fail('producer issue time must not go backwards')

    def _check_observation(self, row):
        robot = row.get('robot_id')
        if not isinstance(robot, str) or not robot.strip():
            self._fail('producer observation row has no robot id')
        sample_id = row.get('sample_id')
        if not isinstance(sample_id, str) or not sample_id.strip():
            self._fail('producer observation row has no sample id')
        if not is_finite_number(row.get('t')):
            self._fail('producer observation row has a malformed time: %r' % (row.get('t'),))
        linked = row.get('linked_issue_seq')
        if linked is not None and type(linked) is not int:
            self._fail('producer observation row has a malformed linked issue: %r' % (linked,))
        key = (robot, sample_id)
        if key in self.observations:
            self._fail('producer observation %r is duplicated for robot %r' % (sample_id, robot))

    def _commit(self, row):
        kind = row.get('kind')
        if kind == 'issue_command':
            robot = row['robot_id']
            self.issues.setdefault(robot, {})[row['issue_number']] = row
            self.issue_order.setdefault(robot, []).append(row)
        elif kind == 'observation':
            self.observations[(row['robot_id'], row['sample_id'])] = row
        self.rows += 1

    # -- binding ---------------------------------------------------------
    def next_issue(self, robot_id, number):
        """The producer issue with this number for this robot, or None."""
        self.refresh()
        return self.issues.get(robot_id, {}).get(number)

    def bind_observation(self, robot_id, sample_id):
        """The producer observation of this robot and sample, or None."""
        self.refresh()
        return self.observations.get((robot_id, sample_id))


class ConsumerLedger:
    """The consumer-side ledger of one run and episode."""

    def __init__(self, *, run_id, episode_id, output_root, producer_audit_path,
                 robots, filename=None, sink=None):
        self.run_id = run_id
        self.episode_id = episode_id
        self.robots = tuple(robots)
        self.producer = ProducerIndex(producer_audit_path, run_id=run_id)
        self.sink = sink if sink is not None else ConsumerSink(
            run_id=run_id, episode_id=episode_id, output_root=output_root,
            filename=filename)
        self._apply_identity = None
        self._bound_issues = {}     # robot_id -> number of bound issues
        self._consumed = set()      # producer issue seqs already bound
        self._consumed_obs = set()  # producer observation seqs already used
        self._open = {}             # robot_id -> the apply call in flight
        self._pending = {}          # robot_id -> the apply awaiting an observation
        self._last_time = {}        # robot_id -> the last accepted time
        self._applied = 0
        self._returned = 0
        self._exceptions = 0
        self._observations = 0
        self._linked_observations = 0
        self._closed = False

    # -- read-only counters ----------------------------------------------
    @property
    def rows_written(self):
        return self.sink._seq

    @property
    def apply_calls(self):
        return self._applied

    @property
    def apply_returned(self):
        return self._returned

    @property
    def apply_exceptions(self):
        return self._exceptions

    @property
    def observations(self):
        return self._observations

    @property
    def observations_linked(self):
        return self._linked_observations

    # -- guards -----------------------------------------------------------
    def _require_open(self):
        if self._closed:
            raise ConsumerAuditError('the consumer ledger is closed')

    def _require_robot(self, robot_id):
        if robot_id not in self.robots:
            raise ConsumerAuditError('robot is not part of this run: %r' % (robot_id,))

    def _check_time(self, robot_id, value):
        if not is_finite_number(value):
            raise ConsumerAuditError('the time must be a finite number: %r' % (value,))
        last = self._last_time.get(robot_id)
        if last is not None and value < last:
            raise ConsumerAuditError('the time must not go backwards for robot %r: %r < %r'
                                     % (robot_id, value, last))
        return float(value)

    # -- phase 1: identity -----------------------------------------------
    def attach_apply(self, callable_, *, expected=None):
        """Bind the ledger to one identified apply callable.

        A differently identified callable (an alias) for the same ledger is
        refused; when ``expected`` is given the identity must match it.  The
        identity is a label (module, qualname, source hash), not an
        authentication of the caller.
        """
        self._require_open()
        identity = identity_of(callable_)
        if expected is not None and identity['identity'] != expected:
            raise ConsumerAuditError('apply callable identity mismatch: %s != %s'
                                     % (identity['identity'], expected))
        if self._apply_identity is not None and self._apply_identity != identity:
            raise ConsumerAuditError('apply callable alias refused: %s != %s'
                                     % (self._apply_identity, identity))
        self._apply_identity = identity
        self.sink.write({'kind': 'inventory', 'episode_id': self.episode_id,
                         'robots': list(self.robots),
                         'producer_audit_path': str(self.producer.path),
                         'producer_rows_read': self.producer.rows,
                         'apply_callable': identity,
                         'apply_callable_is_a_label': 'module, qualname and source hash; '
                                                      'NOT an authentication of the caller',
                         'origin_policy': 'never inferred; only what the caller declares',
                         'scope': 'runtime forensic log of the consumer apply call',
                         'environment_applied': 'unknown',
                         'transmission_acknowledged': 'unknown',
                         'motion_observed': 'unknown',
                         'port_state': 'not captured by this ledger'})
        return identity

    # -- phase 2: the call is about to happen ------------------------------
    def begin_apply(self, robot_id, *, cmd, prior, now, tick=None):
        """Record the call BEFORE it happens: a copy of the command and prior."""
        self._require_open()
        self._require_robot(robot_id)
        if self._apply_identity is None:
            raise ConsumerAuditError('no apply callable is attached to this ledger')
        if robot_id in self._open:
            raise ConsumerAuditError('an apply call is already open for robot %r' % (robot_id,))
        if robot_id in self._pending:
            raise ConsumerAuditError('the previous apply of robot %r has no observation yet'
                                     % (robot_id,))
        now = self._check_time(robot_id, now)
        command_copy = deep_copy(cmd)
        prior_copy = deep_copy(prior)
        raw_digest = digest(command_copy)
        normalized = normalize_command(command_copy)
        normalized_digest = digest(normalized) if normalized is not None else None
        digests = (raw_digest,) if normalized_digest is None else (raw_digest, normalized_digest)
        # the producer numbers its issues densely per robot: the next one is
        # the only one this call may bind.
        number = self._bound_issues.get(robot_id, 0) + 1
        issue = self.producer.next_issue(robot_id, number)
        if issue is None:
            raise ConsumerAuditError('the next producer issue (number %d) is missing for robot %r'
                                     % (number, robot_id))
        if issue['seq'] in self._consumed:
            raise ConsumerAuditError('producer issue already bound: seq=%s' % issue['seq'])
        if issue['command_digest'] not in digests:
            raise ConsumerAuditError('the producer issue does not match the applied command: '
                                     'issue=%s digests=%s' % (issue['seq'], list(digests)))
        seq = self.sink.write({
            'kind': 'apply_call', 'robot_id': robot_id, 'tick': tick, 'now': now,
            'command': command_copy, 'command_digest': raw_digest,
            'command_digest_normalized': normalized_digest,
            'prior_command': prior_copy,
            'prior_command_digest': digest(prior_copy),
            'producer_issue': {'seq': issue['seq'], 'issue_number': issue['issue_number'],
                               'command_digest': issue['command_digest'],
                               't': issue['t'], 'origin': issue.get('origin'),
                               'origin_source': issue.get('origin_source'),
                               'supersedes_observation_seq': issue.get('supersedes_observation_seq')},
            'prior_is_a_copy': True,
            'environment_applied': 'unknown',
            'transmission_acknowledged': 'unknown',
            'motion_observed': 'unknown',
            'port_state': 'not captured by this ledger'})
        # commit
        self._consumed.add(issue['seq'])
        self._bound_issues[robot_id] = number
        self._last_time[robot_id] = now
        self._open[robot_id] = {'seq': seq, 'issue_seq': issue['seq'],
                                 'issue_number': number, 'tick': tick, 'now': now}
        self._applied += 1
        return seq

    # -- phase 3: the call returned or raised -----------------------------
    def end_apply(self, robot_id, *, outcome, result=None, error=None):
        """Record the outcome of the call: the return value or the exception."""
        self._require_open()
        self._require_robot(robot_id)
        if outcome not in ('returned', 'exception'):
            raise ConsumerAuditError('unknown apply outcome: %r' % (outcome,))
        open_ = self._open.get(robot_id)
        if open_ is None:
            raise ConsumerAuditError('no apply call is open for robot %r' % (robot_id,))
        row = {'kind': 'apply_result', 'robot_id': robot_id, 'outcome': outcome,
               'applies_to_seq': open_['seq'],
               'apply_returned_is_only_the_function_return': outcome == 'returned'}
        if outcome == 'returned':
            row['returned'] = deep_copy(result)
            row['returned_digest'] = digest(row['returned'])
        else:
            row['exception_type'] = error.get('type') if isinstance(error, dict) else None
            row['exception'] = error.get('message') if isinstance(error, dict) else str(error)
        row['environment_applied'] = 'unknown'
        row['transmission_acknowledged'] = 'unknown'
        row['motion_observed'] = 'unknown'
        row['port_state'] = 'not captured by this ledger'
        seq = self.sink.write(row)
        # commit
        self._open.pop(robot_id, None)
        self._pending[robot_id] = {'seq': open_['seq'], 'issue_seq': open_['issue_seq'],
                                   'issue_number': open_['issue_number'], 'tick': open_['tick']}
        if outcome == 'returned':
            self._returned += 1
        else:
            self._exceptions += 1
        return seq

    # -- phase 4: the next own observation --------------------------------
    def record_observation(self, robot_id, *, observation, rgb_sha256=None, tick=None):
        """Record the robot's next own observation and link it to the apply.

        The observation is the robot's own next observation.  It is checked
        against the body (the robot id and the time), against the producer's
        observation row (the sample id, the robot id, the time and the
        digest) and against the pending apply (the linked issue).  Only when
        every check passes is the pending apply released and a counter moved:
        a refused observation leaves the ledger untouched.
        """
        self._require_open()
        self._require_robot(robot_id)
        if not isinstance(observation, dict):
            raise ConsumerAuditError('observation must be a mapping')
        body_robot = observation.get('robot_id')
        if body_robot != robot_id:
            raise ConsumerAuditError('the observation belongs to another robot: %r != %r'
                                     % (body_robot, robot_id))
        sample_id = observation.get('sample_id')
        if not isinstance(sample_id, str) or not sample_id.strip():
            raise ConsumerAuditError('observation has no sample id')
        observed_t = self._check_time(robot_id, observation.get('t'))
        producer_observation = self.producer.bind_observation(robot_id, sample_id)
        if producer_observation is None:
            raise ConsumerAuditError('no producer observation for robot %r and sample %r'
                                     % (robot_id, sample_id))
        if producer_observation['robot_id'] != robot_id:
            raise ConsumerAuditError('the producer observation belongs to another robot: %r != %r'
                                     % (producer_observation['robot_id'], robot_id))
        if producer_observation['sample_id'] != sample_id:
            raise ConsumerAuditError('the producer observation has another sample id: %r != %r'
                                     % (producer_observation['sample_id'], sample_id))
        if producer_observation['t'] != observed_t:
            raise ConsumerAuditError('the producer observation has another time: %r != %r'
                                     % (producer_observation['t'], observed_t))
        observation_digest = digest(observation)
        if observation_digest != producer_observation.get('observation_digest'):
            raise ConsumerAuditError('the observation does not match the producer row: '
                                     'digest %s != %s'
                                     % (observation_digest,
                                        producer_observation.get('observation_digest')))
        if producer_observation['seq'] in self._consumed_obs:
            raise ConsumerAuditError('the producer observation was already used: seq=%s'
                                     % producer_observation['seq'])
        linked_issue_seq = producer_observation.get('linked_issue_seq')
        pending = self._pending.get(robot_id)
        if pending is None:
            if linked_issue_seq is not None:
                raise ConsumerAuditError('the producer observation links issue %r, but no '
                                         'apply of robot %r is pending'
                                         % (linked_issue_seq, robot_id))
        elif linked_issue_seq != pending['issue_seq']:
            raise ConsumerAuditError(
                'producer observation links a different issue: sample=%r linked=%r '
                'bound=%r' % (sample_id, linked_issue_seq, pending['issue_seq']))
        row = {'kind': 'observation_link', 'robot_id': robot_id, 'tick': tick,
               'sample_id': sample_id,
               'observation_digest': observation_digest,
               'observation_digest_matches_producer': True,
               'rgb_sha256': rgb_sha256,
               'rgb_note': 'digest of the own JPEG given for this robot only',
               'answers_apply_seq': pending['seq'] if pending else None,
               'producer_observation': {'seq': producer_observation['seq'],
                                        'linked_issue_seq': linked_issue_seq,
                                        'observation_digest': producer_observation.get('observation_digest')},
               'unanswered': pending is None}
        seq = self.sink.write(row)
        # commit
        self._consumed_obs.add(producer_observation['seq'])
        self._last_time[robot_id] = observed_t
        if pending is not None:
            self._pending.pop(robot_id, None)
            self._linked_observations += 1
        self._observations += 1
        return seq

    # -- phase 5: close ----------------------------------------------------
    def close(self):
        """Record the apply calls that no observation answered, plus a summary."""
        if self._closed:
            return
        for robot_id, pending in sorted(self._pending.items()):
            self.sink.write({'kind': 'unanswered_apply', 'robot_id': robot_id,
                             'applies_to_seq': pending['seq'],
                             'producer_issue_seq': pending['issue_seq'],
                             'unanswered': True,
                             'note': 'the apply call was made; no later own observation '
                                     'was observed for this robot in this run'})
        for robot_id, open_ in sorted(self._open.items()):
            self.sink.write({'kind': 'unanswered_apply', 'robot_id': robot_id,
                             'applies_to_seq': open_['seq'],
                             'producer_issue_seq': open_['issue_seq'],
                             'unanswered': True,
                             'note': 'the apply call was made but no outcome was recorded '
                                     'for this robot in this run'})
        self._pending = {}
        self._open = {}
        self.sink.write({
            'kind': 'run_summary', 'episode_id': self.episode_id,
            'apply_calls': self._applied,
            'apply_returned': self._returned,
            'apply_exceptions': self._exceptions,
            'observations': self._observations,
            'observations_linked_to_an_apply': self._linked_observations,
            'producer_rows_read': self.producer.rows,
            'apply_callable': self._apply_identity,
            'environment_applied': 'unknown (this ledger does not observe the environment)',
            'transmission_acknowledged': 'unknown (no transport acknowledgement is observed)',
            'motion_observed': 'unknown (no motion evidence is collected)',
            'port_state': 'not captured by this ledger',
            'last_observation_state': ('the last own observation of a robot may precede '
                                       'its last apply; such an apply is listed as an '
                                       'unanswered_apply row'),
            'scope': 'consumer-side call accounting only; NOT a carry-success claim'})
        self._closed = True
        self.sink.close()
