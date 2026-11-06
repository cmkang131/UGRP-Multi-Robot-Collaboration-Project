"""Tests for the controlled geometry-projection intervention seam.

What is verified here (CPU only, no torch, no model, no simulator):

* the **default path is unchanged**: importing the module and NOT entering
  the context manager leaves the model's projection output exactly as it
  was;
* the ``on`` arm preserves the returned object/value (identity included) and
  counts the hook calls -- it is the control arm that proves the hook
  itself changes nothing;
* the ``off`` arm replaces ONLY the projected contribution with a fresh
  zero-like output that preserves shape, dtype and device, and it does NOT
  mutate the weights, the inputs or the retained geometry prediction;
* normal exit and exception exit both remove ONLY this intervention's own
  hook, and no mode leaks into the next arm;
* an invalid mode, an unsupported target, a reused context and a nested
  activation on the same model are refused;
* the original error of the caller survives an exception inside the
  intervention;
* the source drift of the targeted upstream file is detected.

BOUNDARY
--------
These tests use **explicit fake hook modules and fake tensors**.  They do
NOT validate real PyTorch behaviour, real tensor dtypes/devices, or any
learned output.  They validate the seam's own contract only.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / 'harness' / 'geometry_projection_intervention.py'

TARGET_SOURCE = ('/home/ubuntu/ugrp-retrain-geom-20261029/implementation/'
                 'geometry_policy.py')
TARGET_SOURCE_SHA = ('3681da67642f681615b42673ae004690d2341d62b99c3c6caeae647'
                     'c8851788f')


def _load():
    name = 'ugrp_geometry_intervention_test'
    spec = importlib.util.spec_from_file_location(name, str(MODULE_PATH))
    module = importlib.util.module_from_spec(spec)
    # The module uses dataclasses with postponed annotations, so it must be
    # registered in sys.modules BEFORE it is executed (the dataclass
    # machinery resolves the annotation namespaces through sys.modules).
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope='module')
def intervention():
    return _load()


# ------------------------------------------------------------- fake fixtures

class FakeTensor:
    """A fake tensor with the API the seam relies on.

    It mimics only what the seam touches: ``shape``, ``dtype``, ``device``,
    ``new_zeros`` and ``count_nonzero``.  It is NOT a tensor.
    """

    def __init__(self, values, dtype='float32', device='cpu'):
        self.values = list(values)
        self.dtype = dtype
        self.device = device

    @property
    def shape(self):
        return (len(self.values),)

    def new_zeros(self, shape):
        size = shape[0] if shape else 0
        return FakeTensor([0.0] * size, dtype=self.dtype, device=self.device)

    def count_nonzero(self):
        return sum(1 for value in self.values if value != 0)

    def copy_values(self):
        return list(self.values)


class FakeProjection:
    """A fake ``geometry_to_state`` with a normal forward-hook API."""

    def __init__(self, values=(1.0, 2.0, 3.0), dtype='float32', device='cpu'):
        self.values = list(values)
        self.dtype = dtype
        self.device = device
        self.weight = ('weight-sentinel', tuple(self.values))
        self.bias = ('bias-sentinel',)
        self.calls = 0
        self._hooks = []

    def forward(self, geometry):
        self.calls += 1
        return FakeTensor(self.values, dtype=self.dtype, device=self.device)

    def register_forward_hook(self, hook):
        handle = FakeHandle(self, hook)
        self._hooks.append(hook)
        return handle

    def active_hooks(self):
        return list(self._hooks)

    def __call__(self, geometry):
        result = self.forward(geometry)
        for hook in list(self._hooks):
            replacement = hook(self, (geometry,), result)
            if replacement is not None:
                result = replacement
        return result


class FakeHandle:
    def __init__(self, owner, hook):
        self._owner = owner
        self._hook = hook
        self.removed = False

    def remove(self):
        self.removed = True
        if self._hook in self._owner._hooks:
            self._owner._hooks.remove(self._hook)


class FakeModel:
    """A fake actor: the projection plus a retained geometry prediction."""

    def __init__(self, projection=None):
        self.geometry_to_state = projection or FakeProjection()
        self._geometry_prediction = ('retained-prediction', 0.5)
        self.backbone = object()
        self.encoder = object()

    def forward(self):
        return self.geometry_to_state(('geometry-input',))


class BrokenProjection:
    """A projection without the normal hook API."""

    def forward(self, geometry):
        return FakeTensor([1.0])

    def __call__(self, geometry):
        return self.forward(geometry)


class UnremovableProjection(FakeProjection):
    def register_forward_hook(self, hook):
        self._hooks.append(hook)
        return object()          # no remove() API


class NonZeroFakeTensor(FakeTensor):
    """A fake whose ``new_zeros`` returns NON-ZERO values.

    This is the coordinator's counterexample: the shape, dtype and device are
    all preserved, so a check that only looks at those would pass, while the
    replacement is not a zero contribution at all.
    """

    def new_zeros(self, shape):
        size = shape[0] if shape else 0
        return NonZeroFakeTensor([9.0] * size, dtype=self.dtype,
                                  device=self.device)


class NonZeroProjection(FakeProjection):
    def forward(self, geometry):
        self.calls += 1
        return NonZeroFakeTensor(self.values, dtype=self.dtype, device=self.device)


class UnverifiableFakeTensor(FakeTensor):
    """A fake with NO zero counter: the zero-ness cannot be checked."""

    def new_zeros(self, shape):
        size = shape[0] if shape else 0
        return UnverifiableFakeTensor([0.0] * size, dtype=self.dtype,
                                      device=self.device)

    def count_nonzero(self):
        raise AttributeError('this fake exposes no zero counter')


class UnverifiableProjection(FakeProjection):
    def forward(self, geometry):
        self.calls += 1
        return UnverifiableFakeTensor(self.values, dtype=self.dtype,
                                      device=self.device)


# -------------------------------------------------------------- default path

def test_the_module_imports_stdlib_only(intervention):
    source = MODULE_PATH.read_text(encoding='utf-8')
    assert 'import torch' not in source
    assert 'from torch' not in source


def test_the_default_path_is_unchanged(intervention):
    """Not entering the intervention must not change the output at all."""
    model = FakeModel()
    before = model.geometry_to_state(('geometry-input',)).copy_values()
    after = model.geometry_to_state(('geometry-input',)).copy_values()
    assert before == after == [1.0, 2.0, 3.0]
    assert model.geometry_to_state.active_hooks() == []


def test_creating_the_intervention_without_entering_changes_nothing(intervention):
    model = FakeModel()
    arm = intervention.GeometryProjectionIntervention(model, mode='off',
                                                          source_path=None)
    assert arm.mode == 'off'
    assert model.geometry_to_state.active_hooks() == []
    assert model.geometry_to_state(('g',)).copy_values() == [1.0, 2.0, 3.0]


# ------------------------------------------------------------------- on arm

def test_the_on_arm_preserves_the_returned_object(intervention):
    """The control arm: the very same values come back."""
    model = FakeModel()
    with intervention.GeometryProjectionIntervention(model, mode='on',
                                                          source_path=None) as arm:
        result = model.geometry_to_state(('g',))
        assert result.copy_values() == [1.0, 2.0, 3.0]
        assert arm.zero_replacements == 0
        assert arm.hook_calls == 1
    assert model.geometry_to_state.active_hooks() == []


def test_the_on_arm_does_not_change_the_weights_or_the_prediction(intervention):
    model = FakeModel()
    weight_before = model.geometry_to_state.weight
    prediction_before = model._geometry_prediction
    with intervention.GeometryProjectionIntervention(model, mode='on',
                                                          source_path=None):
        model.forward()
    assert model.geometry_to_state.weight == weight_before
    assert model._geometry_prediction == prediction_before


# ------------------------------------------------------------------ off arm

def test_the_off_arm_returns_a_fresh_zero_like_output(intervention):
    model = FakeModel()
    with intervention.GeometryProjectionIntervention(model, mode='off',
                                                          source_path=None) as arm:
        result = model.geometry_to_state(('g',))
        assert result.copy_values() == [0.0, 0.0, 0.0]
        assert result is not model.geometry_to_state.values
        assert arm.zero_replacements == 1
        assert arm.hook_calls == 1
        assert arm.hook_failures == 0
        assert arm.evidence.zero_verification == 'verified_zero'


def test_the_off_arm_preserves_shape_dtype_and_device(intervention):
    model = FakeModel(FakeProjection(values=(4.0, 5.0), dtype='float64',
                                     device='cuda:0'))
    with intervention.GeometryProjectionIntervention(model, mode='off',
                                                          source_path=None):
        result = model.geometry_to_state(('g',))
    assert result.shape == (2,)
    assert result.dtype == 'float64'
    assert result.device == 'cuda:0'


def test_the_off_arm_does_not_mutate_weights_inputs_or_prediction(intervention):
    model = FakeModel()
    weight_before = model.geometry_to_state.weight
    bias_before = model.geometry_to_state.bias
    values_before = list(model.geometry_to_state.values)
    prediction_before = model._geometry_prediction
    geometry_input = ('geometry-input-object',)
    with intervention.GeometryProjectionIntervention(model, mode='off',
                                                          source_path=None):
        model.geometry_to_state(geometry_input)
    assert model.geometry_to_state.weight == weight_before
    assert model.geometry_to_state.bias == bias_before
    assert model.geometry_to_state.values == values_before
    assert model._geometry_prediction == prediction_before
    assert geometry_input == ('geometry-input-object',)


def test_the_off_arm_still_calls_the_projection(intervention):
    """The projection is still evaluated: only its CONTRIBUTION is replaced."""
    model = FakeModel()
    with intervention.GeometryProjectionIntervention(model, mode='off',
                                                          source_path=None):
        model.geometry_to_state(('g',))
    assert model.geometry_to_state.calls == 1


def test_the_off_arm_does_not_replace_the_projection_object(intervention):
    model = FakeModel()
    projection_before = model.geometry_to_state
    with intervention.GeometryProjectionIntervention(model, mode='off',
                                                          source_path=None):
        model.geometry_to_state(('g',))
    assert model.geometry_to_state is projection_before


# --------------------------------------------- the non-zero counterexample

def test_an_observed_non_zero_replacement_is_refused(intervention):
    """The coordinator's counterexample: new_zeros returns [9, 9, 9].

    Shape, dtype and device are all preserved, so a check that only looks at
    those would pass -- but the replacement is NOT a zero contribution.  It
    must be refused, never returned.
    """
    model = FakeModel(NonZeroProjection())
    with pytest.raises(intervention.InterventionError):
        with intervention.GeometryProjectionIntervention(model, mode='off',
                                                          source_path=None) as arm:
            model.geometry_to_state(('g',))
            arm  # the arm is bound only if the block completes
    # the hook was removed even though the call failed
    assert model.geometry_to_state.active_hooks() == []
    # and the model behaves as before
    assert model.geometry_to_state(('g',)).copy_values() == [1.0, 2.0, 3.0]


def test_an_observed_non_zero_replacement_is_counted_as_a_failure(intervention):
    model = FakeModel(NonZeroProjection())
    arm = intervention.GeometryProjectionIntervention(model, mode='off',
                                                          source_path=None)
    with pytest.raises(intervention.InterventionError):
        with arm:
            model.geometry_to_state(('g',))
    evidence = arm.evidence
    # a FAILED replacement is not a successful zero replacement
    assert evidence.zero_replacements == 0
    assert evidence.hook_failures == 1
    assert evidence.hook_calls == 1
    assert evidence.zero_verification == 'failed'
    assert evidence.last_error is not None
    assert 'not zero' in evidence.last_error
    assert evidence.hook_removed is True


def test_the_non_zero_replacement_is_never_returned(intervention):
    """The off arm must not pass a non-zero contribution on as if it were zero."""
    model = FakeModel(NonZeroProjection())
    returned = []
    with pytest.raises(intervention.InterventionError):
        with intervention.GeometryProjectionIntervention(model, mode='off',
                                                          source_path=None):
            returned.append(model.geometry_to_state(('g',)))
    assert returned == []


def test_a_failed_replacement_leaves_no_mode_leak(intervention):
    model = FakeModel(NonZeroProjection())
    with pytest.raises(intervention.InterventionError):
        with intervention.GeometryProjectionIntervention(model, mode='off',
                                                          source_path=None):
            model.geometry_to_state(('g',))
    assert model.geometry_to_state.active_hooks() == []
    # the next arm starts clean and behaves normally
    with intervention.GeometryProjectionIntervention(model, mode='on',
                                                          source_path=None):
        assert model.geometry_to_state(('g',)).copy_values() == [1.0, 2.0, 3.0]


def test_the_unverifiable_zero_is_reported_as_unverified(intervention):
    """Verification UNAVAILABLE is not the same as a verified contradiction."""
    model = FakeModel(UnverifiableProjection())
    with intervention.GeometryProjectionIntervention(model, mode='off',
                                                          source_path=None) as arm:
        result = model.geometry_to_state(('g',))
        assert result.copy_values() == [0.0, 0.0, 0.0]
        assert arm.zero_replacements == 1
        assert arm.hook_failures == 0
    evidence = arm.evidence
    # it is explicitly NOT claimed as verified
    assert evidence.zero_verification == 'unverified_zero'
    assert evidence.zero_verification != 'verified_zero'
    assert evidence.zero_verification != 'failed'


def test_the_counterexample_is_not_a_verified_contradiction(intervention):
    """The two situations are distinct and are never conflated."""
    nonzero = intervention.GeometryProjectionIntervention(
        FakeModel(NonZeroProjection()), mode='off', source_path=None)
    unverifiable = intervention.GeometryProjectionIntervention(
        FakeModel(UnverifiableProjection()), mode='off', source_path=None)
    with pytest.raises(intervention.InterventionError):
        with nonzero:
            nonzero._model.geometry_to_state(('g',))
    with unverifiable:
        unverifiable._model.geometry_to_state(('g',))
    assert nonzero.evidence.zero_verification == 'failed'
    assert nonzero.evidence.zero_replacements == 0
    assert unverifiable.evidence.zero_verification == 'unverified_zero'
    assert unverifiable.evidence.zero_replacements == 1


def test_the_original_error_wins_over_a_failed_replacement(intervention):
    """A caller's error is preserved even if a replacement failed before it."""
    class Boom(Exception):
        pass

    model = FakeModel(NonZeroProjection())
    original = Boom('the original failure')
    with pytest.raises(Boom) as caught:
        with intervention.GeometryProjectionIntervention(model, mode='off',
                                                          source_path=None):
            try:
                model.geometry_to_state(('g',))
            except intervention.InterventionError:
                pass
            raise original
    assert caught.value is original


# ------------------------------------------------------------------- cleanup

def test_the_normal_exit_removes_only_our_hook(intervention):
    model = FakeModel()
    other = model.geometry_to_state.register_forward_hook(
        lambda module, args, output: None)
    with intervention.GeometryProjectionIntervention(model, mode='off',
                                                          source_path=None):
        assert len(model.geometry_to_state.active_hooks()) == 2
    assert len(model.geometry_to_state.active_hooks()) == 1
    assert other.removed is False
    # the foreign hook stays, ours is gone
    assert model.geometry_to_state(('g',)).copy_values() == [1.0, 2.0, 3.0]


def test_no_mode_leaks_into_the_next_arm(intervention):
    model = FakeModel()
    with intervention.GeometryProjectionIntervention(model, mode='off',
                                                          source_path=None):
        assert model.geometry_to_state(('g',)).copy_values() == [0.0, 0.0, 0.0]
    assert model.geometry_to_state(('g',)).copy_values() == [1.0, 2.0, 3.0]
    with intervention.GeometryProjectionIntervention(model, mode='on',
                                                          source_path=None):
        assert model.geometry_to_state(('g',)).copy_values() == [1.0, 2.0, 3.0]
    assert model.geometry_to_state(('g',)).copy_values() == [1.0, 2.0, 3.0]


def test_the_exception_exit_removes_the_hook(intervention):
    model = FakeModel()
    with pytest.raises(ValueError):
        with intervention.GeometryProjectionIntervention(model, mode='off',
                                                          source_path=None):
            model.geometry_to_state(('g',))
            raise ValueError('caller failure')
    assert model.geometry_to_state.active_hooks() == []
    assert model.geometry_to_state(('g',)).copy_values() == [1.0, 2.0, 3.0]


def test_the_original_error_survives_an_exception_inside_the_intervention(
        intervention):
    class Boom(Exception):
        pass

    model = FakeModel()
    original = Boom('the original failure')
    with pytest.raises(Boom) as caught:
        with intervention.GeometryProjectionIntervention(model, mode='off',
                                                          source_path=None):
            raise original
    assert caught.value is original


# ------------------------------------------------------------------ refusals

def test_an_invalid_mode_is_refused(intervention):
    model = FakeModel()
    with pytest.raises(intervention.InterventionError):
        intervention.GeometryProjectionIntervention(model, mode='maybe')


def test_an_unsupported_target_is_refused(intervention):
    class NoProjection:
        pass

    with pytest.raises(intervention.InterventionError):
        with intervention.GeometryProjectionIntervention(NoProjection(), mode='off',
                                                       source_path=None):
            pass


def test_a_target_without_the_hook_api_is_refused(intervention):
    """No global monkeypatching: the module's own hook API is required."""
    model = FakeModel(BrokenProjection())
    with pytest.raises(intervention.InterventionError):
        with intervention.GeometryProjectionIntervention(model, mode='off',
                                                          source_path=None):
            pass


def test_a_target_with_an_unremovable_handle_is_refused(intervention):
    model = FakeModel(UnremovableProjection())
    with pytest.raises(intervention.InterventionError):
        with intervention.GeometryProjectionIntervention(model, mode='off',
                                                          source_path=None):
            pass


def test_the_unremovable_handle_evidence_is_accurate(intervention):
    """R5: the hook WAS registered, so the evidence must say so.

    The residual hook stays registered but INERT: it can never change an
    output, and the evidence records the true install fact
    (``hook_installed=True``), ``hook_removed=False`` and the cleanup error.
    """
    model = FakeModel(UnremovableProjection())
    arm = intervention.GeometryProjectionIntervention(model, mode='off',
                                                      source_path=None)
    with pytest.raises(intervention.InterventionError):
        with arm:
            pass
    evidence = arm.evidence
    assert evidence.hook_installed is True      # the TRUE install fact
    assert evidence.hook_removed is False       # it was NOT removed
    assert evidence.cleanup_error is not None
    # and the residual hook is inert: the output is unchanged
    assert len(model.geometry_to_state.active_hooks()) == 1
    assert model.geometry_to_state(('g',)).copy_values() == [1.0, 2.0, 3.0]
    assert arm.hook_calls == 0


def test_a_reused_context_is_refused(intervention):
    model = FakeModel()
    arm = intervention.GeometryProjectionIntervention(model, mode='off',
                                                          source_path=None)
    with arm:
        pass
    with pytest.raises(intervention.InterventionError):
        with arm:
            pass


def test_a_nested_activation_on_the_same_model_is_refused(intervention):
    model = FakeModel()
    with intervention.GeometryProjectionIntervention(model, mode='on',
                                                          source_path=None):
        with pytest.raises(intervention.InterventionError):
            with intervention.GeometryProjectionIntervention(model, mode='off',
                                                          source_path=None):
                pass
    assert model.geometry_to_state.active_hooks() == []


def test_two_different_models_may_be_intervened_independently(intervention):
    first = FakeModel()
    second = FakeModel()
    with intervention.GeometryProjectionIntervention(first, mode='off',
                                                      source_path=None):
        assert first.geometry_to_state(('g',)).copy_values() == [0.0, 0.0, 0.0]
        assert second.geometry_to_state(('g',)).copy_values() == [1.0, 2.0, 3.0]


def test_source_drift_is_detected(intervention, tmp_path):
    """A temp file with KNOWN bytes, checked against a DIFFERENT known digest.

    The expected digest is a fixed constant, so the temp file's own bytes
    really do drift from it -- the check is not satisfied by hashing the
    file against itself.
    """
    drifted = tmp_path / 'geometry_policy.py'
    drifted.write_text('# not the pinned source\n', encoding='utf-8')
    actual = hashlib.sha256(drifted.read_bytes()).hexdigest()
    assert actual != TARGET_SOURCE_SHA
    model = FakeModel()
    with pytest.raises(intervention.InterventionError):
        with intervention.GeometryProjectionIntervention(
                model, mode='off', source_path=str(drifted),
                source_sha256=TARGET_SOURCE_SHA):
            pass
    assert model.geometry_to_state.active_hooks() == []


def test_source_drift_can_be_allowed_but_is_recorded(intervention, tmp_path):
    drifted = tmp_path / 'geometry_policy.py'
    drifted.write_text('# a different source\n', encoding='utf-8')
    model = FakeModel()
    with intervention.GeometryProjectionIntervention(
            model, mode='off', source_path=str(drifted),
            source_sha256=TARGET_SOURCE_SHA, allow_source_drift=True) as arm:
        pass
    assert arm.evidence.source_sha256_matches is False
    assert arm.evidence.target_source_sha256 is not None


def test_a_missing_source_file_is_refused(intervention, tmp_path):
    model = FakeModel()
    with pytest.raises(intervention.InterventionError):
        with intervention.GeometryProjectionIntervention(
                model, mode='off', source_path=str(tmp_path / 'absent.py'),
                source_sha256='0' * 64):
            pass


def test_a_matching_temp_source_is_accepted(intervention, tmp_path):
    """A temp file with known bytes and its OWN digest verifies."""
    source = tmp_path / 'geometry_policy.py'
    source.write_text('# synthetic source bytes\n', encoding='utf-8')
    expected = hashlib.sha256(source.read_bytes()).hexdigest()
    model = FakeModel()
    with intervention.GeometryProjectionIntervention(
            model, mode='off', source_path=str(source),
            source_sha256=expected) as arm:
        pass
    evidence = arm.evidence
    assert evidence.source_sha256_matches is True
    assert evidence.target_source_sha256 == expected
    assert evidence.target_source_path == str(source)


# ------------------------------------------------------------------- evidence

def test_the_evidence_describes_the_arm_and_not_a_success(intervention):
    model = FakeModel()
    with intervention.GeometryProjectionIntervention(model, mode='off',
                                                          source_path=None) as arm:
        model.geometry_to_state(('g',))
    # the evidence is read AFTER the exit: the hook removal is part of it
    payload = arm.evidence.to_dict()
    assert payload['arm'] == 'off'
    assert payload['mode'] == 'off'
    assert payload['hook_calls'] == 1
    assert payload['zero_replacements'] == 1
    assert payload['target_identity_label'].startswith('geometry_to_state:')
    assert payload['hook_installed'] is True
    assert payload['hook_removed'] is True
    # it does NOT claim a model success or a forward
    for statement in ('model success', 'independent source authentication',
                      'proof of a model forward'):
        assert statement in payload['not_established']


def test_the_evidence_records_the_targeted_source_sha(intervention, tmp_path):
    """The hash evidence uses a TEMP source with its OWN known digest."""
    source = tmp_path / 'geometry_policy.py'
    source.write_text('# synthetic source bytes\n', encoding='utf-8')
    expected = hashlib.sha256(source.read_bytes()).hexdigest()
    model = FakeModel()
    with intervention.GeometryProjectionIntervention(
            model, mode='off', source_path=str(source),
            source_sha256=expected) as arm:
        pass
    evidence = arm.evidence
    assert evidence.target_source_path == str(source)
    assert evidence.source_sha256_matches is True
    assert evidence.target_source_sha256 == expected


def test_no_source_path_means_no_source_byte_checking(intervention):
    """source_path=None omits the source-byte check; it is NOT evidence."""
    model = FakeModel()
    with intervention.GeometryProjectionIntervention(
            model, mode='off', source_path=None) as arm:
        pass
    evidence = arm.evidence
    assert evidence.target_source_path is None
    assert evidence.target_source_sha256 is None
    assert evidence.source_sha256_matches is None
    # the evidence still refuses to claim source authentication
    assert 'independent source authentication' in evidence.not_established


def test_the_identity_label_is_a_label_not_an_authentication(intervention):
    model = FakeModel()
    with intervention.GeometryProjectionIntervention(model, mode='off',
                                                          source_path=None) as arm:
        pass
    label = arm.evidence.target_identity_label
    assert 'FakeProjection' in label
    # a label says what the object claims to be, not that the claim is true
    assert 'authentic' not in label.lower()


def test_the_arm_document_records_both_arms_identically(intervention):
    model = FakeModel()
    with intervention.GeometryProjectionIntervention(model, mode='on',
                                                          source_path=None) as on_arm:
        model.geometry_to_state(('g',))
        on_evidence = on_arm.evidence
    with intervention.GeometryProjectionIntervention(model, mode='off',
                                                          source_path=None) as off_arm:
        model.geometry_to_state(('g',))
        off_evidence = off_arm.evidence
    document = intervention.build_arm_document([
        intervention.ArmRecord(arm='control', mode='on',
                               checkpoint_sha256='a' * 64, input_sha256='b' * 64,
                               seed=1234, proposal_status_path='/tmp/on.json',
                               intervention=on_evidence),
        intervention.ArmRecord(arm='intervention', mode='off',
                               checkpoint_sha256='a' * 64, input_sha256='b' * 64,
                               seed=1234, proposal_status_path='/tmp/off.json',
                               intervention=off_evidence),
    ])
    assert document['arm_count'] == 2
    on, off = document['arms']
    for key in ('checkpoint_sha256', 'input_sha256', 'seed'):
        assert on[key] == off[key]
    assert on['mode'] == 'on' and off['mode'] == 'off'
    assert on['proposal_status_path'] != off['proposal_status_path']
    assert 'model success' in document['not_established']
    assert json.loads(json.dumps(document)) == document


def test_the_arm_document_is_written_exclusively(intervention, tmp_path):
    document = intervention.build_arm_document([])
    path = tmp_path / 'arms.json'
    intervention.dump_arm_document(document, path)
    assert json.loads(path.read_text(encoding='utf-8'))['arm_count'] == 0
    with pytest.raises(FileExistsError):
        intervention.dump_arm_document(document, path)


# ------------------------------------------------------------------ boundary

def test_the_tests_do_not_validate_real_pytorch(intervention):
    """The boundary is explicit: these are fake objects, not tensors."""
    model = FakeModel()
    result = model.geometry_to_state(('g',))
    assert not hasattr(result, 'detach')
    assert not hasattr(result, 'cpu')
    assert isinstance(result, FakeTensor)
    assert 'import torch' not in MODULE_PATH.read_text(encoding='utf-8')


def test_the_pinned_target_source_is_unchanged(intervention):
    """OPTIONAL archive integration check.

    This is the ONLY test that touches the host's archived research source.
    It is skipped when the archive is not available, so the portable suite
    still runs on a clean machine.  Everything else in this file uses fake
    objects and temp files with known bytes.
    """
    path = Path(TARGET_SOURCE)
    if not path.is_file():
        pytest.skip('the pinned target source archive is not available here')
    hasher = hashlib.sha256(path.read_bytes()).hexdigest()
    assert hasher == TARGET_SOURCE_SHA


def test_the_default_source_constant_is_an_absolute_path(intervention):
    """The default is an ABSOLUTE path: it is not portable by itself.

    The exact value is the host's archived research source.  This test
    asserts the SHAPE of the default (absolute, non-empty, points at a
    ``geometry_policy.py``) instead of the host-specific string, so it stays
    valid wherever the archive lives.
    """
    default = intervention.DEFAULT_TARGET_SOURCE
    assert default.startswith('/')
    assert default.endswith('geometry_policy.py')
    # the module's own default pin is a 64-hex digest
    assert len(intervention.DEFAULT_TARGET_SOURCE_SHA256) == 64
    assert intervention.DEFAULT_TARGET_SOURCE_SHA256 == TARGET_SOURCE_SHA


def test_the_nonportable_default_refuses_when_the_source_is_missing(intervention,
                                                                    tmp_path):
    """A missing source file is refused -- the default check is NOT disabled.

    The refusal is exercised with an explicit path so the test does not
    depend on where the host's archive lives.
    """
    model = FakeModel()
    with pytest.raises(intervention.InterventionError):
        with intervention.GeometryProjectionIntervention(
                model, mode='off', source_path=str(tmp_path / 'absent.py'),
                source_sha256=TARGET_SOURCE_SHA):
            pass
    assert model.geometry_to_state.active_hooks() == []


def test_the_module_default_refuses_on_a_host_without_the_archive(intervention):
    """The module's OWN default is refused when the archive is absent.

    This is the portability fact the module keeps: the default source check
    is NOT disabled.  It is asserted by pointing the default at a path that
    cannot exist, which is what a clean machine looks like.
    """
    model = FakeModel()
    with pytest.raises(intervention.InterventionError):
        with intervention.GeometryProjectionIntervention(
                model, mode='off',
                source_path='/nonexistent/clean-ci/geometry_policy.py',
                source_sha256=TARGET_SOURCE_SHA):
            pass
    assert model.geometry_to_state.active_hooks() == []
