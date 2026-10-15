"""Prerequisite safety boundary: no physics, GPU, credentials or network."""
from scripts.act16w_prerequisites import signals


def test_missing_or_quoted_signal_cannot_admit():
    assert not signals("warp1: READY_HOLD_SCENE")['ready_for_queue_inspection']
    assert not signals("act16w-gate: missing warp1: READY and SCENE_DECISION: x")['signals_present']


def test_latest_not_ready_overrides_historical_ready():
    value = signals("warp1: READY_HOLD_SCENE\nSCENE_DECISION: scene_v1\nwarp1: NOT_READY reason=runtime")
    assert value['status'] == 'WAIT_NOT_READY'
    assert value['warp1'].endswith('reason=runtime')


def test_both_signals_only_admit_queue_inspection():
    value = signals("2026-10-16 warp1: READY_HOLD_SCENE | queue=/tmp/q.json\nSCENE_DECISION: scene_v1")
    assert value['ready_for_queue_inspection']
    assert value['status'] == 'INSPECT_QUEUE'


def test_unready_or_pending_line_is_not_ready():
    for state in ('UNREADY', 'PENDING', 'PLAN_READY', 'NOT_READY'):
        assert not signals(f"warp1: {state}\nSCENE_DECISION: x")['ready_for_queue_inspection']
