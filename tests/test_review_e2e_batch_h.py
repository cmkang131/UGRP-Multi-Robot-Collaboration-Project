"""PR #334 counterexamples imported from review batch H, d17327ae.

The original assertion bodies are unchanged; xfail is removed. Test the current
candidate by default so CI and mutation overlays cannot silently test old blobs.
The unrelated #333 counterexample remains owned by its beam PR.
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
