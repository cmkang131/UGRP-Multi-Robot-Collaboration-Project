"""Independent, offline counterexamples for PR #333/#334 (batch H).

Default: materialize only the named Python blobs from the reviewed commits.
For retesting fixes, set UGRP_REVIEW_H_PR333_ROOT / UGRP_REVIEW_H_PR334_ROOT
to complete candidate trees. No simulator, network, host lock or source edit.
Import/setup errors are NOT expected failures; only the stated assertions are.
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
PINS = {
    333: "cb0735efcd79ebaefd511eb7cd123979512dd0ed",
    334: "a4a0bacb51d46d69c1107277c4d11e67b60e4693",
}


def _load(pr, relative, name, tmp_path, monkeypatch):
    override = os.environ.get(f"UGRP_REVIEW_H_PR{pr}_ROOT")
    if override:
        path = Path(override) / relative
    else:
        path = tmp_path / str(pr) / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        blob = subprocess.run(
            ["git", "show", f"{PINS[pr]}:{relative}"], cwd=ROOT,
            check=True, capture_output=True,
        ).stdout
        path.write_bytes(blob)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    if name.startswith("harness."):
        import harness
        monkeypatch.setattr(harness, name.split(".")[-1], module, raising=False)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def beam(tmp_path, monkeypatch):
    _load(333, "harness/beam_initial_pose_plan.py", "harness.beam_initial_pose_plan", tmp_path, monkeypatch)
    return _load(333, "harness/beam_approach.py", "harness.beam_approach", tmp_path, monkeypatch)


@pytest.fixture
def tile(tmp_path, monkeypatch):
    _load(334, "harness/tile_own_vision.py", "harness.tile_own_vision", tmp_path, monkeypatch)
    candidate = _load(334, "harness/tile_own_skill.py", "harness.tile_own_skill", tmp_path, monkeypatch)
    # Reuse only its offline Port/JPEG helpers, never its assertions or physics.
    helpers = _load(334, "tests/test_zone_own_executor_tile.py", "_review_h_tile_helpers", tmp_path, monkeypatch)
    return candidate, helpers


@pytest.mark.xfail(strict=True, raises=AssertionError,
                   reason="H333-1: native 500..2500 PWM / five active channels rejected as BAD_ISSUED_SERVO")
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


@pytest.mark.xfail(strict=True, raises=AssertionError,
                   reason="H334-1: native issued mecanum duration_s is read as duration")
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


@pytest.mark.xfail(strict=True, raises=AssertionError,
                   reason="H334-2: identical capture timestamp/image with a new ID counts as a second holding frame")
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
