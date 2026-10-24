"""Solo-carry evaluation gates on synthetic rows (derived, unverified; CPU only, no physics)."""
import copy
import math

import pytest

from harness import solo_carry_eval as ev

SLOT = {'zone': 'zone_B', 'pose': [4.6, -2.1, 0.], 'half_extents_m': [.10, .10]}
FINAL = (4.6, -2.1)
LOWER_T = 12.
RELEASE_T = 13.7
LAST_T = 18.
CAP = 60.


def row(t, xy, min_z, forces, tilt=1., missing_contact=False):
    out = {'t': round(t, 6), 'beam': {'pose': [xy[0], xy[1], 0.], 'min_z': min_z, 'tilt_deg': tilt},
           'robots': {'r1': {'pose': [0., 0., 0.]}}}
    if not missing_contact:
        out['contacts'] = {'r1': list(forces)}
    return out


def good_rows():
    """grasp+lift 3.5 s hold, carry, lower from LOWER_T, release at RELEASE_T, rest to LAST_T."""
    rows = []
    for k in range(int(LAST_T*10) + 1):
        t = k*.1
        if t < 1.:
            rows.append(row(t, (1., 1.), 0., (0., 0.)))                      # approach: on the floor, no contact
        elif t < 1.5:
            rows.append(row(t, (1., 1.), .02*(t - 1.)/.5, (4.3, 4.3)))     # grasped, rising
        elif t < LOWER_T:
            xy = (1. + (FINAL[0] - 1.)*min(1., (t - 1.5)/9.), 1. + (FINAL[1] - 1.)*min(1., (t - 1.5)/9.))
            rows.append(row(t, xy, .065, (4.3, 4.3)))                       # carried at 65 mm
        elif t < RELEASE_T:
            u = min(1., (t - LOWER_T)/1.6)
            rows.append(row(t, FINAL, .065*(1 - u), (4.3, 4.3)))            # commanded descent, still held
        else:
            rows.append(row(t, FINAL, 0., (0., 0.)))                        # opened: rests on the floor
    return rows


def run(rows, **kw):
    kw.setdefault('lower_start_t', LOWER_T)
    kw.setdefault('cap_s', CAP)
    return ev.evaluate(rows, SLOT, 'r1', **kw)


def test_good_episode_passes_every_gate():
    report = run(good_rows())
    assert report['success'] is True and report['failure'] is None, report['gates']
    assert set(report['gates']) == set(ev.GATES) and all(g['pass'] for g in report['gates'].values())
    assert report['gates']['lift']['max_stable_lift_s'] >= 3.
    assert report['gates']['release']['release_t'] == pytest.approx(RELEASE_T)
    assert report['status'] == ev.STATUS


def test_unobserved_contact_everywhere_fails_the_lift_gate():
    rows = [{k: v for k, v in r.items() if k != 'contacts'} for r in good_rows()]
    report = run(rows)
    assert not report['success'] and report['failure'] == 'lift'
    assert report['gates']['lift']['reason'] == 'contact_unobserved'
    assert report['gates']['lift']['unobserved_contact_rows'] == len(rows)


@pytest.mark.parametrize('bad', [None, [4.3], [float('nan'), 4.3], [-1., 4.3], 'x', [4.3, None]])
def test_malformed_contact_is_unobserved_never_zero_or_pass(bad):
    assert ev.forces({'contacts': {'r1': bad}}, 'r1') is None


def test_a_single_unobserved_contact_row_fails_the_lift_gate_even_with_a_later_stable_run():
    rows = good_rows()
    for r in rows:
        if 3.0 <= r['t'] < 3.2:
            r.pop('contacts')
    report = run(rows)
    assert report['failure'] == 'lift' and report['gates']['lift']['reason'] == 'contact_unobserved'
    assert report['gates']['lift']['unobserved_contact_rows'] == 2
    assert report['gates']['lift']['max_stable_lift_s'] >= 3.     # the height/force evidence alone would have passed


def test_lift_below_threshold_or_weak_grip_fails_lift():
    weak = [row(r['t'], r['beam']['pose'][:2], r['beam']['min_z'], (0.3, 4.3) if r['t'] > 1 and r['t'] < LOWER_T else (0., 0.))
            for r in good_rows()]
    assert run(weak)['failure'] == 'lift'
    low = copy.deepcopy(good_rows())
    for r in low:
        r['beam']['min_z'] = min(r['beam']['min_z'], .008)
    assert run(low)['failure'] == 'lift'
    tilted = copy.deepcopy(good_rows())
    for r in tilted:
        if r['t'] < LOWER_T:
            r['beam']['tilt_deg'] = 11.
    assert run(tilted)['failure'] == 'lift'


def test_drop_after_lift_fails_even_if_it_is_picked_up_again_and_placed():
    rows = good_rows()
    for r in rows:
        if 7.0 <= r['t'] < 7.1:
            r['beam']['min_z'] = .004          # one sample back near the floor while "carried"
    report = run(rows)
    assert report['failure'] == 'no_drop'
    assert report['gates']['no_drop']['reason'] == 'dropped_after_lift' and report['gates']['no_drop']['first_drop_t'] == pytest.approx(7.0)
    assert report['gates']['lift']['pass']


def test_commanded_descent_after_lower_start_is_not_a_drop():
    assert run(good_rows())['gates']['no_drop']['pass']
    # without the teacher's lower boundary the same descent is indistinguishable from a drop
    report = run(good_rows(), lower_start_t=None)
    assert report['gates']['no_drop']['pass'] is False
    assert report['gates']['release']['reason'] == 'lower_start_missing'


def test_unobserved_cargo_height_while_carried_fails_no_drop():
    rows = good_rows()
    for r in rows:
        if 5.0 <= r['t'] < 5.1:
            r['beam'].pop('min_z')
    report = run(rows)
    assert report['failure'] == 'no_drop' and report['gates']['no_drop']['reason'] == 'cargo_unobserved'


def test_final_pose_outside_the_slot_fails():
    rows = good_rows()
    for r in rows:
        if r['t'] >= LOWER_T:
            r['beam']['pose'][0] = 4.6 + .09           # centre 9 mm inside the edge but the disc (r=19 mm) pokes out
    report = run(rows)
    assert report['failure'] == 'slot' and report['gates']['slot']['reason'] == 'outside_slot'
    for r in rows:
        if r['t'] >= LOWER_T:
            r['beam']['pose'][0] = 4.6 + .08           # disc fully inside
    assert run(rows)['gates']['slot']['pass']


def test_slot_rectangle_yaw_is_honoured():
    slot = {**SLOT, 'pose': [4.6, -2.1, math.pi/2], 'half_extents_m': [.30, .05]}   # long axis along world y
    along, across = good_rows(), good_rows()
    for r in along:
        if r['t'] >= LOWER_T:
            r['beam']['pose'][1] = -2.1 + .25
    for r in across:
        if r['t'] >= LOWER_T:
            r['beam']['pose'][0] = 4.6 + .25
    assert ev.evaluate(along, slot, 'r1', lower_start_t=LOWER_T, cap_s=CAP)['gates']['slot']['pass']
    assert ev.evaluate(across, slot, 'r1', lower_start_t=LOWER_T, cap_s=CAP)['failure'] == 'slot'
    unrotated = {**slot, 'pose': [4.6, -2.1, 0.]}                                     # long axis along world x
    assert not ev.evaluate(along, unrotated, 'r1', lower_start_t=LOWER_T, cap_s=CAP)['gates']['slot']['pass']


def test_cargo_still_moving_or_not_on_floor_fails_rest():
    rows = good_rows()
    for r in rows:
        if r['t'] > LAST_T - 1.0:
            r['beam']['pose'][0] += (r['t'] - (LAST_T - 1.0))*.02      # 2 cm/s creep, > 5 mm over the window
    report = run(rows)
    assert report['failure'] == 'rest' and report['gates']['rest']['reason'] == 'still_moving'
    held = good_rows()
    for r in held:
        if r['t'] > LAST_T - .5:
            r['beam']['min_z'] = .02
    assert run(held)['gates']['rest']['reason'] == 'not_at_rest'


def test_too_few_rows_for_the_rest_window_fails_closed():
    rows = [r for r in good_rows() if r['t'] <= RELEASE_T + .5]
    report = run(rows, cap_s=CAP)                    # only 0.5 s on the floor: the 1 s window still sees the held can
    assert report['failure'] == 'rest' and report['gates']['rest']['reason'] == 'not_at_rest'
    tail = [r for r in good_rows() if r['t'] >= LAST_T - .5]
    assert ev.rest_gate(tail, 'r1')['reason'] == 'insufficient_rows_for_rest'


def test_release_from_height_is_not_gentle():
    rows = good_rows()
    for r in rows:
        if LOWER_T <= r['t'] < RELEASE_T:
            r['beam']['min_z'] = .03
            if r['t'] > RELEASE_T - .2:
                r['contacts']['r1'] = [0., 0.]       # let go 30 mm above the floor
    for r in rows:
        if r['t'] >= RELEASE_T - .2 + .05 and r['t'] < RELEASE_T:
            r['beam']['min_z'] = .03
    report = run(rows)
    assert report['failure'] == 'release' and report['gates']['release']['reason'] == 'released_from_height'


def test_fast_cargo_after_release_is_not_gentle():
    rows = good_rows()
    for r in rows:
        if RELEASE_T <= r['t'] < RELEASE_T + .3:
            r['beam']['pose'][0] += (r['t'] - RELEASE_T)*.3        # 0.3 m/s skid
    for r in rows:
        if r['t'] >= RELEASE_T + .3:
            r['beam']['pose'][0] += .09
    report = run(rows)
    assert report['gates']['release']['reason'] == 'release_too_fast'
    assert report['gates']['release']['max_speed_after_release_mps'] > ev.Criteria.release_speed_max_mps


def test_never_released_and_unobserved_release_contact_fail():
    held = [row(r['t'], r['beam']['pose'][:2], r['beam']['min_z'], (4.3, 4.3)) for r in good_rows()]
    assert ev.release_gate(held, 'r1', LOWER_T)['reason'] == 'never_released'
    rows = good_rows()
    for r in rows:
        if abs(r['t'] - (LOWER_T + .5)) < 1e-6:
            r.pop('contacts')
    assert ev.release_gate(rows, 'r1', LOWER_T)['reason'] == 'contact_unobserved'


def test_completion_must_fit_the_cap_and_the_cap_is_required():
    assert run(good_rows(), cap_s=RELEASE_T + 1.)['gates']['completion']['pass'] is True
    late = run(good_rows(), cap_s=RELEASE_T)
    assert late['failure'] == 'completion' and late['gates']['completion']['reason'] == 'over_cap'
    with pytest.raises(TypeError):
        ev.evaluate(good_rows(), SLOT, 'r1', lower_start_t=LOWER_T)        # cap_s has no default (open pin)
    shifted = run(good_rows(), t0=-50.)
    assert shifted['gates']['completion']['reason'] == 'over_cap'


def test_empty_rows_and_gap_handling():
    assert ev.evaluate([], SLOT, 'r1', lower_start_t=None, cap_s=CAP)['failure'] == 'no_rows'
    rows = [r for r in good_rows() if not (2.0 <= r['t'] < 2.5)]            # 0.5 s hole inside the hold window
    lift = ev.lift_gate(rows, 'r1')
    assert lift['row_gaps'] == 1 and lift['pass']                             # restarts after the hole, still > 3 s


def test_gate_module_imports_nothing_from_the_simulator_or_the_teacher():
    import ast
    import harness.solo_carry_eval as module
    tree = ast.parse(open(module.__file__).read())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module)
    assert imported <= {'__future__', 'math', 'harness.solo_carry_contract'}, imported
