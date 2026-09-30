"""H333-1 regression from review-e2e-batch-h / d17327ae.

Only the #333 counterexample is carried into this candidate. Its assertion is
unchanged; the strict xfail is removed and the current candidate is always used.
#334 counterexamples remain with their owner. No historical blob fallback.
"""
import pytest


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
