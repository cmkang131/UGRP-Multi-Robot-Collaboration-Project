"""chain_analysis.leg_class: a hard-limit violation is FAIL_HARD_LIMIT even when an ordinary leg check also fails."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    'chain_analysis_under_test', ROOT / 'experiments/2026-09-30-door-relax-envelope/analysis/chain_analysis.py')
ca = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ca)


def leg(**over):
    d = {'recorded': True, 'lift_m': .05, 'tilt_deg': 1., 'jaws': {'r1': [True, True], 'r2': [True, True]},
         'end_error_m': .01, 'leg_error_m': .01}
    d.update(over)
    return d


def ep(pen):
    return {'max_pen_m': pen, 't_first': 0., 't_last': 1., 'who': 'chassis'}


def test_clean_and_contact_recovered_unchanged():
    assert ca.leg_class(leg(), [], 2.) == 'PASS_CLEAN'
    assert ca.leg_class(leg(), [ep(.004)], 2.) == 'PASS_CONTACT_RECOVERED'


def test_hard_limit_alone_is_hard_limit_fail():
    assert ca.leg_class(leg(), [ep(.0051)], 2.) == 'FAIL_HARD_LIMIT'
    assert ca.leg_class(leg(), [], 15.01) == 'FAIL_HARD_LIMIT'


def test_hard_limit_wins_over_ordinary_failure():
    bad = leg(end_error_m=5.)  # ordinary check fails
    assert ca.leg_class(bad, [ep(.0051)], 2.) == 'FAIL_HARD_LIMIT'
    assert ca.leg_class(bad, [], 15.01) == 'FAIL_HARD_LIMIT'


def test_ordinary_failure_without_hard_limit_stays_fail():
    assert ca.leg_class(leg(end_error_m=5.), [ep(.004)], 2.) == 'FAIL'
    assert ca.leg_class(leg(end_error_m=5.), [], None) == 'FAIL'
    assert ca.leg_class({'recorded': False}, [ep(.02)], 30.) == 'FAIL'


def test_hard_limit_violated_helper():
    assert not ca.hard_limit_violated([], None)
    assert ca.hard_limit_violated([ep(.006)], None)
    assert ca.hard_limit_violated([], 16.)
