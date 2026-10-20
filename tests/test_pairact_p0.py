"""pairact P0: world-15 log ring (logging-only, default off) and world-37 static stance check."""
import argparse
import inspect
import json
import math
import sys
from pathlib import Path

import pytest

from sim.grasp_act_log_ring import LOG_RING_ROWS, MODE, MODE_KEY, RingLog
from sim.grasp_act_search15_modes import ALL_MODES, add_arguments


def test_log_ring_registered_default_off_and_plumbed():
    assert ALL_MODES[MODE_KEY] == MODE
    args = argparse.ArgumentParser()
    add_arguments(args)
    assert getattr(args.parse_args([]), MODE_KEY) == 'off'
    from scripts.run_grasp_act_teacher import run
    assert MODE_KEY in inspect.signature(run).parameters


def test_ring_keeps_newest_rows_and_counts_drops():
    log = RingLog('goal_set_log', cap=3)
    for i in range(7):
        log.append({'t': i * .1, 'event': 'candidate_counts' if i % 2 else 'x'})
    assert [r['t'] for r in log] == pytest.approx([.4, .5, .6])
    assert log[-1]['t'] == pytest.approx(.6) and log[-1:] == [log[-1]]
    s = log.summary()
    assert s['appended_N'] == 7 and s['retained_N'] == 3 and s['dropped_N'] == 4
    assert s['dropped_events'] == {'candidate_counts': 2, 'x': 2}
    log.extend([{'t': 1.}]); log += [{'t': 2.}]
    assert len(log) == 3 and log.appended_N == 9
    assert json.loads(json.dumps(log))[-1] == {'t': 2.}


def _teacher(**modes):
    from scripts.zone_teacher import FOLDED
    from scripts.replay_grasp_act_recovery import KW
    from sim.grasp_act_teacher_v3 import VisibleOnlyGraspTeacher
    return VisibleOnlyGraspTeacher('r1', 'teal', FOLDED, **KW,
                                   approach_recovery='progress_view_recovery_v3', **modes)


def test_teacher_logs_are_plain_lists_when_off():
    t = _teacher()
    assert type(t.goal_set_log) is list and type(t.search22_log) is list


def test_teacher_installs_ring_when_on():
    t = _teacher(search26_log_ring=MODE)
    assert isinstance(t.goal_set_log, RingLog) and isinstance(t.search22_log, RingLog)
    for i in range(LOG_RING_ROWS + 5):
        t.goal_set_log.append({'t': i, 'candidates': [{'reason': 'blocked_goal', 'offset_deg': 0.}], 'selected': None})
    assert len(t.goal_set_log) == LOG_RING_ROWS and t.goal_set_log[-1]['t'] == LOG_RING_ROWS + 4
    from sim.grasp_act_log_ring import summary
    s = summary(t)
    assert s['mode'] == MODE and s['logs'][0]['dropped_N'] == 5


def test_teacher_diagnostic_reports_ring_only_when_on():
    assert 'log_ring' not in _teacher().diagnostic()
    assert _teacher(search26_log_ring=MODE).diagnostic()['log_ring']['mode'] == MODE


def _static_module():
    path = Path(__file__).resolve().parents[1] / 'experiments/2026-10-21-pairact-p0'
    sys.path.insert(0, str(path))
    try:
        import static_stance_check
    finally:
        sys.path.remove(str(path))
    return static_stance_check


def test_static_thresholds_match_runtime_floor():
    lim = _static_module().thresholds()
    assert lim['overlap'] == 0. and lim['admission'] == pytest.approx(.005)
    assert lim['floor'] == pytest.approx(.01107, abs=1e-5)


def test_static_census_flags_end_whose_family_overlaps_a_box():
    m = _static_module()
    from sim.grasp_act_search18 import body_clearance
    family = [(math.radians(a), d, None, None) for a in (-15, 0, 15) for d in (.198, .203, .208)]
    lim = m.thresholds()
    beam = (0., 0., 0.)
    # teal end at x=-.27; its stances sit around x=-.47; a box there blocks all of them.
    box = ('cyan_1', (-.47, 0., .1, .1, 0.))
    far = ('wall', (3., 3., .1, .1, 0.))
    r = m.case_census(beam, [box, far], family, .27, body_clearance, lim)
    assert r['flagged_ends']['overlap'] == ['teal']
    assert r['ends']['teal']['free_N']['overlap'] == 0 and r['ends']['blue']['free_N']['floor'] == 9
    assert r['ends']['teal']['best']['blocked_object'] == 'cyan_1'
    clear = m.case_census(beam, [far], family, .27, body_clearance, lim)
    assert all(not v for v in clear['flagged_ends'].values())
