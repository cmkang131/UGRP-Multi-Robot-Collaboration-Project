"""PR #333/#334 counterexamples imported from review batch H, d17327ae.

The original assertion bodies are unchanged; xfail is removed. Always test the
current candidate, without a historical blob fallback.
"""
import pytest


@pytest.fixture
def tile():
    from harness import tile_own_skill
    from tests import test_zone_own_executor_tile as helpers
    return tile_own_skill, helpers


def test_tile_consumes_native_navigation_command_history(tile, monkeypatch):
    _, helpers = tile
    port = helpers.Port(monkeypatch)
    port.until("holding")  # ordinary positive-control state, no manual phase edit
    if not port.s.carry_permitted(port.t):
        pytest.fail("Positive control did not reach ordinary holding")
    row = {"robot_id": "r1", "t": port.t, "kind": "mecanum",
           "forward": .05, "left": 0., "turn": 0., "duration_s": .1}
    error = None
    try:
        port.s.on_command(row)
    except ValueError as exc:
        error = str(exc)
    assert error is None, f"Native port receipt cannot continue tile carry: {error}"
    assert port.s.motion_until == pytest.approx(port.t + .1)
    assert not port.s.carry_permitted(port.t)  # wait for a new post-motion frame


def test_tile_same_capture_cannot_supply_two_holding_confirmations(tile, monkeypatch):
    _, helpers = tile
    port = helpers.Port(monkeypatch)
    port.until("verify_hold")
    port.tick()
    if port.s.state != "verify_hold" or port.s.hold_streak != 1:
        pytest.fail("Positive control did not stop at one holding confirmation")
    # Same capture time and JPEG as the first holding frame; only the ID differs.
    replay = helpers.frame(port.fid + 1, port.t)
    port.s.on_frame(port.t, replay)
    port.s.step(port.t)
    assert port.s.state != "holding", (
        f"one capture counted twice: t={port.t}, state={port.s.state}, "
        f"carry_permitted={port.s.carry_permitted(port.t)}"
    )
    assert not port.s.carry_permitted(port.t)


@pytest.fixture
def beam():
    from harness import beam_approach
    return beam_approach


def test_beam_accepts_native_issued_search_history_without_rescaling(beam):
    from harness.owncam_drive import SEARCH_POSE
    if SEARCH_POSE != {1: 2000, 3: 740, 4: 2320, 5: 1320, 6: 1500}:
        pytest.fail("Native search fixture changed; re-audit the counterexample")
    history = [{"kind": "initial_servo_command", "t": 0., "pulses": dict(SEARCH_POSE)}]
    provider = object()  # memory construction must not need a new pose estimate
    memory, error = None, None
    try:
        memory = beam.OwnApproachMemory(provider, history)
    except ValueError as exc:
        error = str(exc)
    assert error is None, f"Native issued PWM cannot enter continuous handoff: {error}"
    assert memory.provider is provider and memory.history is history
    assert memory.servo == SEARCH_POSE
