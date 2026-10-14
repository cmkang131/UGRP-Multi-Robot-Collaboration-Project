"""Offline evidence accounting; no simulator or local raw-data dependency."""
import hashlib

import pytest

from scripts.replay_crate_lift import counts, issued_lift_commands, pair_verdict, verify_fetch_request


def test_release_row_at_final_capture_is_not_an_observer_command():
    commands = [{'t': 1}, {'t': 2}]
    records = [{'t': 0, 'skill': 'grasp', 'applied_command': {'t': 0}},
               {'t': 1, 'skill': 'grasp', 'applied_command': commands[0]},
               {'t': 2, 'skill': 'grasp', 'applied_command': commands[1]},
               {'t': 2, 'skill': 'release', 'pwm': {'1': 1500}}]
    assert issued_lift_commands(records, 1, 2) == commands
    # Malformed grasp evidence must not be silently omitted to pass a replay.
    with pytest.raises(KeyError):
        issued_lift_commands([{'t': 1, 'skill': 'grasp'}], 1, 2)


def test_denominators_retain_unknown_and_pair_requires_both():
    assert pair_verdict(['confirmed', 'undetermined']) == 'undetermined'
    assert pair_verdict(['confirmed']) == 'undetermined'
    assert pair_verdict(['confirmed', 'not_confirmed']) == 'not_confirmed'
    assert pair_verdict(['confirmed', 'confirmed']) == 'confirmed'
    assert counts(['confirmed', 'undetermined', 'undetermined']) == {
        'N': 3, 'confirmed': 1, 'not_confirmed': 0, 'undetermined': 2}


def test_fetch_hash_rows_are_verified_and_operator_notes_are_not_paths(tmp_path):
    raw = tmp_path/'raw'
    raw.mkdir()
    (raw/'image.png').write_bytes(b'original')
    sha = hashlib.sha256(b'original').hexdigest()
    request = tmp_path/'fetch.txt'
    request.write_text(f'# request\n{sha}  /home/ugrp/ugrp-sim/runs/image.png\n22:02 complete\n')
    out = verify_fetch_request(request, raw)
    assert out['N'] == out['matched'] == 1
    assert out['operator_notes'] == ['22:02 complete']
    (raw/'image.png').write_bytes(b'changed')
    with pytest.raises(ValueError, match='hash mismatch'):
        verify_fetch_request(request, raw)
