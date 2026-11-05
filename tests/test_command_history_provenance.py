"""Unit tests for harness/command_history_provenance.py (offline, non-physical).

Run from the repository root:
    PYTHONPATH=. python3 -m unittest tests.test_command_history_provenance -v
or standalone:
    python3 tests/test_command_history_provenance.py
"""
from __future__ import annotations

import copy
import os
import sys
import unittest
from collections.abc import Mapping

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harness import command_history_provenance as p


def command(t, wheels, duration_s, pwm=(1500, 1500, 1500, 1500, 1500)):
    return {'t': t, 'wheels': list(wheels), 'duration_s': list(duration_s),
            'pwm': {'1': pwm[0], '3': pwm[1], '4': pwm[2], '5': pwm[3], '6': pwm[4]}}


STOP = command(0.0, [0., 0., 0., 0.], [0., 0., 0., 0.])
MOVE = command(0.1, [.35, .35, .35, .35], [.05, .05, .05, .05])
STOP_2 = command(0.2, [0., 0., 0., 0.], [0., 0., 0., 0.])


class RawPreservation(unittest.TestCase):
    """The raw issued window is never modified, relabeled or aliased."""

    def test_describe_leaves_the_raw_window_unchanged(self):
        window = [STOP, MOVE]
        before = copy.deepcopy(window)
        before_digest = p.fingerprint(window)
        p.describe(window, origins=['policy', 'policy'])
        self.assertEqual(window, before)
        self.assertEqual(p.fingerprint(window), before_digest)

    def test_validate_sidecar_leaves_the_raw_window_unchanged(self):
        window = [STOP, MOVE]
        sidecar = p.describe(window, origins=['policy', 'policy'])
        before = copy.deepcopy(window)
        p.validate_sidecar(window, sidecar)
        self.assertEqual(window, before)

    def test_resolve_prior_leaves_the_raw_window_and_prior_unchanged(self):
        window = [MOVE, STOP_2]
        prior = command(-0.1, [.35, .35, .35, .35], [.05, .05, .05, .05])
        before_window, before_prior = copy.deepcopy(window), copy.deepcopy(prior)
        p.resolve_prior(window, prior)
        self.assertEqual(window, before_window)
        self.assertEqual(prior, before_prior)

    def test_sidecar_holds_no_command_object(self):
        sidecar = p.describe([STOP, MOVE], origins=['policy', 'protocol_hold'])
        for value in sidecar.values():
            if isinstance(value, Mapping):
                # the only mapping allowed is the label count table
                self.assertFalse(set(value) & {'wheels', 'duration_s', 'pwm', 't'})
                for item in value.values():
                    self.assertIn(type(item), (int, bool))
                continue
            if isinstance(value, list):
                for item in value:
                    self.assertNotIsInstance(item, Mapping)
                    self.assertIn(type(item), (str, bool))

    def test_copies_do_not_alias_the_raw_window(self):
        window = [STOP, MOVE]
        copies = p.copy_commands(window)
        copies[0]['wheels'][0] = .35
        self.assertEqual(window[0]['wheels'], [0., 0., 0., 0.])


class IssuedFactsSurvive(unittest.TestCase):
    """A real policy stop and a real protocol hold both stay issued facts."""

    def test_policy_stop_is_kept_as_an_issued_command(self):
        window = [STOP, MOVE]
        sidecar = p.describe(window, origins=['policy', 'policy'])
        self.assertEqual(sidecar['origins'][0], 'policy')
        self.assertIs(sidecar['issued'][0], True)
        self.assertEqual(window[0]['wheels'], [0., 0., 0., 0.])

    def test_protocol_hold_is_kept_as_an_issued_command(self):
        window = [STOP, MOVE]
        sidecar = p.describe(window, origins=['protocol_hold', 'policy'])
        self.assertEqual(sidecar['origins'][0], 'protocol_hold')
        self.assertIs(sidecar['issued'][0], True)
        self.assertEqual(window[0]['wheels'], [0., 0., 0., 0.])

    def test_padding_is_marked_only_in_the_sidecar(self):
        window = [STOP, MOVE]
        sidecar = p.describe(window, origins=['padding', 'policy'],
                             padding_valid=[True, False])
        self.assertIs(sidecar['issued'][0], False)
        self.assertIs(sidecar['padding_valid'][0], True)
        self.assertEqual(sidecar['counts']['padding'], 1)
        self.assertEqual(sidecar['counts']['issued'], 1)
        # the padding slot is still exactly the raw row it was
        self.assertEqual(window[0], STOP)
        self.assertEqual(len(window), 2)

    def test_padding_validity_is_unclaimed_by_default(self):
        sidecar = p.describe([STOP, MOVE], origins=['padding', 'policy'])
        self.assertEqual(sidecar['padding_valid'], [False, False])
        self.assertEqual(sidecar['counts']['padding_valid'], 0)


class UnknownStaysUnknown(unittest.TestCase):
    """Missing provenance is never promoted to a policy command."""

    def test_missing_origin_label_stays_unknown(self):
        sidecar = p.describe([STOP, MOVE])
        self.assertEqual(sidecar['origins'], ['unknown', 'unknown'])
        self.assertEqual(sidecar['issued'], [None, None])
        self.assertEqual(sidecar['counts']['unknown'], 2)

    def test_explicit_unknown_is_not_promoted(self):
        sidecar = p.describe([STOP, MOVE], origins=['unknown', 'policy'])
        self.assertEqual(sidecar['origins'][0], 'unknown')
        self.assertIsNone(sidecar['issued'][0])
        self.assertEqual(sidecar['counts']['policy'], 1)

    def test_neutral_values_do_not_imply_a_label(self):
        sidecar = p.describe([STOP, MOVE])
        self.assertNotEqual(sidecar['origins'][0], 'padding')
        self.assertNotEqual(sidecar['origins'][0], 'policy')


class PriorBoundary(unittest.TestCase):
    """A prior may not postdate the window start; a past stop prior is fine."""

    def test_future_prior_is_rejected(self):
        window = [MOVE, STOP_2]
        future = command(0.5, [.35, .35, .35, .35], [.05, .05, .05, .05])
        with self.assertRaises(p.ProvenanceError):
            p.resolve_prior(window, future)

    def test_past_stop_prior_is_accepted(self):
        window = [MOVE, STOP_2]
        prior = command(-0.1, [0., 0., 0., 0.], [0., 0., 0., 0.])
        accepted = p.resolve_prior(window, prior)
        self.assertEqual(accepted['wheels'], [0., 0., 0., 0.])
        self.assertEqual(accepted['t'], -0.1)

    def test_prior_at_the_window_start_is_accepted(self):
        window = [MOVE, STOP_2]
        prior = command(0.1, [.35, .35, .35, .35], [.05, .05, .05, .05])
        self.assertEqual(p.resolve_prior(window, prior)['t'], 0.1)


class SidecarMismatch(unittest.TestCase):
    """Wrong lengths, wrong labels and drifted raw history are refused."""

    def test_origin_length_mismatch_is_refused(self):
        with self.assertRaises(p.ProvenanceError):
            p.describe([STOP, MOVE], origins=['policy'])

    def test_unknown_label_is_refused(self):
        with self.assertRaises(p.ProvenanceError):
            p.describe([STOP, MOVE], origins=['policy', 'invented'])

    def test_padding_validity_length_mismatch_is_refused(self):
        with self.assertRaises(p.ProvenanceError):
            p.describe([STOP, MOVE], origins=['padding', 'policy'],
                       padding_valid=[True])

    def test_padding_validity_on_a_non_padding_slot_is_refused(self):
        with self.assertRaises(p.ProvenanceError):
            p.describe([STOP, MOVE], origins=['policy', 'policy'],
                       padding_valid=[True, False])

    def test_sidecar_length_mismatch_is_refused(self):
        window = [STOP, MOVE]
        sidecar = p.describe(window, origins=['policy', 'policy'])
        sidecar['length'] = 1
        with self.assertRaises(p.ProvenanceError):
            p.validate_sidecar(window, sidecar)

    def test_sidecar_label_mismatch_is_refused(self):
        window = [STOP, MOVE]
        sidecar = p.describe(window, origins=['policy', 'policy'])
        sidecar['origins'] = ['policy', 'padding']
        with self.assertRaises(p.ProvenanceError):
            p.validate_sidecar(window, sidecar)

    def test_sidecar_of_a_different_raw_window_is_refused(self):
        window = [STOP, MOVE]
        sidecar = p.describe(window, origins=['policy', 'policy'])
        with self.assertRaises(p.ProvenanceError):
            p.validate_sidecar([MOVE, STOP_2], sidecar)

    def test_sidecar_extra_field_is_refused(self):
        window = [STOP, MOVE]
        sidecar = p.describe(window, origins=['policy', 'policy'])
        sidecar['issued_commands'] = window
        with self.assertRaises(p.ProvenanceError):
            p.validate_sidecar(window, sidecar)

    def test_malformed_command_is_refused(self):
        with self.assertRaises(ValueError):
            p.describe([{'t': 0.0, 'wheels': [0.] * 4, 'duration_s': [0.] * 4}])


class AuditRegressions(unittest.TestCase):
    def test_forged_count_rejected(self):
        sidecar = p.describe([STOP, MOVE])
        sidecar['counts']['issued'] = 999
        with self.assertRaises(p.ProvenanceError):
            p.validate_sidecar([STOP, MOVE], sidecar)

    def test_raw_object_in_counts_rejected_and_window_unchanged(self):
        window = copy.deepcopy([STOP, MOVE])
        before = copy.deepcopy(window)
        sidecar = p.describe(window)
        sidecar['counts']['raw_command'] = window[0]
        with self.assertRaises(p.ProvenanceError):
            p.validate_sidecar(window, sidecar)
        self.assertEqual(window, before)

    def test_count_schema_and_scalar_types(self):
        for value in (None, [], {'issued': 0}, {'issued': True}):
            sidecar = p.describe([STOP])
            sidecar['counts'] = value
            with self.subTest(value=value), self.assertRaises(p.ProvenanceError):
                p.validate_sidecar([STOP], sidecar)
        sidecar = p.describe([STOP], origins=['policy'])
        sidecar['counts']['issued'] = True
        with self.assertRaises(p.ProvenanceError):
            p.validate_sidecar([STOP], sidecar)

    def test_serialized_arrays_are_explicit(self):
        for key in ('origins', 'issued', 'padding_valid'):
            for value in (None, (), 'unknown'):
                sidecar = p.describe([STOP])
                sidecar[key] = value
                with self.subTest(key=key, value=value), self.assertRaises(p.ProvenanceError):
                    p.validate_sidecar([STOP], sidecar)
        sidecar = p.describe([STOP]); sidecar['origins'] = [None]
        with self.assertRaises(p.ProvenanceError):
            p.validate_sidecar([STOP], sidecar)

    def test_boolean_length_rejected(self):
        sidecar = p.describe([STOP]); sidecar['length'] = True
        with self.assertRaises(p.ProvenanceError):
            p.validate_sidecar([STOP], sidecar)

    def test_validated_sidecar_is_detached(self):
        window = copy.deepcopy([STOP, MOVE])
        original = p.describe(window)
        accepted = p.validate_sidecar(window, original)
        self.assertIsNot(accepted, original)
        accepted['origins'][0] = 'policy'
        accepted['counts']['issued'] = 999
        self.assertEqual(original, p.describe(window))
        self.assertEqual(window, [STOP, MOVE])

    def test_reversed_history_rejected_by_all_window_apis(self):
        window = [MOVE, STOP]
        for call in (lambda: p.describe(window), lambda: p.window_start(window),
                     lambda: p.resolve_prior(window, STOP)):
            with self.assertRaises(p.ProvenanceError):
                call()

    def test_duplicate_padding_times_allowed(self):
        self.assertEqual(p.window_start([STOP, STOP]), 0.)

    def test_any_future_prior_rejected_without_undocumented_slack(self):
        prior = copy.deepcopy(STOP); prior['t'] = 1e-10
        with self.assertRaises(p.ProvenanceError):
            p.resolve_prior([STOP, MOVE], prior)

    def test_raw_hash_preserves_numeric_representation(self):
        raw = copy.deepcopy(STOP); raw['t'] = 0
        normalized = copy.deepcopy(raw); normalized['t'] = 0.0
        self.assertNotEqual(p.fingerprint([raw]), p.fingerprint([normalized]))
        with self.assertRaises(p.ProvenanceError):
            p.validate_sidecar([normalized], p.describe([raw]))
        self.assertEqual(p.fingerprint([raw]), p.fingerprint(p.copy_commands([raw])))

    def test_padding_prior_rejected_without_rejecting_actual_stop(self):
        with self.assertRaises(p.ProvenanceError):
            p.resolve_prior([MOVE], STOP, origin='padding')
        self.assertEqual(p.resolve_prior([MOVE], STOP, origin='policy')['wheels'], STOP['wheels'])

    def test_labels_are_assertions_and_not_inferred_from_motion(self):
        sidecar = p.describe([STOP, MOVE])
        self.assertEqual(sidecar['origins'], ['unknown', 'unknown'])
        self.assertEqual(sidecar['issued'], [None, None])


class PaddingConsistency(unittest.TestCase):
    def test_moving_valid_padding_rejected_by_describe_and_validate(self):
        with self.assertRaises(p.ProvenanceError):
            p.describe([MOVE], origins=['padding'], padding_valid=[True])
        sidecar = p.describe([MOVE], origins=['padding'])
        sidecar['padding_valid'] = [True]
        with self.assertRaises(p.ProvenanceError):
            p.validate_sidecar([MOVE], sidecar)

    def test_unconfirmed_padding_is_unknown_even_if_neutral(self):
        for row in (STOP, MOVE):
            sidecar = p.describe([row], origins=['padding'])
            self.assertEqual(sidecar['issued'], [None])
            self.assertEqual(sidecar['counts']['issued'], 0)
            self.assertEqual(p.validate_sidecar([row], sidecar), sidecar)

    def test_neutrality_does_not_infer_origin(self):
        self.assertEqual(p.describe([STOP])['issued'], [None])
        self.assertEqual(p.describe([STOP], origins=['policy'])['issued'], [True])
        sidecar = p.describe([STOP], origins=['padding'], padding_valid=[True])
        self.assertEqual(sidecar['issued'], [False])
        self.assertEqual(p.validate_sidecar([STOP], sidecar), sidecar)


if __name__ == '__main__':
    unittest.main()
