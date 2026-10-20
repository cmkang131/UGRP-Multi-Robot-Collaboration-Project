"""pairact P1 cand-3: align relook cap (default off)."""
import inspect

from sim.grasp_act_search15_modes import ALL_MODES
from sim.grasp_act_search26 import ALIGN_RELOOK_LIMIT, ALIGN_RELOOK_LIMIT_V1
from tests_helpers_r3 import teacher

KEY, MODE = 'search26_align_relook_cap', 'search26_align_relook_cap_v1'


def _relooks_until_terminal(t):
    for n in range(1, 10):
        t._begin_relook(10. + n, 'no_visible_error_progress_3s')
        if t.outcome is not None:
            return n, t.outcome
    return None, None


def test_registered_default_off_and_plumbed():
    assert ALL_MODES[KEY] == MODE
    from scripts.run_grasp_act_teacher import run
    assert KEY in inspect.signature(run).parameters
    assert (ALIGN_RELOOK_LIMIT, ALIGN_RELOOK_LIMIT_V1) == (2, 4)


def test_default_ends_on_third_relook_unchanged():
    assert _relooks_until_terminal(teacher()) == (3, 'alignment_no_progress')


def test_cap_mode_ends_on_fifth_relook():
    t = teacher(**{KEY: MODE})
    assert _relooks_until_terminal(t) == (5, 'alignment_no_progress')
    assert t.align_relooks == 5
