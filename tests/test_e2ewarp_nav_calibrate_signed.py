"""Non-physical tests for the signed turn evidence of the nav calibration.

The calibration script only runs on gcp6 with ``--execute``; these tests cover
the pure measurement math that a physical run would write into
``nav-calibration.json``.
"""
from scripts.e2ewarp_nav_calibrate import rotation_sign, turn_measurement


def test_negative_turn_is_preserved():
    # The turn phase issues the controller's +turn wheel pattern.  If the base
    # physically yaws the other way, the sign must survive into the artifact.
    measured = turn_measurement(10.0, -30.0)
    assert measured == {'turn_deg': 40.0, 'turn_deg_signed': -40.0}
    assert measured['turn_deg'] > 0.0  # existing positive-magnitude contract
    assert measured['turn_deg_signed'] < 0.0


def test_signed_turn_wraps_across_pi_without_flipping_direction():
    measured = turn_measurement(-170.0, 170.0)
    assert measured['turn_deg'] == 20.0
    assert measured['turn_deg_signed'] == -20.0


def test_rotation_sign_reports_both_robots():
    assert rotation_sign([{'turn_deg_signed': -5.0}, {'turn_deg_signed': -7.0}]) == 'negative'
    assert rotation_sign([{'turn_deg_signed': 5.0}, {'turn_deg_signed': 7.0}]) == 'positive'
    # Opposite signs are reported as mixed: never pick one robot's sign.
    assert rotation_sign([{'turn_deg_signed': 5.0}, {'turn_deg_signed': -7.0}]) == 'mixed'
    assert rotation_sign([]) == 'mixed'
