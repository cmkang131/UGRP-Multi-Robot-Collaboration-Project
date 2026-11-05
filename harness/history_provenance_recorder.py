"""Opt-in audit recorder for the issued-history producer (OwnHistory).

Contract (2026-11-05, UGRP-Pair, PR639 follow-up, fix round 1)
--------------------------------------------------------------
* The recorder is OPT-IN and OFF by default.  Without a recorder, OwnHistory
  behaves exactly as before: same observation dict, same return tuple, same
  raw issued values.
* The recorder writes only to its own storage.  It never changes an issued
  command, never enters the model observation dict, and never returns the
  model a different window.
* A FAILED issue call changes nothing: the raw deque and the recorder state
  stay exactly as they were.  Validation (command shape, origin label, time
  order) finishes BEFORE the single commit.
* It records TWO kinds of production-time facts and nothing else:
  1. the creation fact of the initial history replication (padding), and
  2. one event per OwnHistory.issue call.
* An issue event records that a command was issued at the producer.  It is NOT
  evidence that the command was applied to the environment, acknowledged, or
  that the robot moved.
* The origin of an issue call defaults to 'unknown'.  Only a caller that
  explicitly declares 'policy' or 'protocol_hold' is recorded as such; values
  never imply an origin, and a neutral command is never relabelled.
* Padding validity follows the v2 sidecar contract: validity is claimed only
  for a replicated neutral row, and padding is never an issued command.
* Identity is checked when the recorder is attached: the recorder's robot and
  episode must match the OwnHistory that owns it.  A recorder is bound once:
  it cannot be re-initialised, and padding cannot be injected after an issue.
* Time comparison is EXACT and non-decreasing, like the v2 sidecar.  A
  timestamp that moves backwards by any amount, including 1e-10 s, is refused.
* The live association is one explicit choice: an observation binds the
  recorder to that observation's sample id and window hash, and the next issue
  call INVALIDATES that association.  A snapshot can therefore only be
  verified against the observation that produced it.
* Stored records and snapshots are independent copies.  There is no API to
  relabel or overwrite a stored event after the fact.
* `recorder.verify(snapshot)` is the authoritative check: it compares the
  snapshot with the recorder's OWN stored events slot by slot (kind, slot
  index, sequence, origin, issued flag, padding validity, time, issue offset,
  row hash), with the raw window hash, the identity and the field schema.  A
  consistent forgery of several fields at once is refused.
* `verify_snapshot(...)` is only a structural check plus optional external
  identity and an optional raw window comparison.  It never certifies that a
  snapshot matches what was stored.

This module is non-physical and offline: no simulator, no model forward, no
network, no file writes.
"""
from __future__ import annotations

from collections import deque
from collections.abc import Mapping
import copy

from harness import command_history_provenance as p
from harness import grasp_act_contract as c

SCHEMA = 'ugrp.history_provenance_recorder.v1'
DECLARABLE_ORIGINS = ('policy', 'protocol_hold')
EVENT_KINDS = ('padding', 'issue')
SLOT_FIELDS = {'slot', 'seq', 'kind', 'origin', 'issued', 'padding_valid', 't',
               'issue_offset', 'row_hash'}
SNAPSHOT_FIELDS = {'schema', 'run_id', 'episode_id', 'robot_id', 'sample_id',
                   'slots', 'rows', 'raw_window_hash', 'issue_offset',
                   'event_count', 'note'}
NOTE = ('issued-command recorded at production time; not evidence of environment '
        'application, acknowledgement, or motion success')
HEX = set('0123456789abcdef')


class RecorderError(ValueError):
    """Raised when a record or a snapshot contradicts the producer's stream."""


def _nonempty_text(value, name):
    if type(value) is not str or not value.strip():
        raise RecorderError('%s must be a nonempty string' % name)
    return value


def _row_hash(command):
    return p.fingerprint([command])


def _issued_flag(origin, padding_valid):
    """Same rule as the v2 sidecar: policy/hold are issued, valid padding is
    not issued, everything else stays unknown."""
    if origin in DECLARABLE_ORIGINS:
        return True
    if origin == 'padding' and padding_valid is True:
        return False
    return None


class HistoryProvenanceRecorder:
    """Record what the producer issued, at the moment it issued it."""

    def __init__(self, *, run_id, episode_id, robot_id):
        self._run_id = _nonempty_text(run_id, 'run_id')
        self._episode_id = _nonempty_text(episode_id, 'episode_id')
        self._robot_id = _nonempty_text(robot_id, 'robot_id')
        self._events = []
        self._window = deque(maxlen=c.HISTORY)
        self._issue_offset = 0
        self._last_t = None
        self._bound = False
        self._padding_recorded = False
        self._association = None
        self._prepared = None

    # -- identity -------------------------------------------------------
    @property
    def run_id(self):
        return self._run_id

    @property
    def episode_id(self):
        return self._episode_id

    @property
    def robot_id(self):
        return self._robot_id

    @property
    def issue_offset(self):
        return self._issue_offset

    @property
    def event_count(self):
        return len(self._events)

    @property
    def association(self):
        """The current observation binding, or None when there is none."""
        return None if self._association is None else dict(self._association)

    # -- attachment -----------------------------------------------------
    def bind_identity(self, robot_id, episode_id):
        """Bind this recorder to one OwnHistory; a recorder is used once."""
        if self._bound:
            raise RecorderError('recorder is already bound to an owner')
        robot_id = _nonempty_text(robot_id, 'robot_id')
        episode_id = _nonempty_text(episode_id, 'episode_id')
        if robot_id != self._robot_id or episode_id != self._episode_id:
            raise RecorderError('recorder identity does not match its owner')
        self._bound = True
        return True

    # -- producer-time recording ---------------------------------------
    def record_initial_padding(self, command, *, count=c.HISTORY):
        """Record the creation fact of the initial history replication.

        The replicated rows are padding, not issued commands.  Validity follows
        the v2 contract: it is claimed only for a neutral replicated row, and
        the row values never imply a policy or hold origin.  This may run only
        once, and never after an issue call.
        """
        if not self._bound:
            raise RecorderError('recorder is not bound to an owner')
        if self._padding_recorded:
            raise RecorderError('initial padding was already recorded')
        if self._issue_offset:
            raise RecorderError('padding cannot be injected after an issue call')
        if type(count) is not int or count <= 0:
            raise RecorderError('padding count must be a positive integer')
        row = c.command(command)
        valid = not any(row['wheels']) and not any(row['duration_s'])
        for _ in range(count):
            self._append({'kind': 'padding', 'origin': 'padding',
                          'issued': False if valid else None,
                          'padding_valid': valid, 't': row['t'],
                          'issue_offset': None, 'note': NOTE}, row)
        self._padding_recorded = True
        return count

    def _validate_issue(self, command, origin):
        if not self._bound or not self._padding_recorded:
            raise RecorderError('issue requires a bound and initialized recorder')
        if type(origin) is not str or origin not in p.ORIGINS or origin == 'padding':
            raise RecorderError('issue origin must be policy, protocol_hold or unknown')
        try:
            row = c.command(command)
        except (ValueError, TypeError, KeyError) as exc:
            raise RecorderError('invalid issued command') from exc
        if self._last_t is not None and row['t'] < self._last_t:
            raise RecorderError('issue timestamp moved backwards')
        return row

    def prepare_issue(self, command, *, origin='unknown'):
        """Return an opaque, owner-local, single-use token for this generation.

        A newer preparation supersedes the older one. No event is recorded
        here and callers cannot edit the stored command through the token.
        """
        row = self._validate_issue(command, origin)
        token = object()
        self._prepared = (token, self._issue_offset, copy.deepcopy(row), origin)
        return token

    def commit_issue(self, token):
        """Revalidate and record this owner's current single-use preparation.

        Foreign, superseded, reused and stale tokens are refused before any
        event or observation association changes. Not a concurrency API.
        """
        prepared = self._prepared
        if prepared is None or token is not prepared[0] or prepared[1] != self._issue_offset:
            raise RecorderError('foreign, stale or consumed issue token')
        row = self._validate_issue(prepared[2], prepared[3])
        origin = prepared[3]
        offset = self._issue_offset
        self._append({'kind': 'issue', 'origin': origin,
                      'issued': True if origin in DECLARABLE_ORIGINS else None,
                      'padding_valid': False, 't': row['t'],
                      'issue_offset': offset, 'note': NOTE}, row)
        self._issue_offset += 1
        self._prepared = None
        self._association = None
        return offset

    def record_issue(self, command, *, origin='unknown'):
        """Validate and record one issue call in a single step."""
        return self.commit_issue(self.prepare_issue(command, origin=origin))

    def note_sample(self, sample_id, *, window=None):
        """Bind the recorder to one observation and its window hash."""
        sample = _nonempty_text(sample_id, 'sample_id')
        authoritative = p.fingerprint([row for _, row in self._window])
        if window is not None and p.fingerprint(list(window)) != authoritative:
            raise RecorderError('observation window does not match the recorded window')
        self._association = {'sample_id': sample, 'window_hash': authoritative}
        return sample

    def _append(self, event, row):
        event = dict(event)
        event['seq'] = len(self._events)
        stored = copy.deepcopy(event)
        self._events.append(stored)
        self._window.append((stored, copy.deepcopy(row)))
        self._last_t = stored['t']

    # -- audit API ------------------------------------------------------
    def stored_events(self):
        """Independent copies of every recorded event."""
        return copy.deepcopy(self._events)

    def _slots(self):
        slots = []
        for index, (event, row) in enumerate(self._window):
            slots.append({'slot': index, 'seq': event['seq'], 'kind': event['kind'],
                          'origin': event['origin'], 'issued': event['issued'],
                          'padding_valid': event['padding_valid'], 't': event['t'],
                          'issue_offset': event['issue_offset'],
                          'row_hash': _row_hash(row)})
        return slots

    def _rows(self):
        return [_row_hash(row) for _, row in self._window]

    def _raw_window_hash(self):
        return p.fingerprint([row for _, row in self._window])

    def audit_snapshot(self, *, sample_id=None, window=None):
        """Return an independent audit snapshot of the current window.

        The snapshot never enters the model observation.  When `window` is
        given it must be the issued window this recorder produced; a shifted
        or edited window is refused instead of being described.
        """
        sample = sample_id
        if sample is None:
            if self._association is None:
                raise RecorderError('sample_id is required for an audit snapshot')
            sample = self._association['sample_id']
        sample = _nonempty_text(sample, 'sample_id')
        if window is not None:
            if p.fingerprint(list(window)) != self._raw_window_hash():
                raise RecorderError('window does not match the recorded window')
        slots = self._slots()
        return {'schema': SCHEMA, 'run_id': self._run_id, 'episode_id': self._episode_id,
                'robot_id': self._robot_id, 'sample_id': sample, 'slots': slots,
                'rows': [slot['row_hash'] for slot in slots],
                'raw_window_hash': self._raw_window_hash(),
                'issue_offset': self._issue_offset, 'event_count': len(self._events),
                'note': NOTE}

    def verify(self, snapshot):
        """Authoritative check of a snapshot against the stored events.

        The snapshot is compared with this recorder's OWN records slot by
        slot, so a consistent forgery of several fields at once is refused.
        The sample id cannot be overridden by the caller: it must be the
        observation this recorder is currently bound to.
        """
        if self._association is None:
            raise RecorderError('no current observation association to verify against')
        sample = self._association['sample_id']
        verify_snapshot(snapshot, run_id=self._run_id, episode_id=self._episode_id,
                        robot_id=self._robot_id, sample_id=sample,
                        window=[row for _, row in self._window])
        if snapshot['slots'] != self._slots():
            raise RecorderError('snapshot slots do not match the recorded events')
        if snapshot['rows'] != self._rows():
            raise RecorderError('snapshot rows do not match the recorded events')
        if snapshot['raw_window_hash'] != self._raw_window_hash():
            raise RecorderError('snapshot raw window hash does not match the recorded window')
        if snapshot['raw_window_hash'] != self._association['window_hash']:
            raise RecorderError('snapshot window is not the observed window')
        if snapshot['issue_offset'] != self._issue_offset:
            raise RecorderError('snapshot issue offset is stale')
        if snapshot['event_count'] != len(self._events):
            raise RecorderError('snapshot event count is stale')
        return True


def verify_snapshot(snapshot, *, run_id=None, episode_id=None, robot_id=None,
                    sample_id=None, window=None):
    """Structural check of a snapshot, with optional external expectations.

    This function checks the FIELD SCHEMA, the TYPES, the slot index range,
    the sequence and offset ranges, the kind/origin consistency, the row hash
    format, an externally supplied identity, and an optionally supplied raw
    window.  It does NOT certify that the snapshot matches what was recorded:
    only `HistoryProvenanceRecorder.verify` can do that, and it needs the
    recorder's own events.  Without `window` this function makes no claim
    about the truth of the recorded content.
    """
    if not isinstance(snapshot, Mapping) or set(snapshot) != SNAPSHOT_FIELDS:
        raise RecorderError('snapshot field whitelist mismatch')
    if snapshot['schema'] != SCHEMA:
        raise RecorderError('unknown snapshot schema')
    for key, expected in (('run_id', run_id), ('episode_id', episode_id),
                          ('robot_id', robot_id), ('sample_id', sample_id)):
        if expected is not None and snapshot[key] != expected:
            raise RecorderError('snapshot %s does not match this identity' % key)
    for key in ('run_id', 'episode_id', 'robot_id', 'sample_id'):
        if type(snapshot[key]) is not str or not snapshot[key]:
            raise RecorderError('snapshot %s must be a nonempty string' % key)
    if snapshot['note'] != NOTE:
        raise RecorderError('snapshot evidence limitation note mismatch')
    for key in ('issue_offset', 'event_count'):
        if type(snapshot[key]) is not int or snapshot[key] < 0:
            raise RecorderError('snapshot counters must be nonnegative integers')
    initial_count = snapshot['event_count'] - snapshot['issue_offset']
    if initial_count <= 0:
        raise RecorderError('snapshot must include initial padding creation')
    slots = snapshot['slots']
    if type(slots) is not list or not slots:
        raise RecorderError('snapshot slots must be a nonempty list')
    if len(slots) != min(snapshot['event_count'], c.HISTORY):
        raise RecorderError('snapshot slot count does not match event count')
    seqs = []
    times = []
    for index, slot in enumerate(slots):
        if not isinstance(slot, Mapping) or set(slot) != SLOT_FIELDS:
            raise RecorderError('snapshot slot field whitelist mismatch')
        if type(slot['slot']) is not int or slot['slot'] != index:
            raise RecorderError('slot index must match the slot position')
        if type(slot['seq']) is not int or slot['seq'] < 0:
            raise RecorderError('slot sequence numbers must be nonnegative integers')
        seqs.append(slot['seq'])
        if type(slot['kind']) is not str or slot['kind'] not in EVENT_KINDS:
            raise RecorderError('unknown slot kind')
        origin = slot['origin']
        if type(origin) is not str or origin not in p.ORIGINS:
            raise RecorderError('unknown slot origin')
        if type(slot['padding_valid']) is not bool:
            raise RecorderError('slot padding validity must be a boolean')
        if slot['issued'] is not _issued_flag(origin, slot['padding_valid']):
            raise RecorderError('slot issued flag contradicts its origin')
        try:
            times.append(c.finite(slot['t']))
        except ValueError as exc:
            raise RecorderError('slot time must be finite numeric') from exc
        if slot['kind'] == 'padding':
            if origin != 'padding' or slot['seq'] >= initial_count:
                raise RecorderError('padding kind, origin and sequence disagree')
        elif (origin == 'padding' or slot['padding_valid']
              or slot['seq'] < initial_count
              or slot['issue_offset'] != slot['seq'] - initial_count):
            raise RecorderError('issue kind, origin and offset disagree')
        if slot['kind'] == 'issue':
            if type(slot['issue_offset']) is not int or slot['issue_offset'] < 0:
                raise RecorderError('issue slot offset must be a nonnegative integer')
        elif slot['issue_offset'] is not None:
            raise RecorderError('padding slot cannot carry an issue offset')
        row_hash = slot['row_hash']
        if type(row_hash) is not str or len(row_hash) != 64 or set(row_hash) - HEX:
            raise RecorderError('row hash must be a sha256 digest')
    if times != sorted(times):
        raise RecorderError('snapshot timestamps moved backwards')
    if seqs != list(range(snapshot['event_count'] - len(slots), snapshot['event_count'])):
        raise RecorderError('snapshot sequence must end at current event count')
    if len(set(seqs)) != len(seqs):
        raise RecorderError('duplicate slot sequence number')
    if any(second != first + 1 for first, second in zip(seqs, seqs[1:])):
        raise RecorderError('slot sequence numbers must be consecutive')
    rows = snapshot['rows']
    if type(rows) is not list or len(rows) != len(slots):
        raise RecorderError('snapshot rows must match the slot count')
    for slot, row_hash in zip(slots, rows):
        if slot['row_hash'] != row_hash:
            raise RecorderError('snapshot row hash does not match its slot')
    raw_hash = snapshot['raw_window_hash']
    if type(raw_hash) is not str or len(raw_hash) != 64 or set(raw_hash) - HEX:
        raise RecorderError('snapshot raw window hash must be a sha256 digest')
    for key in ('issue_offset', 'event_count'):
        if type(snapshot[key]) is not int or snapshot[key] < 0:
            raise RecorderError('snapshot %s must be a nonnegative integer' % key)
    if snapshot['issue_offset'] > snapshot['event_count']:
        raise RecorderError('snapshot issue offset exceeds its event count')
    if window is not None:
        raw = list(window)
        try:
            sidecar = p.describe(raw, origins=[slot['origin'] for slot in slots],
                                 padding_valid=[slot['padding_valid'] for slot in slots])
        except (ValueError, TypeError, KeyError) as exc:
            raise RecorderError('window violates the issued command contract') from exc
        if sidecar['raw_sha256'] != raw_hash:
            raise RecorderError('window does not match the snapshot')
        if [_row_hash(command) for command in raw] != rows:
            raise RecorderError('window rows do not match the snapshot rows')
        if [command['t'] for command in raw] != [slot['t'] for slot in slots]:
            raise RecorderError('window time does not match snapshot slots')
    return True
