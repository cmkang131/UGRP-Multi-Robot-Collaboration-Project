"""Pure recorded-data labeling regressions; no physics, render or provider."""
import pytest
from scripts.evaluate_s4_grip_raw import contact_labels, finger_sides


def contact(t, sides=(), dist=-.001, robot='r1', cargo='cargo_beam_1__bar'):
    return dict(t=t, contacts=[dict(geom1=cargo, geom2=f'{robot}__{s}_finger',
                                  dist_m=dist) for s in sides])


def command(t, pulse):
    return dict(t=t, kind='arm', servo_id=1, pulse=pulse)


def test_proxy_ignores_foreign_cargo_robot_and_positive_distance():
    assert finger_sides(contact(0, ['left', 'right']), 'r1') == ['left', 'right']
    assert not finger_sides(contact(0, ['left'], robot='r2'), 'r1')
    assert not finger_sides(contact(0, ['left'], cargo='cargo_cyan_1_geom'), 'r1')
    assert not finger_sides(contact(0, ['left'], dist=.001), 'r1')


def test_pregrasp_partial_loss_and_reacquisition():
    c = [contact(1), contact(1.1, ['left']), contact(1.2, ['left', 'right']),
         contact(1.3, ['right']), contact(1.4), contact(1.5),
         contact(1.6, ['left', 'right']), contact(1.7)]
    labels, episodes = contact_labels(c, [command(0, 1500)], 'r1')
    assert [x['label'] for x in labels.values()] == [
        'not_held', 'partial_contact', 'held_contact', 'partial_contact',
        'lost_contact', 'lost_contact', 'held_contact', 'lost_contact']
    assert [x['onset_t'] for x in episodes] == [1.4, 1.7]


def test_release_and_missing_history_are_not_loss():
    c = [contact(1, ['left', 'right']), contact(1.1)]
    assert not contact_labels(c, [command(0, 1500), command(1.05, 1600)], 'r1')[1]
    assert not contact_labels(c, [], 'r1')[1]


def test_equal_time_command_applies_after_capture():
    c = [contact(1, ['left', 'right']), contact(1.1), contact(1.2)]
    labs, eps = contact_labels(c, [command(0, 1500), command(1.1, 2000)], 'r1')
    assert labs[1.1]['label'] == 'lost_contact'
    assert labs[1.2]['label'] == 'not_held'
    assert len(eps) == 1


def test_gap_is_unobserved_not_a_loss_transition():
    assert not contact_labels([contact(1, ['left', 'right']), contact(2)],
                              [command(0, 1500)], 'r1')[1]


def test_duplicate_timestamps_fail_instead_of_overwriting():
    with pytest.raises(ValueError, match='duplicate'):
        contact_labels([contact(1), contact(1)], [], 'r1')
