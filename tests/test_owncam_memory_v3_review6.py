"""Review 6: stationary recovery must not time out a resumed initial sweep.

Synthetic own-pose reports; real collision checks, sweep state machine and
issued-command bookkeeping at 0.1 s. No physics, RGB inference or model calls.
"""
from dataclasses import replace
from unittest import mock

import pytest

from harness.owncam_drive import SEARCH_POSE, WIDE_LOOK_PANS
from scripts.run_m1_owncam_memory_v3 import THREAD_VARS, controller_class
from tests.test_owncam_memory_v3 import controller, report


@pytest.fixture(autouse=True)
def thread_caps():
    with mock.patch.dict('os.environ', {name: '1' for name in THREAD_VARS}):
        yield


def initial_controller(condition, *, rejected=True):
    ctl = controller(controller_class(condition))
    ctl.on_command({'t': 0., 'kind': 'initial_servo_command', 'pulses': SEARCH_POSE})
    ctl.pose.report = lambda now: replace(
        report(now, x=0., y=0., sigma=.09 if now < 2.8 else .02),
        initialized=not rejected or now >= 2.)
    return ctl


def decide_tick(ctl, step, *, apply_commands=True, fresh_each_tick=False):
    now = round(step * .1, 6)
    ctl.pose.loc.predict_to(now)
    # 5 Hz synthetic observation metadata; the pose report above is the input.
    if step % 2 == 0 or fresh_each_tick:
        ctl.last_frame_id = step
        ctl.last_obs = {'frame_id': step, 'sim_time': now}
    result = ctl.decide(now)
    if apply_commands:
        for command in result.get('commands', []):
            ctl.on_command({'t': now, **command})
    return result


@pytest.mark.parametrize('condition', ['off', 'memory_v3'])
def test_resumed_initial_sweep_completes_after_old_stationary_deadline(condition):
    ctl = initial_controller(condition)
    for step in range(18, 112):
        result = decide_tick(ctl, step)
        if step == 18:
            assert ctl.sweep is None and ctl.init_looks == 0
            assert ctl.init_recovery['deadline'] == pytest.approx(9.8)
        if step == 20:
            assert ctl.sweep['queue'] == list(WIDE_LOOK_PANS)
            assert ctl.init_looks == 1
        if ctl.outcome:
            print(condition, 'terminated:', step / 10, ctl.outcome, ctl.events[-1])
        assert ctl.outcome is None, (step / 10, result)
        if step == 98:
            assert ctl.sweep is not None  # old 8 s deadline must not stop motion
        if step == 110:
            assert ctl.sweep is None
            assert ctl.events[-1]['event'] == 'sweep_done'
    assert ctl.phase == 'search_leg' and ctl.leg is not None
    assert ctl.init_recovery is None
    timeline = [(row['t'], row['event']) for row in ctl.events
                if row['event'] in ('init_sweep_deferred', 'sweep_start', 'sweep_done', 'initialized')]
    print(condition, 'timeline:', timeline)
    assert timeline == [(1.8, 'init_sweep_deferred'), (2., 'sweep_start'),
                        (11., 'sweep_done'), (11.1, 'initialized')]


@pytest.mark.parametrize('condition', ['off', 'memory_v3'])
def test_repeated_rejections_never_extend_stationary_budget(condition):
    ctl = initial_controller(condition)
    ctl.pose.report = lambda now: replace(report(now), initialized=False)
    for step in range(18, 98):
        result = decide_tick(ctl, step, fresh_each_tick=True)
        assert result['mode'] in ('tick', 'capture')
        assert all(cmd['kind'] == 'hold' for cmd in result.get('commands', []))
        assert ctl.sweep is None and ctl.init_looks == 0
        assert ctl.init_recovery['deadline'] == pytest.approx(9.8)
    assert decide_tick(ctl, 98) == {'mode': 'done', 'outcome': 'NOT_INITIALIZED'}
    assert ctl.events[-1]['reason'] == 'stationary_deadline'


@pytest.mark.parametrize('condition', ['off', 'memory_v3'])
@pytest.mark.parametrize('rejected', [False, True])
def test_active_sweep_still_obeys_total_initialization_deadline(condition, rejected):
    ctl = initial_controller(condition, rejected=rejected)
    # Deliberately withhold issued-command acknowledgements: the arm stage
    # cannot advance even though the synthetic pose converges. No physics.
    for step in range(18, 319):
        result = decide_tick(ctl, step, apply_commands=False)
        if step < 318:
            assert ctl.outcome is None, (step / 10, result)
        if step == 317:
            assert ctl.sweep is not None
    assert result == {'mode': 'done', 'outcome': 'NOT_INITIALIZED'}
    assert ctl.sweep is None
    assert ctl.events[-1]['reason'] == 'initialization_deadline'
    assert ctl.init_started == 1.8


@pytest.mark.parametrize('condition', ['off', 'memory_v3'])
def test_sweep_command_rejection_retains_remaining_time_and_capture_count(condition):
    ctl = initial_controller(condition)
    for step in (18, 19, 20):
        decide_tick(ctl, step)
    assert ctl.sweep is not None and ctl.init_recovery['captures'] == 1
    # The resumed sweep now loses its own pose; the real command guard refuses
    # the arm step. Only its 0.1 s of execution may be excluded from recovery.
    ctl.pose.report = lambda now: replace(report(now), initialized=False)
    for step in range(21, 99):
        result = decide_tick(ctl, step, fresh_each_tick=True)
        assert ctl.outcome is None
        assert ctl.sweep is None
        assert all(cmd['kind'] == 'hold' for cmd in result.get('commands', []))
        assert ctl.init_recovery['deadline'] == pytest.approx(9.9)
    assert ctl.init_recovery['captures'] == 1  # no refill on the resumed sweep
    assert decide_tick(ctl, 99) == {'mode': 'done', 'outcome': 'NOT_INITIALIZED'}
    assert ctl.events[-1]['reason'] == 'stationary_deadline'


@pytest.mark.parametrize('condition', ['off', 'memory_v3'])
def test_capture_limit_survives_a_resumed_sweep(condition):
    from harness.owncam_safety_v3 import INIT_MAX_CAPTURES
    ctl = initial_controller(condition)
    decide_tick(ctl, 18)
    for attempt in range(INIT_MAX_CAPTURES - 1):
        assert ctl.decide(1.9 + attempt * .21)['mode'] == 'capture'
    ctl.pose.report = lambda now: report(now, x=0., y=0., sigma=.09)
    decide_tick(ctl, 60)
    assert ctl.sweep is not None
    assert ctl.init_recovery['captures'] == INIT_MAX_CAPTURES - 1
    ctl.pose.report = lambda now: replace(report(now), initialized=False)
    decide_tick(ctl, 61)
    assert ctl.sweep is None
    assert ctl.decide(6.2)['mode'] == 'capture'
    assert ctl.decide(6.41) == {'mode': 'done', 'outcome': 'NOT_INITIALIZED'}
    assert ctl.init_recovery['captures'] == INIT_MAX_CAPTURES
    assert ctl.events[-1]['reason'] == 'capture_budget'


def test_review6_is_in_ci():
    from scripts.run_ci_tests import TEST_PATTERNS
    assert 'tests/test_owncam_memory_v3_review6.py' in TEST_PATTERNS
