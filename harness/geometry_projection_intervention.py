"""Controlled geometry-projection intervention seam (CPU-only, stdlib only).

Why this module exists
----------------------
The pinned geometry head injects the predicted geometry into the ACT
encoder through ONE linear projection::

    # implementation/geometry_policy.py, install_geometry_head
    conditioned[1] = conditioned[1] + model.geometry_to_state(geometry)

``geometry_to_state`` is a plain ``nn.Linear(3, dim)``.  The geometry
*prediction* (the visual head output) is computed and retained separately, so
the geometry contribution to the encoder state token can be toggled **without
touching the actor weights, the inputs, the seed, the protocol or the gates**.

That is the smallest intervention that separates "the geometry projection
contributes to the output" from "the actor is different".  Comparing two
different actors changes the checkpoint AND the presence of the geometry
conditioning path at the same time, so it cannot separate the two.

Scope of this module
--------------------
* This is the **seam**, not a runner and not a logger.  No runner, bundle or
  observer file is edited here, and no model is loaded or executed.
* The module imports **stdlib only**.  It never imports torch and never runs
  a learned forward.  It talks to the target module through the module's own
  **normal hook API** (``register_forward_hook``), not by monkeypatching
  global classes and not by installing a second geometry pipeline.
* Importing this module changes nothing.  The path is only altered inside
  the explicit context manager.

The two arms
------------
``mode='on'``
    The projection output is passed through unchanged.  The hook is installed
    and counted, but the returned object/value is preserved (identity
    included).  This is the CONTROL arm: it proves that installing the hook
    itself does not change the model.

``mode='off'``
    The projection output is replaced by a **fresh** zero-like tensor that
    preserves shape, dtype and device.  Only the projected contribution is
    zeroed.  The geometry prediction is still computed and retained, the
    weights are still the same weights, and the inputs are still the same
    inputs.

    The zero-ness of the replacement is part of the contract and is checked,
    not assumed:

    * **verified zero** -- the replacement was observed to be all zeros;
    * **unverified zero** -- the replacement could not be checked at all
      (the output object exposes no zero counter).  This is reported as
      *unverified*, never as verified;
    * **refused** -- the replacement was observed to carry **non-zero**
      values.  That contradicts the ``off`` contract, so it raises
      ``InterventionError``, is counted as a hook failure and is **not**
      counted as a successful zero replacement.  A non-zero contribution is
      never passed on as if it were a zeroed one.

Not established by this module
------------------------------
The evidence records the arm, the targeted source SHA, a module identity
**label**, the number of active hook calls and any failure.  It does NOT
establish model success, source authentication, or that a model forward
happened.  See ``docs/geometry_projection_intervention.md`` for the full
interpretation boundary.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Iterable, Optional, Sequence

SCHEMA = 'ugrp.geometry_projection_intervention.v1'

#: The two supported arms.
MODE_ON = 'on'
MODE_OFF = 'off'
MODES = (MODE_ON, MODE_OFF)

#: The attribute of the actor that carries the geometry -> state projection.
TARGET_ATTRIBUTE = 'geometry_to_state'

#: The upstream file whose behaviour is targeted.  It is READ (hashed) only;
#: it is never imported, edited or executed by this module.
DEFAULT_TARGET_SOURCE = ('/home/ubuntu/ugrp-retrain-geom-20261029/implementation/'
                          'geometry_policy.py')
DEFAULT_TARGET_SOURCE_SHA256 = ('3681da67642f681615b42673ae004690d2341d62b99c3c'
                                '6caeae647c8851788f')
#: Statements this module deliberately does NOT make.
NOT_ESTABLISHED = (
    'model success',
    'independent source authentication',
    'proof of a model forward',
    'transport or physical causation',
    'process or thread concurrency safety',
)


class InterventionError(RuntimeError):
    """The intervention refuses to run or cannot keep its own invariant."""


# --------------------------------------------------------------------- helpers

def sha256_file(path) -> str:
    """sha256 of a file, read only."""
    hasher = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            hasher.update(chunk)
    return hasher.hexdigest()


def identity_label(target) -> str:
    """A LABEL for the hooked module.

    This is an identity label, not authentication: it says what the object
    claims to be, not that the claim is true.
    """
    kind = type(target)
    return '%s:%s.%s' % (TARGET_ATTRIBUTE, kind.__module__, kind.__qualname__)


def _shape_of(value):
    shape = getattr(value, 'shape', None)
    return None if shape is None else tuple(shape)


def _same(a, b) -> bool:
    try:
        return bool(a == b)
    except Exception:                                   # noqa: BLE001
        return False


def _zero_like(output):
    """A FRESH zero-like tensor with the same shape, dtype and device.

    The construction goes through the output object's own API
    (``new_zeros``), so no framework import is needed here.  If the object
    does not expose that API the intervention refuses rather than guessing.

    A replacement that is **observed to be non-zero** is a CONTRADICTION of
    the ``off`` contract: it is refused with ``InterventionError`` and never
    returned.  A replacement whose zero-ness cannot be checked at all is a
    different situation -- it is reported as *unverified*, not as verified.
    """
    new_zeros = getattr(output, 'new_zeros', None)
    if not callable(new_zeros):
        raise InterventionError(
            'the projection output exposes no new_zeros() API: refusing to '
            'build a zero-like replacement')
    shape = _shape_of(output)
    if shape is None:
        raise InterventionError('the projection output exposes no shape')
    zeros = new_zeros(shape)
    if zeros is output:
        raise InterventionError('the zero-like replacement must be a fresh object')
    if not _same(_shape_of(zeros), shape):
        raise InterventionError('the zero-like replacement changed the shape')
    for attribute in ('dtype', 'device'):
        original = getattr(output, attribute, None)
        replacement = getattr(zeros, attribute, None)
        if original is not None and not _same(replacement, original):
            raise InterventionError(
                'the zero-like replacement changed the %s' % attribute)
    # The zero-ness itself is part of the contract: a replacement that is
    # OBSERVED to carry non-zero values contradicts the "off" arm and is
    # refused instead of being passed on as if it were a zero contribution.
    verified = _is_all_zero(zeros)
    if verified is False:
        raise InterventionError(
            'the zero-like replacement is not zero: the off arm would apply a '
            'non-zero contribution')
    return zeros, verified


def _is_all_zero(value) -> Optional[bool]:
    """Best-effort zero check.

    ``True``  -- verified zero.
    ``False`` -- verified NOT zero (a contradiction of the off contract).
    ``None``  -- the zero-ness could NOT be verified at all.
    """
    counter = getattr(value, 'count_nonzero', None)
    if callable(counter):
        try:
            return int(counter()) == 0
        except Exception:                               # noqa: BLE001
            return None
    return None


# ------------------------------------------------------------------ evidence

@dataclass(frozen=True)
class InterventionEvidence:
    """What the intervention can honestly say about itself."""

    arm: str
    mode: str
    target_attribute: str
    target_identity_label: str
    target_source_path: Optional[str]
    target_source_sha256: Optional[str]
    source_sha256_expected: Optional[str]
    source_sha256_matches: Optional[bool]
    hook_calls: int
    hook_failures: int
    zero_replacements: int
    zero_verification: str
    last_error: Optional[str]
    hook_installed: bool
    hook_removed: bool
    cleanup_error: Optional[str]
    not_established: Sequence[str] = NOT_ESTABLISHED

    def to_dict(self) -> dict:
        return {
            'schema': SCHEMA,
            'arm': self.arm,
            'mode': self.mode,
            'target_attribute': self.target_attribute,
            'target_identity_label': self.target_identity_label,
            'target_source_path': self.target_source_path,
            'target_source_sha256': self.target_source_sha256,
            'source_sha256_expected': self.source_sha256_expected,
            'source_sha256_matches': self.source_sha256_matches,
            'hook_calls': self.hook_calls,
            'hook_failures': self.hook_failures,
            'zero_replacements': self.zero_replacements,
            'zero_verification': self.zero_verification,
            'last_error': self.last_error,
            'hook_installed': self.hook_installed,
            'hook_removed': self.hook_removed,
            'cleanup_error': self.cleanup_error,
            'not_established': list(self.not_established),
        }


@dataclass(frozen=True)
class ArmRecord:
    """One arm of a future two-arm run, as a future runner would record it.

    Nothing here is filled in by this module: the seam only defines the
    SHAPE of the record so that a later runner records both arms the same
    way.
    """

    arm: str
    mode: str
    checkpoint_sha256: Optional[str] = None
    input_sha256: Optional[str] = None
    seed: Optional[int] = None
    proposal_status_path: Optional[str] = None
    raw_proposal_log_path: Optional[str] = None
    intervention: Optional[InterventionEvidence] = None

    def to_dict(self) -> dict:
        return {
            'arm': self.arm,
            'mode': self.mode,
            'checkpoint_sha256': self.checkpoint_sha256,
            'input_sha256': self.input_sha256,
            'seed': self.seed,
            'proposal_status_path': self.proposal_status_path,
            'raw_proposal_log_path': self.raw_proposal_log_path,
            'intervention': (self.intervention.to_dict()
                             if self.intervention is not None else None),
        }


def build_arm_document(records: Iterable[ArmRecord], *,
                       note: Optional[str] = None) -> dict:
    """The document a future runner should write for a two-arm comparison.

    It records, for BOTH arms, the checkpoint identity, the input identity,
    the seed and the raw-proposal paths, so the arms can be compared without
    guessing what else differed.
    """
    arms = [record.to_dict() for record in records]
    return {
        'schema': 'ugrp.geometry_projection_intervention.arms.v1',
        'arms': arms,
        'arm_count': len(arms),
        'note': note,
        'not_established': list(NOT_ESTABLISHED),
    }


def dump_arm_document(document: dict, path) -> str:
    """Write the arm document as JSON (exclusive create).  Returns the path."""
    target = Path(path)
    with open(target, 'x', encoding='utf-8') as stream:
        json.dump(document, stream, indent=1, sort_keys=True)
        stream.write('\n')
    return str(target)


# ------------------------------------------------------------- the intervention

#: Active interventions, keyed by ``id(model)``.  The model object is kept
#: alive by the value, so an id can never be recycled while a hook is active.
_ACTIVE: dict = {}


class GeometryProjectionIntervention:
    """Own ONE hook on an already-loaded model's geometry projection.

    Usage::

        with GeometryProjectionIntervention(model, mode='off') as arm:
            ...  # actor inference happens here

    The hook is removed on normal exit AND on exception.  Only this
    intervention's own hook is removed: nothing else is touched.

    The caller must own the actor's inference exclusively while the
    intervention is active.  Process/thread concurrency is NOT supported and
    is not claimed.
    """

    def __init__(self, model, *, mode: str = MODE_OFF,
                 source_path: Optional[str] = DEFAULT_TARGET_SOURCE,
                 source_sha256: Optional[str] = DEFAULT_TARGET_SOURCE_SHA256,
                 allow_source_drift: bool = False):
        if mode not in MODES:
            raise InterventionError('unsupported mode: %r (expected one of %s)'
                                     % (mode, ', '.join(MODES)))
        if model is None:
            raise InterventionError('a model is required')
        self._model = model
        self._mode = mode
        self._source_path = str(source_path) if source_path is not None else None
        self._source_sha256_expected = source_sha256
        self._allow_source_drift = bool(allow_source_drift)
        self._source_sha256: Optional[str] = None
        self._source_matches: Optional[bool] = None
        self._target = None
        self._handle = None
        self._hook_calls = 0
        self._hook_failures = 0
        self._zero_replacements = 0
        self._zero_verification = 'not_attempted'
        self._last_error: Optional[str] = None
        self._cleanup_error: Optional[str] = None
        self._hook_installed = False
        self._hook_removed = False
        self._entered = False
        self._exited = False
        self._active = False

    # -- introspection ---------------------------------------------------
    @property
    def mode(self) -> str:
        return self._mode

    @property
    def arm(self) -> str:
        """The arm label: 'on' keeps the projection, 'off' zeroes it."""
        return self._mode

    @property
    def hook_calls(self) -> int:
        return self._hook_calls

    @property
    def hook_failures(self) -> int:
        return self._hook_failures

    @property
    def zero_replacements(self) -> int:
        return self._zero_replacements

    @property
    def evidence(self) -> InterventionEvidence:
        return InterventionEvidence(
            arm=self.arm,
            mode=self._mode,
            target_attribute=TARGET_ATTRIBUTE,
            target_identity_label=(identity_label(self._target)
                                   if self._target is not None else None),
            target_source_path=self._source_path,
            target_source_sha256=self._source_sha256,
            source_sha256_expected=self._source_sha256_expected,
            source_sha256_matches=self._source_matches,
            hook_calls=self._hook_calls,
            hook_failures=self._hook_failures,
            zero_replacements=self._zero_replacements,
            zero_verification=self._zero_verification,
            last_error=self._last_error,
            hook_installed=self._hook_installed,
            hook_removed=self._hook_removed,
            cleanup_error=self._cleanup_error,
        )

    # -- lifecycle -------------------------------------------------------
    def __enter__(self) -> 'GeometryProjectionIntervention':
        if self._entered:
            raise InterventionError('this intervention instance is single use')
        key = id(self._model)
        if key in _ACTIVE:
            raise InterventionError(
                'a geometry projection intervention is already active on this '
                'model: nested activation is refused')
        self._entered = True
        try:
            self._check_source()
            self._resolve_target()
            self._install()
        except Exception:
            # Nothing is installed yet or the installation failed: make sure
            # no hook of ours survives.
            self._safe_remove()
            raise
        _ACTIVE[key] = self
        self._active = True
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        self._exited = True
        self._active = False
        _ACTIVE.pop(id(self._model), None)
        cleanup_failed = False
        try:
            self._remove()
        except Exception as error:                       # noqa: BLE001
            self._cleanup_error = repr(error)
            cleanup_failed = True
        if exc_type is not None:
            # The ORIGINAL exception is preserved: a cleanup problem is
            # recorded in the evidence, never raised over the user's error.
            return False
        if cleanup_failed:
            raise InterventionError('the hook could not be removed: %s'
                                     % self._cleanup_error)
        return False

    # -- internals -------------------------------------------------------
    def _check_source(self) -> None:
        if self._source_path is None:
            return
        path = Path(self._source_path)
        if not path.is_file():
            raise InterventionError('the targeted source file is missing: %s'
                                     % path)
        self._source_sha256 = sha256_file(path)
        if self._source_sha256_expected is None:
            return
        self._source_matches = (self._source_sha256 == self._source_sha256_expected)
        if not self._source_matches and not self._allow_source_drift:
            raise InterventionError(
                'the targeted source drifted: expected %s, found %s'
                % (self._source_sha256_expected, self._source_sha256))

    def _resolve_target(self) -> None:
        target = getattr(self._model, TARGET_ATTRIBUTE, None)
        if target is None:
            raise InterventionError(
                'the model has no %s projection: refusing to install a hook'
                % TARGET_ATTRIBUTE)
        if not callable(target):
            raise InterventionError('the %s projection is not callable'
                                    % TARGET_ATTRIBUTE)
        register = getattr(target, 'register_forward_hook', None)
        if not callable(register):
            raise InterventionError(
                'the %s projection exposes no register_forward_hook API: this '
                'module does not monkeypatch global classes'
                % TARGET_ATTRIBUTE)
        self._target = target

    def _install(self) -> None:
        def hook(module, args, output):                 # noqa: ARG001
            if not self._active:
                # A stale hook (only possible if the handle could not be
                # removed) must be inert, never a silent mode leak.
                return None
            self._hook_calls += 1
            if self._mode == MODE_ON:
                # CONTROL arm: the returned object/value is preserved.
                return None
            try:
                zeros, verified = _zero_like(output)
            except Exception as error:                   # noqa: BLE001
                # A failed zero construction is a FAILED replacement: it is
                # recorded as a hook failure and it never counts as a
                # successful zero replacement.
                self._hook_failures += 1
                self._last_error = repr(error)
                self._zero_verification = 'failed'
                raise
            self._zero_replacements += 1
            # "verified" is True (checked and zero) or None (the zero-ness
            # could NOT be checked).  The two are different statements and
            # are never conflated.
            self._zero_verification = ('verified_zero' if verified is True
                                       else 'unverified_zero')
            return zeros

        handle = self._target.register_forward_hook(hook)
        self._handle = handle
        # The hook IS registered at this point, whatever happens next.
        self._hook_installed = True
        if not callable(getattr(handle, 'remove', None)):
            # The hook cannot be removed later, so it is made INERT (the
            # intervention is never active, so it can never change an
            # output) and the intervention refuses rather than leaking a
            # mode.  The evidence keeps the TRUE install fact
            # (hook_installed=True) and records hook_removed=False with the
            # cleanup error, so a residual registered hook is visible
            # instead of being reported as "never installed".
            self._active = False
            self._cleanup_error = ('the hook handle exposes no remove() API: '
                                   'the hook stays registered but inert')
            raise InterventionError(
                'the hook handle exposes no remove() API: the intervention '
                'cannot guarantee its own cleanup')

    def _remove(self) -> None:
        if self._handle is None:
            return
        self._handle.remove()
        self._hook_removed = True

    def _safe_remove(self) -> None:
        try:
            self._remove()
        except Exception as error:                       # noqa: BLE001
            # The FIRST cleanup error is the informative one: a later attempt
            # must not overwrite the reason the hook could not be removed.
            if self._cleanup_error is None:
                self._cleanup_error = repr(error)


def geometry_projection_intervention(model, *, mode: str = MODE_OFF, **kwargs):
    """Convenience factory: the same object, as a context manager."""
    return GeometryProjectionIntervention(model, mode=mode, **kwargs)
