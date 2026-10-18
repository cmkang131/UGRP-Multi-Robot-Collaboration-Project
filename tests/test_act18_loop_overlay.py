"""act18-loop overlay must only post-process own issued base commands."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from act18_loop_overlay import (CLOSE_PWM, HOLD_TICKS, HOLD_WHEEL_SCALE, RETREAT_TICKS,
                                RETREAT_WHEEL, LoopOverlay, overlay_receipt)


def command(wheels, pwm5=1500, t=0.0):
    return dict(t=t, wheels=list(wheels), duration_s=[0.1]*4,
                pwm={'1': 1500, '3': 1500, '4': 1500, '5': pwm5, '6': pwm5})


def test_hold_brake_after_three_closed_ticks_is_bounded():
    overlay = LoopOverlay()
    for _ in range(2):
        _, event = overlay.step('grasp', command([.35]*4, CLOSE_PWM+100))
        assert event is None
    values = []
    for _ in range(HOLD_TICKS+3):
        out, event = overlay.step('grasp', command([.35]*4, CLOSE_PWM+100))
        if event is not None:
            assert event['kind'] == 'hold_brake'
            values.append(out['wheels'][0])
    assert len(values) == HOLD_TICKS
    assert all(abs(v - .35*HOLD_WHEEL_SCALE) < 1e-9 for v in values)


def test_release_retreat_uses_grasp_direction_and_stops_after_window():
    overlay = LoopOverlay()
    for _ in range(5):
        overlay.step('grasp', command([.35, .35, .35, .35]))
    out, event = overlay.step('release', command([0.0]*4, 1100))
    assert event['kind'] == 'release_retreat'
    assert out['wheels'] == [-RETREAT_WHEEL]*4 and out['duration_s'] == [.1]*4
    events = 0
    for _ in range(RETREAT_TICKS+2):
        _, event = overlay.step('release', command([0.0]*4, 1100))
        events += int(event is not None)
    assert events == RETREAT_TICKS-1
    _, event = overlay.step('release', command([0.0]*4, 1100))
    assert event is None


def test_moving_release_is_not_overridden():
    overlay = LoopOverlay()
    for _ in range(5):
        overlay.step('grasp', command([.35]*4))
    out, event = overlay.step('release', command([-.31]*4, 1100))
    assert event is None and out['wheels'] == [-.31]*4


def test_overlay_receipt_declares_no_teacher_or_ground_truth():
    receipt = overlay_receipt()
    assert 'own issued base command post-processing only' in receipt['scope']
    assert 'no teacher/GT/top-camera' in receipt['scope']
    assert receipt['hold_ticks'] == HOLD_TICKS and receipt['retreat_ticks'] == RETREAT_TICKS
