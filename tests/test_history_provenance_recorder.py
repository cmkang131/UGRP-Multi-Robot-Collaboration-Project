"""Unit tests for the opt-in issued-history producer recorder.

Offline and non-physical: no simulator, no model forward, no network.

Run from the repository root:
    PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 \
        python3 -m unittest tests.test_history_provenance_recorder -v
"""
from __future__ import annotations

import copy
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harness import command_history_provenance as p
from harness import grasp_act_contract as c
from harness import grasp_act_rollout as rollout
from harness import history_provenance_recorder as rec


def command(t, wheels, duration_s):
    return {'t': t, 'wheels': list(wheels), 'duration_s': list(duration_s),
            'pwm': {'1': 1500, '3': 1500, '4': 1500, '5': 1500, '6': 1500}}


STOP = command(0.0, [0., 0., 0., 0.], [0., 0., 0., 0.])
MOVE = command(0.1, [.35, .35, .35, .35], [.05, .05, .05, .05])
JPEG = b'\xff\xd8not-a-real-jpeg-but-bytes\xff\xd9'


def recorder(run_id='run-a', episode_id='ep-1', robot_id='r1'):
    return rec.HistoryProvenanceRecorder(run_id=run_id, episode_id=episode_id,
                                         robot_id=robot_id)


def history(with_recorder=True, **kwargs):
    audit = recorder(**kwargs) if with_recorder else None
    return rollout.OwnHistory('r1', 'ep-1', STOP, recorder=audit), audit


def observe(history_owner, now=1.0):
    return history_owner.observe(now, JPEG, skill='grasp', object_kind='can',
                                  role='any')


class AuditOff(unittest.TestCase):
    """Without a recorder the producer must behave exactly as before."""

    def test_observation_is_identical_with_and_without_a_recorder(self):
        plain, _ = history(False)
        audited, _ = history(True)
        plain_obs, _, _ = observe(plain)
        audited_obs, _, _ = observe(audited)
        self.assertEqual(plain_obs, audited_obs)

    def test_issued_values_are_unchanged_by_a_recorder(self):
        plain, _ = history(False)
        audited, _ = history(True)
        plain.issue(MOVE)
        audited.issue(MOVE)
        self.assertEqual(list(plain.issued), list(audited.issued))

    def test_issue_return_value_is_unchanged(self):
        plain, _ = history(False)
        audited, _ = history(True)
        self.assertIsNone(plain.issue(MOVE))
        self.assertIsNone(audited.issue(MOVE))

    def test_no_recorder_means_no_record(self):
        plain, _ = history(False)
        plain.issue(MOVE)
        self.assertIsNone(plain.recorder)
        self.assertFalse(hasattr(plain, 'audit_snapshot'))


class AuditOn(unittest.TestCase):
    """The recorder observes; it never changes the model contract."""

    def test_model_observation_schema_is_unchanged(self):
        audited, _ = history(True)
        obs, _, _ = observe(audited)
        self.assertEqual(set(obs), c.FIELDS)
        self.assertEqual(obs['schema'], c.SCHEMA)
        self.assertEqual(len(obs['issued']), c.HISTORY)

    def test_return_tuple_is_unchanged(self):
        audited, _ = history(True)
        result = observe(audited)
        self.assertEqual(len(result), 3)
        self.assertIsInstance(result[1], list)
        self.assertIsInstance(result[2], str)

    def test_issued_window_in_the_observation_is_the_raw_window(self):
        audited, _ = history(True)
        audited.issue(MOVE)
        obs, _, _ = observe(audited)
        self.assertEqual(obs['issued'][-1]['wheels'], [.35, .35, .35, .35])
        self.assertEqual(obs['issued'][-1]['t'], MOVE['t'])

    def test_sidecar_is_not_injected_into_the_observation(self):
        audited, audit = history(True)
        obs, _, _ = observe(audited)
        self.assertFalse(any('provenance' in key or 'audit' in key for key in obs))
        self.assertNotIn(audit.audit_snapshot(), obs.values())


class MixedOrigins(unittest.TestCase):
    """Reset padding, a policy stop, a protocol hold and an unknown call."""

    def test_padding_policy_hold_and_unknown_are_recorded_apart(self):
        audited, audit = history(True)
        audited.issue(command(0.1, [0., 0., 0., 0.], [0., 0., 0., 0.]), origin='policy')
        audited.issue(command(0.2, [0., 0., 0., 0.], [0., 0., 0., 0.]), origin='protocol_hold')
        audited.issue(command(0.3, [.35, .35, .35, .35], [.05, .05, .05, .05]))
        events = audit.stored_events()
        self.assertEqual(len(events), c.HISTORY + 3)
        self.assertTrue(all(event['kind'] == 'padding' for event in events[:c.HISTORY]))
        self.assertTrue(all(event['origin'] == 'padding' for event in events[:c.HISTORY]))
        self.assertTrue(all(event['issued'] is False for event in events[:c.HISTORY]))
        self.assertEqual(events[c.HISTORY]['origin'], 'policy')
        self.assertIs(events[c.HISTORY]['issued'], True)
        self.assertEqual(events[c.HISTORY + 1]['origin'], 'protocol_hold')
        self.assertIs(events[c.HISTORY + 1]['issued'], True)
        self.assertEqual(events[c.HISTORY + 2]['origin'], 'unknown')
        self.assertIsNone(events[c.HISTORY + 2]['issued'])

    def test_default_issue_origin_is_unknown(self):
        audited, audit = history(True)
        audited.issue(MOVE)
        self.assertEqual(audit.stored_events()[-1]['origin'], 'unknown')
        self.assertIsNone(audit.stored_events()[-1]['issued'])

    def test_a_policy_stop_stays_an_issued_fact(self):
        audited, audit = history(True)
        stop = command(0.1, [0., 0., 0., 0.], [0., 0., 0., 0.])
        audited.issue(stop, origin='policy')
        self.assertEqual(audit.stored_events()[-1]['issued'], True)
        self.assertEqual(audit.stored_events()[-1]['origin'], 'policy')
        self.assertEqual(list(audited.issued)[-1]['wheels'], [0., 0., 0., 0.])

    def test_padding_origin_cannot_be_declared_for_an_issue(self):
        audited, audit = history(True)
        with self.assertRaises(rec.RecorderError):
            audited.issue(MOVE, origin='padding')

    def test_unknown_origin_label_is_refused(self):
        audited, audit = history(True)
        with self.assertRaises(rec.RecorderError):
            audited.issue(MOVE, origin='invented')

    def test_an_issue_event_claims_no_environment_application(self):
        audited, audit = history(True)
        audited.issue(MOVE)
        event = audit.stored_events()[-1]
        self.assertEqual(event['kind'], 'issue')
        self.assertIn('not evidence', event['note'])
        self.assertNotIn('applied', event)
        self.assertNotIn('acknowledged', event)
        self.assertNotIn('success', event)


class RejectedIssueIsAtomic(unittest.TestCase):
    """A refused issue call changes neither the raw history nor the recorder."""

    def test_rejected_origin_leaves_the_raw_history_unchanged(self):
        audited, audit = history(True)
        before = list(audited.issued)
        events_before = audit.stored_events()
        with self.assertRaises(rec.RecorderError):
            audited.issue(MOVE, origin='padding')
        self.assertEqual(list(audited.issued), before)
        self.assertEqual(audit.stored_events(), events_before)
        self.assertEqual(audit.issue_offset, 0)

    def test_rejected_timestamp_leaves_the_raw_history_unchanged(self):
        audited, audit = history(True)
        audited.issue(command(0.5, [.35] * 4, [.05] * 4))
        before = list(audited.issued)
        events_before = audit.stored_events()
        with self.assertRaises(rec.RecorderError):
            audited.issue(command(0.2, [.35] * 4, [.05] * 4))
        self.assertEqual(list(audited.issued), before)
        self.assertEqual(audit.stored_events(), events_before)
        self.assertEqual(audit.issue_offset, 1)

    def test_malformed_command_leaves_the_raw_history_unchanged(self):
        audited, audit = history(True)
        before = list(audited.issued)
        with self.assertRaises(ValueError):
            audited.issue({'t': 0.1, 'wheels': [0.] * 4})
        self.assertEqual(list(audited.issued), before)
        self.assertEqual(audit.issue_offset, 0)

    def test_one_backwards_second_is_refused(self):
        audited, audit = history(True)
        audited.issue(command(0.5, [.35] * 4, [.05] * 4))
        before = list(audited.issued)
        with self.assertRaises(rec.RecorderError):
            audited.issue(command(0.5 - 1e-10, [.35] * 4, [.05] * 4))
        self.assertEqual(list(audited.issued), before)

    def test_equal_timestamp_is_allowed(self):
        audited, audit = history(True)
        audited.issue(command(0.5, [.35] * 4, [.05] * 4))
        audited.issue(command(0.5, [.35] * 4, [.05] * 4))
        self.assertEqual(audit.issue_offset, 2)


class IdentityBinding(unittest.TestCase):
    """A recorder belongs to one robot and episode, and is used once."""

    def test_recorder_of_another_robot_is_refused(self):
        audit = recorder(robot_id='r2')
        with self.assertRaises(rec.RecorderError):
            rollout.OwnHistory('r1', 'ep-1', STOP, recorder=audit)

    def test_recorder_of_another_episode_is_refused(self):
        audit = recorder(episode_id='ep-2')
        with self.assertRaises(rec.RecorderError):
            rollout.OwnHistory('r1', 'ep-1', STOP, recorder=audit)

    def test_a_recorder_cannot_be_reused_for_a_second_history(self):
        audited, audit = history(True)
        with self.assertRaises(rec.RecorderError):
            rollout.OwnHistory('r1', 'ep-1', STOP, recorder=audit)
        self.assertEqual(audit.event_count, c.HISTORY)

    def test_initial_padding_is_recorded_only_once(self):
        audit = recorder()
        with self.assertRaises(rec.RecorderError):
            audit.record_initial_padding(STOP, count=c.HISTORY)
        audit.bind_identity('r1', 'ep-1')
        audit.record_initial_padding(STOP, count=c.HISTORY)
        with self.assertRaises(rec.RecorderError):
            audit.record_initial_padding(STOP, count=c.HISTORY)

    def test_padding_cannot_be_injected_after_an_issue(self):
        audited, audit = history(True)
        audited.issue(MOVE)
        with self.assertRaises(rec.RecorderError):
            audit.record_initial_padding(STOP, count=c.HISTORY)
        self.assertEqual(audit.event_count, c.HISTORY + 1)


class SampleBinding(unittest.TestCase):
    """A snapshot is bound to the observation that produced it."""

    def test_snapshot_after_observe_verifies(self):
        audited, audit = history(True)
        observe(audited)
        snapshot = audit.audit_snapshot()
        self.assertIs(audit.verify(snapshot), True)

    def test_wrong_sample_is_refused_by_live_verify(self):
        audited, audit = history(True)
        observe(audited)
        snapshot = audit.audit_snapshot()
        snapshot['sample_id'] = 'wrong-sample'
        with self.assertRaises(rec.RecorderError):
            audit.verify(snapshot)

    def test_caller_cannot_override_the_sample(self):
        audited, audit = history(True)
        observe(audited)
        snapshot = audit.audit_snapshot()
        with self.assertRaises(TypeError):
            audit.verify(snapshot, sample_id='wrong-sample')

    def test_an_issue_invalidates_the_previous_sample_association(self):
        audited, audit = history(True)
        observe(audited)
        snapshot = audit.audit_snapshot()
        audited.issue(MOVE)
        with self.assertRaises(rec.RecorderError):
            audit.verify(snapshot)

    def test_a_failed_observe_leaves_no_sample_association(self):
        audited, audit = history(True)
        with self.assertRaises(ValueError):
            audited.observe(1.0, JPEG, skill='release', object_kind='can', role='any')
        with self.assertRaises(rec.RecorderError):
            audit.audit_snapshot()

    def test_snapshot_needs_a_sample_id(self):
        _, audit = history(True)
        with self.assertRaises(rec.RecorderError):
            audit.audit_snapshot()


class LiveVerifyIsAuthoritative(unittest.TestCase):
    """The live check compares the snapshot with the stored events."""

    def test_consistent_origin_and_issued_forgery_is_refused(self):
        audited, audit = history(True)
        observe(audited)
        snapshot = audit.audit_snapshot()
        snapshot['slots'][0]['origin'] = 'policy'
        snapshot['slots'][0]['issued'] = True
        with self.assertRaises(rec.RecorderError):
            audit.verify(snapshot)

    def test_joint_kind_slot_time_and_offset_forgery_is_refused(self):
        audited, audit = history(True)
        observe(audited)
        snapshot = audit.audit_snapshot()
        snapshot['slots'][0]['kind'] = 'issue'
        snapshot['slots'][0]['slot'] = 7
        snapshot['slots'][0]['t'] = 12.5
        snapshot['slots'][0]['issue_offset'] = 99
        with self.assertRaises(rec.RecorderError):
            audit.verify(snapshot)

    def test_row_hash_forgery_is_refused(self):
        audited, audit = history(True)
        observe(audited)
        snapshot = audit.audit_snapshot()
        snapshot['slots'][3]['row_hash'] = '0' * 64
        snapshot['rows'][3] = '0' * 64
        with self.assertRaises(rec.RecorderError):
            audit.verify(snapshot)

    def test_raw_window_hash_forgery_is_refused(self):
        audited, audit = history(True)
        observe(audited)
        snapshot = audit.audit_snapshot()
        snapshot['raw_window_hash'] = 'f' * 64
        with self.assertRaises(rec.RecorderError):
            audit.verify(snapshot)

    def test_stale_offset_is_refused(self):
        audited, audit = history(True)
        observe(audited)
        snapshot = audit.audit_snapshot()
        snapshot['issue_offset'] = 5
        with self.assertRaises(rec.RecorderError):
            audit.verify(snapshot)

    def test_snapshot_of_another_run_is_refused(self):
        first_owner, first = history(True)
        observe(first_owner)
        snapshot = first.audit_snapshot()
        other_owner, other = history(True, run_id='run-b')
        observe(other_owner)
        with self.assertRaises(rec.RecorderError):
            other.verify(snapshot)

    def test_snapshot_of_another_sample_is_refused(self):
        audited, audit = history(True)
        observe(audited)
        snapshot = audit.audit_snapshot()
        with self.assertRaises(rec.RecorderError):
            rec.verify_snapshot(snapshot, sample_id='ep-1:9:r1')


class StandaloneVerification(unittest.TestCase):
    """verify_snapshot checks structure, not stored truth."""

    def test_structure_check_passes_for_a_consistent_forgery(self):
        audited, audit = history(True)
        observe(audited)
        snapshot = audit.audit_snapshot()
        audited.issue(MOVE)
        observe(audited)
        snapshot = audit.audit_snapshot()
        snapshot['slots'][-1]['origin'] = 'policy'
        snapshot['slots'][-1]['issued'] = True
        self.assertIs(rec.verify_snapshot(snapshot), True)

    def test_but_the_live_check_refuses_the_same_forgery(self):
        audited, audit = history(True)
        observe(audited)
        snapshot = audit.audit_snapshot()
        snapshot['slots'][0]['origin'] = 'policy'
        snapshot['slots'][0]['issued'] = True
        with self.assertRaises(rec.RecorderError):
            audit.verify(snapshot)

    def test_external_identity_is_checked(self):
        audited, audit = history(True)
        observe(audited)
        snapshot = audit.audit_snapshot()
        with self.assertRaises(rec.RecorderError):
            rec.verify_snapshot(snapshot, run_id='run-b')
        with self.assertRaises(rec.RecorderError):
            rec.verify_snapshot(snapshot, robot_id='r2')

    def test_a_provided_window_is_compared(self):
        audited, audit = history(True)
        observe(audited)
        snapshot = audit.audit_snapshot()
        self.assertIs(rec.verify_snapshot(snapshot, window=list(audited.issued)), True)
        shifted = list(audited.issued)[1:] + [MOVE]
        with self.assertRaises(rec.RecorderError):
            rec.verify_snapshot(snapshot, window=shifted)

    def test_field_schema_is_checked(self):
        audited, audit = history(True)
        observe(audited)
        snapshot = copy.deepcopy(audit.audit_snapshot())
        snapshot['extra'] = 1
        with self.assertRaises(rec.RecorderError):
            rec.verify_snapshot(snapshot)

    def test_slot_index_range_is_checked(self):
        audited, audit = history(True)
        observe(audited)
        snapshot = copy.deepcopy(audit.audit_snapshot())
        snapshot['slots'][2]['slot'] = 9
        with self.assertRaises(rec.RecorderError):
            rec.verify_snapshot(snapshot)

    def test_row_hash_format_is_checked(self):
        audited, audit = history(True)
        observe(audited)
        snapshot = copy.deepcopy(audit.audit_snapshot())
        snapshot['slots'][0]['row_hash'] = 'not-a-hash'
        with self.assertRaises(rec.RecorderError):
            rec.verify_snapshot(snapshot)

    def test_missing_sequence_number_is_refused(self):
        audited, audit = history(True)
        audited.issue(MOVE)
        snapshot = copy.deepcopy(audit.audit_snapshot(sample_id='ep-1:0:r1'))
        snapshot['slots'][5]['seq'] -= 1
        with self.assertRaises(rec.RecorderError):
            rec.verify_snapshot(snapshot)

    def test_duplicated_sequence_number_is_refused(self):
        audited, audit = history(True)
        audited.issue(MOVE)
        snapshot = copy.deepcopy(audit.audit_snapshot(sample_id='ep-1:0:r1'))
        snapshot['slots'][5]['seq'] = snapshot['slots'][4]['seq']
        with self.assertRaises(rec.RecorderError):
            rec.verify_snapshot(snapshot)

    def test_shifted_window_is_refused_at_snapshot_time(self):
        audited, audit = history(True)
        audited.issue(MOVE)
        shifted = list(audited.issued)[1:] + [MOVE]
        with self.assertRaises(rec.RecorderError):
            audit.audit_snapshot(window=shifted)


class RollingWindow(unittest.TestCase):
    """Past 16 slots the raw rows, labels and event offsets stay aligned."""

    def test_window_rolls_and_offsets_stay_consistent(self):
        audited, audit = history(True)
        for index in range(20):
            audited.issue(command(0.1 + index * 0.1, [.35] * 4, [.05] * 4))
        snapshot = audit.audit_snapshot(sample_id='ep-1:0:r1')
        self.assertEqual(len(snapshot['slots']), c.HISTORY)
        self.assertEqual(snapshot['issue_offset'], 20)
        self.assertEqual(snapshot['event_count'], c.HISTORY + 20)
        seqs = [slot['seq'] for slot in snapshot['slots']]
        self.assertEqual(seqs, list(range(seqs[0], seqs[0] + c.HISTORY)))
        offsets = [slot['issue_offset'] for slot in snapshot['slots']]
        self.assertEqual(offsets, list(range(offsets[0], offsets[0] + c.HISTORY)))
        self.assertEqual(snapshot['raw_window_hash'], p.fingerprint(list(audited.issued)))
        self.assertEqual(snapshot['rows'],
                         [p.fingerprint([row]) for row in list(audited.issued)])

    def test_slot_order_matches_the_raw_window_order(self):
        audited, audit = history(True)
        for index in range(5):
            audited.issue(command(0.1 + index * 0.1, [.35] * 4, [.05] * 4))
        snapshot = audit.audit_snapshot(sample_id='ep-1:0:r1')
        for slot, row in zip(snapshot['slots'], list(audited.issued)):
            self.assertEqual(slot['row_hash'], p.fingerprint([row]))
            self.assertEqual(slot['t'], row['t'])


class TimestampAndOffsetBounds(unittest.TestCase):
    """Timestamp order and issue offsets are bounded."""

    def test_backwards_timestamp_is_refused(self):
        audited, audit = history(True)
        audited.issue(command(0.5, [.35] * 4, [.05] * 4))
        with self.assertRaises(rec.RecorderError):
            audited.issue(command(0.2, [.35] * 4, [.05] * 4))

    def test_issue_offset_counts_issue_calls_only(self):
        audited, audit = history(True)
        audited.issue(MOVE)
        audited.issue(MOVE)
        self.assertEqual(audit.issue_offset, 2)
        self.assertEqual(audit.event_count, c.HISTORY + 2)

    def test_offset_and_event_numbers_are_dense(self):
        audited, audit = history(True)
        for index in range(4):
            audited.issue(command(0.1 + index * 0.1, [.35] * 4, [.05] * 4))
        events = audit.stored_events()
        self.assertEqual([event['seq'] for event in events],
                         list(range(len(events))))
        self.assertEqual([event['issue_offset'] for event in events[c.HISTORY:]],
                         [0, 1, 2, 3])


class StoredCopies(unittest.TestCase):
    """Stored records and snapshots are independent copies."""

    def test_mutating_the_input_command_does_not_change_the_record(self):
        audited, audit = history(True)
        row = command(0.1, [.35] * 4, [.05] * 4)
        audited.issue(row)
        before = audit.audit_snapshot(sample_id='ep-1:0:r1')['rows'][-1]
        row['wheels'][0] = .4
        row['t'] = 0.9
        after = audit.audit_snapshot(sample_id='ep-1:0:r1')['rows'][-1]
        self.assertEqual(before, after)
        self.assertEqual(list(audited.issued)[-1]['t'], 0.1)
        self.assertEqual(list(audited.issued)[-1]['wheels'][0], .35)

    def test_mutating_a_snapshot_does_not_change_the_recorder(self):
        audited, audit = history(True)
        audited.issue(MOVE)
        snapshot = audit.audit_snapshot(sample_id='ep-1:0:r1')
        snapshot['slots'][0]['origin'] = 'policy'
        snapshot['issue_offset'] = 999
        fresh = audit.audit_snapshot(sample_id='ep-1:0:r1')
        self.assertEqual(fresh['issue_offset'], 1)
        self.assertNotEqual(fresh['slots'][0]['origin'], 'policy')

    def test_mutating_stored_events_does_not_change_the_recorder(self):
        audited, audit = history(True)
        audited.issue(MOVE)
        events = audit.stored_events()
        events[-1]['origin'] = 'policy'
        events[-1]['issued'] = True
        fresh = audit.stored_events()
        self.assertEqual(fresh[-1]['origin'], 'unknown')
        self.assertIsNone(fresh[-1]['issued'])

    def test_there_is_no_relabel_api(self):
        audited, audit = history(True)
        for name in dir(audit):
            self.assertNotIn('relabel', name)
            self.assertNotIn('overwrite', name)
            self.assertNotIn('set_origin', name)


class TokenAndSemanticRegressions(unittest.TestCase):
    def test_tokens_are_opaque_single_use_and_owner_local(self):
        _, audit = history(True)
        _, other = history(True)
        token = audit.prepare_issue(MOVE)
        with self.assertRaises(TypeError):
            token['origin'] = 'padding'
        with self.assertRaises(rec.RecorderError):
            other.commit_issue(token)
        audit.commit_issue(token)
        before = audit.stored_events()
        with self.assertRaises(rec.RecorderError):
            audit.commit_issue(token)
        self.assertEqual(before, audit.stored_events())

    def test_stale_and_forged_token_refused_before_state_changes(self):
        h, audit = history(True)
        token = audit.prepare_issue(command(.2, [0.]*4, [0.]*4))
        h.issue(command(.3, [0.]*4, [0.]*4))
        before = audit.stored_events()
        for candidate in (token, {'origin': 'padding', 'command': MOVE}, object()):
            with self.assertRaises(rec.RecorderError):
                audit.commit_issue(candidate)
            self.assertEqual(audit.stored_events(), before)

    def test_unbound_recording_refused(self):
        audit = recorder()
        with self.assertRaises(rec.RecorderError):
            audit.record_issue(MOVE)
        self.assertEqual(audit.event_count, 0)

    def test_superseded_preparation_cannot_be_committed(self):
        _, audit = history(True)
        older = audit.prepare_issue(MOVE)
        latest = audit.prepare_issue(STOP)
        with self.assertRaises(rec.RecorderError):
            audit.commit_issue(older)
        audit.commit_issue(latest)
        self.assertEqual(audit.issue_offset, 1)

    def test_note_and_semantic_slot_tampering_rejected(self):
        h, audit = history(True)
        observe(h)
        for mutate in (lambda s: s.update(note='environment application proven'),
                       lambda s: s['slots'][0].update(kind='issue'),
                       lambda s: s['slots'][0].update(t=float('inf')),
                       lambda s: s['slots'][0].update(t=1.),
                       lambda s: s.update(event_count=999)):
            snapshot = audit.audit_snapshot()
            mutate(snapshot)
            with self.assertRaises(rec.RecorderError):
                audit.verify(snapshot)

    def test_live_verify_checks_stored_raw_command_contract(self):
        h, audit = history(True)
        h.issue(MOVE)
        # Simulate corrupted storage to check semantic validation independently
        # of producer validation. Not a public mutation API or threat model.
        audit._window[-1][1]['wheels'] = [.09]*4
        audit.note_sample('corrupt')
        with self.assertRaises(rec.RecorderError):
            audit.verify(audit.audit_snapshot())

    def test_sequence_checks_allow_a_valid_rolled_window(self):
        h, audit = history(True)
        for index in range(25):
            h.issue(command(index * .01, [0.]*4, [0.]*4))
        observe(h)
        self.assertTrue(audit.verify(audit.audit_snapshot()))


if __name__ == '__main__':
    unittest.main()
