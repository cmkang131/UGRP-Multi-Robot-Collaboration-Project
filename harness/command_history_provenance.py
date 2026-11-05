"""Issued-command provenance sidecar: the raw issued facts stay untouched.

Contract (2026-11-05, UGRP-Pair)
--------------------------------
* A real policy stop and a real protocol hold are BOTH issued facts.  This
  module never removes, rewrites, relabels, or replaces them, and never turns a
  stop or a hold into a moving command.
* Padding is not an issued command.  It is only marked in a sidecar, and that
  sidecar is never injected into the model observation dict.
* Unknown provenance stays unknown.  Nothing is inferred from values, timing,
  repetition, or neutrality.
* The API never mutates the caller's command list and never asks the caller to
  replace the raw window with a normalized object.  Validation results are
  reported next to the raw window, not in place of it.
* A prior is accepted only when it does not postdate the window start.  A prior that is
  itself a real stop (zero wheels) is a normal issued command and is accepted.

This module is a non-physical, offline contract only: no simulator, no model
forward, no network, no file writes.  It repairs nothing and duplicates no
earlier history-repair candidate.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
import json

from harness import grasp_act_contract as c

SCHEMA = 'ugrp.command_history.provenance.v2'
ORIGINS = ('policy', 'protocol_hold', 'padding', 'unknown')
ISSUED_ORIGINS = ('policy', 'protocol_hold')
SIDECAR_FIELDS = {'schema', 'length', 'origins', 'issued', 'padding_valid',
                  'raw_sha256', 'counts'}


class ProvenanceError(ValueError):
    """Raised when a sidecar or a prior contradicts the issued history."""


def _canonical(command):
    """Stable text for one raw command; values only, never a rewritten command."""
    return json.dumps(command, sort_keys=True, separators=(',', ':'),
                      allow_nan=False)


def fingerprint(commands):
    """SHA256 over the raw command values of a window.

    The digest covers what was issued, so a later audit can prove that the raw
    history was not changed.  The command objects themselves are never touched.
    """
    hasher = hashlib.sha256()
    for command in commands:
        hasher.update(_canonical(command).encode('utf-8'))
        hasher.update(b'\n')
    return hasher.hexdigest()


def copy_commands(commands):
    """Independent copies of a window, so a caller cannot mutate the raw window
    through an alias."""
    return [json.loads(_canonical(command)) for command in commands]


def _validated(commands):
    """Contract-check a window without replacing any of its rows."""
    if isinstance(commands, (str, bytes)) or not isinstance(commands, Sequence):
        raise ProvenanceError('issued command list required')
    if not commands:
        raise ProvenanceError('nonempty issued history required')
    times = [c.command(command)['t'] for command in commands]
    if times != sorted(times):
        raise ProvenanceError('command history must be in nondecreasing time order')
    return list(commands)


def _validate_origins(origins, length):
    if origins is None:
        return ['unknown'] * length
    if isinstance(origins, (str, bytes)) or not isinstance(origins, Sequence):
        raise ProvenanceError('origins must be a sequence')
    if len(origins) != length:
        raise ProvenanceError('origin count must match the issued history length')
    labels = []
    for label in origins:
        if label is None:
            labels.append('unknown')
        elif isinstance(label, str) and label in ORIGINS:
            labels.append(label)
        else:
            raise ProvenanceError('unknown origin label: %r' % (label,))
    return labels


def _validate_padding_valid(padding_valid, labels):
    if padding_valid is None:
        return [False] * len(labels)
    if isinstance(padding_valid, (str, bytes)) or not isinstance(padding_valid, Sequence):
        raise ProvenanceError('padding validity must be a sequence')
    if len(padding_valid) != len(labels):
        raise ProvenanceError('padding validity length must match the issued history length')
    validity = []
    for index, flag in enumerate(padding_valid):
        if type(flag) is not bool:
            raise ProvenanceError('padding validity entries must be booleans')
        if flag and labels[index] != 'padding':
            raise ProvenanceError('padding validity may only mark padding slots')
        validity.append(flag)
    return validity


def _issued_flag(label, padding_valid=False):
    """Caller assertion: True issued, False valid padding, else unknown."""
    if label in ISSUED_ORIGINS:
        return True
    return False if label == 'padding' and padding_valid else None


def describe(commands, *, origins=None, padding_valid=None):
    """Build a provenance sidecar for one issued window.

    `commands` is the raw issued window and is returned nowhere and changed
    nowhere: this function only reports.  `origins` is one label per slot in
    ORIGINS (a missing label or None means 'unknown'), and `padding_valid` is
    one boolean per slot that says whether a padding slot is valid padding;
    validity may only be claimed for slots labelled 'padding'.  Neither
    argument is inferred from the command values.

    The returned sidecar contains labels, counts and a digest of the raw
    values.  It holds no command object, so it can never be an alias of the
    issued window, and it is not part of the model observation contract.
    """
    raw = _validated(commands)
    labels = _validate_origins(origins, len(raw))
    validity = _validate_padding_valid(padding_valid, labels)
    for command, valid in zip(raw, validity):
        # A necessary consistency check, never an inference of event origin.
        if valid and (any(command['wheels']) or any(command['duration_s'])):
            raise ProvenanceError('valid neutral padding cannot contain wheel motion')
    issued = [_issued_flag(label, valid) for label, valid in zip(labels, validity)]
    counts = {'policy': labels.count('policy'),
              'protocol_hold': labels.count('protocol_hold'),
              'padding': labels.count('padding'),
              'unknown': labels.count('unknown'),
              'issued': sum(1 for flag in issued if flag is True),
              'padding_valid': sum(1 for flag in validity if flag)}
    return {'schema': SCHEMA, 'length': len(raw), 'origins': labels, 'issued': issued,
            'padding_valid': validity, 'raw_sha256': fingerprint(raw), 'counts': counts}


def validate_sidecar(commands, sidecar):
    """Check that a sidecar matches this raw issued window; never rewrites it."""
    raw = _validated(commands)
    if not isinstance(sidecar, Mapping) or set(sidecar) != SIDECAR_FIELDS:
        raise ProvenanceError('sidecar field whitelist mismatch')
    if sidecar['schema'] != SCHEMA:
        raise ProvenanceError('unknown sidecar schema')
    if type(sidecar['length']) is not int or sidecar['length'] != len(raw):
        raise ProvenanceError('sidecar length does not match the issued history')
    for key in ('origins', 'issued', 'padding_valid'):
        if type(sidecar[key]) is not list or len(sidecar[key]) != len(raw):
            raise ProvenanceError('sidecar arrays must be lists matching history length')
    if any(type(label) is not str or label not in ORIGINS
           for label in sidecar['origins']):
        raise ProvenanceError('stored origins must contain explicit origin labels')
    expected = describe(raw, origins=sidecar['origins'],
                        padding_valid=sidecar['padding_valid'])
    for flag, wanted in zip(sidecar['issued'], expected['issued']):
        if flag is not wanted:
            raise ProvenanceError('sidecar issued flag contradicts the origin label')
    counts = sidecar['counts']
    if (type(counts) is not dict or set(counts) != set(expected['counts'])
            or any(type(value) is not int or value < 0 for value in counts.values())
            or counts != expected['counts']):
        raise ProvenanceError('sidecar counts must match origin and validity arrays')
    if type(sidecar['raw_sha256']) is not str or sidecar['raw_sha256'] != expected['raw_sha256']:
        raise ProvenanceError('sidecar does not describe this raw issued history')
    # Rebuild from validated scalars: never return caller-owned mutable objects.
    return expected


def window_start(commands):
    """First timestamp of the window; the window is issued in time order."""
    raw = _validated(commands)
    return raw[0]['t']


def resolve_prior(commands, prior, *, origin='unknown'):
    """Return a temporally accepted prior candidate for this window.

    A prior must not postdate the window start.  A prior that is itself a real
    stop (all wheels zero) is a normal issued command and is accepted.  The
    returned dict is a validated copy; the caller's raw window and raw prior
    are unchanged. Origin is a caller assertion, not authenticated evidence.
    The default unknown performs only temporal validation; it does not certify
    issuance. An explicitly declared padding prior is rejected.
    """
    raw = _validated(commands)
    if type(origin) is not str or origin not in ORIGINS or origin == 'padding':
        raise ProvenanceError('prior cannot have padding or invalid origin')
    if not isinstance(prior, Mapping):
        raise ProvenanceError('prior command required')
    row = c.command(prior)
    if row['t'] > window_start(raw):
        raise ProvenanceError('prior command must not postdate the window start')
    return dict(row)
